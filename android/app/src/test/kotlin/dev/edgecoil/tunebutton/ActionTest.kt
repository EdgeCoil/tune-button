// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
package dev.edgecoil.tunebutton

import org.junit.Assert.assertEquals
import org.junit.Test

class ActionTest {
    private fun defaults(k: Int, g: Int) = Action.default(k, g, "pl", "Mine")

    @Test fun defaultsAreLikePlaylistSkipPlayPause() {
        assertEquals(Action.Type.LIKE, defaults(1, Packet.PRESS).type)
        assertEquals(Action(Action.Type.ADD, "pl", "Mine"), defaults(2, Packet.PRESS))
        assertEquals(Action.Type.NEXT, defaults(3, Packet.PRESS).type)
        assertEquals(Action.Type.PLAY_PAUSE, defaults(4, Packet.PRESS).type)
        for (k in 1..4) for (g in listOf(Packet.HOLD, Packet.DOUBLE)) assertEquals(Action.NOTHING, defaults(k, g))
    }

    @Test fun defaultsNeedNoWaiting() = assertEquals(0, Action.settingsByte(::defaults))

    @Test fun settingsByte() {
        val slots = mapOf((1 to Packet.HOLD) to Action(Action.Type.UNLIKE), (4 to Packet.DOUBLE) to Action(Action.Type.SHUFFLE))
        val slot = { k: Int, g: Int -> slots[k to g] ?: defaults(k, g) }
        // Key 1 hold is bit 0; key 4 double press is bit 7.
        assertEquals(0x81, Action.settingsByte(slot))
    }

    @Test fun unassignedHoldOrDoubleDoesThePress() {
        assertEquals(Action.Type.NEXT, Action.forEvent(3, Packet.HOLD, ::defaults).type)
        assertEquals(Action.Type.LIKE, Action.forEvent(1, Packet.DOUBLE, ::defaults).type)
        val slot = { k: Int, g: Int -> if (k == 3 && g == Packet.HOLD) Action(Action.Type.PREVIOUS) else defaults(k, g) }
        assertEquals(Action.Type.PREVIOUS, Action.forEvent(3, Packet.HOLD, slot).type)
    }

    @Test fun jsonRoundTrip() {
        for (a in listOf(Action.NOTHING, Action(Action.Type.ADD, "id1", "Name"), Action(Action.Type.WEBHOOK, url = "https://x/y")))
            assertEquals(a, Action.fromJson(a.toJson()))
        assertEquals(null, Action.fromJson("{\"type\":\"GONE\"}"))
    }
}
