#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Clearance check for stack.scad, independent of its own geometry.

Every part's footprint comes from the KiCad board files in ../pcb (courtyard bounding boxes), not
from stack.scad. Each is given a height (HEIGHT below; the connector, switch and module heights
are datasheet figures or ESTIMATES, marked), turned into a box on the right side of the board, and
intersected with every acrylic layer in OpenSCAD. A non-empty intersection is a collision.

The mating plugs, cells, keycaps and arcade buttons are added as boxes too. Run from this
directory: python3 check-stack.py. Exits 1 on any collision.
"""
import math
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "..", "pcb")

# Part height above its side of the board, mm, by footprint name fragment.
HEIGHT = [
    ("SW_Cherry_MX", None),            # handled separately
    ("USB_C_Receptacle_HRO", 3.26),    # HRO TYPE-C-31-M-12 datasheet
    ("JST_PH_S7B-PH-SM4", 4.8),        # ESTIMATE: JST PH side-entry SMT
    ("JST_PH_S2B-PH-SM4", 4.8),        # ESTIMATE
    ("ESP32-C3-WROOM-02", 3.2),        # Espressif datasheet
    ("PinSocket_1x07", 8.5),           # C2932672, 8.5 mm socket (the XIAO stands on it)
    ("PinHeader_1x02", 8.5),           # 2.5 mm body + 6 mm pins
    ("SW_Push_1P1T_XKB_TS-1187A", 1.6),
    ("SOT-23", 1.2), ("SOD-323", 1.2), ("LED_0", 1.1), ("R_0", 0.6), ("R_1", 0.6), ("C_0", 1.0), ("C_1", 1.6), ("TestPoint", 0.1),
    ("MountingHole", 0.0),
]
MX_BELOW_PLATE = 5.0                   # Cherry MX: key face to plate top
TRIMMED_LEADS = 2.0                    # through-hole leads on the far side, after trimming

VARIANTS = {
    # name: (pcb dir, mirror x (board width) or None, side the F parts face (+1 up, -1 down),
    #        key face z, board bottom z)
    "xiao": ("xiao", None, +1, 16.0, 14.4),
    "c3": ("c3", 46.0, -1, 16.0, 14.4),
    "c3-jst": ("c3-jst", None, +1, 7.6, 6.0),
}


def blocks(s, head):
    out, i = [], 0
    while True:
        j = s.find("(" + head, i)
        if j < 0:
            return out
        d, k = 0, j
        while True:
            c = s[k]
            if c == "(":
                d += 1
            elif c == ")":
                d -= 1
                if d == 0:
                    break
            elif c == '"':
                k = s.find('"', k + 1)
            k += 1
        out.append(s[j:k + 1])
        i = k + 1


def parts(pcbdir):
    s = open(os.path.join(PCB, pcbdir, f"tune-button-{pcbdir}.kicad_pcb")).read()
    for fp in blocks(s, "footprint "):
        name = re.match(r'\(footprint "([^"]+)"', fp).group(1)
        side = re.search(r'\(layer "([^"]+)"\)', fp).group(1)[0]
        at = re.search(r"\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)", fp).groups()
        ref = re.search(r'\(property "Reference" "([^"]+)"', fp).group(1)
        x0, y0, r = float(at[0]), float(at[1]), math.radians(float(at[2] or 0))
        xs, ys = [], []
        for m in re.finditer(r"\(fp_(?:line|rect|circle|poly)\b(.*?)\(layer \"[FB]\.CrtYd\"\)", fp, re.S):
            for q in re.finditer(r"\((?:start|end|center|xy) ([-\d.]+) ([-\d.]+)\)", m.group(1)):
                lx, ly = float(q.group(1)), float(q.group(2))
                xs.append(x0 + lx * math.cos(r) + ly * math.sin(r))
                ys.append(y0 - lx * math.sin(r) + ly * math.cos(r))
        if xs:
            yield ref, name, side, [min(xs), min(ys), max(xs), max(ys)]


def boxes(variant):
    pcbdir, mirror, fdir, key_z, bot_z = VARIANTS[variant]
    top_z = bot_z + 1.6
    out = []

    def add(label, r, z0, z1):
        x0, y0, x1, y1 = r
        if mirror is not None:
            x0, x1 = mirror - x1, mirror - x0
        out.append((label, [x0, y0, x1, y1], min(z0, z1), max(z0, z1)))

    for ref, name, side, r in parts(pcbdir):
        up = (fdir if side == "F" else -fdir) > 0
        face, far = (top_z, bot_z) if up else (bot_z, top_z)
        sgn = 1 if up else -1
        if "SW_Cherry_MX" in name:
            cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
            add(ref + " housing", [cx - 6.9, cy - 6.9, cx + 6.9, cy + 6.9], face + 0.05, face + MX_BELOW_PLATE - 0.05)
            # keycap, from rest down to fully pressed: plate top + 2.5 .. + 13 (ESTIMATE, OEM R3)
            add(ref + " keycap", [cx - 9, cy - 9, cx + 9, cy + 9], face + MX_BELOW_PLATE + 2.5, face + MX_BELOW_PLATE + 13)
            add(ref + " leads", [cx - 6, cy - 6, cx + 6, cy + 6], far, far - sgn * TRIMMED_LEADS)
            continue
        if "ESP32-C3-WROOM-02" in name:
            # the courtyard includes Espressif's antenna keep-out (no copper or metal; acrylic is
            # neither). Check the module's body: 18 x 20 x 3.2, its bottom 0.5 inside the courtyard.
            cx = (r[0] + r[2]) / 2
            r = [cx - 9, r[3] - 0.5 - 20, cx + 9, r[3] - 0.5]
        h = next((hv for frag, hv in HEIGHT if frag in name), None)
        if h is None:
            sys.exit(f"no height for {ref} {name}")
        if h > 0:
            add(f"{ref} {name.split(':')[1][:24]}", r, face + sgn * 0.05, face + sgn * h)
        if "PinSocket" in name or "PinHeader" in name:
            add(ref + " leads", r, far, far - sgn * TRIMMED_LEADS)
        if "PinSocket_1x07" in name and ref == "J1":
            # the XIAO on its sockets: 21 x 17.8 PCB, 1.2 thick, its USB-C on top (3.3)
            add("XIAO", [23 - 8.9, 4.4 - 2.88 - 1.2, 23 + 8.9, 4.4 - 2.88 + 21], face + 8.5, face + 8.5 + 1.2 + 3.3)
    # cells, plugs and buttons: positions from the README's assembly notes, not from stack.scad
    if variant == "xiao":
        add("cell 503040", [8, 13.5, 38, 53.5], 3.5, 9.0)
        add("J3 plug", [-5.5, 9.5, 1.9, 16.5], top_z + 0.05, top_z + 4.6)
    if variant == "c3":
        add("cell 503040", [8, 22.5, 38, 62.5], 3.5, 9.0)   # symmetric about x = 23
        add("J2 plug", [44.0, 39.5, 50.5, 47.5], bot_z - 0.05, bot_z - 4.6)
    if variant == "c3-jst":
        add("cell 502030", [44.5, 19.1, 64.5, 49.1], 3.5, 9.0)
        add("J3 plug", [17.4, 49.6, 34.6, 55.5], top_z + 0.05, top_z + 4.6)
        add("J2 plug", [35.6, 30.5, 42.0, 37.7], top_z + 0.05, top_z + 4.6)
        for cx in (15.5, 49.5):
            for cy in (6.5, 40.5):
                add("arcade body", [cx - 12, cy - 12, cx + 12, cy + 12], 48 - 32, 48 - 0.05)
                add("arcade nut", [cx - 14.5, cy - 14.5, cx + 14.5, cy + 14.5], 48 - 4, 48 - 0.05)
    return out


def main():
    # extra -D overrides for mutation tests, e.g.: python3 check-stack.py mx_hole=12
    extra = [a for kv in sys.argv[1:] for a in ("-D", kv)]
    failed = 0
    for v in VARIANTS:
        bs = boxes(v)
        subprocess.run(["openscad", "-D", f'variant="{v}"', "-D", 'part="none"', "-o",
                        os.path.join(tempfile.gettempdir(), "l.echo"), "stack.scad"],
                       cwd=HERE, capture_output=True)
        echo = open(os.path.join(tempfile.gettempdir(), "l.echo")).read()
        layers = re.search(r'ECHO: "LAYERS (.*)"', echo).group(1).split()
        for i, kind in enumerate(layers):
            z0, z1 = 3.0 * i, 3.0 * i + 3.0
            hits = [b for b in bs if b[3] > z0 + 0.01 and b[2] < z1 - 0.01]
            if not hits:
                continue
            body = "\n".join(
                f"translate([{b[1][0]}, {-b[1][3]}, {b[2]}]) cube([{b[1][2] - b[1][0]}, {b[1][3] - b[1][1]}, {b[3] - b[2]}]);"
                for b in hits)
            src = (f'include <{os.path.join(HERE, "stack.scad")}>\n'
                   f"intersection() {{ translate([0, 0, {z0}]) linear_extrude(height = 3) top_view() layer2d({i});\n"
                   f"union() {{ {body} }} }}\n")
            with tempfile.NamedTemporaryFile("w", suffix=".scad", delete=False) as f:
                f.write(src)
            stl = f.name[:-5] + ".stl"
            r = subprocess.run(["openscad", "-D", f'variant="{v}"', "-D", 'part="none"', "-D", "kerf=0", *extra,
                                "-o", stl, f.name], capture_output=True, text=True)
            empty = "top level object is empty" in r.stderr.lower()
            if empty:
                continue
            # find which boxes collide, one by one
            for b in hits:
                one = (f'include <{os.path.join(HERE, "stack.scad")}>\n'
                       f"intersection() {{ translate([0, 0, {z0}]) linear_extrude(height = 3) top_view() layer2d({i});\n"
                       f"translate([{b[1][0]}, {-b[1][3]}, {b[2]}]) cube([{b[1][2] - b[1][0]}, {b[1][3] - b[1][1]}, {b[3] - b[2]}]); }}\n")
                with open(f.name, "w") as g:
                    g.write(one)
                r = subprocess.run(["openscad", "-D", f'variant="{v}"', "-D", 'part="none"', "-D", "kerf=0", *extra,
                                    "-o", stl, f.name], capture_output=True, text=True)
                if "top level object is empty" not in r.stderr.lower():
                    failed += 1
                    print(f"COLLISION {v} L{i:02d} {kind}: {b[0]} z {b[2]:.1f}-{b[3]:.1f}")
        print(f"{v}: {len(bs)} parts checked against {len(layers)} layers")
        if v == "c3":
            # the printed c3 case: base, and the top in its assembled position
            for label, expr in (("printed base", "base();"), ("printed top", "translate([0, 0, plate_z]) top();")):
                for b in bs:
                    one = (f'include <{os.path.join(HERE, "tune-button-c3-printed.scad")}>\n'
                           f"intersection() {{ {expr}\n"
                           f"translate([{b[1][0]}, {-b[1][3]}, {b[2]}]) cube([{b[1][2] - b[1][0]}, {b[1][3] - b[1][1]}, {b[3] - b[2]}]); }}\n")
                    with tempfile.NamedTemporaryFile("w", suffix=".scad", delete=False) as g:
                        g.write(one)
                    r = subprocess.run(["openscad", "-D", 'piece="none"', *extra, "-o", g.name[:-5] + ".stl", g.name],
                                       capture_output=True, text=True)
                    if "top level object is empty" not in r.stderr.lower():
                        failed += 1
                        print(f"COLLISION c3 {label}: {b[0]} z {b[2]:.1f}-{b[3]:.1f}")
            print(f"c3: {len(bs)} parts checked against the printed base and top")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
