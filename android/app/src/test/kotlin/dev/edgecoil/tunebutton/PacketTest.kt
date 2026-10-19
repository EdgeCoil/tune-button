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

    private val vectors = JSONObject(File("../../protocol/vectors.json").readText()).getJSONArray("press")
    private fun each(f: (JSONObject) -> Unit) = (0 until vectors.length()).forEach { f(vectors.getJSONObject(it)) }

    @Test fun acceptsEveryVector() = each { v ->
        val p = Packet.verify(hex(v.getString("payload")), hex(v.getString("device_id")), hex(v.getString("key")))
        assertNotNull(p)
        assertEquals(v.getLong("counter"), p!!.counter)
        assertEquals(v.getInt("button"), p.button)
        assertEquals(v.getInt("battery").takeIf { it <= 100 }, p.battery)
        assertEquals(v.getInt("age") * 100, p.ageMs)
    }

    @Test fun rejectsAnyFlippedAuthenticatedBit() = each { v ->
        val payload = hex(v.getString("payload"))
        for (i in 0 until Packet.AUTH_LEN + Packet.TAG_LEN) for (bit in 0 until 8) {
            val bad = payload.copyOf()
            bad[i] = (bad[i].toInt() xor (1 shl bit)).toByte()
            assertNull("byte $i bit $bit", Packet.verify(bad, hex(v.getString("device_id")), hex(v.getString("key"))))
        }
    }

    @Test fun ageIsNotAuthenticated() = each { v ->
        val payload = hex(v.getString("payload"))
        payload[Packet.LEN - 1] = 42
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
        val v = vectors.getJSONObject(0)
        val payload = hex(v.getString("payload"))
        assertNull(Packet.verify(payload.copyOf(Packet.LEN - 1), hex(v.getString("device_id")), hex(v.getString("key"))))
        assertNull(Packet.verify(null, hex(v.getString("device_id")), hex(v.getString("key"))))
    }

    @Test fun replayRule() {
        assertTrue(Packet.isNew(0, 1))
        assertFalse(Packet.isNew(5, 5))
        assertFalse(Packet.isNew(5, 4))
        assertTrue(Packet.isNew(0xFFFFFFFEL, 0xFFFFFFFFL))
    }
}
