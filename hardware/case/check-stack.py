#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Clearance check for stack.scad, independent of its own geometry.

Every part's footprint comes from the KiCad board files in ../pcb (courtyard bounding boxes), not
from stack.scad. Each is given a height (HEIGHT below; the connector, switch and module heights
are datasheet figures or ESTIMATES, marked), turned into a box on the right side of the board, and
intersected with every acrylic layer in OpenSCAD. A non-empty intersection is a collision. The bare
board itself (its Edge.Cuts outline, less its mounting holes) is an obstacle too.

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
    ("PogoPin_YTC1P", 11.0),           # YTC1P-8535 at its working height (12 free); xiao rev B
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
    "c3-btn": ("c3", 46.0, -1, 9.6, 8.0),     # printed only: tune-button-printed.scad big_button
    "c3-raven": ("c3", 46.0, -1, 9.6, 8.0),   # printed only: big_button with raven (beak on the tower)
}
STACKED = ("xiao", "c3", "c3-jst")            # the variants stack.scad builds
# openscad -D arguments that select each printed variant in tune-button-printed.scad
PRINTED_DEFINES = {"c3-btn": ["-D", 'variant="c3"', "-D", "big_button=true"],
                   "c3-raven": ["-D", 'variant="c3"', "-D", "big_button=true", "-D", "raven=true"]}
BIG_BUTTON = ("c3-btn", "c3-raven")


def printed_echo(v, key):
    """Numbers the printed case echoes for the checker (ECHO: "<key> a b c ...")."""
    out = os.path.join(tempfile.gettempdir(), "p.echo")
    subprocess.run(["openscad", *PRINTED_DEFINES.get(v, ["-D", f'variant="{v}"']), "-D", 'piece="none"',
                    "-o", out, "tune-button-printed.scad"], cwd=HERE, capture_output=True)
    return [float(x) for x in re.search(r'ECHO: "' + key + r' ([^"]*)"', open(out).read()).group(1).split()]


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
        for g in blocks(fp, "fp_"):
            kind = re.match(r"\(fp_(\w+)", g).group(1)
            if kind not in ("line", "rect", "circle", "poly", "arc") or not re.search(r'\(layer "[FB]\.CrtYd"\)', g):
                continue
            pts = [(float(q.group(1)), float(q.group(2)))
                   for q in re.finditer(r"\((?:start|mid|end|center|xy) ([-\d.]+) ([-\d.]+)\)", g)]
            if kind == "circle":      # (center) (end): a point on the circle, not a corner
                (cx, cy), (ex, ey) = pts
                rr = math.hypot(ex - cx, ey - cy)
                pts = [(cx - rr, cy - rr), (cx + rr, cy + rr)]
            for lx, ly in pts:
                xs.append(x0 + lx * math.cos(r) + ly * math.sin(r))
                ys.append(y0 - lx * math.sin(r) + ly * math.cos(r))
        if xs:
            yield ref, name, side, [min(xs), min(ys), max(xs), max(ys)]


def board_outline(pcbdir, mirror):
    """The board's Edge.Cuts outline as one polygon, arcs sampled, in top-view coordinates."""
    s = open(os.path.join(PCB, pcbdir, f"tune-button-{pcbdir}.kicad_pcb")).read()
    segs = []
    for head in ("gr_line", "gr_arc"):
        for b in blocks(s, head + "\n"):
            if '(layer "Edge.Cuts")' not in b:
                continue
            pt = lambda k: tuple(map(float, re.search(r"\(" + k + r" ([-\d.]+) ([-\d.]+)\)", b).groups()))
            a, e = pt("start"), pt("end")
            if head == "gr_arc":
                m = pt("mid")
                # circle through a, m, e
                ax, ay, bx, by, cx, cy = *a, *m, *e
                d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
                ux = ((ax**2 + ay**2) * (by - cy) + (bx**2 + by**2) * (cy - ay) + (cx**2 + cy**2) * (ay - by)) / d
                uy = ((ax**2 + ay**2) * (cx - bx) + (bx**2 + by**2) * (ax - cx) + (cx**2 + cy**2) * (bx - ax)) / d
                rr = math.hypot(ax - ux, ay - uy)
                t0, tm, t1 = (math.atan2(q[1] - uy, q[0] - ux) for q in (a, m, e))
                # go from t0 to t1 through tm
                def norm(x):
                    return (x - t0) % (2 * math.pi)
                sweep = norm(t1) if norm(tm) < norm(t1) else norm(t1) - 2 * math.pi
                pts = [(ux + rr * math.cos(t0 + sweep * i / 12), uy + rr * math.sin(t0 + sweep * i / 12)) for i in range(13)]
            else:
                pts = [a, e]
            segs.append(pts)
    loop = segs.pop(0)
    close = lambda p, q: abs(p[0] - q[0]) < 1e-3 and abs(p[1] - q[1]) < 1e-3
    while segs:
        for i, g in enumerate(segs):
            if close(g[0], loop[-1]):
                loop += g[1:]
                break
            if close(g[-1], loop[-1]):
                loop += g[::-1][1:]
                break
        else:
            sys.exit(f"{pcbdir}: Edge.Cuts outline does not close")
        segs.pop(i)
    if not close(loop[0], loop[-1]):
        sys.exit(f"{pcbdir}: Edge.Cuts outline does not close")
    if mirror is not None:
        loop = [(mirror - x, y) for x, y in loop]
    holes = []
    for ref, name, side, r in parts(pcbdir):
        if "MountingHole" in name:
            cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
            holes.append((mirror - cx if mirror is not None else cx, cy))
    return loop[:-1], holes


