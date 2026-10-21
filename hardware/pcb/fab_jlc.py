# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""JLCPCB assembly files from KiCad's BOM and position exports: only parts with an LCSC number
(the ones JLC fits), in the column names JLC's upload expects.

    python3 fab_jlc.py <kicad-bom.csv> <kicad-pos.csv> <out-bom.csv> <out-cpl.csv>
"""
import csv
import sys

bom_in, pos_in, bom_out, cpl_out = sys.argv[1:5]

fitted = set()
with open(bom_in, newline="") as f, open(bom_out, "w", newline="") as g:
    w = csv.writer(g)
    w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
    for row in csv.DictReader(f):
        if row["LCSC"]:
            w.writerow([row["Value"], row["Reference"], row["Footprint"].split(":")[-1], row["LCSC"]])
            fitted.update(r.strip() for r in row["Reference"].split(","))

with open(pos_in, newline="") as f, open(cpl_out, "w", newline="") as g:
    w = csv.writer(g)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for row in csv.DictReader(f):
        if row["Ref"] in fitted:
            w.writerow([row["Ref"], f'{row["PosX"]}mm', f'{row["PosY"]}mm', row["Side"].capitalize(), row["Rot"]])
