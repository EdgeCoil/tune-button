# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""CI: the fab outputs exist, are plausibly sized, and every timestamp in them is UTC.

    python3 ci/check_outputs.py <fab dir> <board name> [min BOM rows] [min CPL rows]

A missing tool can make a step succeed while writing nothing useful, so exit codes alone are not
trusted here.
"""
import csv
import os
import re
import sys
import zipfile

fab, name = sys.argv[1], sys.argv[2]
min_bom = int(sys.argv[3]) if len(sys.argv) > 3 else 10
min_cpl = int(sys.argv[4]) if len(sys.argv) > 4 else 20
bad = []


def need(path, min_bytes):
    p = os.path.join(fab, path)
    if not os.path.exists(p):
        bad.append(f"missing {path}")
    elif os.path.getsize(p) < min_bytes:
        bad.append(f"{path} is only {os.path.getsize(p)} bytes (expected >= {min_bytes})")
    return p


z = need(f"{name}-gerbers.zip", 20_000)
if os.path.exists(os.path.join(fab, f"{name}-schematic.pdf")) or not name.endswith("-panel"):
    need(f"{name}-schematic.pdf", 20_000)
for f, min_rows in ((f"{name}-jlc-bom.csv", min_bom), (f"{name}-jlc-cpl.csv", min_cpl)):
    p = need(f, 200)
    if os.path.exists(p):
        rows = sum(1 for _ in csv.reader(open(p, newline="", encoding="utf-8-sig"))) - 1
        if rows < min_rows:
            bad.append(f"{f} has {rows} rows (expected >= {min_rows})")

if os.path.exists(z):
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        for layer in ("F_Cu", "B_Cu", "F_Mask", "B_Mask", "F_Silkscreen", "Edge_Cuts"):
            if not any(layer in n for n in names):
                bad.append(f"gerber zip has no {layer} layer")
        if not any(n.endswith(".drl") for n in names):
            bad.append("gerber zip has no drill file")
        stamps = 0
        for n in names:
            text = zf.read(n).decode("latin-1")
            for stamp in re.findall(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d([+-]\d\d:?\d\d|Z)?", text):
                stamps += 1
                if stamp not in ("", "Z", "+00:00", "+0000", "-00:00"):
                    bad.append(f"{n}: a timestamp carries offset {stamp}, not UTC")
        if stamps == 0:
            bad.append("no timestamps found in the gerbers: the UTC check checked nothing")

if bad:
    print("\n".join(f"check_outputs: {b}" for b in bad))
    sys.exit(1)
print(f"check_outputs: {name} fab outputs present, sized and UTC ({stamps} timestamps)")