def board_solid(variant):
    """OpenSCAD for the bare board: its outline, less its mounting holes, 0.02 inside each face."""
    pcbdir, mirror, fdir, key_z, bot_z = VARIANTS[variant]
    loop, holes = board_outline(pcbdir, mirror)
    poly = ", ".join(f"[{x:.4f}, {-y:.4f}]" for x, y in loop)
    hs = " ".join(f"translate([{x:.3f}, {-y:.3f}]) circle(d = 2.2, $fn = 24);" for x, y in holes)
    return (f"translate([0, 0, {bot_z + 0.02}]) linear_extrude(height = {1.6 - 0.04}) "
            f"difference() {{ polygon([{poly}]); {hs} }}")


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
        if variant in BIG_BUTTON and ref == "TP1":
            continue   # not fitted on this variant: wires go straight to its pads
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
    if variant in BIG_BUTTON:
        # the case's own figures, in the top view: mirror them back so add() can mirror them again
        cx, cy, top, depth, nut, body, panel, c0, c1, c2, c3 = printed_echo(variant, "BIGBUTTON")
        tv = lambda r: [mirror - r[2], r[1], mirror - r[0], r[3]]
        add("cell 502535", tv([c0 + 0.5, c1 + 0.5, c2 - 0.5, c3 - 0.5]), 2.05, 7.0)
        add("J2 plug", [44.0, 39.5, 50.5, 47.5], bot_z - 0.05, bot_z - 4.6)
        roof = top - panel
        # Round parts, at any rotation (the nut is a hex, its 28.5 across the corners), as two
        # crossed boxes: together they cover the circle, and leave out most of a square's corners.
        def round_part(name, d, z0, z1):
            r, k = d / 2, d / 2 * 0.7072
            add(name, tv([cx - r, cy - k, cx + r, cy + k]), z0, z1)
            add(name, tv([cx - k, cy - r, cx + k, cy + r]), z0, z1)
        round_part("button body", body, top - depth, roof - 0.05)
        round_part("button nut", nut, roof - 4, roof - 0.05)
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


def cube(b):
    return (f"translate([{b[1][0]}, {-b[1][3]}, {b[2]}]) "
            f"cube([{b[1][2] - b[1][0]}, {b[1][3] - b[1][1]}, {b[3] - b[2]}]);")


def nonempty(inc, body, defines):
    """True if the OpenSCAD geometry `body`, after including `inc`, has any volume."""
    with tempfile.NamedTemporaryFile("w", suffix=".scad", delete=False) as f:
        f.write(f"include <{os.path.join(HERE, inc)}>\n{body}\n")
    r = subprocess.run(["openscad", *defines, "-o", f.name[:-5] + ".stl", f.name], capture_output=True, text=True)
    err = r.stderr.lower()
    if "top level object is empty" in err:
        return False
    if r.returncode != 0:
        sys.exit(f"openscad failed on {f.name}:\n{r.stderr[-800:]}")
    return True


def main():
    # extra -D overrides for mutation tests, e.g.: python3 check-stack.py mx_hole=12
    extra = [a for kv in sys.argv[1:] for a in ("-D", kv)]
    failed = 0
    only = os.environ.get("CHECK_ONLY")   # e.g. CHECK_ONLY=c3-btn: one variant
    for v in VARIANTS:
        if only and v != only:
            continue
        bs = boxes(v)
        board = board_solid(v)
        obstacles = [(b[0], cube(b), b[2], b[3]) for b in bs] + [("the board", board, VARIANTS[v][4], VARIANTS[v][4] + 1.6)]
        if v not in STACKED:
            print(f"{v}: printed only")
            failed += check_printed(v, obstacles, extra)
            continue
        sd = ["-D", f'variant="{v}"', "-D", 'part="none"', "-D", "kerf=0", *extra]
        subprocess.run(["openscad", "-D", f'variant="{v}"', "-D", 'part="none"', "-o",
                        os.path.join(tempfile.gettempdir(), "l.echo"), "stack.scad"],
                       cwd=HERE, capture_output=True)
        echo = open(os.path.join(tempfile.gettempdir(), "l.echo")).read()
        layers = re.search(r'ECHO: "LAYERS (.*)"', echo).group(1).split()
        for i, kind in enumerate(layers):
            z0, z1 = 3.0 * i, 3.0 * i + 3.0
            hits = [o for o in obstacles if o[3] > z0 + 0.01 and o[2] < z1 - 0.01]
            if not hits:
                continue
            lay = f"translate([0, 0, {z0}]) linear_extrude(height = 3) top_view() layer2d({i});"
            if not nonempty("stack.scad", f"intersection() {{ {lay}\nunion() {{ {' '.join(o[1] for o in hits)} }} }}", sd):
                continue
            for o in hits:   # find which ones collide
                if nonempty("stack.scad", f"intersection() {{ {lay}\n{o[1]} }}", sd):
                    failed += 1
                    print(f"COLLISION {v} L{i:02d} {kind}: {o[0]} z {o[2]:.1f}-{o[3]:.1f}")
        print(f"{v}: {len(obstacles)} parts and the board checked against {len(layers)} layers")
        if v in PRINTED:
            failed += check_printed(v, obstacles, extra)
    sys.exit(1 if failed else 0)


