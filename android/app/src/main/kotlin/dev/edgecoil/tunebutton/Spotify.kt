// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
package dev.edgecoil.tunebutton

import android.net.Uri
import android.util.Base64
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.security.MessageDigest
import java.security.SecureRandom
import org.json.JSONArray
import org.json.JSONObject

/**
 * The few Spotify Web API calls this needs, using the endpoints as of the February 2026 changes:
 * library saves go to PUT /me/library (URIs), playlist adds to POST /playlists/{id}/items.
 * Auth is Authorization Code with PKCE, so no client secret exists anywhere.
 */
class Spotify(private val store: Store) {
    class AuthRequired(msg: String) : Exception(msg)
    class ApiError(val code: Int, msg: String) : Exception(msg)

    data class Playing(val uri: String, val title: String, val artist: String)
    data class Playlist(val id: String, val name: String)

    // ---------------------------------------------------------------- auth

    fun authorizeUri(): Uri {
        require(store.clientId.isNotEmpty()) { "Enter the Spotify client ID first" }
        val verifier = randomUrlSafe(64)
        val state = randomUrlSafe(16)
        store.pendingAuth = "$state $verifier"
        val challenge = b64url(MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray()))
        return Uri.parse(AUTH_URL).buildUpon()
            .appendQueryParameter("client_id", store.clientId)
            .appendQueryParameter("response_type", "code")
            .appendQueryParameter("redirect_uri", REDIRECT_URI)
            .appendQueryParameter("code_challenge_method", "S256")
            .appendQueryParameter("code_challenge", challenge)
            .appendQueryParameter("state", state)
            .appendQueryParameter("scope", SCOPES)
            .build()
    }

    /** Handles the redirect. Returns null on success, or a message. */
    fun completeAuthorization(redirect: Uri): String? {
        val pending = store.pendingAuth ?: return "No login in progress"
        store.pendingAuth = null
        val (state, verifier) = pending.split(" ", limit = 2)
        redirect.getQueryParameter("error")?.let { return "Spotify said: $it" }
        if (redirect.getQueryParameter("state") != state) return "Login state mismatch; try again"
        val code = redirect.getQueryParameter("code") ?: return "No code in redirect"
        tokenRequest(
            "grant_type" to "authorization_code", "code" to code,
            "redirect_uri" to REDIRECT_URI, "client_id" to store.clientId, "code_verifier" to verifier,
        )
        return null
    }

    fun signedIn(): Boolean = store.refreshToken != null

    fun signOut() {
        store.refreshToken = null
        store.accessToken = null
        store.accessExpiresAt = 0
    }

    private fun token(): String {
        val t = store.accessToken
        if (t != null && System.currentTimeMillis() < store.accessExpiresAt - 60_000) return t
        val refresh = store.refreshToken ?: throw AuthRequired("Not signed in to Spotify")
        tokenRequest("grant_type" to "refresh_token", "refresh_token" to refresh, "client_id" to store.clientId)
        return store.accessToken!!
    }

    private fun tokenRequest(vararg form: Pair<String, String>) {
        val body = form.joinToString("&") { (k, v) -> "$k=${URLEncoder.encode(v, "UTF-8")}" }
        val conn = URL(TOKEN_URL).openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
        conn.doOutput = true
        conn.outputStream.use { it.write(body.toByteArray()) }
        val code = conn.responseCode
        val text = (if (code < 400) conn.inputStream else conn.errorStream)?.bufferedReader()?.readText() ?: ""
        if (code == 400 && text.contains("invalid_grant")) {
            signOut()
            throw AuthRequired("Spotify login expired; sign in again")
        }
        if (code != 200) throw ApiError(code, "Token request failed ($code)")
        val j = JSONObject(text)
        store.accessToken = j.getString("access_token")
        store.accessExpiresAt = System.currentTimeMillis() + j.getLong("expires_in") * 1000
        // PKCE refresh tokens may rotate; keep the newest.
        j.optString("refresh_token").takeIf { it.isNotEmpty() }?.let { store.refreshToken = it }
    }

    // ---------------------------------------------------------------- API

    fun nowPlaying(): Playing? {
        val (code, text) = call("GET", "/me/player/currently-playing?additional_types=episode")
        if (code == 204 || text.isBlank()) return null
        val item = JSONObject(text).optJSONObject("item") ?: return null
        val uri = item.optString("uri")
        if (uri.isEmpty()) return null
        val artist = item.optJSONArray("artists")?.let { a ->
            (0 until a.length()).joinToString(", ") { a.getJSONObject(it).optString("name") }
        } ?: item.optJSONObject("show")?.optString("name") ?: ""
        return Playing(uri, item.optString("name"), artist)
    }

    fun like(uri: String) {
        call("PUT", "/me/library?uris=" + URLEncoder.encode(uri, "UTF-8"))
    }

    fun addToPlaylist(playlistId: String, uri: String) {
        call("POST", "/playlists/$playlistId/items", JSONObject().put("uris", JSONArray().put(uri)))
    }

    /** Playlists the user can add to: their own, plus collaborative ones. */
    fun writablePlaylists(): List<Playlist> {
        val me = JSONObject(call("GET", "/me").second).getString("id")
        val out = mutableListOf<Playlist>()
        var path: String? = "/me/playlists?limit=50"
        while (path != null) {
            val page = JSONObject(call("GET", path).second)
            val items = page.getJSONArray("items")
            for (i in 0 until items.length()) {
                val p = items.optJSONObject(i) ?: continue
                val owner = p.optJSONObject("owner")?.optString("id")
                if (owner == me || p.optBoolean("collaborative")) out += Playlist(p.getString("id"), p.optString("name"))
            }
            path = page.optString("next").takeIf { it.isNotEmpty() && it != "null" }?.removePrefix(API)
        }
        return out
    }

    private fun call(method: String, path: String, json: JSONObject? = null): Pair<Int, String> {
        val conn = URL(API + path).openConnection() as HttpURLConnection
        conn.requestMethod = method
        conn.connectTimeout = 10_000
        conn.readTimeout = 10_000
        conn.setRequestProperty("Authorization", "Bearer ${token()}")
        if (json != null) {
            conn.setRequestProperty("Content-Type", "application/json")
            conn.doOutput = true
            conn.outputStream.use { it.write(json.toString().toByteArray()) }
        } else if (method == "PUT" || method == "POST") {
            conn.doOutput = true
            conn.setFixedLengthStreamingMode(0)
            conn.outputStream.close()
        }
        val code = conn.responseCode
        val text = try {
            (if (code < 400) conn.inputStream else conn.errorStream)?.bufferedReader()?.readText() ?: ""
        } catch (e: IOException) { "" }
        when {
            code == 401 -> { store.accessToken = null; throw AuthRequired("Spotify rejected the token; sign in again") }
            code == 403 -> throw ApiError(code, "Spotify refused (403). Is this account a user of the developer app?")
            code == 429 -> throw ApiError(code, "Spotify rate limit; try again shortly")
            code >= 400 -> throw ApiError(code, "Spotify error $code: ${errorMessage(text)}")
        }
        return code to text
    }

    private fun errorMessage(text: String): String =
        try { JSONObject(text).getJSONObject("error").getString("message") } catch (e: Exception) { text.take(120) }

    companion object {
        const val REDIRECT_URI = "tunebutton://callback"
        private const val AUTH_URL = "https://accounts.spotify.com/authorize"
        private const val TOKEN_URL = "https://accounts.spotify.com/api/token"
        private const val API = "https://api.spotify.com/v1"
        private const val SCOPES = "user-read-currently-playing user-read-playback-state user-library-modify " +
            "playlist-read-private playlist-read-collaborative playlist-modify-public playlist-modify-private"

        private fun b64url(b: ByteArray) = Base64.encodeToString(b, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
        private fun randomUrlSafe(bytes: Int) = b64url(ByteArray(bytes).also { SecureRandom().nextBytes(it) })
    }
}
