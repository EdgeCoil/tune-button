// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
package dev.edgecoil.tunebutton

import android.content.Context
import android.content.pm.ServiceInfo
import android.os.Build
import androidx.work.ForegroundInfo
import androidx.work.Worker
import androidx.work.WorkerParameters
import java.io.IOException
import org.json.JSONObject

/** Does what a press asks: reads the current song and likes it or adds it to the playlist. */
class PressWorker(ctx: Context, params: WorkerParameters) : Worker(ctx, params) {

    override fun doWork(): Result {
        val store = Store(applicationContext)
        val button = inputData.getInt("button", 0)
        val entry = JSONObject()
            .put("kind", "press")
            .put("button", if (button == Packet.LIKE) "like" else "playlist")
            .put("counter", inputData.getLong("counter", -1))
            .put("battery", inputData.getInt("battery", -1))
            .put("age_ms", inputData.getInt("age_ms", -1))  // press → first heard, measured by the device
            .put("rssi", inputData.getInt("rssi", 0))
        val started = System.currentTimeMillis()
        val (ok, title, text) = act(store, button)
        entry.put("ok", ok).put("result", "$title — $text").put("api_ms", System.currentTimeMillis() - started)
        store.log(entry)
        Notify.show(applicationContext, ok, title, text)
        return Result.success()
    }

    private fun act(store: Store, button: Int): Triple<Boolean, String, String> {
        val spotify = Spotify(store)
        var lastError: Exception? = null
        repeat(2) { attempt ->
            try {
                val playing = spotify.nowPlaying() ?: return Triple(false, "Nothing playing", "Spotify reports no current song")
                if (playing.uri.startsWith("spotify:local:")) return Triple(false, "Local file", "Spotify can't save local files")
                val what = "${playing.title} · ${playing.artist}"
                return if (button == Packet.LIKE) {
                    spotify.like(playing.uri)
                    Triple(true, "♥ Liked", what)
                } else {
                    val pid = store.playlistId ?: return Triple(false, "No playlist chosen", "Pick one in the app")
                    spotify.addToPlaylist(pid, playing.uri)
                    Triple(true, "+ ${store.playlistName ?: "playlist"}", what)
                }
            } catch (e: Spotify.AuthRequired) {
                return Triple(false, "Sign in to Spotify", e.message ?: "")
            } catch (e: Spotify.ApiError) {
                if (e.code != 429 && e.code < 500) return Triple(false, "Not saved", e.message ?: "")
                lastError = e
            } catch (e: IOException) {
                lastError = e  // network blip: one retry
            }
            if (attempt == 0) Thread.sleep(2000)
        }
        return Triple(false, "Not saved", lastError?.message ?: "network error")
    }

    override fun getForegroundInfo(): ForegroundInfo =
        if (Build.VERSION.SDK_INT >= 29)
            ForegroundInfo(Notify.WORK_ID, Notify.working(applicationContext), ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        else ForegroundInfo(Notify.WORK_ID, Notify.working(applicationContext))
}
