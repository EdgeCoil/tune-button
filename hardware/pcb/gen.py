# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Generate the three tune-button PCBs: a KiCad schematic and an unrouted board for each.

    xiao    - sockets for a Seeed XIAO ESP32-C3 on 2.54 mm headers
    c3      - an ESP32-C3-WROOM-02 module on the board, with USB-C, charger and regulator
    c3-jst  - the c3's circuit on a smaller board, its buttons wired to a JST connector

xiao and c3 have four Cherry MX switches in a 2 x 2 grid. The netlist below is the single source of
truth: the schematic (labels on every pin) and the board are both written from it, and build.sh's
DRC parity check compares the netlist KiCad reads back from the schematic against the board's pads.

    python3 gen.py [xiao|c3|c3-jst ...]     then ./build.sh to route, check and export
"""
import math
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
from edgecoil_pcb import (C, C0805, LCSC_LED_RED, LED0603, LED0805, R, R1206, Config, Part,  # noqa: E402
                          build, holes)
from edgecoil_pcb.board import set_stackup  # noqa: E402,F401  (panel.py)

HERE = os.path.dirname(os.path.abspath(__file__))

KEY_PITCH = 19.05
KEYCAP = 18.0  # a 1u cap's footprint; screw heads and labels stay outside it so they can be reached
SCREW_HEAD = 4.0  # M2 pan head, with a little room for the driver
W = 46.0  # board width of the two keyboard versions; c3-jst gives its own in extras["width"]


def keys(top, back=False):
    """Four MX switches, 2 x 2, centred across the board; `top` is the upper row's centre y.

    The KiCad footprint's origin is pin 1, 2.54 mm right of and 5.08 mm above the switch centre.
    With `back`, the switches go on the back and the board is used key side up: K1 is still top left
    as you look at the keys, which is top right in KiCad's (front) view, and each footprint is
    mirrored, so its pin 1 is 2.54 mm left of the centre."""
    parts = []
    for i, net in enumerate(["K1", "K2", "K3", "K4"]):
        left = (i % 2 == 0) != back
        cx = W / 2 + (-0.5 if left else 0.5) * KEY_PITCH
        cy = top + (i // 2) * KEY_PITCH
        at = (cx - 2.54, cy - 5.08) if back else (cx + 2.54, cy - 5.08)
        parts.append(Part(f"SW{i + 1}", "Switch:SW_Push", "Button_Switch_Keyboard:SW_Cherry_MX_1.00u_PCB",
                          "MX switch", {"1": net, "2": "GND"}, at, mpn="Cherry MX (3 or 5 pin)",
                          side="B" if back else "F"))
    return parts


def key_pin_zones(top):
    """For back-mounted switches: circles on the front around every switch pin and post, where the
    leads and posts come through, so no front-side part is placed on them. (cx, cy, r) in mm."""
    zones = []
    for row in range(2):
        for col in (-0.5, 0.5):
            cx, cy = W / 2 + col * KEY_PITCH, top + row * KEY_PITCH
            # Mirrored footprint: pin 1, pin 2, the centre post, the two side posts.
            # The pins get 2.5 mm: room for the iron without reflowing a front-side part.
            zones += [(cx - 2.54, cy - 5.08, 2.5), (cx + 3.81, cy - 2.54, 2.5), (cx, cy, 2.5),
                      (cx - 5.08, cy, 1.35), (cx + 5.08, cy, 1.35)]
    return zones


def below_keys(top):
    """Board height that leaves a row of screw heads clear below the lower keycaps: (height, hole y)."""
    y = top + KEY_PITCH + KEYCAP / 2 + SCREW_HEAD / 2 + 0.5
    return y + 3.0, y


def variant_xiao():
    """XIAO on two 1x7 sockets, USB-C at the top edge. Pin 1 of each socket is at the USB end.

    Only GPIO2-5 are both broken out and able to wake the C3 from deep sleep, and the battery needs
    an ADC1 pin (GPIO0-4). So K1-K3 get D1-D3, the battery divider keeps D0, and K4 is read on D4
    and ORed onto K3's wake line through a diode: a K4 press wakes on GPIO5 with D4 low."""
    x0, x1 = W / 2 - 7.62, W / 2 + 7.62  # 15.24 mm between rows: CHECK with calipers
    y1 = 4.4
    parts = [
        Part("J1", "Connector_Generic:Conn_01x07", "Connector_PinSocket_2.54mm:PinSocket_1x07_P2.54mm_Vertical",
             "XIAO left", {"1": "VBAT_SENSE", "2": "K1", "3": "K2", "4": "K3", "5": "K4", "6": "LED", "7": ""},
             (x0, y1), note="D0-D6, USB end first", mpn="Kinghelm KH-2.54FH-1X7P-H8.5", lcsc="C2932672"),
        Part("J2", "Connector_Generic:Conn_01x07", "Connector_PinSocket_2.54mm:PinSocket_1x07_P2.54mm_Vertical",
             "XIAO right", {"1": "", "2": "GND", "3": "", "4": "", "5": "", "6": "", "7": ""},
             (x1, y1), note="5V GND 3V3 D10 D9 D8 D7", mpn="Kinghelm KH-2.54FH-1X7P-H8.5", lcsc="C2932672"),
        Part("J3", "Connector_Generic:Conn_01x02", "Connector_JST:JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2.00mm_Horizontal",
             "LiPo", {"1": "VBAT", "2": "GND"}, (7.0, 13.0), rot=270, mpn="JST S2B-PH-SM4-TB", lcsc="C295747"),
        Part("J4", "Connector_Generic:Conn_01x02", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
             "to XIAO BAT", {"1": "VBAT", "2": "GND"}, (4.0, 20.5), note="wire to the XIAO's BAT+/BAT- pads",
             mpn="XFCN PZ254V-11-02P", lcsc="C492401"),
        R("R1", "220k", "VBAT", "VBAT_SENSE", (11.5, 19.4), 90),
        R("R2", "220k", "VBAT_SENSE", "GND", (11.5, 22.8), 90),
        C("C1", "100n", "VBAT_SENSE", "GND", (9.0, 22.0), 90),
        # 1N4148WS, not a Schottky: with K3 held, a BAT54's reverse leakage drags K4 low when warm
        # (simulated: misread from about 60 C). The press must read below 0.25 x VDD, so the part needs
        # VF <= 0.715 V at 1 mA, as C2128 (Changjing) specifies; hand-soldering pads, as this board is.
        Part("D1", "Diode:1N4148WS", "Diode_SMD:D_SOD-323_HandSoldering", "1N4148WS", {"1": "K4", "2": "K3"},
             (38.5, 16.0), 90, mpn="1N4148WS", lcsc="C2128"),
        R("R3", "1k", "LED", "LED_A", (38.5, 6.0), 0),
        Part("D2", "Device:LED", LED0603, "LED", {"1": "GND", "2": "LED_A"}, (38.5, 9.5), 180, lcsc=LCSC_LED_RED),
    ]
    top = 33.5
    parts += keys(top)
    H, hy = below_keys(top)
    parts += holes([(3.5, 3.5), (W - 3.5, 3.5), (3.5, hy), (W - 3.5, hy)])
    silk = [("rect", W / 2 - 8.75, y1 - 2.9, W / 2 + 8.75, y1 + 18.1), ("text", W / 2, y1 + 6.5, "XIAO"),
            ("text", W / 2, y1 + 9.0, "C3"), ("text", W / 2, y1 - 1.2, "USB"),
            ("text", 12.6, 12.0, "+"), ("text", 6.0, 20.5, "+"), ("text", 6.0, 23.04, "-"),
            ("text", 1.5, 21.77, "BAT", 90)]
    return parts, H, [], silk, {}


