# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Check jlc.ROTATE/OFFSET against JLC's own footprints, pad by pad.

JLC places each part with the EasyEDA footprint of its LCSC number, not KiCad's. For every LCSC
part on the boards named, this fetches that footprint, places it where the CPL would (KiCad's
origin, plus jlc_place's offset and rotation), and checks every pad lands on the KiCad pad with
the same number:

    python3 -m edgecoil_pcb.jlc_verify board.kicad_pcb [...]     exit 1 on any mismatch

Needs network access to easyeda.com, which answers only a curl-like User-Agent. Footprints are
cached in $EASYEDA_CACHE (default ~/.cache/edgecoil-pcb/easyeda).
"""
import json
import math
import os
import re
import subprocess
import sys

import pcbnew

from .jlc import jlc_place

MIL10 = 0.254  # EasyEDA's footprint unit, in mm


def _easyeda(lcsc):
    cache = os.environ.get("EASYEDA_CACHE", os.path.expanduser("~/.cache/edgecoil-pcb/easyeda"))
    path = os.path.join(cache, f"{lcsc}.json")
    if not os.path.exists(path):
        os.makedirs(cache, exist_ok=True)
        raw = subprocess.run(["curl", "-sf", "-A", "curl/8", f"https://easyeda.com/api/products/{lcsc}/components"],
                             check=True, capture_output=True).stdout
        open(path, "wb").write(raw)
    return json.load(open(path))["result"]


def easyeda_pads(lcsc):
    """JLC's footprint for the part: package name and pad number -> [(x, y)] in mm, y up."""
    data = _easyeda(lcsc)["packageDetail"]["dataStr"]
    ox, oy = float(data["head"]["x"]), float(data["head"]["y"])
    pads = {}
    for s in data["shape"]:
        if s.startswith("PAD~"):
            f = s.split("~")
            # PAD~shape~x~y~w~h~layer~net~number~...; y down, origin at the head's x, y.
            x, y, num = (float(f[2]) - ox) * MIL10, (float(f[3]) - oy) * MIL10, f[8]
            pads.setdefault(num, []).append((x, -y))
    return data["head"]["c_para"].get("package", "?"), pads


def easyeda_pin_names(lcsc):
    """Pin number -> name from JLC's symbol (P~...^^...^^ entries; the name is the 5th field of the
    third part)."""
    names = {}
    for s in _easyeda(lcsc)["dataStr"]["shape"]:
        if s.startswith("P~"):
            parts = s.split("^^")
            num = parts[0].split("~")[3]
            names[num] = parts[3].split("~")[4] if len(parts) > 3 else ""
    return names


CATHODE, ANODE = {"K", "C", "CATHODE", "-"}, {"A", "ANODE", "+"}


def role(name):
    n = name.strip().upper()
    return "K" if n in CATHODE else "A" if n in ANODE else None


def kicad_pad_extent(fp):
    """Pad number -> (w, h) in the footprint's own frame."""
    out = {}
    for p in fp.Pads():
        w, h = p.GetSize(pcbnew.F_Cu).x / 1e6, p.GetSize(pcbnew.F_Cu).y / 1e6
        if round(p.GetFPRelativeOrientation().AsDegrees()) % 180 == 90:
            w, h = h, w
        out.setdefault(p.GetNumber(), []).append((w, h))
    return {n: (min(w for w, _ in v), min(h for _, h in v)) for n, v in out.items()}


def kicad_pads(fp):
    """The footprint's pads at rotation 0, about its origin, y up."""
    pos, rot = fp.GetPosition(), fp.GetOrientationDegrees()
    a = math.radians(rot)
    pads = {}
    for p in fp.Pads():
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH or not p.GetNumber():
            continue
        dx, dy = (p.GetPosition().x - pos.x) / 1e6, -(p.GetPosition().y - pos.y) / 1e6
        if fp.GetLayer() == pcbnew.B_Cu:
            dx = -dx
        # Undo the footprint's own rotation (KiCad's angles are counter-clockwise, y up).
        x, y = dx * math.cos(-a) - dy * math.sin(-a), dx * math.sin(-a) + dy * math.cos(-a)
        pads.setdefault(p.GetNumber(), []).append((x, y))
    return pads


def schematic_pin_names(sch_path):
    """Reference -> {pin number: name}, from the symbols embedded in a .kicad_sch."""
    if not os.path.exists(sch_path):
        return {}
    from .symbols import block
    text = open(sch_path).read()
    lib = {}
    i = text.find("(lib_symbols")
    libblk = block(text, i) if i >= 0 else ""
    for m in re.finditer(r'\n\t\t\(symbol "([^"]+)"', libblk):
        blk = block(libblk, m.start() + 3)
        lib[m.group(1)] = {pm.group(2): pm.group(1) for pm in
                           re.finditer(r'\(name "([^"]*)".*?\(number "([^"]*)"', blk, re.S)}
    refs = {}
    for m in re.finditer(r'\n\t\(symbol\n\t\t\(lib_id "([^"]+)"', text):
        blk = block(text, m.start() + 2)
        r = re.search(r'\(property "Reference" "([^"]+)"', blk)
        if r:
            refs[r.group(1)] = lib.get(m.group(1), {})
    return refs


GEOM = 0.35    # mm: pads of one part drawn by two libraries differ in size, so their centres too
CENTRE = 0.05  # mm: but the pattern must be centred where JLC's is, to this or 5 % of the smallest
               # pad along that axis if more (a 0.075 mm shift along a 3.5 mm connector pad is nothing)
WHOLE = 0.2    # mm, on an axis only the whole pattern can judge (see fit)


def fit(kpads, epads, x0, y0, rot, core=None):
    """How JLC's footprint at (x0, y0, rot) lies on KiCad's: worst pad distance either way, the
    centroid error, and for each KiCad pad the EasyEDA pad number it lands on."""
    a = math.radians(rot)
    placed = [(n, (x0 + x * math.cos(a) - y * math.sin(a), y0 + x * math.sin(a) + y * math.cos(a)))
              for n, v in epads.items() for x, y in v]
    kp = [(n, p) for n, v in kpads.items() for p in v]
    if not placed or not kp:
        return math.inf, math.inf, {}
    lands, worst = {}, 0.0
    for n, p in kp:
        d, en = min((math.dist(p, q), m) for m, q in placed)
        worst = max(worst, d)
        lands.setdefault(n, set()).add(en)
    for _, q in placed:
        worst = max(worst, min(math.dist(q, p) for _, p in kp))
    # The middle of the pattern's extent, not its centroid: a SOT-23's lone pad drawn longer in one
    # library would pull a centroid sideways though the part sits in the same place.
    # Centred on the pads both libraries number alike (`core`), where there are any: shell legs and
    # mounting tabs are drawn differently by each and say nothing about where the pins land.
    mid = lambda pts, i: (min(p[i] for _, p in pts) + max(p[i] for _, p in pts)) / 2
    allk, allp = kp, placed
    if core:
        kp = [(n, p) for n, p in kp if n in core]
        placed = [(m, q) for m, q in placed if any(n in core and (m == n or n in re.findall(r"[A-Z]+\d+", m))
                                                     for n in kpads)]
    # On an axis where the core pads all sit in one row (a SOT-223's three pins opposite its tab, a USB-C's
    # signal row), their middle says where each library put its pads, not where the part sits. There
    # the whole pattern decides, to the looser WHOLE (its mechanical pads differ between libraries:
    # the USB-C's shell legs by 0.15 mm). A negative error marks an axis judged that way.
    def axis(i):
        span = max(p[i] for _, p in kp) - min(p[i] for _, p in kp)
        if span > 0.5:
            return abs(mid(kp, i) - mid(placed, i))
        return -abs(mid(allk, i) - mid(allp, i))
    centre = (axis(0), axis(1))
    return worst, centre, lands


def merge_groups(kpads, epads):
    """A number drawn as several pads in one library and one in the other (an exposed pad with its
    thermal vias, say) is compared as the one pad: the group's middle."""
    def middle(v):
        return [((min(x for x, _ in v) + max(x for x, _ in v)) / 2, (min(y for _, y in v) + max(y for _, y in v)) / 2)]
    def cluster(v, one):  # all within 2 mm of the single pad: vias in a pad, not separate legs
        return all(math.dist(p, one[0]) <= 2.0 for p in v)
    k, e = dict(kpads), dict(epads)
    for n in set(k) & set(e):
        if len(k[n]) > 1 and len(e[n]) == 1 and cluster(k[n], e[n]):
            k[n] = middle(k[n])
        elif len(e[n]) > 1 and len(k[n]) == 1 and cluster(e[n], k[n]):
            e[n] = middle(e[n])
        elif len(k[n]) > 1 and len(e[n]) > 1 and cluster(k[n], middle(k[n])) and cluster(e[n], middle(e[n])):
            k[n], e[n] = middle(k[n]), middle(e[n])  # both draw vias in the pad, in different patterns
    return k, e


def judge(kpads, epads, enames, kicad_names, sizes, x0, y0, rot):
    """Problems and notes for JLC's footprint at (x0, y0, rot) on KiCad's."""
    worst, _, lands = fit(kpads, epads, x0, y0, rot)
    core = {n for n, es in lands.items() if es == {n} or all(n in re.findall(r"[A-Z]+\d+", e) for e in es)}
    _, centre, _ = fit(kpads, epads, x0, y0, rot, core)
    problems, notes = [], []
    if worst > GEOM:
        problems.append(f"pads {worst:.2f} mm apart")
    for axis, err in zip("xy", centre):
        dims = [sizes[n][axis == "y"] for n in (core or sizes) if n in sizes]
        tol = max(CENTRE, 0.05 * min(dims)) if dims else CENTRE
        if err < 0:
            err, tol = -err, WHOLE
        if err > tol:
            problems.append(f"centred {err:.3f} mm off in {axis} (allowed {tol:.3f})")
    for n, es in sorted(lands.items()):
        kr = role(kicad_names.get(n, ""))
        ers = {role(enames.get(e, "")) for e in es}
        # A role that disagrees is wrong whatever the numbers say (an LED turned round).
        if kr and ers and ers != {kr} and None not in ers:
            problems.append(f"pad {n} is {kr} but lands on EasyEDA's {'/'.join(sorted(ers))}")
            continue
        if es == {n}:
            continue
        kname = kicad_names.get(n, "").strip().upper()
        if all(n in re.findall(r"[A-Z]+\d+", e) for e in es):
            continue  # EasyEDA joins paired pins in one pad: A1B12 is A1 and B12
        if kr and ers == {kr}:
            notes.append(f"{n}->{'/'.join(sorted(es))} by role {kr}")
        elif kname and all(enames.get(e, "").strip().upper() == kname for e in es):
            notes.append(f"{n}->{'/'.join(sorted(es))} by name {kname}")
        elif len(kpads[n]) > 1 or any(len(epads.get(e, [])) > 1 for e in es) or len(es) > 1:
            notes.append(f"{n}->{'/'.join(sorted(es))} geometry only")
        else:
            problems.append(f"pad {n} ({kicad_names.get(n, '?')}) lands on EasyEDA {'/'.join(sorted(es))} "
                            f"({'/'.join(enames.get(e, '?') for e in sorted(es))})")
    return worst, centre, problems, notes


def check(lcsc, fp, kicad_names):
    package, epads = easyeda_pads(lcsc)
    enames = easyeda_pin_names(lcsc)
    kpads, epads = merge_groups(kicad_pads(fp), epads)
    sizes = kicad_pad_extent(fp)
    x0, y0, rot = jlc_place(lcsc, 0.0, 0.0, 0.0, fp.GetFPIDAsString().split(":")[-1])
    worst, centre, problems, notes = judge(kpads, epads, enames, kicad_names, sizes, x0, y0, rot)
    # Would another rotation pass as well? A symmetric part's would; an asymmetric one's shouldn't,
    # and if it does the table entry is a guess the geometry can't settle.
    alt = [r for r in (0, 90, 180, 270) if (r - rot) % 360
           and not judge(kpads, epads, enames, kicad_names, sizes, x0, y0, r)[2]]
    if alt and not problems:
        notes.append(f"also passes at {alt}")
    return package, worst, tuple(abs(c) for c in centre), problems, notes


def main(paths):
    seen, bad = {}, 0
    for path in paths:
        board = pcbnew.LoadBoard(path)
        names = schematic_pin_names(path[:-len(".kicad_pcb")] + ".kicad_sch")
        for fp in board.GetFootprints():
            lcsc = fp.GetFieldText("LCSC") if fp.HasFieldByName("LCSC") else ""
            if lcsc and lcsc not in seen:
                seen[lcsc] = (fp, names.get(fp.GetReference(), {}))
    for lcsc, (fp, names) in sorted(seen.items()):
        package, worst, centre, problems, notes = check(lcsc, fp, names)
        x0, y0, rot = jlc_place(lcsc, 0.0, 0.0, 0.0, fp.GetFPIDAsString().split(":")[-1])
        bad += bool(problems)
        print(f"{'BAD' if problems else 'ok '} {lcsc:>10} rot {rot:>3.0f} off ({x0:.3f},{y0:.3f}) {fp.GetReference():>4} "
              f"{fp.GetFPIDAsString().split(':')[1][:34]:34} [{package[:30]}] pads {worst:.2f} centre {max(centre):.3f}"
              + (f"  {'; '.join(problems)}" if problems else "") + (f"  ({'; '.join(notes)})" if notes else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
