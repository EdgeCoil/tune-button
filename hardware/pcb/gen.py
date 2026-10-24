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
import re
import sys
import uuid

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
SYMDIR = os.environ.get("KICAD_SYMBOL_DIR", "/usr/share/kicad/symbols")
FPDIR = os.environ.get("KICAD_FOOTPRINT_DIR", "/usr/share/kicad/footprints")
NS = uuid.UUID("6d1c5f0e-6f0a-4c43-9a59-2b1b8f3a7e10")

KEY_PITCH = 19.05
KEYCAP = 18.0  # a 1u cap's footprint; screw heads and labels stay outside it so they can be reached
SCREW_HEAD = 4.0  # M2 pan head, with a little room for the driver
W = 46.0  # board width of the two keyboard versions; c3-jst gives its own in extras["width"]


def uid(*parts):
    return str(uuid.uuid5(NS, "/".join(parts)))


class Part:
    def __init__(self, ref, sym, fp, value, pins, at, rot=0, mpn="", note="", lcsc="", side="F"):
        self.ref, self.sym, self.fp, self.value = ref, sym, fp, value
        self.pins = pins  # pin number -> net name; unlisted pins are no-connect
        self.at, self.rot, self.mpn, self.note, self.lcsc = at, rot, mpn, note, lcsc
        self.side = side  # "B" parts are flipped to the back; `at` is still in front-view coordinates


R0603 = "Resistor_SMD:R_0603_1608Metric"
R1206 = "Resistor_SMD:R_1206_3216Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
LED0603 = "LED_SMD:LED_0603_1608Metric"
LED0805 = "LED_SMD:LED_0805_2012Metric"


# JLCPCB "Basic" parts for the passives and LED: Basic parts carry no per-type assembly fee.
LCSC_R0603 = {"1": "C22936", "330": "C23138", "1k": "C21190", "3.3k": "C22978", "4.7k": "C23162", "5.1k": "C23186", "10k": "C25804", "100k": "C25803",
              "220k": "C22961"}
LCSC_R1206 = {"1": "C17928"}
LCSC_C = {("100n", C0603): "C14663", ("1u", C0603): "C15849", ("4.7u", C0603): "C19666",
          ("22u", C0805): "C45783", ("10u", C0805): "C15850"}
LCSC_LED_RED = "C2286"


def R(ref, value, a, b, at, rot=0, fp=R0603):
    lcsc = (LCSC_R1206 if fp == R1206 else LCSC_R0603)[value]
    return Part(ref, "Device:R", fp, value, {"1": a, "2": b}, at, rot, lcsc=lcsc)


def C(ref, value, a, b, at, rot=0, fp=C0603):
    return Part(ref, "Device:C", fp, value, {"1": a, "2": b}, at, rot, lcsc=LCSC_C[(value, fp)])


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


def holes(points):
    return [Part(f"H{i + 1}", None, "MountingHole:MountingHole_2.2mm_M2", "M2", {}, p) for i, p in enumerate(points)]


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
             (x0, y1), note="D0-D6, USB end first"),
        Part("J2", "Connector_Generic:Conn_01x07", "Connector_PinSocket_2.54mm:PinSocket_1x07_P2.54mm_Vertical",
             "XIAO right", {"1": "", "2": "GND", "3": "", "4": "", "5": "", "6": "", "7": ""},
             (x1, y1), note="5V GND 3V3 D10 D9 D8 D7"),
        Part("J3", "Connector_Generic:Conn_01x02", "Connector_JST:JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2.00mm_Horizontal",
             "LiPo", {"1": "VBAT", "2": "GND"}, (7.0, 13.0), rot=270, mpn="JST S2B-PH-SM4-TB"),
        Part("J4", "Connector_Generic:Conn_01x02", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
             "to XIAO BAT", {"1": "VBAT", "2": "GND"}, (4.0, 20.5), note="wire to the XIAO's BAT+/BAT- pads"),
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
    # JLC prints its order number where this marker is, rather than wherever it likes.
    return parts, H, [], silk, {"jlc_mark": (W / 2, 12.0, "B")}


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
              "hide_refs": ["D1", "D3"],  # named in the back text above
              # JLC's order number goes on the electronics side, not next to the mark.
              "jlc_mark": (19.5, 44.0, "F")}
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
        "R13": (32.4, 2.0, 0), "R14": (32.4, 4.5, 0), "C1": (32.4, 6.9, 0),
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
              "hide_refs": ["TP1", "TP2", "U3", "SW6"],  # TX/RX, RESET/BOOT name those; U3's only spot reads as R3's
              "jlc_mark": (26.0, h - 3.7, "B")}
    return parts, h, [], silk, extras


VARIANTS = {"xiao": variant_xiao, "c3": variant_c3, "c3-jst": variant_c3_jst}


# ---------------------------------------------------------------- symbol library handling

def block(text, start):
    """The balanced s-expression starting at text[start] == '('."""
    depth, i, instr = 0, start, False
    while True:
        ch = text[i]
        if instr:
            if ch == "\\":
                i += 1
            elif ch == '"':
                instr = False
        elif ch == '"':
            instr = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1


_libs = {}