def variant_c3():
    """ESP32-C3-WROOM-02 with its antenna over a notch in the top edge, native USB on USB-C at the
    bottom, TP4054 charger, load sharing (a P-FET from the cell, a Schottky from VBUS) and a 2 uA,
    600 mA RT9080 regulator."""
    mx, my = 14.0, 13.2  # module origin; the antenna end is flush with the top edge
    parts = [
        Part("U1", "RF_Module:ESP32-C3-WROOM-02", "RF_Module:ESP32-C3-WROOM-02", "ESP32-C3-WROOM-02-N4",
             {"1": "3V3", "2": "EN", "3": "K2", "4": "K3", "5": "", "6": "", "7": "IO8", "8": "IO9", "9": "GND",
              "10": "LED", "11": "RXD", "12": "TXD", "13": "USB_DN", "14": "USB_DP", "15": "K1", "16": "IO2",
              "17": "VBAT_SENSE", "18": "K4", "19": "GND"}, (mx, my), mpn="ESP32-C3-WROOM-02-N4",
             lcsc="C2934560"),
        # USB-C on the bottom edge, as far from the antenna as the board allows (placed below).
        Part("J1", "Connector:USB_C_Receptacle_USB2.0_16P", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
             "USB-C", {"A1": "GND", "A4": "VBUS", "A5": "CC1", "A6": "USB_DP", "A7": "USB_DN", "A8": "",
                       "A9": "VBUS", "A12": "GND", "B1": "GND", "B4": "VBUS", "B5": "CC2", "B6": "USB_DP",
                       "B7": "USB_DN", "B8": "", "B9": "VBUS", "B12": "GND", "S1": "GND"},
             None, mpn="HRO TYPE-C-31-M-12", lcsc="C165948"),
        R("R1", "5.1k", "CC1", "GND", None, 90),
        R("R2", "5.1k", "CC2", "GND", None, 90),
        # USB ESD: SRV05-4 is a JLC "preferred" part with USBLC6-2SC6's pinout, so no feeder fee.
        # Its rail is 3V3, not VBUS: on battery, the chip's D+ pull-up would otherwise leak through
        # the steering diode onto VBUS (simulated at 2.6 V) and half turn Q1 off.
        Part("U2", "Power_Protection:SRV05-4", "Package_TO_SOT_SMD:SOT-23-6", "SRV05-4",
             {"1": "USB_DP", "2": "GND", "3": "USB_DN", "4": "USB_DN", "5": "3V3", "6": "USB_DP"},
             None, 90, mpn="SRV05-4-P-T7", lcsc="C85364"),
        # Charger: TP4054 (the LTC4054's pinout and PROG formula; a JLC "preferred" part). Pin 1 pulls
        # low while charging, which lights D1.
        Part("U3", "Battery_Management:LTC4054ES5-4.2", "Package_TO_SOT_SMD:SOT-23-5", "TP4054",
             {"1": "STAT", "2": "GND", "3": "VBAT", "4": "VBUS", "5": "PROG"}, (37.0, 19.0), 0,
             mpn="TP4054-42-SOT25R", lcsc="C32574"),
        R("R3", "4.7k", "PROG", "GND", (41.5, 19.0), 90),  # about 200 mA by the TP4054's own formula
        # 0.5 ohm (two 1 ohm Basic parts; 0.47 ohm is Extended) in series with the input capacitor
        # damps the cable's ringing on plug-in, which otherwise peaks around 7 V. Simulated: 1 ohm
        # still let a stiff 5.5 V source with no cell fitted reach 6.8 V on VSYS, past the RT9080's
        # 6.5 V; 0.47 ohm keeps every cable corner under 6.4 V (0.68 ohm doesn't).
        # 10 uF (the most USB allows on VBUS) with R13, so low-resistance cables ring to about 5.6 V
        # rather than 6.1 V: the regulator's limit is 6.5 V.
        C("C1", "10u", "VBUS_C", "GND", (33.0, 17.0), 90, fp=C0805),
        # 1206: each takes a ~35 W, ~50 uJ pulse at every plug-in from a stiff source, about twice
        # what an 0603 is rated to take repeatedly (Vishay CRCW chart); a 1206 has ~2.5x the capacity.
        R("R13", "1", "VBUS", "VBUS_C", (31.9, 13.95), 0, fp=R1206),
        R("R14", "1", "VBUS", "VBUS_C", (31.9, 11.55), 0, fp=R1206),
        C("C2", "4.7u", "VBAT", "GND", (41.5, 23.0), 90),
        R("R4", "1k", "VBUS", "CHG_A", (32.5, 20.5), 90),
        # The LEDs face the keys, so they go on the back with the switches (hand-soldered, 0805).
        Part("D1", "Device:LED", LED0805, "CHG red", {"1": "STAT", "2": "CHG_A"}, (40.0, 20.0), 0, side="B"),
        # Load sharing: on USB, VBUS feeds VSYS through D2 and Q1 is off; on battery, Q1 is on.
        Part("Q1", "Transistor_FET:AO3401A", "Package_TO_SOT_SMD:SOT-23", "AO3401A",
             {"1": "VBUS", "2": "VSYS", "3": "VBAT"}, (37.0, 26.5), 0, mpn="AO3401A", lcsc="C15127"),
        # 3.3k: pulls Q1's gate (and C1) down within ~5-8 ms of unplugging (up to ~15 ms at tolerance extremes), and holds it down against
        # D2's reverse leakage when warm. 1.5 mA, only while on USB.
        R("R5", "3.3k", "VBUS", "GND", (41.5, 27.0), 90),
        # Across Q1: for the few ms after unplugging, before Q1's gate is pulled down, the cell feeds
        # VSYS through this (0.35 V) rather than Q1's body diode (0.6 V), which kept 3V3 above brown-out.
        Part("D4", "Diode:1N5819WS", "Diode_SMD:D_SOD-323", "1N5819WS", {"1": "VSYS", "2": "VBAT"},
             (37.0, 29.8), 0, mpn="1N5819WS", lcsc="C191023"),
        Part("D2", "Diode:1N5819WS", "Diode_SMD:D_SOD-323", "1N5819WS", {"1": "VSYS", "2": "VBUS"},
             (37.0, 23.0), 0, mpn="1N5819WS", lcsc="C191023"),
        # 3.3 V: RT9080, 600 mA (current limit at least 610 mA) with 2 uA quiescent, so Wi-Fi's
        # 350 mA bursts don't sag the rail (a JLC Extended part). It has the AP2112K's pinout; EN is
        # tied on. Its operating limit is 5.5 V in (6.5 V absolute), so C1's damping resistor matters.
        Part("U4", "Regulator_Linear:AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5", "RT9080-3.3",
             {"1": "VSYS", "2": "GND", "3": "VSYS", "4": "", "5": "3V3"}, (27.5, 18.0), 180,
             mpn="RT9080-33GJ5", lcsc="C841192"),
        C("C3", "1u", "VSYS", "GND", (27.5, 22.0), 0),
        C("C4", "22u", "3V3", "GND", (27.5, 14.5), 0, fp=C0805),
        C("C5", "100n", "3V3", "GND", (3.0, 8.4), 90),
        # Reset, boot and straps. IO9 has an internal pull-up; IO2 and IO8 must read high at reset.
        R("R6", "10k", "3V3", "EN", (3.0, 11.4), 90),
        C("C6", "1u", "EN", "GND", (3.0, 14.4), 90),
        R("R7", "10k", "3V3", "IO8", (3.0, 17.4), 90),
        R("R9", "10k", "3V3", "IO2", (25.5, 10.2), 180),
        Part("SW5", "Switch:SW_Push", "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A", "RESET",
             {"1": "EN", "2": "GND"}, (9.4, 24.0), mpn="XKB TS-1187A-B-A-B", lcsc="C318884"),
        Part("SW6", "Switch:SW_Push", "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A", "BOOT",
             {"1": "IO9", "2": "GND"}, (21.0, 24.0), mpn="XKB TS-1187A-B-A-B", lcsc="C318884"),
        # Battery (on the right edge, between the key rows), its divider, the LED.
        Part("J2", "Connector_Generic:Conn_01x02", "Connector_JST:JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2.00mm_Horizontal",
             "LiPo", {"1": "VBAT", "2": "GND"}, (40.5, 43.5), rot=90, mpn="JST S2B-PH-SM4-TB",
             lcsc="C295747"),
        R("R10", "220k", "VBAT", "VBAT_SENSE", (26.5, 26.0), 0),
        R("R11", "220k", "VBAT_SENSE", "GND", (26.5, 28.5), 0),
        C("C7", "100n", "VBAT_SENSE", "GND", (24.0, 28.5), 90),
        R("R12", "1k", "LED", "LED_A", (15.3, 23.0), 0),
        Part("D3", "Device:LED", LED0805, "LED", {"1": "GND", "2": "LED_A"}, (34.0, 20.0), 0, side="B"),
        Part("TP1", "Connector_Generic:Conn_01x02", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
             "UART", {"1": "TXD", "2": "RXD"}, (3.0, 41.0), 0, note="debug UART, optional"),
    ]
    # The switches go on the back, so the keys can sit behind the electronics: only their pins and
    # posts, which come through to the front, need room there.
    top = 36.0
    parts += keys(top, back=True)
    H, hy = below_keys(top)
    # USB-C centred on the bottom edge, its face 0.46 mm proud of the edge so a plug's moulding clears
    # the board: HRO's recommended layout puts the edge 5.79 mm from the locating holes (2.6 mm
    # behind the origin), and JLC cuts outlines to about +-0.2 mm.
    usb_face = 3.65  # footprint origin to the receptacle's front face
    usb_overhang = 2.6 + 3.65 - 5.79
    # The USB-C shell legs come through to the key side: their pads (4.18 mm in from the footprint
    # origin) stay 0.3 mm clear of the bottom switches' 14 mm housings.
    H = max(H, top + KEY_PITCH + 7.0 + 0.3 + 4.18 + usb_face - usb_overhang)
    at = {"J1": (W / 2, H - usb_face + usb_overhang), "U2": (W / 2, H - 11.6), "R1": (W / 2 - 1.0, H - 15.7),
          "R2": (W / 2 + 1.0, H - 15.7)}
    for p in parts:
        if p.ref in at:
            p.at = at[p.ref]
    # The upper pair sit above the keycaps on the left and beside them on the right.
    parts += holes([(W - 3.5, hy), (3.5, hy), (3.0, 23.0), (W - 2.4, 31.0)])
    # Antenna: no board under it at all. Espressif's guidelines prefer the antenna clear of the base
    # board; this notch takes out the board below it and 5 mm to its right (the footprint's keep-out
    # drawing), and the left edge is already within 5 mm. It stops 0.3 mm short of the antenna's end so
    # the module's top row of pads keeps its 0.25 mm copper-to-edge clearance.
    notch = (mx + 14.3, my - 6.8)
    silk = [("text", 34.9, 44.5, "+"), ("text", 9.4, 28.0, "RESET"), ("text", 21.0, 28.0, "BOOT"),
            ("text", 5.6, 41.0, "TX"), ("text", 5.6, 43.54, "RX")]
    # The key side, above the keys, is the emptiest face: the mark and the name go there.
    extras = {"notch": notch, "part_free": key_pin_zones(top),
              # The mark goes over the right half, where the front has only SMD parts: the module's
              # ground-pad vias (pads x 13.5-16.4, y 12.0-14.8) would punch through it. The text sits
              # above and below those vias.
              "logo": (37.0, 12.2, 15.0),
              "back_text": [(14.5, 8.3, "tune-button", 1.5), (14.5, 10.4, "c3 · rev A", 1.0),
                            (14.5, 17.0, "edgecoil.dev", 1.2), (40.0, 22.0, "D1 CHG", 1.0),
                            (34.0, 22.0, "D3 LED", 1.0)],
              "hide_refs": ["D1", "D3"]}  # named in the back text above
    return parts, H, [], silk, extras


