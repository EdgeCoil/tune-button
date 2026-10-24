# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""One JLC panel holding all three boards, for Standard PCBA (which wants at least 70 x 70 mm, and parts
2.5 mm from the edge the line holds). Built with KiKit from the committed, routed boards:

    xiao | c3 | c3-jst, side by side, in a 6 mm frame (rails left and right, bars top and bottom)

Mouse-bite tabs join neighbours and the rails, only where no track, via or pad comes within 1 mm of
the edge and no part reaches it (so a bite never tears copper), and the ground pour is held back
around each tab.
The frame carries four tooling holes and three fiducials. The panel BOM and placement file are written
here too, with fab_jlc.py's per-part corrections, every reference prefixed with its board.

    python3 panel.py      (after ./build.sh; needs KiKit 1.8.1 where KiCad's pcbnew module is visible,
                           e.g. python3 -m venv --system-site-packages v && v/bin/pip install kikit==1.8.1)
"""
import csv
import os
import shutil
import subprocess
import sys

import pcbnew
from kikit.annotations import TabAnnotation
from kikit.panelize import Origin, Panel
from kikit.panelize_ui_impl import polygonToSubstrate
from kikit.units import mm
from shapely.geometry import LineString, box
from shapely.ops import unary_union

from fab_jlc import jlc_place
from gen import set_stackup

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "panel")
GAP, RAIL, RAIL_GAP, FRAME_GAP = 2.0, 6.0, 2.0, 1.5  # mm: between boards, rail and bar width, rail to
                                                     # boards, bars to anything overhanging the boards
TAB, MIN_TAB, FILLET, EDGE_CLEAR = 3.0, 2.0, 1.0, 1.0  # tab widths and fillet; clear of copper by EDGE_CLEAR
# (name, designator prefix, y offset). c3-jst sits 7 mm down so its antenna, which overhangs its top
# edge by 6.35 mm, stays level with the other boards' tops.
BOARDS = [("xiao", "XIAO_", 1.5), ("c3", "C3_", 1.0), ("c3-jst", "JST_", 7.0)]


def source(name):
    return os.path.join(HERE, name, f"tune-button-{name}.kicad_pcb")


def free_spans(path, side):
    """Where along one straight edge of a board (left, right, top or bottom; mm along the edge, board
    coordinates) a tab may go: the edge minus wherever a track, via or pad comes within EDGE_CLEAR of
    it, a part body reaches it, or a mounting hole leaves less than 3 mm of board to it."""
    b = pcbnew.LoadBoard(path)
    across = side in ("top", "bottom")  # then u runs across the edge in y, v along it in x

    def uv(p):
        x, y = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
        return (y, x) if across else (x, y)

    def box_uv(bb):  # (u min, u max, v min, v max)
        lo, hi = uv(bb.GetOrigin()), uv(bb.GetEnd())
        return min(lo[0], hi[0]), max(lo[0], hi[0]), min(lo[1], hi[1]), max(lo[1], hi[1])

    edges = []
    for d in b.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts and d.GetShape() == pcbnew.SHAPE_T_SEGMENT:
            (ua, va), (ub, vb) = uv(d.GetStart()), uv(d.GetEnd())
            if abs(ua - ub) < 1e-6:
                edges.append((ua, sorted((va, vb))))
    u0, u1 = min(e[0] for e in edges), max(e[0] for e in edges)
    low = side in ("left", "top")
    spans = [vs for eu, vs in edges if abs(eu - (u0 if low else u1)) < 0.001]

    def near(u):  # how far inside the edge
        return u - u0 if low else u1 - u

    def near_box(bb):
        a, z, _, _ = box_uv(bb)
        return near(a if low else z)

    blocked = []
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            (pu, pv), r = uv(t.GetPosition()), pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2
            if near(pu) - r < EDGE_CLEAR:
                blocked.append((pv - r - 0.5, pv + r + 0.5))
            continue
        # A track, sampled along its length: a diagonal leaving the edge only blocks where it is close.
        (ua, va), (ub, vb) = uv(t.GetStart()), uv(t.GetEnd())
        half = pcbnew.ToMM(t.GetWidth()) / 2
        for k in range(101):
            pu, pv = ua + (ub - ua) * k / 100, va + (vb - va) * k / 100
            if near(pu) - half < EDGE_CLEAR:
                blocked.append((pv - half - 0.3, pv + half + 0.3))
    for p in b.GetPads():
        if near_box(p.GetBoundingBox()) < EDGE_CLEAR:
            _, _, a, z = box_uv(p.GetBoundingBox())
            blocked.append((a - 0.5, z + 0.5))
        # Mounting holes near the edge leave a thin web: a tab snapped beside one could crack into it.
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH and near_box(p.GetBoundingBox()) < 3.0:
            _, _, a, z = box_uv(p.GetBoundingBox())
            blocked.append((a - 2.0, z + 2.0))
    # Ceramic capacitors of 0805 and up crack when the board flexes, and snapping a tab flexes it: none
    # within 3 mm of a tab (c3-jst's C1 on VBUS, audit round 8).
    for fp in b.Footprints():
        if fp.GetReference().startswith("C") and any(k in fp.GetFPIDAsString() for k in ("0805", "1206", "1210")):
            box = pcbnew.BOX2I()
            for pd in fp.Pads():
                box.Merge(pd.GetBoundingBox())
            if near_box(box) < 3.0:
                _, _, a, z = box_uv(box)
                blocked.append((a - 3.0, z + 3.0))
    # Part bodies (their fab outline) where they reach or overhang the edge: the USB-C, the antenna.
    for fp in b.Footprints():
        body = pcbnew.BOX2I()
        for item in fp.GraphicalItems():
            if item.GetLayer() in (pcbnew.F_Fab, pcbnew.B_Fab):
                body.Merge(item.GetBoundingBox())
        if body.GetWidth() and near_box(body) < 0.2:
            _, _, a, z = box_uv(body)
            blocked.append((a - 1.0, z + 1.0))
    free = []
    for a, z in spans:
        pos = a
        for ba, bz in sorted(blocked):
            if bz <= pos or ba >= z:
                continue
            if ba > pos:
                free.append((pos, ba))
            pos = max(pos, bz)
        if pos < z:
            free.append((pos, z))
    return [(a, z) for a, z in free if z - a >= MIN_TAB + 2 * FILLET + 0.5]


def tab_positions(spans, lo, hi, count):
    """Up to `count` (centre, width) tabs, as near evenly spaced over lo..hi as the free spans allow.
    Every tab's corners are milled to FILLET (addMillFillets would round them anyway), and the bites
    run round those fillets, so a tab needs a span of its width plus both fillets; a short span takes
    a narrower tab, down to MIN_TAB."""
    picks = []
    for target in [lo + (hi - lo) * (i + 0.5) / count for i in range(count)]:
        best = None
        for a, z in spans:
            width = min(TAB, z - a - 2 * FILLET - 0.5)
            reach = width / 2 + FILLET + 0.25
            c = min(max(target, a + reach), z - reach)
            if best is None or abs(c - target) < abs(best[0] - target):
                best = (c, width)
        if best is not None and all(abs(best[0] - p) > TAB + 2 * FILLET + 1 for p, _ in picks):
            picks.append(best)
    return picks


def part_bodies(board):
    bodies = []
    for fp in board.Footprints():
        body = pcbnew.BOX2I()
        for item in fp.GraphicalItems():
            if item.GetLayer() in (pcbnew.F_Fab, pcbnew.B_Fab):
                body.Merge(item.GetBoundingBox())
        if body.GetWidth():
            bodies.append(body)
    return bodies


def main():
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "tune-button-panel.kicad_pcb")
    panel = Panel(path)
    ref = pcbnew.LoadBoard(source("c3"))
    panel.inheritDesignSettings(ref)
    panel.inheritProperties(ref)

    x = RAIL + RAIL_GAP
    placed = []
    for name, prefix, dy in BOARDS:
        edge = pcbnew.LoadBoard(source(name)).GetBoardEdgesBoundingBox()
        w, h = round(pcbnew.ToMM(edge.GetWidth()) - 0.1, 3), round(pcbnew.ToMM(edge.GetHeight()) - 0.1, 3)
        # Tolerance takes in what overhangs the outline: c3-jst's antenna, the USB-C faces.
        panel.appendBoard(source(name), pcbnew.VECTOR2I(int(x * mm), int(dy * mm)), origin=Origin.TopLeft,
                          tolerance=int(8 * mm), inheritDrc=not placed)
        # (KiKit refuses to merge several boards' rule files, so only the first is inherited; the
        # panel's .kicad_dru still lists gen.py's one rule once per board, prefixed, all the same.)
        placed.append((name, x, dy, w, h))
        x += w + GAP

    # The frame: rails left and right, and bars across the top and bottom joining them. The bars keep
    # FRAME_GAP from anything overhanging the boards (c3-jst's antenna, the USB-C faces), and more than
    # two fillets from every board edge, or the milling fillets would bridge the gap.
    minx, miny, maxx, maxy = panel.boardsBBox()
    rail, railspace = int(RAIL * mm), int(RAIL_GAP * mm)
    bodies = part_bodies(panel.board)
    clear = int((2 * FILLET + 0.5) * mm)
    top = min(miny - clear, min(bb.GetTop() for bb in bodies) - int(FRAME_GAP * mm))
    bottom = max(maxy + clear, max(bb.GetBottom() for bb in bodies) + int(FRAME_GAP * mm))
    left, right = minx - railspace - rail, maxx + railspace + rail

    # Tabs: on each side edge that faces a neighbour or a rail (at the same height on both sides of a
    # gap, where both edges are free), and on each top and bottom edge to the bars.
    def spans(name, side, offset):
        return [(a + offset, z + offset) for a, z in free_spans(source(name), side)]

    def overlap(s1, s2):
        return [(max(a, c), min(z, d)) for a, z in s1 for c, d in s2
                if min(z, d) - max(a, c) >= MIN_TAB + 2 * FILLET + 0.5]

    def count(length):
        return 3 if length > 40 else 2 if length > 20 else 1

    tabs = []  # (substrate index, x, y, direction into the board, width), mm
    for i, (name, bx, by, w, h) in enumerate(placed):
        if i == 0:
            tabs += [(i, bx, y, (1, 0), tw) for y, tw in tab_positions(spans(name, "left", by), by, by + h, count(h))]
        if i + 1 < len(placed):
            nname, nx, ny, nw, nh = placed[i + 1]
            lo, hi = max(by, ny), min(by + h, ny + nh)
            for y, tw in tab_positions(overlap(spans(name, "right", by), spans(nname, "left", ny)), lo, hi, count(hi - lo)):
                tabs += [(i, bx + w, y, (-1, 0), tw), (i + 1, nx, y, (1, 0), tw)]
        else:
            tabs += [(i, bx + w, y, (-1, 0), tw) for y, tw in tab_positions(spans(name, "right", by), by, by + h, count(h))]
        n = 1 if w < 40 else 2
        tabs += [(i, x, by, (0, 1), tw) for x, tw in tab_positions(spans(name, "top", bx), bx, bx + w, n)]
        tabs += [(i, x, by + h, (0, -1), tw) for x, tw in tab_positions(spans(name, "bottom", bx), bx, bx + w, n)]
    for name, *_ in placed:
        ends = sum(1 for i, *_ in tabs if placed[i][0] == name)
        if ends < 3:  # (c3-jst gets three: its right and top edges carry copper or the antenna)
            sys.exit(f"panel: only {ends} tabs on {name}")

    # Partition lines (a tab runs from its board to the line): between the boards and towards the
    # rails, from stand-ins for the rails; above and below, the bars' centre lines.
    ghosts = [polygonToSubstrate(box(minx - 2 * railspace - mm, top, minx - 2 * railspace, bottom)),
              polygonToSubstrate(box(maxx + 2 * railspace, top, maxx + 2 * railspace + mm, bottom))]
    panel.buildPartitionLineFromBB(ghosts)
    bars = [LineString([(left, y), (right, y)]) for y in (top - rail // 2, bottom + rail // 2)]
    for s in panel.substrates:
        s.partitionLine = unary_union([s.partitionLine] + bars)
    for i, tx, ty, (dx, dy), tw in tabs:
        # Hold the pour back where the bites go, 1 mm past the end bites, so no hole meets copper.
        along = tw / 2 + FILLET + 1
        if dx:
            area = box(min(tx, tx + 1.2 * dx) * mm, (ty - along) * mm, max(tx, tx + 1.2 * dx) * mm, (ty + along) * mm)
        else:
            area = box((tx - along) * mm, min(ty, ty + 1.2 * dy) * mm, (tx + along) * mm, max(ty, ty + 1.2 * dy) * mm)
        keepout = panel.addKeepout(area, noTracks=False, noVias=False, noCopper=True)
        keepout.SetDoNotAllowPads(False)
        keepout.SetDoNotAllowFootprints(False)  # the bites themselves are NPTH footprints
        panel.substrates[i].annotations.append(
            TabAnnotation(None, (int(tx * mm), int(ty * mm)), (dx, dy), int(tw * mm)))
    cuts = panel.buildTabsFromAnnotations(int(FILLET * mm))
    # JLC wants a tab 2 mm from a connector's pads; where no other edge is free (c3's J2 and c3-jst's J3
    # face theirs), the bites go 0.25 mm outside the board instead of inside, moving the break line
    # 0.5 mm further from the pads, and the README says to cut those tabs rather than snap them.
    pads = [p.GetBoundingBox() for fp in panel.board.Footprints() if fp.GetReference().startswith("J")
            for p in fp.Pads()]
    connector = unary_union([box(bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()) for bb in pads])
    near = [c for c in cuts if c.distance(connector) < 2.25 * mm]
    cuts = [c for c in cuts if c.distance(connector) >= 2.25 * mm]
    for c in near:
        x, y = c.centroid.x / mm, c.centroid.y / mm
        print(f"panel: tab at ({x:.1f}, {y:.1f}) is {c.distance(connector) / mm:.2f} mm from a connector pad: bites outside")
    for x0 in (left, right - rail):
        panel.appendSubstrate(box(x0, top - rail, x0 + rail, bottom + rail))
    for y0 in (top - rail, bottom):
        panel.appendSubstrate(box(left, y0, right, y0 + rail))
    panel.addMillFillets(int(FILLET * mm))
    # Each board must still come away at its tabs alone: material along its edge, beyond the tabs
    # and their fillets, means the milling has bridged a gap.
    # Each piece of material along a board's edge must lie at one of its tabs.
    whole = panel.boardSubstrate.substrates
    for i, (name, *_) in enumerate(placed):
        outline = panel.substrates[i].substrates
        ring = outline.buffer(0.3 * mm).difference(outline)
        allowed = unary_union([box((tx - (tw / 2 + FILLET + 0.5) * abs(dy) - 1.5 * abs(dx)) * mm,
                                   (ty - (tw / 2 + FILLET + 0.5) * abs(dx) - 1.5 * abs(dy)) * mm,
                                   (tx + (tw / 2 + FILLET + 0.5) * abs(dy) + 1.5 * abs(dx)) * mm,
                                   (ty + (tw / 2 + FILLET + 0.5) * abs(dx) + 1.5 * abs(dy)) * mm)
                               for j, tx, ty, (dx, dy), tw in tabs if j == i])
        stray = ring.intersection(whole).difference(allowed).area / (0.3 * mm) / mm
        if stray > 0.05:
            sys.exit(f"panel: {name} is joined to the panel along {stray:.1f} mm away from its tabs")
    # JLC's 1.152 mm tooling holes (0.148 mm mask expansion) in the frame corners, and three
    # fiducials 4.35 mm in from the rails' outer edges (JLC: the 2 mm opening 3.35 mm from the edge).
    panel.addCornerTooling(4, int(RAIL / 2 * mm), int(RAIL / 2 * mm), int(1.152 * mm),
                           solderMaskMargin=int(0.148 * mm))
    panel.addCornerFiducials(3, int(4.35 * mm), int(RAIL * mm + 4 * mm), int(1 * mm), int(2 * mm))
    # Bites along each tab's cut, fillets included, 0.25 mm into the board so the snapped edge is at
    # or inside the outline.
    # KiKit spreads int(length / spacing) + 1 holes evenly over each cut: 0.8 mm asked gives 0.80-0.83
    # mm here. Closer (JLC suggests 0.7-0.8) would leave webs under the 0.25 mm hole-to-hole rule.
    panel.makeMouseBites(cuts, int(0.5 * mm), int(0.8 * mm), int(0.25 * mm), 0)
    panel.makeMouseBites(near, int(0.5 * mm), int(0.8 * mm), int(-0.25 * mm), 0)
    panel.save(reconstructArcs=True)
    # Fill now, with the project's rules in place (gen.py's pour clearance to through-hole pins);
    # KiKit's own refill runs before it copies the rules across.
    board = pcbnew.LoadBoard(path)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    # JLC replaces only the order-number marker named in the order: keep the c3's, drop the others.
    c3 = next((bx, w) for name, bx, _, w, _ in placed if name == "c3")
    for d in [d for d in board.GetDrawings() if isinstance(d, pcbnew.PCB_TEXT) and d.GetText() == "JLCJLCJLCJLC"
              and not c3[0] <= pcbnew.ToMM(d.GetPosition().x) <= c3[0] + c3[1]]:
        board.Remove(d)
    board.Save(path)
    set_stackup(path)
    outline = board.GetBoardEdgesBoundingBox()
    print("panel:", ", ".join(f"{n} at ({bx:.1f}, {by:.1f})" for n, bx, by, *_ in placed),
          f"; {len(tabs)} tab ends; {pcbnew.ToMM(outline.GetWidth()):.1f} x {pcbnew.ToMM(outline.GetHeight()):.1f} mm")
    for i, (name, *_) in enumerate(placed):
        print(f"  {name}:", ", ".join(f"({tx:.1f}, {ty:.1f}) {tw:.1f} mm" for j, tx, ty, _, tw in tabs if j == i))
    export(path, placed)


def export(path, placed):
    """Gerbers, drills and JLC's BOM and placement files for the panel, into panel/fab."""
    fab = os.path.join(OUT, "fab")
    gerber = os.path.join(fab, "gerber")
    shutil.rmtree(fab, ignore_errors=True)  # nothing stale gets zipped
    os.makedirs(gerber)
    cli = ["kicad-cli", "pcb"]
    subprocess.run(cli + ["export", "gerbers", "--layers", "F.Cu,B.Cu,F.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts",
                          "--subtract-soldermask", "-o", gerber + "/", path], check=True, capture_output=True)
    subprocess.run(cli + ["export", "drill", "--format", "excellon", "--excellon-separate-th", "-o", gerber + "/", path],
                   check=True, capture_output=True)
    shutil.make_archive(os.path.join(fab, "tune-button-panel-gerbers"), "zip", gerber)
    # The panel keeps each board's references (so its silkscreen is the boards'); JLC needs unique
    # designators, so its files prefix each with the board it sits on.
    prefix = {name: p for name, p, _ in BOARDS}

    def owner(fp):
        x = pcbnew.ToMM(fp.GetPosition().x)
        return next(name for name, bx, _, w, _ in placed if bx - 0.5 <= x <= bx + w + 0.5)

    board = pcbnew.LoadBoard(path)
    fitted = {}
    for fp in board.Footprints():
        if fp.HasField("LCSC") and fp.GetFieldText("LCSC") and fp.GetLayer() == pcbnew.F_Cu:
            fitted[prefix[owner(fp)] + fp.GetReference()] = fp
    if len(fitted) != sum(1 for fp in board.Footprints() if fp.HasField("LCSC") and fp.GetFieldText("LCSC")
                          and fp.GetLayer() == pcbnew.F_Cu):
        sys.exit("panel: duplicate designators after prefixing")
    groups = {}
    for r, fp in sorted(fitted.items()):
        key = (fp.GetValue(), fp.GetFPID().GetLibItemName().wx_str(), fp.GetFieldText("LCSC"))
        groups.setdefault(key, []).append(r)
    with open(os.path.join(fab, "tune-button-panel-jlc-bom.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, footprint, lcsc), refs in sorted(groups.items()):
            w.writerow([value, ",".join(refs), footprint, lcsc])
    # Positions as kicad-cli's front-side pos export gives them (y up), then fab_jlc's corrections.
    with open(os.path.join(fab, "tune-button-panel-jlc-cpl.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r, fp in sorted(fitted.items()):
            p = fp.GetPosition()
            x, y, rot = jlc_place(fp.GetFieldText("LCSC"), pcbnew.ToMM(p.x), -pcbnew.ToMM(p.y),
                                  fp.GetOrientationDegrees() % 360)
            w.writerow([r, f"{x:.6f}mm", f"{y:.6f}mm", "Top", f"{rot:.6f}"])
    print(f"panel: {len(fitted)} parts for JLC in {len(groups)} BOM lines; fab files in {os.path.relpath(fab, HERE)}")


if __name__ == "__main__":
    main()