def lib_symbol(lib_id):
    lib, name = lib_id.split(":")
    if lib not in _libs:
        _libs[lib] = open(os.path.join(SYMDIR, lib + ".kicad_sym")).read()
    text = _libs[lib]
    m = re.search(r'\n\t\(symbol "%s"' % re.escape(name), text)
    if not m:
        raise SystemExit(f"symbol {lib_id} not found")
    blk = block(text, m.start() + 2)
    ext = re.search(r'\(extends "([^"]+)"\)', blk)
    if ext:
        parent = lib_symbol(f"{lib}:{ext.group(1)}")
        props = [block(blk, mm.start()) for mm in re.finditer(r"\(property ", blk)]
        body = re.sub(r'^\(symbol "[^"]+"', "", parent[0])
        body = re.sub(r"\n\t*\(property .*?\n\t\t\)", "", body, flags=re.S)  # drop parent's properties
        body = body.replace(f'"{ext.group(1)}_', f'"{name}_')
        head = f'(symbol "{lib_id}"'
        # Properties go after the pin_names/exclude flags; inserting them first is accepted too.
        return head + "\n" + "\n".join(props) + body, parent[1]
    pins = {}
    for pm in re.finditer(r"\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\)", blk):
        pb = block(blk, pm.start())
        num = re.search(r'\(number "([^"]*)"', pb).group(1)
        unit = re.findall(r'\(symbol "%s_(\d+)_(\d+)"' % re.escape(name), blk[:pm.start()])
        if unit and unit[-1][1] == "2":
            continue  # De Morgan alternate body
        pname = re.search(r'\(name "([^"]*)"', pb).group(1)
        pins.setdefault(num, []).append((float(pm.group(1)), float(pm.group(2)), int(pm.group(3)), pname))
    out = blk.replace(f'(symbol "{name}"', f'(symbol "{lib_id}"', 1)
    return out, pins


# ---------------------------------------------------------------- schematic

