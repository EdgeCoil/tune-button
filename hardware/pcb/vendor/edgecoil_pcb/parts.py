# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""The part model, the common footprints and JLCPCB's Basic-part numbers for passives."""


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
MIN_DRILL = 0.3  # JLC standard; smaller holes cost extra
LED0603 = "LED_SMD:LED_0603_1608Metric"
LED0805 = "LED_SMD:LED_0805_2012Metric"


# JLCPCB "Basic" parts for the passives and LED: Basic parts carry no per-type assembly fee.
LCSC_R0603 = {"1": "C22936", "100": "C22775", "27k": "C22967", "330": "C23138", "1k": "C21190", "3.3k": "C22978", "4.7k": "C23162", "5.1k": "C23186", "10k": "C25804", "100k": "C25803",
              "220k": "C22961", "22k": "C31850", "330k": "C23137"}
LCSC_R1206 = {"1": "C17928"}
R0805 = "Resistor_SMD:R_0805_2012Metric"
LCSC_R0805 = {"33": "C17634", "47": "C17714"}
LCSC_C = {("100n", C0603): "C14663", ("4.7n", C0603): "C53987", ("1u", C0603): "C15849", ("4.7u", C0603): "C19666",
          ("22u", C0805): "C45783", ("10u", C0805): "C15850", ("10u", C0603): "C19702"}
LCSC_LED_RED = "C2286"


def R(ref, value, a, b, at, rot=0, fp=R0603):
    lcsc = {R1206: LCSC_R1206, R0805: LCSC_R0805}.get(fp, LCSC_R0603)[value]
    return Part(ref, "Device:R", fp, value, {"1": a, "2": b}, at, rot, lcsc=lcsc)


def C(ref, value, a, b, at, rot=0, fp=C0603):
    return Part(ref, "Device:C", fp, value, {"1": a, "2": b}, at, rot, lcsc=LCSC_C[(value, fp)])


def holes(points):
    return [Part(f"H{i + 1}", "", "MountingHole:MountingHole_2.2mm_M2", "M2", {}, pt) for i, pt in enumerate(points)]