def volume(inc, body, defines):
    """The volume of the OpenSCAD geometry `body`, in mm^3 (0 if empty). Faces that only touch
    give a zero-thickness result, which has no volume."""
    with tempfile.NamedTemporaryFile("w", suffix=".scad", delete=False) as f:
        f.write(f"include <{os.path.join(HERE, inc)}>\n{body}\n")
    stl = f.name[:-5] + ".stl"
    r = subprocess.run(["openscad", *defines, "-o", stl, f.name], capture_output=True, text=True)
    if "top level object is empty" in r.stderr.lower():
        return 0.0
    if r.returncode != 0:
        sys.exit(f"openscad failed on {f.name}:\n{r.stderr[-800:]}")
    v = [tuple(map(float, m)) for m in re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", open(stl).read())]
    tot = 0.0
    for k in range(0, len(v), 3):
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = v[k:k + 3]
        tot += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)) / 6
    return abs(tot)


PRINTED = {   # variant: its printed parts, each in its assembled position
    "c3": [("base", "base();"), ("lid", "translate([0, 0, part_z]) lid();")],
    "xiao": [("base", "base();"), ("lid", "translate([0, 0, part_z]) lid();"), ("hood", "hood();")],
    "c3-btn": [("base", "base();"), ("lid", "translate([0, 0, part_z]) lid();"), ("tower", "tower();")],
    "c3-raven": [("base", "base();"), ("lid", "translate([0, 0, part_z]) lid();"), ("tower", "tower();")],
}


def check_printed(v, obstacles, extra):
    """A printed case: nothing may enter any part, no two parts may overlap, and the clamp must
    close: a spacer from below and a post or bracket from above at every mounting hole."""
    inc, failed = "tune-button-printed.scad", 0
    pd = [*PRINTED_DEFINES.get(v, ["-D", f'variant="{v}"']), "-D", 'piece="none"', *extra]
    parts_ = PRINTED[v]
    for label, expr in parts_:
        for o in obstacles:
            if nonempty(inc, f"intersection() {{ {expr}\n{o[1]} }}", pd):
                failed += 1
                print(f"COLLISION {v} printed {label}: {o[0]} z {o[2]:.1f}-{o[3]:.1f}")
    for a in range(len(parts_)):
        for b in range(a + 1, len(parts_)):
            vol = volume(inc, f"intersection() {{ {parts_[a][1]}\n{parts_[b][1]} }}", pd)
            if vol > 0.001:
                failed += 1
                print(f"COLLISION {v} printed: the {parts_[a][0]} and the {parts_[b][0]} overlap by {vol:.3f} mm^3")
    # The clamp: grow the board 0.05 mm up and down. At each mounting hole (from KiCad, not from
    # the case's own list) a spacer must reach it from below, and the parts above it from above.
    pcbdir, mirror, _, key_z, bot_z = VARIANTS[v]
    _, holes = board_outline(pcbdir, mirror)
    above = "union() { " + " ".join(e for l, e in parts_ if l != "base") + " }"
    for label, expr, z0 in (("spacer", "base();", bot_z - 0.05), ("post or bracket", above, key_z)):
        for hx, hy in holes:
            probe = (f"intersection() {{ {expr}\ntranslate([{hx:.3f}, {-hy:.3f}, {z0}]) "
                     f"difference() {{ cylinder(d = 4.2, h = 0.05); cylinder(d = 2.4, h = 1, center = true); }} }}")
            if not nonempty(inc, probe, pd):
                failed += 1
                print(f"NO CONTACT {v} printed: no {label} reaches the board at its hole ({hx:.1f}, {hy:.1f})")
    print(f"{v}: {len(obstacles)} parts and the board checked against the printed {', '.join(l for l, e in parts_)}; clamp checked")
    return failed


if __name__ == "__main__":
    main()