def fmt(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def write_schematic(name, parts, path):
    root = uid(name, "root")
    used = {}
    for p in parts:
        if p.sym:
            used[p.sym] = lib_symbol(p.sym)
    used["power:PWR_FLAG"] = lib_symbol("power:PWR_FLAG")
    out = [f'(kicad_sch\n\t(version 20250114)\n\t(generator "tune-button-gen")\n\t(generator_version "9.0")'
           f'\n\t(uuid "{root}")\n\t(paper "A3")',
           f'\t(title_block\n\t\t(title "tune-button {name}")\n\t\t(company "edgecoil")\n\t\t'
           f'(comment 1 "Generated by hardware/pcb/gen.py - edit the script, not this file")\n\t)',
           "\t(lib_symbols"]
    out += ["\t\t" + s.replace("\n", "\n\t\t") for s, _ in used.values()]
    out.append("\t)")

    def instance(lib_id, ref, value, fp, x, y, pins, extra=()):
        su = uid(name, "sym", ref)
        s = [f'\t(symbol\n\t\t(lib_id "{lib_id}")\n\t\t(at {fmt(x)} {fmt(y)} 0)\n\t\t(unit 1)'
             # Test pads are bare copper, not parts: out of the BOM, as their footprint already is.
             f'\n\t\t(exclude_from_sim no)\n\t\t(in_bom {"no" if ref.startswith("#") or lib_id == "Connector:TestPoint" else "yes"})'
             f'\n\t\t(on_board {"no" if ref.startswith("#") else "yes"})\n\t\t(dnp no)\n\t\t(uuid "{su}")']
        hide = " (hide yes)" if ref.startswith("#") else ""
        for k, v, dy, h in [("Reference", ref, -2.54, hide), ("Value", value, 2.54, ""),
                            ("Footprint", fp, 5.08, " (hide yes)"), ("Datasheet", "", 0, " (hide yes)")] + list(extra):
            s.append(f'\t\t(property "{k}" "{v}"\n\t\t\t(at {fmt(x)} {fmt(y + dy)} 0)\n\t\t\t(effects (font (size 1.27 1.27)){h})\n\t\t)')
        for num in pins:
            s.append(f'\t\t(pin "{num}" (uuid "{uid(name, "pin", ref, num)}"))')
        s.append(f'\t\t(instances\n\t\t\t(project "tune-button-{name}"\n\t\t\t\t(path "/{root}"\n\t\t\t\t\t'
                 f'(reference "{ref}")\n\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)')
        return "\n".join(s)

    def labels(x, y, pins, nets):
        s = []
        for num, locs in pins.items():
            net = nets.get(num, "")
            for (px, py, ang, _) in locs[:1]:
                ax, ay = round(x + px, 2), round(y - py, 2)
                if not net:
                    s.append(f'\t(no_connect (at {fmt(ax)} {fmt(ay)}) (uuid "{uid(name, "nc", str(x), str(y), num)}"))')
                    continue
                la = {0: 180, 180: 0, 90: 270, 270: 90}[ang]
                just = "right" if la in (180, 270) else "left"
                # Global labels, so the nets keep their bare names (a local label's net is "/NAME").
                s.append(f'\t(global_label "{net}"\n\t\t(shape passive)\n\t\t(at {fmt(ax)} {fmt(ay)} {la})'
                         f'\n\t\t(fields_autoplaced yes)\n\t\t(effects (font (size 1.27 1.27)) (justify {just}))'
                         f'\n\t\t(uuid "{uid(name, "lbl", str(x), str(y), num)}")'
                         f'\n\t\t(property "Intersheetrefs" "${{INTERSHEET_REFS}}"\n\t\t\t(at {fmt(ax)} {fmt(ay)} 0)'
                         f'\n\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n\t\t)\n\t)')
        return s

    # Grid placement: big symbols in the first row, everything else after.
    x, y, col = 40.64, 50.8, 0
    order = sorted([p for p in parts if p.sym], key=lambda p: (0 if p.ref.startswith(("U", "J")) else 1, p.ref))
    for p in order:
        _, pins = used[p.sym]
        ys = [loc[1] for locs in pins.values() for loc in locs]
        span = (max(ys) - min(ys)) if ys else 0
        cell_h = max(25.4, span + 17.78)
        if y + cell_h > 280:
            x, y = x + 76.2, 50.8
        cy = round((y + span / 2 + 5.08) / 2.54) * 2.54
        extra = [("MPN", p.mpn, 7.62, " (hide yes)")] if p.mpn else []
        extra += [("LCSC", p.lcsc, 10.16, " (hide yes)")] if p.lcsc else []
        out.append(instance(p.sym, p.ref, p.value, p.fp, x, cy, pins, extra))
        out += labels(x, cy, pins, p.pins)
        y += cell_h
    # PWR_FLAGs on the supply nets, so ERC knows they are driven.
    # (Not on nets a power-output pin already drives: the charger's VBAT and the regulator's 3V3.)
    driven = {"3V3", "VBAT"} if "VBUS" in {n for p in parts for n in p.pins.values()} else set()
    supplies = sorted(({n for p in parts for n in p.pins.values()} & {"GND", "VBAT", "VBUS", "VSYS", "3V3"}) - driven)
    _, fpins = used["power:PWR_FLAG"]
    for i, net in enumerate(supplies):
        fx, fy = 360.68, 50.8 + i * 15.24
        out.append(instance("power:PWR_FLAG", f"#FLG0{i + 1}", "PWR_FLAG", "", fx, fy, fpins))
        out += labels(fx, fy, fpins, {"1": net})
    out.append(f'\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)')
    open(path, "w").write("\n".join(out) + "\n")
    return root


# ---------------------------------------------------------------- board

def mm(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def outline(board, w, h, notch=None, r=2.5, rn=1.0):
    """Rounded-rectangle board edge, optionally with the top-left corner cut away to `notch` (x, y).
    The notch's corners get a smaller radius; its inside corner is what the router bit leaves anyway."""
    if notch:
        nx, ny = notch
        corners = [((nx, 0), rn), ((w, 0), r), ((w, h), r), ((0, h), r), ((0, ny), rn), ((nx, ny), rn)]
    else:
        corners = [((0, 0), r), ((w, 0), r), ((w, h), r), ((0, h), r)]

    def unit(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = (dx * dx + dy * dy) ** 0.5
        return dx / n, dy / n

    ends = []
    for i, (c, rad) in enumerate(corners):
        d1 = unit(corners[i - 1][0], c)                     # direction arriving at this corner
        d2 = unit(c, corners[(i + 1) % len(corners)][0])    # direction leaving it
        a = (c[0] - d1[0] * rad, c[1] - d1[1] * rad)
        b = (c[0] + d2[0] * rad, c[1] + d2[1] * rad)
        centre = (a[0] + d2[0] * rad, a[1] + d2[1] * rad)
        k = rad / 2 ** 0.5
        mid = (centre[0] + (d1[0] - d2[0]) * k, centre[1] + (d1[1] - d2[1]) * k)
        arc = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC)
        arc.SetArcGeometry(mm(*a), mm(*mid), mm(*b)); arc.SetLayer(pcbnew.Edge_Cuts); arc.SetWidth(pcbnew.FromMM(0.1))
        board.Add(arc)
        ends.append((a, b))
    for i in range(len(ends)):
        seg = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(mm(*ends[i][1])); seg.SetEnd(mm(*ends[(i + 1) % len(ends)][0]))
        seg.SetLayer(pcbnew.Edge_Cuts); seg.SetWidth(pcbnew.FromMM(0.1))
        board.Add(seg)


def usb_crossover(board, fp):
    """Join the USB-C's doubled D+/D- pads, which interleave (B7 A6 A7 B6), so one pair has to cross.
    Freerouting finds this in some runs and not others, with the shell keepout and U2 crowding it,
    so it is laid here and locked: D+ joins across the inner tips, D- drops through two vias at the
    outer tips (inside the open band of the keepout) and joins on the back. The two VBUS pad pairs
    are joined the same way, through vias at their inner tips, so the router has no reason to run
    VBUS along the GND pads and shell legs to reach them."""
    pads = {p.GetNumber(): p for p in fp.Pads()}
    if not {"A6", "A7", "B6", "B7"} <= pads.keys():
        return
    def at(p, side, off):  # a point `off` mm out from the pad's inner (-1) or outer (+1) tip
        box = p.GetBoundingBox()
        y = box.GetTop() - pcbnew.FromMM(off) if side < 0 else box.GetBottom() + pcbnew.FromMM(off)
        return pcbnew.VECTOR2I(p.GetPosition().x, y)
    def track(net, layer, a, b, w=0.25):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(a); t.SetEnd(b); t.SetLayer(layer); t.SetWidth(pcbnew.FromMM(w))
        t.SetNet(board.FindNet(net)); t.SetLocked(True)
        board.Add(t)
    def via(net, p, d=0.6):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(p); v.SetDrill(pcbnew.FromMM(d / 2)); v.SetWidth(pcbnew.FromMM(d))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(board.FindNet(net)); v.SetLocked(True)
        board.Add(v)
    # D+: up from both pads, 0.5 mm clear of A7's tip, and across.
    a, b = at(pads["A6"], -1, 0.5), at(pads["B6"], -1, 0.5)
    track("USB_DP", pcbnew.F_Cu, pads["A6"].GetPosition(), a)
    track("USB_DP", pcbnew.F_Cu, pads["B6"].GetPosition(), b)
    track("USB_DP", pcbnew.F_Cu, a, b)
    # D-: down from both pads to a via each, joined underneath.
    # (0.55 mm out, so the stubs end short of the keepout and only the via caps reach it.)
    a, b = at(pads["B7"], 1, 0.55), at(pads["A7"], 1, 0.55)
    for p, v in ((pads["B7"], a), (pads["A7"], b)):
        track("USB_DN", pcbnew.F_Cu, p.GetPosition(), v)
        via("USB_DN", v)
    track("USB_DN", pcbnew.B_Cu, a, b)
    # VBUS: up from both pairs to a power via each, joined underneath.
    # (Standard 0.6 mm vias, 0.5 mm out: a mask web clear of the pad, and the join still clears
    # the ESD chip's ground via behind the row.)
    a, b = at(pads["A4"], -1, 0.5), at(pads["A9"], -1, 0.5)
    for p, v in ((pads["A4"], a), (pads["A9"], b)):
        track("VBUS", pcbnew.F_Cu, p.GetPosition(), v, 0.4)
        via("VBUS", v)
    track("VBUS", pcbnew.B_Cu, a, b, 0.4)


def esd_ground(board, ref="U2"):
    """The ESD array's GND pin sits between its two signal pins, where its pour island is too small
    for the stitcher: give it its own via just off the pin's tip, on the connector side (the pin
    rows are too close for one between them), so the clamp current goes straight down to the plane."""
    fp = board.FindFootprintByReference(ref)
    if not fp:
        return
    gnd = next(p for p in fp.Pads() if p.GetNetname() == "GND")
    c, g = fp.GetPosition(), gnd.GetPosition()
    tip = gnd.GetBoundingBox().GetBottom() if g.y > c.y else gnd.GetBoundingBox().GetTop()
    off = pcbnew.FromMM(0.3 + 0.3)  # via radius plus a mask web from the pad
    at = pcbnew.VECTOR2I(g.x, tip + off if g.y > c.y else tip - off)
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(g); t.SetEnd(at); t.SetLayer(pcbnew.F_Cu); t.SetWidth(pcbnew.FromMM(0.4))
    t.SetNet(gnd.GetNet()); t.SetLocked(True)
    board.Add(t)
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(at); v.SetDrill(pcbnew.FromMM(0.3)); v.SetWidth(pcbnew.FromMM(0.6))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(gnd.GetNet()); v.SetLocked(True)
    board.Add(v)


def zone(board, net, layer, pts, keepout=False, part_free=False, via_free=False, gap_free=False,
         track_free=False, hole=None):
    z = pcbnew.ZONE(board)
    if gap_free or track_free:
        # gap_free: between a hand-soldered part's pads, on its own side: nothing a solder bridge
        # could reach. track_free: under a metal-bodied part, where only mask would insulate a
        # track (a tented via is a flat cap, so it may sit there).
        z.SetIsRuleArea(True)
        side = pcbnew.LSET(); side.AddLayer(layer)
        z.SetLayerSet(side)
        z.SetDoNotAllowTracks(True); z.SetDoNotAllowVias(gap_free); z.SetDoNotAllowPads(False)
        fills = gap_free
        z.SetDoNotAllowZoneFills(fills) if hasattr(z, "SetDoNotAllowZoneFills") else z.SetDoNotAllowCopperPour(fills)
        z.SetDoNotAllowFootprints(False)
    elif via_free:
        # Under silkscreen artwork: a via's hole would punch through the print.
        z.SetIsRuleArea(True)
        z.SetLayerSet(pcbnew.LSET.AllCuMask())
        z.SetDoNotAllowTracks(False); z.SetDoNotAllowVias(True); z.SetDoNotAllowPads(False)
        z.SetDoNotAllowZoneFills(False) if hasattr(z, "SetDoNotAllowZoneFills") else z.SetDoNotAllowCopperPour(False)
        z.SetDoNotAllowFootprints(False)
    elif part_free:
        # Front-side parts only: tracks, vias and copper are fine here.
        z.SetIsRuleArea(True)
        front = pcbnew.LSET(); front.AddLayer(pcbnew.F_Cu)
        z.SetLayerSet(front)
        z.SetDoNotAllowTracks(False); z.SetDoNotAllowVias(False); z.SetDoNotAllowPads(False)
        z.SetDoNotAllowZoneFills(False) if hasattr(z, "SetDoNotAllowZoneFills") else z.SetDoNotAllowCopperPour(False)
        z.SetDoNotAllowFootprints(True)
    elif keepout:
        z.SetIsRuleArea(True)
        z.SetLayerSet(pcbnew.LSET.AllCuMask())
        z.SetDoNotAllowTracks(True); z.SetDoNotAllowVias(True); z.SetDoNotAllowPads(False)
        z.SetDoNotAllowZoneFills(True) if hasattr(z, "SetDoNotAllowZoneFills") else z.SetDoNotAllowCopperPour(True)
        z.SetDoNotAllowFootprints(False)
    else:
        z.SetLayer(layer); z.SetNet(net)
        z.SetLocalClearance(pcbnew.FromMM(0.3)) if hasattr(z, "SetLocalClearance") else None
        z.SetMinThickness(pcbnew.FromMM(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)  # spokes on every pad: even reflow, easy rework
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetThermalReliefGap(pcbnew.FromMM(0.4)); z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.4))
    ol = z.Outline(); ol.NewOutline()
    for p in pts:
        ol.Append(mm(*p))
    if hole:
        ol.NewHole()
        for p in hole:
            ol.Append(mm(*p))
    board.Add(z)


def write_board(name, parts, h, keepouts, silk, extras, path, root):
    board = pcbnew.BOARD()
    board.SetFileName(path)
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    nets = {}
    for netname in sorted({n for p in parts for n in p.pins.values() if n}):
        ni = pcbnew.NETINFO_ITEM(board, netname)
        board.Add(ni)
        nets[netname] = ni
    for p in parts:
        lib, fpname = p.fp.split(":")
        fp = pcbnew.FootprintLoad(os.path.join(FPDIR, lib + ".pretty"), fpname)
        fp.SetFPIDAsString(p.fp)
        fp.SetReference(p.ref)
        fp.SetValue(p.value)
        if not p.sym:
            fp.SetBoardOnly(True)  # mounting holes have no symbol
            fp.Reference().SetVisible(False)
        if p.sym:
            fp.SetPath(pcbnew.KIID_PATH(f"/{uid(name, 'sym', p.ref)}"))
            fp.SetSheetname("Root"); fp.SetSheetfile(f"tune-button-{name}.kicad_sch")
        board.Add(fp)
        fp.SetPosition(mm(*p.at))
        fp.SetOrientationDegrees(p.rot)
        if p.side == "B":
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        pins = lib_symbol(p.sym)[1] if p.sym else {}
        for pad in fp.Pads():
            num = pad.GetNumber()
            net = p.pins.get(num, "")
            if not net and num in pins:
                # The name KiCad's schematic gives an unconnected pin's net, so parity checks pass.
                net = f"unconnected-({p.ref}-{pins[num][0][3]}-Pad{num})"
                if net not in nets:
                    nets[net] = pcbnew.NETINFO_ITEM(board, net)
                    board.Add(nets[net])
            if net:
                pad.SetNet(nets[net])
        if p.mpn:
            fp.SetField("MPN", p.mpn)
            fp.GetFieldByName("MPN").SetVisible(False)
        if p.lcsc:
            fp.SetField("LCSC", p.lcsc)
            fp.GetFieldByName("LCSC").SetVisible(False)
            # Slotted legs (the USB-C shell) on a reflowed part: paste them, overprinted 0.12 mm (which
            # leaves a 0.15 mm stencil web to the next pad), so
            # they solder in reflow.
            for pad in fp.Pads():
                if pad.HasHole() and pad.GetDrillShape() == pcbnew.PAD_DRILL_SHAPE_OBLONG:
                    layers = pad.GetLayerSet(); layers.AddLayer(pcbnew.F_Paste); pad.SetLayerSet(layers)
                    pad.SetLocalSolderPasteMargin(pcbnew.FromMM(0.12))
        # JLC's minimum legend line is 0.15 mm; library footprints draw 0.12.
        for item in fp.GraphicalItems():
            if item.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS) and isinstance(item, pcbnew.PCB_SHAPE):
                item.SetWidth(max(item.GetWidth(), pcbnew.FromMM(0.15)))
    w = extras.get("width", W)
    outline(board, w, h, extras.get("notch"))
    inset = [(0.3, 0.3), (w - 0.3, 0.3), (w - 0.3, h - 0.3), (0.3, h - 0.3)]
    zone(board, nets["GND"], pcbnew.F_Cu, inset)
    zone(board, nets["GND"], pcbnew.B_Cu, inset)
    for k in keepouts:
        zone(board, None, None, k, keepout=True)
    for cx, cy, r in extras.get("part_free", []):
        circle = [(cx + r * math.cos(a * math.pi / 8), cy + r * math.sin(a * math.pi / 8)) for a in range(16)]
        zone(board, None, None, circle, part_free=True)
    # The USB-C's shell sits flat on the board, grounded: no tracks under its body (ground pour is
    # fine), where nothing but mask would separate them. Its metal floor starts about 0.75 mm past
    # the pad tips (HRO: 6.28 mm plate in a 7.35 mm body); up to there stays open for the crossover.
    for fp in board.Footprints():
        if not fp.GetFPIDAsString().startswith("Connector_USB:"):
            continue
        body = pcbnew.BOX2I()
        for item in fp.GraphicalItems():
            if item.GetLayer() == pcbnew.F_Fab and isinstance(item, pcbnew.PCB_SHAPE):
                body.Merge(item.GetBoundingBox())
        row = max(pd.GetBoundingBox().GetBottom() for pd in fp.Pads() if pd.GetAttribute() == pcbnew.PAD_ATTRIB_SMD)
        x0, y0, x1, y1 = (v / 1e6 for v in (body.GetLeft(), row + pcbnew.FromMM(0.7), body.GetRight(), body.GetBottom()))
        zone(board, None, pcbnew.F_Cu, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], track_free=True)
        usb_crossover(board, fp)
    esd_ground(board)
    # Back-side SMD parts are soldered by hand: keep tracks and vias out from between their pads.
    for fp in board.Footprints():
        smd = [pd.GetBoundingBox() for pd in fp.Pads() if pd.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
        if fp.GetLayer() != pcbnew.B_Cu or len(smd) != 2:
            continue
        a, b = sorted(smd, key=lambda r: (r.GetCenter().x, r.GetCenter().y))
        m = pcbnew.FromMM(0.5)
        if a.GetRight() < b.GetLeft():
            box = (a.GetRight(), min(a.GetTop(), b.GetTop()) - m, b.GetLeft(), max(a.GetBottom(), b.GetBottom()) + m)
        else:
            a, b = sorted(smd, key=lambda r: r.GetCenter().y)
            box = (min(a.GetLeft(), b.GetLeft()) - m, a.GetBottom(), max(a.GetRight(), b.GetRight()) + m, b.GetTop())
        x0, y0, x1, y1 = (v / 1e6 for v in box)
        zone(board, None, pcbnew.B_Cu, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], gap_free=True)
        # And no via hard up against either pad. (Vias are tented, so beyond this margin one is no
        # worse than a track; at 0.6 mm the router ran out of room.)
        whole = pcbnew.BOX2I(a.GetPosition(), a.GetSize()); whole.Merge(b); whole.Inflate(pcbnew.FromMM(0.25))
        x0, y0, x1, y1 = (v / 1e6 for v in (whole.GetLeft(), whole.GetTop(), whole.GetRight(), whole.GetBottom()))
        zone(board, None, None, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], via_free=True)
    for item in silk:
        if item[0] == "rect":
            x0, y0, x1, y1 = item[1:]
            r = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_RECT)
            r.SetStart(mm(x0, y0)); r.SetEnd(mm(x1, y1)); r.SetLayer(pcbnew.F_SilkS); r.SetWidth(pcbnew.FromMM(0.15))
            board.Add(r)
        else:
            t = pcbnew.PCB_TEXT(board)
            t.SetText(item[3]); t.SetPosition(mm(item[1], item[2])); t.SetLayer(pcbnew.F_SilkS)
            t.SetTextSize(mm(1.0, 1.0)); t.SetTextThickness(pcbnew.FromMM(0.15))
            if len(item) > 4:
                t.SetTextAngleDegrees(item[4])
            board.Add(t)
    back_text = extras.get("back_text", [(w / 2, h - 6.0, f"tune-button {name}\nedgecoil.dev  rev A", 1.0)])
    for x, y, text, size in back_text:
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text); t.SetPosition(mm(x, y)); t.SetLayer(pcbnew.B_SilkS); t.SetMirrored(True)
        t.SetTextSize(mm(size, size)); t.SetTextThickness(pcbnew.FromMM(max(0.15, size * 0.15)))
        board.Add(t)
    if "logo" in extras:
        logo(board, *extras["logo"])
    art, logo_box = [], pcbnew.BOX2I()
    if "jlc_mark" in extras:
        x, y, side = extras["jlc_mark"]
        t = pcbnew.PCB_TEXT(board)
        t.SetText("JLCJLCJLCJLC"); t.SetPosition(mm(x, y))
        t.SetLayer(pcbnew.B_SilkS if side == "B" else pcbnew.F_SilkS); t.SetMirrored(side == "B")
        t.SetTextSize(mm(1.0, 1.0)); t.SetTextThickness(pcbnew.FromMM(0.15))
        board.Add(t)
        # JLC prints its order number over it: no footprint hole may sit under it (nor a via; see
        # the end of this function).
        box = t.GetBoundingBox(); box.Inflate(pcbnew.FromMM(0.2))
        for pad in board.GetPads():
            if pad.HasHole() and box.Intersects(pad.GetBoundingBox()):
                raise SystemExit(f"{name}: hole in {pad.GetParentFootprint().GetReference()} under the JLC mark")
    # Keep vias out from under the back-side text and the mark.
    for d in board.Drawings():
        if d.GetLayer() == pcbnew.B_SilkS:
            if isinstance(d, pcbnew.PCB_SHAPE) and d.GetShape() == pcbnew.SHAPE_T_SEGMENT:
                logo_box.Merge(d.GetBoundingBox())
            else:
                art.append(d.GetBoundingBox())
    if logo_box.GetWidth():
        art.append(logo_box)
        # And no back tracks under the logo: they fence off pockets of the ground plane there that
        # can't take a via (the logo keeps vias out), and the fill removes them, which shows
        # through the mask.
        b = pcbnew.BOX2I(logo_box.GetPosition(), logo_box.GetSize()); b.Inflate(pcbnew.FromMM(0.4))
        x0, y0, x1, y1 = (pcbnew.ToMM(v) for v in (b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom()))
        zone(board, None, pcbnew.B_Cu, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], track_free=True)
    for b in art:
        b.Inflate(pcbnew.FromMM(0.4))
        # Footprint holes (the module's ground-pad vias, switch pins) can't be routed around.
        for pad in board.GetPads():
            if pad.HasHole() and b.Intersects(pad.GetBoundingBox()):
                raise SystemExit(f"{name}: hole in {pad.GetParentFootprint().GetReference()} under back artwork")
        b.Inflate(pcbnew.FromMM(0.6))  # vias 1 mm clear, so none reads as part of the print
        x0, y0, x1, y1 = (pcbnew.ToMM(v) for v in (b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom()))
        zone(board, None, None, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], via_free=True)
    for ref in extras.get("hide_refs", []):
        board.FindFootprintByReference(ref).Reference().SetVisible(False)
    place_labels(board, w, h, extras.get("notch"))
    # No via under a part label or front text (BOOT, the JLC mark...) either: a via cap breaks up
    # 1 mm text.
    boxes = [fp.Reference().GetBoundingBox() for fp in board.Footprints()
             if fp.Reference().IsVisible() and not fp.GetFPIDAsString().startswith("Button_Switch_Keyboard:")]
    boxes += [d.GetBoundingBox() for d in board.Drawings()
              if isinstance(d, pcbnew.PCB_TEXT) and d.GetLayer() == pcbnew.F_SilkS]
    for b in boxes:
        b.Inflate(pcbnew.FromMM(0.1))
        x0, y0, x1, y1 = (pcbnew.ToMM(v) for v in (b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom()))
        zone(board, None, None, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], via_free=True)
    board.Save(path)
    set_stackup(path)


