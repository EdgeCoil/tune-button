# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""JLCPCB assembly files from KiCad's BOM and position exports: only parts with an LCSC number
(the ones JLC fits), in the column names JLC's upload expects.

    python3 -m edgecoil_pcb.jlc <kicad-bom.csv> <kicad-pos.csv> <out-bom.csv> <out-cpl.csv>

A panel script imports jlc_place for the panel's placement file. Every ROTATE/OFFSET entry is
checked against JLC's own footprint by `python3 -m edgecoil_pcb.jlc_verify`; PROVENANCE says how
each was last checked, and the build warns about any part placed on an unchecked entry.
"""
import csv
import math
import sys

# Where JLC's own footprint for a part differs from KiCad's, checked against the EasyEDA footprint
# for each LCSC number: degrees to add to KiCad's rotation, and the offset (mm, part's own frame,
# y up) from KiCad's origin to JLC's.
ROTATE = {"C841192": 270, "C15127": 180, "C85364": 180, "C32574": 270,  # RT9080, AO3401A, SRV05-4, TP4054
          "C124691": 180,  # TPD4E1U06 (SOT-23-6 like the SRV05-4: verify pad by pad)
          "C265453": 180,  # JST S7B-PH-SM4-TB: JLC draws it pins-down
          "C82045": 180, "C20917": 180, "C37704": 180, "C109309": 180,  # BSS138, AO3400A, BAT54C, BAV170: pins 1-2 on +x in EasyEDA
          "C2932672": 270, "C492401": 270}  # 1x7 socket, 1x2 header: JLC draws them across, not down
# KiCad's pin headers and sockets have their origin on pin 1; JLC's are centred.
OFFSET = {"C165948": (0.0, 1.571),  # HRO TYPE-C-31-M-12: JLC's origin is towards the pads
          "C2932672": (0.0, -7.62), "C492401": (0.0, -1.27)}

# How each part's placement was last checked. jlc_verify places JLC's own EasyEDA footprint by the
# table above and checks every pad lands on KiCad's (by number, or by anode/cathode where the two
# libraries number them differently), centred, and that no other rotation would pass too. It caught
# all nine of a set of planted errors (a dropped +180, an LED turned round, a 0.27 mm offset...).
# A part not listed here gets a warning from main(); run jlc_verify on the board and add it.
V = "jlc_verify 2026-10-30"
PROVENANCE = {
    "C109309": V, "C124691": V, "C128401": V, "C138388": V, "C14663": V, "C15127": V, "C15849": V, "C15850": V,
    "C165948": V, "C17714": V, "C17928": V, "C191023": V, "C19666": V, "C19702": V, "C20917": V, "C21190": V,
    "C2128": V, "C22466173": V, "C22775": V, "C2286": V, "C22961": V, "C22967": V, "C22978": V, "C23137": V,
    "C23138": V, "C23162": V, "C23186": V, "C25803": V, "C25804": V, "C265453": V, "C2932672": V, "C2934560": V,
    "C295747": V, "C318884": V, "C32574": V, "C435835": V, "C45783": V, "C492401": V, "C82045": V, "C841192": V,
    "C84256": V, "C85364": V, "C91447": V,
}


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

    unchecked = sorted(set(fitted.values()) - set(PROVENANCE))
    if unchecked:
        print(f"jlc: placement not checked against JLC's footprint for {', '.join(unchecked)}: "
              "run python3 -m edgecoil_pcb.jlc_verify on the board", file=sys.stderr)
    # Every part JLC is asked to fit must have a placement, or it is silently left off.
    placed = {row["Ref"] for row in csv.DictReader(open(pos_in, newline=""))}
    missing = sorted(set(fitted) - placed)
    if missing:
        sys.exit(f"fab_jlc: no placement for {', '.join(missing)} (a designator range in the BOM?)")


if __name__ == "__main__":
    main(*sys.argv[1:5])
