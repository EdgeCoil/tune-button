// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
package dev.edgecoil.tunebutton

import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/** Press-advert decoding and verification (protocol/spec.md). No Android dependencies. */
object Packet {
    const val COMPANY_ID = 0xFFFF
    const val VERSION = 1
    const val LEN = 22
    const val AUTH_LEN = 13
    const val TAG_LEN = 8
    const val LIKE = 1
    const val PLAYLIST = 2
    private val MAGIC = byteArrayOf(0x54, 0x42)

    data class Press(val counter: Long, val button: Int, val battery: Int?, val ageMs: Int)

    /** The bytes a scan filter matches on: magic, version and device id. */
    fun filterPrefix(deviceId: ByteArray): ByteArray = MAGIC + byteArrayOf(VERSION.toByte()) + deviceId

    /** Returns the press if [payload] is a genuine advert from the device holding [key], else null. */
    fun verify(payload: ByteArray?, deviceId: ByteArray, key: ByteArray): Press? {
        if (payload == null || payload.size < LEN) return null
        val prefix = filterPrefix(deviceId)
        if (!payload.copyOfRange(0, prefix.size).contentEquals(prefix)) return null
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        mac.update(payload, 0, AUTH_LEN)
        val tag = mac.doFinal().copyOfRange(0, TAG_LEN)
        if (!MessageDigest.isEqual(tag, payload.copyOfRange(AUTH_LEN, AUTH_LEN + TAG_LEN))) return null

        val counter = (0 until 4).fold(0L) { acc, i -> acc or ((payload[7 + i].toLong() and 0xFF) shl (8 * i)) }
        val button = payload[11].toInt() and 0xFF
        if (button != LIKE && button != PLAYLIST) return null
        val battery = (payload[12].toInt() and 0xFF).takeIf { it <= 100 }
        val age = payload[21].toInt() and 0xFF
        return Press(counter, button, battery, age * 100)
    }

    /** Replay rule: only a counter strictly above the last accepted one is new. */
    fun isNew(lastAccepted: Long, counter: Long): Boolean = counter > lastAccepted
}
