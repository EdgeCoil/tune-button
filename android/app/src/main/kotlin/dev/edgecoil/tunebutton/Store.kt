// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
package dev.edgecoil.tunebutton

import android.content.Context
import android.content.SharedPreferences
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import org.json.JSONArray
import org.json.JSONObject

/**
 * Settings and secrets. Secrets (device key, Spotify tokens) are AES-GCM encrypted under a key that
 * lives in the Android Keystore, so a copy of the preferences file alone is not enough to use them.
 */
class Store(context: Context) {
    private val prefs: SharedPreferences = context.applicationContext.getSharedPreferences("tb", Context.MODE_PRIVATE)

    var clientId: String
        get() = prefs.getString("client_id", "") ?: ""
        set(v) = prefs.edit().putString("client_id", v.trim()).apply()

    var playlistId: String?
        get() = prefs.getString("playlist_id", null)
        set(v) = prefs.edit().putString("playlist_id", v).apply()

    var playlistName: String?
        get() = prefs.getString("playlist_name", null)
        set(v) = prefs.edit().putString("playlist_name", v).apply()

    /** What [key]'s [gesture] does; the default until one is chosen. */
    fun slot(key: Int, gesture: Int): Action =
        Action.fromJson(prefs.getString("slot_${key}_$gesture", null))
            ?: Action.default(key, gesture, playlistId, playlistName)

    fun setSlot(key: Int, gesture: Int, a: Action) = prefs.edit().putString("slot_${key}_$gesture", a.toJson()).apply()

    /** The settings byte these slots need on the button. */
    val wantedSettings: Int get() = Action.settingsByte(::slot)

    /** The settings byte last written to the button, or -1 if never (firmware before four keys). */
    var deviceSettings: Int
        get() = prefs.getInt("device_settings", -1)
        set(v) = prefs.edit().putInt("device_settings", v).apply()

    /** Spotify scopes granted with the current token, space separated. */
    var grantedScopes: String
        get() = prefs.getString("scopes", "") ?: ""
        set(v) = prefs.edit().putString("scopes", v).apply()

    var scanMode: Int
        get() = prefs.getInt("scan_mode", 1)  // ScanSettings.SCAN_MODE_BALANCED
        set(v) = prefs.edit().putInt("scan_mode", v).apply()

    var refreshToken: String?
        get() = secret("refresh_token")
        set(v) = putSecret("refresh_token", v)

    var accessToken: String?
        get() = secret("access_token")
        set(v) = putSecret("access_token", v)

    var accessExpiresAt: Long
        get() = prefs.getLong("access_expires_at", 0)
        set(v) = prefs.edit().putLong("access_expires_at", v).apply()

    /** PKCE verifier and state for a login in progress. */
    var pendingAuth: String?
        get() = secret("pending_auth")
        set(v) = putSecret("pending_auth", v)

    data class Device(val id: ByteArray, val key: ByteArray)

    var device: Device?
        get() {
            val id = prefs.getString("device_id", null) ?: return null
            val key = secret("device_key") ?: return null
            return Device(Base64.decode(id, Base64.NO_WRAP), Base64.decode(key, Base64.NO_WRAP))
        }
        set(v) {
            prefs.edit().putString("device_id", v?.id?.let { Base64.encodeToString(it, Base64.NO_WRAP) }).commit()
            putSecret("device_key", v?.key?.let { Base64.encodeToString(it, Base64.NO_WRAP) })
        }

    val lastCounter: Long get() = prefs.getLong("last_counter", -1)

    /**
     * Accept a press atomically: its events not yet acted on, oldest first, exactly once each (see
     * [Packet.newEvents]); empty for a repeat or a replay.
     */
    fun accept(press: Packet.Press): List<Packet.Event> = synchronized(LOCK) {
        val events = Packet.newEvents(lastCounter, press)
        if (events.isNotEmpty()) prefs.edit().putLong("last_counter", press.counter).commit()
        events
    }

    fun resetCounter(to: Long) = synchronized(LOCK) { prefs.edit().putLong("last_counter", to).commit() }

    // ---- event log, shown in the app; the latency column is what Phase 0 measures ----

    fun log(event: JSONObject) = synchronized(LOCK) {
        val arr = JSONArray(prefs.getString("log", "[]"))
        event.put("t", System.currentTimeMillis())
        val out = JSONArray().put(event)
        for (i in 0 until minOf(arr.length(), MAX_LOG - 1)) out.put(arr.get(i))
        prefs.edit().putString("log", out.toString()).commit()
    }

    fun logEntries(): List<JSONObject> {
        val arr = JSONArray(prefs.getString("log", "[]"))
        return (0 until arr.length()).map { arr.getJSONObject(it) }
    }

    fun clearLog() = prefs.edit().putString("log", "[]").apply()

    // ---- Keystore-backed encryption ----

    private fun secret(name: String): String? {
        val blob = prefs.getString("s_$name", null) ?: return null
        return try {
            val raw = Base64.decode(blob, Base64.NO_WRAP)
            val c = Cipher.getInstance("AES/GCM/NoPadding")
            c.init(Cipher.DECRYPT_MODE, vaultKey(), GCMParameterSpec(128, raw, 0, 12))
            String(c.doFinal(raw, 12, raw.size - 12), Charsets.UTF_8)
        } catch (e: Exception) {
            null  // keystore key gone (e.g. after a restore): treat as unset
        }
    }

    private fun putSecret(name: String, value: String?) {
        if (value == null) { prefs.edit().remove("s_$name").commit(); return }
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.ENCRYPT_MODE, vaultKey())
        val blob = c.iv + c.doFinal(value.toByteArray(Charsets.UTF_8))
        prefs.edit().putString("s_$name", Base64.encodeToString(blob, Base64.NO_WRAP)).commit()
    }

    private fun vaultKey(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return gen.generateKey()
    }

    companion object {
        private const val ALIAS = "tune-button-vault"
        private const val MAX_LOG = 50
        private val LOCK = Any()
    }
}
