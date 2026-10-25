// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
package dev.edgecoil.tunebutton

import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/** Press-advert decoding and verification (protocol/spec.md). No Android dependencies. */
object Packet {
    const val COMPANY_ID = 0xFFFF
    const val VERSION = 2
    /** Version 1, from firmware before four keys: no history bytes. Still accepted. */
    const val VERSION_1 = 1
    const val TAG_LEN = 8
    const val HISTORY = 2
    const val KEYS = 4
    const val PRESS = 0
    const val HOLD = 1
    const val DOUBLE = 2
    private val MAGIC = byteArrayOf(0x54, 0x42)

    /** One key event, with the counter the button gave it. */
    data class Event(val counter: Long, val key: Int, val gesture: Int)

    /**
     * A verified advert: its own event, then [earlier], the presses just before it that it also names
     * (counter − 1 and counter − 2, newest first; only those made in the same wake).
     */
    data class Press(val event: Event, val earlier: List<Event>, val battery: Int?, val ageMs: Int) {
        val counter get() = event.counter
    }

    /** The bytes a scan filter matches on: magic, version and device id. */
    fun filterPrefix(deviceId: ByteArray, version: Int = VERSION): ByteArray =
        MAGIC + byteArrayOf(version.toByte()) + deviceId

    private fun authLen(version: Int) = if (version == VERSION_1) 13 else 13 + HISTORY
    fun length(version: Int) = authLen(version) + TAG_LEN + 1

    /** Key 1–4 and gesture from a button code, or null if it isn't one. */
    fun decodeButton(code: Int): Pair<Int, Int>? {
        val key = code and 0x0F
        val gesture = code shr 4
        return if (key in 1..KEYS && gesture in PRESS..DOUBLE) key to gesture else null
    }

    fun buttonCode(key: Int, gesture: Int) = key or (gesture shl 4)

    /** Returns the press if [payload] is a genuine advert from the device holding [key], else null. */
    fun verify(payload: ByteArray?, deviceId: ByteArray, key: ByteArray): Press? {
        if (payload == null || payload.size < 3) return null
        val version = payload[2].toInt()
        if (version != VERSION && version != VERSION_1) return null
        val auth = authLen(version)
        if (payload.size < length(version)) return null
        val prefix = filterPrefix(deviceId, version)
        if (!payload.copyOfRange(0, prefix.size).contentEquals(prefix)) return null
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        mac.update(payload, 0, auth)
        val tag = mac.doFinal().copyOfRange(0, TAG_LEN)
        if (!MessageDigest.isEqual(tag, payload.copyOfRange(auth, auth + TAG_LEN))) return null

        val counter = (0 until 4).fold(0L) { acc, i -> acc or ((payload[7 + i].toLong() and 0xFF) shl (8 * i)) }
        val (k, g) = decodeButton(payload[11].toInt() and 0xFF) ?: return null
        val earlier = if (version == VERSION_1) emptyList() else (0 until HISTORY).mapNotNull { i ->
            val c = counter - 1 - i
            if (c < 0) null
            else decodeButton(payload[13 + i].toInt() and 0xFF)?.let { (hk, hg) -> Event(c, hk, hg) }
        }
        val battery = (payload[12].toInt() and 0xFF).takeIf { it <= 100 }
        val age = payload[auth + TAG_LEN].toInt() and 0xFF
        return Press(Event(counter, k, g), earlier, battery, age * 100)
    }

    /**
     * The events to act on, oldest first: any of [press]'s earlier ones not yet accepted (the phone
     * missed their own adverts), then its own. Empty if the press itself isn't new.
     */
    fun newEvents(lastAccepted: Long, press: Press): List<Event> {
        if (!isNew(lastAccepted, press.counter)) return emptyList()
        return press.earlier.filter { isNew(lastAccepted, it.counter) }.sortedBy { it.counter } + press.event
    }

    /** Replay rule: only a counter strictly above the last accepted one is new. */
    fun isNew(lastAccepted: Long, counter: Long): Boolean = counter > lastAccepted

    /** The tag that goes with new key settings: HMAC-SHA256(key, "TBcfg" | nonce | settings), first 8 bytes. */
    fun settingsTag(key: ByteArray, nonce: ByteArray, settings: Int): ByteArray {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        mac.update("TBcfg".toByteArray())
        mac.update(nonce)
        mac.update(settings.toByte())
        return mac.doFinal().copyOfRange(0, TAG_LEN)
    }
}