def variant_c3_jst():
    """The c3's circuit with no switches on the board: the buttons wire to a 7-pin JST PH, which also
    gives the LED (for an illuminated button) and 3V3. Every part is on the front, so JLC fits them all;
    the board is the module's width plus a column, with the antenna past the top edge.

    J3, cable end down: 1 GND, 2-5 K1-K4, 6 LED (through R15), 7 3V3. A button goes between its K pin
    and GND. 3V3 is the RT9080's, shared with Wi-Fi's 350 mA bursts: budget 100 mA for what hangs on it."""
    # 36 x 50: at 34 x 47 the autorouter never came out clean (32 attempts, 3 to 27 faults each). The
    # extra goes into the channels it kept failing in: beside the module, under it, and the right column.
    w, h = 36.0, 50.0
    mx, my = 14.0, 6.8  # module origin; the antenna (the module's top 6.35 mm) overhangs the top edge
    parts = [p for p in variant_c3()[0] if not p.ref.startswith(("SW1", "SW2", "SW3", "SW4", "H", "TP"))]
    at = {
        # Straps and reset in the strip left of the module, as on the c3.
        "C5": (2.2, 2.0, 90), "R6": (2.2, 5.0, 90), "C6": (2.2, 8.0, 90), "R7": (2.2, 11.0, 90),
        # Right of the module: the divider by VBAT_SENSE, the input resistors and the regulator.
        # (The top row sits 1 mm down, so a track can pass above it with its edge clearance.)
        "R10": (26.1, 2.0, 0), "R9": (26.1, 4.3, 0), "R11": (26.1, 6.5, 0), "C7": (26.0, 8.5, 0),
        # C1 and its 2 x 1 ohm damper sit by the USB-C (J1), not by the regulator: up at the top right they
        # were ~45 mm of track (about 36 nH) from J1, and a hot-plug with no cell rang VBUS to 9.7-11.7 V
        # in the routed-copper simulation (sim11) against 5.5-5.9 V on the c3.
        "R13": (2.0, 35.0, 90), "R14": (4.35, 35.0, 90), "C1": (3.2, 39.4, 0),
        "U4": (29.7, 10.2, 180), "C4": (29.7, 13.0, 0), "C3": (33.6, 10.6, 90),
        # Below the module: reset and boot, then the charger and load sharing.
        "SW5": (5.7, 18.8, 0), "SW6": (14.6, 18.8, 0),
        "U3": (22.5, 17.5, 0), "R3": (26.5, 17.5, 90), "C2": (28.5, 17.5, 90), "R4": (30.5, 17.5, 90),
        "D1": (33.3, 17.5, 90), "Q1": (22.5, 22.0, 0), "D2": (26.7, 21.2, 0), "D4": (26.7, 23.7, 0),
        "R5": (30.0, 22.0, 90), "D3": (33.3, 22.0, 90), "R12": (18.5, 24.0, 0),
        # USB-C at the bottom left, as on the c3 relative to its edge; the battery on the right edge.
        "J1": (7.5, h - 3.19, 0), "U2": (7.5, h - 11.6, 90), "R1": (6.5, h - 15.7, 90), "R2": (8.5, h - 15.7, 90),
        "J2": (30.5, 34.1, 90),
    }
    for p in parts:
        if p.ref in at:
            p.at, p.rot, p.side = at[p.ref][:2], at[p.ref][2], "F"
            if p.ref in ("D1", "D3"):
                p.lcsc = "C84256"  # on the front now, so JLC fits them: a Basic red 0805
        elif p.ref != "U1":
            raise SystemExit(f"c3-jst: no place for {p.ref}")
        else:
            p.at = (mx, my)
    parts += [
        Part("J3", "Connector_Generic:Conn_01x07", "Connector_JST:JST_PH_S7B-PH-SM4-TB_1x07-1MP_P2.00mm_Horizontal",
             "Buttons", {"1": "GND", "2": "K1", "3": "K2", "4": "K3", "5": "K4", "6": "LED_OUT", "7": "3V3"},
             (26.0, h - 5.5), 0, mpn="JST S7B-PH-SM4-TB", lcsc="C265453"),
        # The button wires leave the box's metal-free inside but are handled: clamp them to the rails.
        Part("U5", "Power_Protection:SRV05-4", "Package_TO_SOT_SMD:SOT-23-6", "SRV05-4",
             {"1": "K1", "2": "GND", "3": "K2", "4": "K3", "5": "3V3", "6": "K4"},
             (20.5, 36.0), 0, mpn="SRV05-4-P-T7", lcsc="C85364"),
        # 330 ohm: about 4 mA into a red LED at 3.3 V, enough for a lit button; 10 mA into a short.
        R("R15", "330", "LED", "LED_OUT", (23.0, 30.5), 0),
        # A damper at the regulator: with C1 down by J1, the ~44 nH of VSYS track up to here rang
        # against C3 to 6.6-6.7 V on a hot-plug with no cell (sim12), past the RT9080's 6.5 V. 1 ohm
        # in series with 10 uF absorbs it: 5.86 V worst over every cable and part corner (sim13).
        # Retuning C3 alone left 0.15 V at best and failed with C1 at Samsung's DC-bias low end.
        R("R16", "1", "VSYS", "VSYS_D", (32.4, 6.9), 0, fp=R1206),
        C("C8", "10u", "VSYS_D", "GND", (32.4, 4.5), 180, fp=C0805),
        Part("TP1", "Connector:TestPoint", "TestPoint:TestPoint_Pad_1.0x1.0mm", "TXD", {"1": "TXD"}, (9.5, 26.5),
             note="debug UART"),
        Part("TP2", "Connector:TestPoint", "TestPoint:TestPoint_Pad_1.0x1.0mm", "RXD", {"1": "RXD"}, (12.0, 26.5),
             note="debug UART"),
    ]
    parts += holes([(3.0, 29.0), (17.0, 31.0)])
    silk = [("text", 5.7, 22.8, "RESET"), ("text", 14.6, 22.8, "BOOT"), ("text", 9.5, 28.4, "TX"),
            ("text", 12.0, 28.4, "RX"), ("text", 20.0, h - 10.9, "1"),
            ("text", 24.9, 35.1, "+")]
    extras = {"width": w,
              # The mark and text go behind J3, which has only SMD pads: the back is the main routing
              # layer between the module and the connectors, and no back track may cross the mark.
              "logo": (21.0, h - 8.5, 7.0),
              # The J3 legend in a narrow column at the right, so its via keepout leaves room for a
              # ground via beside U5.
              "back_text": [(30.6, h - 16.2, "J3: 1 GND", 1.0), (30.6, h - 14.5, "2-5 K1-K4", 1.0),
                            (30.6, h - 12.8, "6 LED 7 3V3", 1.0),
                            (30.6, h - 10.4, "tune-button", 1.0), (30.6, h - 8.6, "c3-jst rev A", 1.0),
                            (30.6, h - 6.8, "edgecoil.dev", 1.0)],
              # TX/RX and RESET/BOOT name the pads and switches.
              "hide_refs": ["TP1", "TP2", "SW6"],
              # Parts sit close here: a label 0.25 mm from its part and 0.6 mm from the next read as the
              # next one's (R9, C4, U3 in audits), so a label must be clearly nearer its own part.
              "label_margin": 0.5,
              # A back 3V3 track runs 1.09 mm from the top edge at the antenna base; the pour between it
              # and the edge would be a 0.29 mm strip held at one end (audit round 8), so none goes there.
              "back_pour_notch": (7.0, 21.0, 0.9)}
    return parts, h, [], silk, extras