# Black solder mask, white legend, 1.6 mm FR4. The Python API doesn't reach the stackup, so it is
# written into the file; KiCad's renders and the gerber job file take their colours from it.
STACKUP = """\t\t(stackup
\t\t\t(layer "F.SilkS" (type "Top Silk Screen") (color "White"))
\t\t\t(layer "F.Paste" (type "Top Solder Paste"))
\t\t\t(layer "F.Mask" (type "Top Solder Mask") (color "Black") (thickness 0.01))
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 1" (type "core") (color "FR4 natural") (thickness 1.51) (material "FR4")
\t\t\t\t(epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "B.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (color "Black") (thickness 0.01))
\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))
\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen") (color "White"))
\t\t\t(copper_finish "HAL lead-free")
\t\t\t(dielectric_constraints no)
\t\t)
"""


def set_stackup(path):
    src = open(path).read()
    src = re.sub(r"\t\t\(stackup\n.*?\n\t\t\)\n", "", src, flags=re.S)
    open(path, "w").write(src.replace("\t(setup\n", "\t(setup\n" + STACKUP, 1))


def logo(board, cx, cy, width, svg=os.path.join(HERE, "edgecoil-mark.svg"), stroke=0.15, res=0.025):
    """The EdgeCoil mark in back silkscreen, `width` mm wide, centred on (cx, cy), mirrored so it reads
    from the back. It is drawn as horizontal 0.15 mm strokes, one row every 0.15 mm so the rows tile
    without overlap, each run shortened by the stroke's round caps. So the print covers what the mark
    covers and its gaps keep their drawn size, to the 0.15 mm the legend can resolve."""
    import subprocess
    import tempfile
    from PIL import Image
    def render(px):
        with tempfile.NamedTemporaryFile(suffix=".png") as png:
            subprocess.run(["rsvg-convert", "-w", str(px), "-o", png.name, svg], check=True)
            im = Image.open(png.name).convert("RGBA")
        return im.crop(im.getchannel("A").point(lambda a: 255 if a >= 128 else 0).getbbox())
    # The SVG's canvas has margins: scale so the mark itself, not the canvas, is `width` wide.
    px = round(width / res)
    img = render(round(px * px / render(px).width))
    w, h = img.size
    alpha = img.getchannel("A").load()
    x0, y0 = cx - width / 2, cy - h * res / 2
    step = round(stroke / res)
    for row in range(step // 2, h, step):  # sample each 0.15 mm band at its centre
        runs, col = [], 0
        while col < w:
            if alpha[col, row] < 128:
                col += 1
                continue
            start = col
            while col < w and alpha[col, row] >= 128:
                col += 1
            runs.append([x0 + start * res, x0 + col * res])  # the run covers [start, col) pixels
        # A gap narrower than the legend can print would fill in: open it to `stroke`.
        for left, right in zip(runs, runs[1:]):
            short = stroke - (right[0] - left[1])
            if short > 0:
                left[1] -= short / 2; right[0] += short / 2
        for ra, rb in runs:
            # The stroke's round caps add stroke/2 at each end.
            a, b = ra + stroke / 2, rb - stroke / 2
            if b < a:
                a = b = (a + b) / 2
            # Mirror x about the centre: the back is seen from the other side.
            xa, xb = 2 * cx - a, 2 * cx - b
            y = y0 + (row + 0.5) * res
            seg = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
            seg.SetStart(mm(xa, y)); seg.SetEnd(mm(xb - (0.001 if xa == xb else 0), y))
            seg.SetLayer(pcbnew.B_SilkS); seg.SetWidth(pcbnew.FromMM(stroke))
            board.Add(seg)


def place_labels(board, w, h, notch=None):
    """Put each part's reference in the first spot beside it that covers no pad, no part body and no
    other label, so the silkscreen stays readable once the parts are on. MX switch labels stay where
    the footprint puts them: their caps cover that whole area anyway."""
    def grow(b, d):
        b = pcbnew.BOX2I(b.GetPosition(), b.GetSize())
        b.Inflate(pcbnew.FromMM(d))
        return b

    # A part's body is its fab-layer outline and its pads. (Not the courtyard: the module's takes in
    # the antenna clearance, which is the whole column beside it.)
    # Each side is placed against its own parts and silkscreen; pads (through-hole ones come through)
    # count on both.
    bodies = {pcbnew.F_SilkS: {}, pcbnew.B_SilkS: {}}
    side_of = {}
    for fp in board.Footprints():
        back = fp.GetLayer() == pcbnew.B_Cu
        fab, silk = (pcbnew.B_Fab, pcbnew.B_SilkS) if back else (pcbnew.F_Fab, pcbnew.F_SilkS)
        box = pcbnew.BOX2I()
        for item in list(fp.GraphicalItems()) + list(fp.Pads()):
            if item.IsOnLayer(fab) or isinstance(item, pcbnew.PAD):
                box.Merge(item.GetBoundingBox())
        bodies[silk][fp.GetReference()] = box
        side_of[fp.GetReference()] = silk
    # Keycaps on front-mounted switches cover an 18 mm square round the centre post.
    for fp in board.Footprints():
        if fp.GetFPIDAsString().startswith("Button_Switch_Keyboard:") and fp.GetLayer() == pcbnew.F_Cu:
            post = max(fp.Pads(), key=lambda p: p.GetDrillSize().x).GetPosition()
            half = pcbnew.FromMM(KEYCAP / 2)
            bodies[pcbnew.F_SilkS][f"cap-{fp.GetReference()}"] = pcbnew.BOX2I(
                pcbnew.VECTOR2I(post.x - half, post.y - half), pcbnew.VECTOR2I(2 * half, 2 * half))
    # A silkscreen outline marks something that sits over the board (the XIAO): nothing goes under it.
    for d in board.Drawings():
        if isinstance(d, pcbnew.PCB_SHAPE) and d.GetLayer() in bodies and d.GetShape() == pcbnew.SHAPE_T_RECT:
            bodies[d.GetLayer()][f"outline-{len(bodies[d.GetLayer()])}"] = d.GetBoundingBox()
    if notch:  # no board there
        for layer in bodies:
            bodies[layer]["notch"] = pcbnew.BOX2I(mm(0, 0), mm(notch[0] + 0.5, notch[1] + 0.5))
    pads = [grow(p.GetBoundingBox(), 0.15) for p in board.GetPads()]
    texts = {layer: [grow(d.GetBoundingBox(), 0.1) for d in board.Drawings()
                     if d.GetLayer() == layer and (isinstance(d, pcbnew.PCB_TEXT) or d.GetShape() == pcbnew.SHAPE_T_SEGMENT)]
             for layer in bodies}
    area = pcbnew.BOX2I(mm(0.6, 0.6), mm(w - 1.2, h - 1.2))

    def owner(b, layer):
        """The part whose body is clearly nearest the label (by 0.25 mm), so it reads as its own part's."""
        def dist(box):  # edge to edge
            dx = max(box.GetLeft() - b.GetRight(), 0, b.GetLeft() - box.GetRight())
            dy = max(box.GetTop() - b.GetBottom(), 0, b.GetTop() - box.GetBottom())
            return math.hypot(dx, dy)
        parts = sorted((dist(v), r) for r, v in bodies[layer].items() if r in side_of)
        if len(parts) > 1 and parts[1][0] - parts[0][0] < pcbnew.FromMM(0.25):
            return None
        return parts[0][1]
    # Small parts first: they have the fewest places to go.
    order = sorted((fp for fp in board.Footprints() if fp.Reference().IsVisible()),
                   key=lambda fp: bodies[side_of[fp.GetReference()]][fp.GetReference()].GetArea())
    for fp in order:
        ref = fp.Reference()
        layer = side_of[fp.GetReference()]
        if fp.GetFPIDAsString().startswith("Button_Switch_Keyboard:"):
            texts[layer].append(grow(ref.GetBoundingBox(), 0.1))
            continue
        ref.SetTextSize(mm(1.0, 1.0)); ref.SetTextThickness(pcbnew.FromMM(0.15))
        ref.SetKeepUpright(True)
        body = bodies[layer][fp.GetReference()]
        c, half_w, half_h = body.GetCenter(), body.GetWidth() // 2, body.GetHeight() // 2
        gap = pcbnew.FromMM(0.25)

        def spots():
            # Horizontal above, below and beside; then vertical beside (for parts in a narrow column).
            for angle in (0, 90):
                ref.SetTextAngleDegrees(angle)
                ref.SetPosition(c)
                tw, th = ref.GetBoundingBox().GetWidth() // 2, ref.GetBoundingBox().GetHeight() // 2
                ox, oy = half_w + tw + gap, half_h + th + gap
                near = [(0, -oy), (0, oy), (-ox, 0), (ox, 0)] if angle == 0 else [(-ox, 0), (ox, 0)]
                near += [(sx * ox, sy * oy) for sx in (-1, 1) for sy in (-1, 1)]
                near += [(sx * pcbnew.FromMM(d), sy * oy) for d in (1, 2, 3) for sx in (-1, 1) for sy in (-1, 1)]
                near += [(sx * ox, sy * pcbnew.FromMM(d)) for d in (1, 2, 3) for sx in (-1, 1) for sy in (-1, 1)]
                for dx, dy in near:
                    yield angle, dx, dy

        for angle, dx, dy in spots():
            ref.SetTextAngleDegrees(angle)
            ref.SetPosition(pcbnew.VECTOR2I(c.x + dx, c.y + dy))
            b = ref.GetBoundingBox()
            if (area.Contains(b.GetOrigin()) and area.Contains(b.GetEnd())
                    and not any(b.Intersects(o) for o in pads + texts[layer])
                    and not any(b.Intersects(v) for v in bodies[layer].values())
                    and owner(b, layer) == fp.GetReference()):
                break
        else:
            print(f"{fp.GetReference()}: no clear spot for its label; hidden", file=sys.stderr)
            ref.SetVisible(False)
            continue
        texts[layer].append(grow(ref.GetBoundingBox(), 0.1))


def write_project(name, path):
    """Design rules sized for a 2-layer JLCPCB/PCBWay order, and a wider class for supply nets."""
    import json
    pro = {
        "board": {"design_settings": {
            "defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.2, "copper_text_size_h": 1.5,
                         "silk_line_width": 0.15, "silk_text_size_h": 1.0, "silk_text_size_v": 1.0},
            "rules": {"min_clearance": 0.2, "min_track_width": 0.2, "min_via_diameter": 0.6,
                      "min_through_hole_diameter": 0.2, "min_copper_edge_clearance": 0.3,
                      "min_hole_to_hole": 0.25, "min_hole_clearance": 0.25, "min_silk_clearance": 0.0},
            "rule_severities": {"silk_overlap": "ignore", "silk_over_copper": "ignore",
                                "silk_edge_clearance": "ignore", "lib_footprint_mismatch": "ignore",
                                "lib_footprint_issues": "ignore", "text_height": "ignore",
                                "courtyards_overlap": "error"},
            "track_widths": [0.0, 0.25, 0.5], "via_dimensions": [{"diameter": 0.0, "drill": 0.0},
                                                                   {"diameter": 0.6, "drill": 0.3}],
        }},
        "meta": {"filename": f"tune-button-{name}.kicad_pro", "version": 3},
        "net_settings": {
            "classes": [
                {"name": "Default", "clearance": 0.2, "track_width": 0.25, "via_diameter": 0.6, "via_drill": 0.3,
                 "diff_pair_width": 0.2, "diff_pair_gap": 0.25, "microvia_diameter": 0.3, "microvia_drill": 0.1,
                 "wire_width": 6, "bus_width": 12, "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)",
                 "schematic_color": "rgba(0, 0, 0, 0.000)", "priority": 2147483647},
                {"name": "Power", "clearance": 0.2, "track_width": 0.4, "via_diameter": 0.8, "via_drill": 0.4,
                 "diff_pair_width": 0.2, "diff_pair_gap": 0.25, "microvia_diameter": 0.3, "microvia_drill": 0.1,
                 "wire_width": 6, "bus_width": 12, "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)",
                 "schematic_color": "rgba(0, 0, 0, 0.000)", "priority": 0},
            ],
            "meta": {"version": 4},
            "netclass_patterns": [{"netclass": "Power", "pattern": n} for n in ["GND", "VBAT", "VBUS", "VSYS", "3V3"]],
        },
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [[uid(name, "root"), "Root"]],
    }
    open(path, "w").write(json.dumps(pro, indent=2) + "\n")
    # The only through-hole pads off the GND net are hand-soldered pins (switches, sockets, headers):
    # hold the pour as far from them as route.py holds other nets' tracks (PIN_GAP).
    open(path[:-len(".kicad_pro")] + ".kicad_dru", "w").write(
        '(version 1)\n(rule "hand-soldered pins to pour"\n  (constraint clearance (min 0.4mm))\n'
        '  (condition "A.Pad_Type == \'Through-hole\' && B.Type == \'Zone\'"))\n')


def main(names):
    for name in names:
        parts, h, keepouts, silk, extras = VARIANTS[name]()
        d = os.path.join(HERE, name)
        os.makedirs(d, exist_ok=True)
        base = os.path.join(d, f"tune-button-{name}")
        write_project(name, base + ".kicad_pro")
        root = write_schematic(name, parts, base + ".kicad_sch")
        write_board(name, parts, h, keepouts, silk, extras, base + ".kicad_pcb", root)
        write_project(name, base + ".kicad_pro")  # Save() may have rewritten it
        print(f"{name}: {extras.get('width', W):.1f} x {h:.1f} mm, {len(parts)} footprints")


if __name__ == "__main__":
    main(sys.argv[1:] or list(VARIANTS))
