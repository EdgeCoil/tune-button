// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
package dev.edgecoil.tunebutton

import java.io.File
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PacketTest {
    private fun hex(s: String) = ByteArray(s.length / 2) { s.substring(2 * it, 2 * it + 2).toInt(16).toByte() }

    private val all = JSONObject(File("../../protocol/vectors.json").readText())
    private val v2 = all.getJSONArray("press")
    private val v1 = all.getJSONArray("press_v1")
    private fun each(f: (JSONObject) -> Unit) = listOf(v2, v1).forEach { a -> (0 until a.length()).forEach { f(a.getJSONObject(it)) } }

    @Test fun acceptsEveryVector() = each { v ->
        val p = Packet.verify(hex(v.getString("payload")), hex(v.getString("device_id")), hex(v.getString("key")))
        assertNotNull(p)
        assertEquals(v.getLong("counter"), p!!.counter)
        assertEquals(v.getInt("button"), Packet.buttonCode(p.event.key, p.event.gesture))
        assertEquals(v.getInt("battery").takeIf { it <= 100 }, p.battery)
        assertEquals(v.getInt("age") * 100, p.ageMs)
        // History: the byte for counter − 1 − i, where non-zero.
        val history = if (v.has("history")) hex(v.getString("history")) else ByteArray(0)
        val want = history.withIndex().filter { it.value.toInt() != 0 }.map { (i, b) ->
            Triple(v.getLong("counter") - 1 - i, b.toInt() and 0x0F, b.toInt() shr 4)
        }
        assertEquals(want, p.earlier.map { Triple(it.counter, it.key, it.gesture) })
    }

    @Test fun versionOneIsLikeAndPlaylist() {
        val p = (0 until v1.length()).map { v1.getJSONObject(it) }.map { v ->
            Packet.verify(hex(v.getString("payload")), hex(v.getString("device_id")), hex(v.getString("key")))!!
        }
        assertTrue(p.all { it.event.gesture == Packet.PRESS && it.event.key in 1..2 && it.earlier.isEmpty() })
    }

    @Test fun settingsVectors() {
        val s = all.getJSONArray("settings")
        for (i in 0 until s.length()) {
            val v = s.getJSONObject(i)
            assertEquals(v.getString("tag"),
                Packet.settingsTag(hex(v.getString("key")), hex(v.getString("nonce")), v.getInt("config")).joinToString("") { "%02x".format(it) })
        }
    }

    @Test fun newEventsRecoversMissedPresses() {
        val e = { c: Long, k: Int -> Packet.Event(c, k, Packet.PRESS) }
        val press = Packet.Press(e(10, 3), listOf(e(9, 3), e(8, 3)), null, 0)
        // Heard only the third of three quick skips: all three run, oldest first.
        assertEquals(listOf(e(8, 3), e(9, 3), e(10, 3)), Packet.newEvents(7, press))
        // Had already heard #8.
        assertEquals(listOf(e(9, 3), e(10, 3)), Packet.newEvents(8, press))
        // A repeat of #10, or a replay.
        assertEquals(emptyList<Packet.Event>(), Packet.newEvents(10, press))
        assertEquals(emptyList<Packet.Event>(), Packet.newEvents(11, press))
    }

    @Test fun rejectsUnknownButtonCodes() {
        for (code in listOf(0x00, 0x05, 0x31, 0xFF)) assertNull("code $code", Packet.decodeButton(code))
        assertEquals(4 to Packet.DOUBLE, Packet.decodeButton(0x24))
    }

    @Test fun rejectsAnyFlippedAuthenticatedBit() = each { v ->
        val payload = hex(v.getString("payload"))
        for (i in 0 until payload.size - 1) for (bit in 0 until 8) {
            val bad = payload.copyOf()
            bad[i] = (bad[i].toInt() xor (1 shl bit)).toByte()
            assertNull("byte $i bit $bit", Packet.verify(bad, hex(v.getString("device_id")), hex(v.getString("key"))))
        }
    }

    @Test fun ageIsNotAuthenticated() = each { v ->
        val payload = hex(v.getString("payload"))
        payload[payload.size - 1] = 42
        assertEquals(4200, Packet.verify(payload, hex(v.getString("device_id")), hex(v.getString("key")))!!.ageMs)
    }

    @Test fun rejectsWrongKeyAndWrongDevice() = each { v ->
        val payload = hex(v.getString("payload"))
        val key = hex(v.getString("key")).also { it[0] = (it[0] + 1).toByte() }
        assertNull(Packet.verify(payload, hex(v.getString("device_id")), key))
        val id = hex(v.getString("device_id")).also { it[3] = (it[3] + 1).toByte() }
        assertNull(Packet.verify(payload, id, hex(v.getString("key"))))
    }

    @Test fun rejectsShortAndNull() {
        val v = v2.getJSONObject(0)
        val payload = hex(v.getString("payload"))
        assertNull(Packet.verify(payload.copyOf(payload.size - 1), hex(v.getString("device_id")), hex(v.getString("key"))))
        assertNull(Packet.verify(null, hex(v.getString("device_id")), hex(v.getString("key"))))
    }

    @Test fun replayRule() {
        assertTrue(Packet.isNew(0, 1))
        assertFalse(Packet.isNew(5, 5))
        assertFalse(Packet.isNew(5, 4))
        assertTrue(Packet.isNew(0xFFFFFFFEL, 0xFFFFFFFFL))
    }
}