VARIANTS = {"xiao": variant_xiao, "c3": variant_c3, "c3-jst": variant_c3_jst}

CFG = Config(
    project="tune-button", here=HERE, ns=uuid.UUID("6d1c5f0e-6f0a-4c43-9a59-2b1b8f3a7e10"), variants=VARIANTS,
    width=W, file_prefix="tune-button-", keycap=KEYCAP,
    # Rev A as ordered: an A3 sheet, the company line, IC values shown, and none of the silk and
    # label fixes the cec-bridge added. Turning those on is rev B's change, not this port's.
    paper="A3", sheet_bottom=280, flag_x=360.68, company="edgecoil",
    title=lambda v: f"tune-button {v}", instance_project=lambda v: f"tune-button-{v}",
    comment="Generated by hardware/pcb/gen.py - edit the script, not this file",
    hide_ic_values=False, trim_silk=False, title_block=False, off_sheet_ok=True,
    labels_avoid_marks=False, labels_avoid_own_outline=False, replay_checks=False,
    power_nets=("GND", "VBAT", "VBUS", "VSYS", "3V3"),
    back_text=lambda v, w, h: [(w / 2, h - 6.0, f"tune-button {v}\nedgecoil.dev  rev A", 1.0)],
    logo_svg=os.path.join(HERE, "edgecoil-mark.svg"),
)


if __name__ == "__main__":
    build(CFG, sys.argv[1:])
