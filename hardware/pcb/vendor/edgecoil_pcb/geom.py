# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
import pcbnew


def mm(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def is_key_switch(fp):
    """A keyboard switch footprint: KiCad's Button_Switch_Keyboard library, or a board's own Cherry MX
    footprint (SW_Cherry_MX..., such as a reversible one in a local library)."""
    fpid = fp.GetFPIDAsString()
    return fpid.startswith("Button_Switch_Keyboard:") or fpid.split(":")[-1].startswith("SW_Cherry_MX")


def is_reversible_switch(fp):
    """A switch footprint with both pin pairs, so the switch (and its keycap) can be on either side."""
    return is_key_switch(fp) and "Reversible" in fp.GetFPIDAsString()
