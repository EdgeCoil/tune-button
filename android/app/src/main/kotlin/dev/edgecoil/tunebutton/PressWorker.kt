// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
package dev.edgecoil.tunebutton

import dev.edgecoil.tunebutton.Action.Type as T
import android.content.Context
import android.content.pm.ServiceInfo
import android.os.Build
import androidx.work.ForegroundInfo
import androidx.work.Worker
import androidx.work.WorkerParameters
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONObject

/** Does what a key event asks: looks up the key's action and runs it. */
class PressWorker(ctx: Context, params: WorkerParameters) : Worker(ctx, params) {

    private data class Outcome(val ok: Boolean, val title: String, val text: String)

    override fun doWork(): Result {
        val store = Store(applicationContext)
        val key = inputData.getInt("key", inputData.getInt("button", 0))  // "button": queued by app 0.1
        val gesture = inputData.getInt("gesture", Packet.PRESS)
        val action = Action.forEvent(key, gesture, store::slot)
        val entry = JSONObject()
            .put("kind", "press")
            .put("key", key)
            .put("gesture", Action.gestureName(gesture))
            .put("action", action.type.label)
            .put("counter", inputData.getLong("counter", -1))
            .put("battery", inputData.getInt("battery", -1))
            .put("age_ms", inputData.getInt("age_ms", -1))  // press → first heard, measured by the device
            .put("rssi", inputData.getInt("rssi", 0))
        val started = System.currentTimeMillis()
        val o = act(store, key, gesture, action)
        entry.put("ok", o.ok).put("result", if (o.text.isEmpty()) o.title else "${o.title} — ${o.text}").put("api_ms", System.currentTimeMillis() - started)
        store.log(entry)
        if (action.type != Action.Type.NONE) Notify.show(applicationContext, o.ok, o.title, o.text)
        return Result.success()
    }

    private fun act(store: Store, key: Int, gesture: Int, action: Action): Outcome {
        if (action.type == Action.Type.NONE) return Outcome(true, "Nothing assigned", "key $key ${Action.gestureName(gesture)}")
        val spotify = Spotify(store)
        if (action.type.player && !spotify.canControlPlayback())
            return Outcome(false, "Sign in to Spotify again", "to allow playback control (${action.type.label})")
        if (action.type.needsPlaylist && action.playlistId == null)
            return Outcome(false, "No playlist chosen", "Pick one for key $key in the app")
        var lastError: Exception? = null
        repeat(2) { attempt ->
            try {
                return run(spotify, key, gesture, action)
            } catch (e: Spotify.AuthRequired) {
                return Outcome(false, "Sign in to Spotify", e.message ?: "")
            } catch (e: Spotify.ApiError) {
                // 429 means Spotify did nothing, so any action can go again; a 5xx may have half-run.
                if (e.code != 429 && (e.code < 500 || !action.type.repeatable)) return Outcome(false, "Didn't work", e.message ?: "")
                lastError = e
            } catch (e: IOException) {
                // A network blip: one retry, but only if running it twice can't skip twice.
                if (!action.type.repeatable) return Outcome(false, "Didn't work", e.message ?: "network error")
                lastError = e
            }
            if (attempt == 0) Thread.sleep(2000)
        }
        return Outcome(false, "Didn't work", lastError?.message ?: "network error")
    }

