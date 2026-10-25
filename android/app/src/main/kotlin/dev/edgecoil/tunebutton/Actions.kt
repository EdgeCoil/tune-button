// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
package dev.edgecoil.tunebutton

import org.json.JSONObject

/**
 * What a key does. Each of the four keys has three slots, press, hold and double press, and each
 * slot holds one action. No Android dependencies, so the unit tests can check the defaults and the
 * settings byte.
 */
data class Action(
    val type: Type,
    /** The playlist for ADD, REMOVE and PLAY_PLAYLIST. */
    val playlistId: String? = null,
    val playlistName: String? = null,
    /** The URL for WEBHOOK. */
    val url: String? = null,
) {
    /**
     * [repeatable]: running it twice is the same as once, so a request that may or may not have
     * reached Spotify (a timeout, a 5xx) can be retried. A skip, volume step or toggle can't.
     */
    enum class Type(
        val label: String, val needsPlaylist: Boolean = false, val needsSong: Boolean = false,
        val player: Boolean = false, val repeatable: Boolean = false,
    ) {
        NONE("Nothing"),
        LIKE("Like the song", needsSong = true, repeatable = true),
        UNLIKE("Remove from Liked Songs", needsSong = true, repeatable = true),
        ADD("Add to a playlist", needsPlaylist = true, needsSong = true),
        REMOVE("Remove from a playlist", needsPlaylist = true, needsSong = true, repeatable = true),
        PLAY_PAUSE("Play / pause", player = true),
        NEXT("Next track", player = true),
        PREVIOUS("Previous track", player = true),
        VOLUME_UP("Volume up 10%", player = true),
        VOLUME_DOWN("Volume down 10%", player = true),
        SHUFFLE("Shuffle on / off", player = true),
        REPEAT("Repeat: off → all → one", player = true),
        PLAY_PLAYLIST("Play a playlist", needsPlaylist = true, player = true, repeatable = true),
        WEBHOOK("Call a webhook (e.g. Home Assistant)"),
    }

    fun describe(): String = when {
        type.needsPlaylist -> "${type.label}: ${playlistName ?: "(none chosen)"}"
        type == Type.WEBHOOK -> "Webhook: ${url ?: "(no URL)"}"
        else -> type.label
    }

    /** Shorter, for the key cards. */
    fun short(): String = when (type) {
        Type.ADD -> "Add to ${playlistName ?: "playlist"}"
        Type.REMOVE -> "Remove from ${playlistName ?: "playlist"}"
        Type.PLAY_PLAYLIST -> "Play ${playlistName ?: "a playlist"}"
        Type.WEBHOOK -> "Webhook"
        else -> type.label
    }

    fun toJson(): String = JSONObject().put("type", type.name)
        .putOpt("playlist_id", playlistId).putOpt("playlist_name", playlistName).putOpt("url", url).toString()

    companion object {
        val NOTHING = Action(Type.NONE)

        fun fromJson(s: String?): Action? = try {
            s?.let { JSONObject(it) }?.let { j ->
                Action(
                    Type.valueOf(j.getString("type")),
                    j.optString("playlist_id").ifEmpty { null },
                    j.optString("playlist_name").ifEmpty { null },
                    j.optString("url").ifEmpty { null },
                )
            }
        } catch (e: Exception) { null }

        /**
         * Out of the box: key 1 likes and key 2 adds to the playlist (as on the two-button
         * firmware), key 3 skips and key 4 plays or pauses. Holds and double presses do nothing
         * until set, so no key waits to see whether one is coming.
         */
        fun default(key: Int, gesture: Int, playlistId: String?, playlistName: String?): Action =
            if (gesture != Packet.PRESS) NOTHING else when (key) {
                1 -> Action(Type.LIKE)
                2 -> Action(Type.ADD, playlistId, playlistName)
                3 -> Action(Type.NEXT)
                4 -> Action(Type.PLAY_PAUSE)
                else -> NOTHING
            }

        /**
         * The settings byte the button keeps (protocol/spec.md): bit k−1 when key k has a hold action,
         * bit k+3 when it has a double press. A key with neither sends its press the moment it goes
         * down; one with either has to wait to find out.
         */
        fun settingsByte(slot: (key: Int, gesture: Int) -> Action): Int {
            var b = 0
            for (k in 1..Packet.KEYS) {
                if (slot(k, Packet.HOLD).type != Type.NONE) b = b or (1 shl (k - 1))
                if (slot(k, Packet.DOUBLE).type != Type.NONE) b = b or (1 shl (k + 3))
            }
            return b
        }

        /**
         * The action for an event. A hold or double press with nothing assigned does the key's press
         * action, which is what the one-button build's long press relies on, and what happens if the
         * button's settings are out of date.
         */
        fun forEvent(key: Int, gesture: Int, slot: (key: Int, gesture: Int) -> Action): Action {
            val a = slot(key, gesture)
            return if (a.type == Type.NONE && gesture != Packet.PRESS) slot(key, Packet.PRESS) else a
        }

        fun gestureName(g: Int) = when (g) { Packet.HOLD -> "hold"; Packet.DOUBLE -> "double"; else -> "press" }
    }
}
