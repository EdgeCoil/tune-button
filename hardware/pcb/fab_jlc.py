# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""JLCPCB assembly files from KiCad's BOM and position exports: only parts with an LCSC number
(the ones JLC fits), in the column names JLC's upload expects.

    python3 fab_jlc.py <kicad-bom.csv> <kicad-pos.csv> <out-bom.csv> <out-cpl.csv>

panel.py imports jlc_place for the panel's placement file.
"""
import csv
import math
import sys

# Where JLC's own footprint for a part differs from KiCad's, checked against the EasyEDA footprint
# for each LCSC number: degrees to add to KiCad's rotation, and the offset (mm, part's own frame,
# y up) from KiCad's origin to JLC's.
ROTATE = {"C841192": 270, "C15127": 180, "C85364": 180, "C32574": 270,  # RT9080, AO3401A, SRV05-4, TP4054
          "C265453": 180,  # JST S7B-PH-SM4-TB: JLC draws it pins-down
          "C2932672": 270, "C492401": 270}  # 1x7 socket, 1x2 header: JLC draws them across, not down
# KiCad's pin headers and sockets have their origin on pin 1; JLC's are centred.
OFFSET = {"C165948": (0.0, 1.571),  # HRO TYPE-C-31-M-12: JLC's origin is towards the pads
          "C2932672": (0.0, -7.62), "C492401": (0.0, -1.27)}

def jlc_place(lcsc, x, y, rot):
    """A part's KiCad position and rotation, moved to JLC's footprint origin and rotation."""
    ox, oy = OFFSET.get(lcsc, (0.0, 0.0))
    a = math.radians(rot)
    return x + ox * math.cos(a) - oy * math.sin(a), y + ox * math.sin(a) + oy * math.cos(a), (rot + ROTATE.get(lcsc, 0)) % 360


def main(bom_in, pos_in, bom_out, cpl_out):
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
                x, y, rot = jlc_place(lcsc, float(row["PosX"]), float(row["PosY"]), float(row["Rot"]))
                w.writerow([row["Ref"], f"{x:.6f}mm", f"{y:.6f}mm", row["Side"].capitalize(), f"{rot:.6f}"])

    # Every part JLC is asked to fit must have a placement, or it is silently left off.
    placed = {row["Ref"] for row in csv.DictReader(open(pos_in, newline=""))}
    missing = sorted(set(fitted) - placed)
    if missing:
        sys.exit(f"fab_jlc: no placement for {', '.join(missing)} (a designator range in the BOM?)")


if __name__ == "__main__":
    main(*sys.argv[1:5])