    private fun run(spotify: Spotify, key: Int, gesture: Int, a: Action): Outcome {
        if (a.type.needsSong) {
            val playing = spotify.nowPlaying() ?: return Outcome(false, "Nothing playing", "Spotify reports no current song")
            if (playing.uri.startsWith("spotify:local:")) return Outcome(false, "Local file", "Spotify can't save local files")
            val what = "${playing.title} · ${playing.artist}"
            when (a.type) {
                T.LIKE -> { spotify.like(playing.uri); return Outcome(true, "♥ Liked", what) }
                T.UNLIKE -> { spotify.unlike(playing.uri); return Outcome(true, "♡ Removed from Liked Songs", what) }
                T.ADD -> { spotify.addToPlaylist(a.playlistId!!, playing.uri); return Outcome(true, "+ ${a.playlistName ?: "playlist"}", what) }
                T.REMOVE -> { spotify.removeFromPlaylist(a.playlistId!!, playing.uri); return Outcome(true, "− ${a.playlistName ?: "playlist"}", what) }
                else -> {}
            }
        }
        when (a.type) {
            T.NEXT -> { spotify.next(); return Outcome(true, "⏭ Next track", "") }
            T.PREVIOUS -> { spotify.previous(); return Outcome(true, "⏮ Previous track", "") }
            T.PLAY_PLAYLIST -> { spotify.play("spotify:playlist:${a.playlistId}"); return Outcome(true, "▶ ${a.playlistName ?: "Playlist"}", "") }
            T.WEBHOOK -> return webhook(spotify, key, gesture, a.url)
            else -> {}
        }
        // The rest depend on the current playback state.
        val p = spotify.player() ?: return Outcome(false, "Nothing playing", "No Spotify device is active")
        return when (a.type) {
            T.PLAY_PAUSE -> if (p.isPlaying) { spotify.pause(); Outcome(true, "⏸ Paused", "") }
                else { spotify.play(); Outcome(true, "▶ Playing", "") }
            T.VOLUME_UP, T.VOLUME_DOWN -> {
                val v = p.volume ?: return Outcome(false, "Can't set volume", "This Spotify device doesn't allow it")
                val to = (v + if (a.type == T.VOLUME_UP) 10 else -10).coerceIn(0, 100)
                spotify.volume(to)
                Outcome(true, "🔊 Volume $to%", "")
            }
            T.SHUFFLE -> { spotify.shuffle(!p.shuffle); Outcome(true, if (p.shuffle) "Shuffle off" else "🔀 Shuffle on", "") }
            T.REPEAT -> {
                val next = when (p.repeat) { "off" -> "context"; "context" -> "track"; else -> "off" }
                spotify.repeat(next)
                Outcome(true, when (next) { "context" -> "🔁 Repeat all"; "track" -> "🔂 Repeat one"; else -> "Repeat off" }, "")
            }
            else -> Outcome(false, "Unknown action", a.type.name)
        }
    }

    /** POSTs the event and the current song as JSON. The song is left out if Spotify can't say. */
    private fun webhook(spotify: Spotify, key: Int, gesture: Int, url: String?): Outcome {
        if (url.isNullOrBlank()) return Outcome(false, "No webhook URL", "Set one for key $key in the app")
        val body = JSONObject().put("key", key).put("gesture", Action.gestureName(gesture))
        try {
            spotify.nowPlaying()?.let { body.put("uri", it.uri).put("title", it.title).put("artist", it.artist) }
        } catch (e: Exception) { }
        // Not retried: a webhook that timed out may still have run, and running it twice is worse.
        val code = try {
            val conn = URL(url).openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.connectTimeout = 10_000
            conn.readTimeout = 10_000
            conn.setRequestProperty("Content-Type", "application/json")
            conn.doOutput = true
            conn.outputStream.use { it.write(body.toString().toByteArray()) }
            conn.responseCode.also { conn.disconnect() }
        } catch (e: IOException) {
            return Outcome(false, "Webhook failed", e.message ?: "network error")
        }
        return if (code in 200..299) Outcome(true, "Webhook sent", "key $key ${Action.gestureName(gesture)}")
            else Outcome(false, "Webhook failed", "HTTP $code")
    }

    override fun getForegroundInfo(): ForegroundInfo =
        if (Build.VERSION.SDK_INT >= 29)
            ForegroundInfo(Notify.WORK_ID, Notify.working(applicationContext), ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        else ForegroundInfo(Notify.WORK_ID, Notify.working(applicationContext))

    companion object {
        const val QUEUE = "presses"
    }
}
