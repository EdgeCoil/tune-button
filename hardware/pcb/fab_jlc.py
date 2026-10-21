# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""JLCPCB assembly files from KiCad's BOM and position exports: only parts with an LCSC number
(the ones JLC fits), in the column names JLC's upload expects.

    python3 fab_jlc.py <kicad-bom.csv> <kicad-pos.csv> <out-bom.csv> <out-cpl.csv>
"""
import csv
import math
import sys

# Where JLC's own footprint for a part differs from KiCad's, checked against the EasyEDA footprint
# for each LCSC number: degrees to add to KiCad's rotation, and the offset (mm, part's own frame,
# y up) from KiCad's origin to JLC's.
ROTATE = {"C39051": 180, "C15127": 180, "C85364": 180, "C32574": 270}  # MCP1700, AO3401A, SRV05-4, TP4054
OFFSET = {"C165948": (0.0, 1.571)}  # HRO TYPE-C-31-M-12: JLC's origin is towards the pads

bom_in, pos_in, bom_out, cpl_out = sys.argv[1:5]

fitted = {}
with open(bom_in, newline="") as f, open(bom_out, "w", newline="") as g:
    w = csv.writer(g)
    w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
    for row in csv.DictReader(f):
        if row["LCSC"]:
            w.writerow([row["Value"], row["Reference"], row["Footprint"].split(":")[-1], row["LCSC"]])
            fitted.update({r.strip(): row["LCSC"] for r in row["Reference"].split(",")})

with open(pos_in, newline="") as f, open(cpl_out, "w", newline="") as g:
    w = csv.writer(g)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for row in csv.DictReader(f):
        lcsc = fitted.get(row["Ref"])
        if lcsc:
            x, y, rot = float(row["PosX"]), float(row["PosY"]), float(row["Rot"])
            ox, oy = OFFSET.get(lcsc, (0.0, 0.0))
            a = math.radians(rot)
            x, y = x + ox * math.cos(a) - oy * math.sin(a), y + ox * math.sin(a) + oy * math.cos(a)
            w.writerow([row["Ref"], f"{x:.6f}mm", f"{y:.6f}mm", row["Side"].capitalize(),
                        f"{(rot + ROTATE.get(lcsc, 0)) % 360:.6f}"])
