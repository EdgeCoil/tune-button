# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""One JLC panel holding all three boards, for Standard PCBA (which wants at least 70 x 70 mm, and parts
2.5 mm from the edge the line holds). Built with KiKit from the committed, routed boards:

    xiao | c3 | c3-jst, side by side, in a 5 mm frame (rails left and right, bars top and bottom)

Mouse-bite tabs join neighbours and the rails, only where no track, via or pad comes within 1 mm of
the edge and no part reaches it (so a bite never tears copper), and the ground pour is held back
around each tab.
The frame carries four tooling holes and three fiducials. The panel BOM and placement file are written
here too, with fab_jlc.py's per-part corrections, every reference prefixed with its board.

    python3 panel.py      (after ./build.sh; needs KiKit 1.8, pip install kikit)
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
from shapely.geometry import box

from fab_jlc import jlc_place
from gen import set_stackup

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "panel")
GAP, RAIL, RAIL_GAP, FRAME_GAP = 2.0, 5.0, 2.0, 1.5  # mm: between boards, rail and bar width, rail to
                                                     # boards, bars to anything overhanging the boards
TAB, MIN_TAB, FILLET, EDGE_CLEAR = 3.0, 2.0, 1.0, 1.0  # tab widths and fillet; clear of copper by EDGE_CLEAR
# (name, designator prefix, y offset). c3-jst sits 7 mm down so its antenna, which overhangs its top
# edge by 6.35 mm, stays level with the other boards' tops.
BOARDS = [("xiao", "XIAO_", 1.5), ("c3", "C3_", 1.0), ("c3-jst", "JST_", 7.0)]


def source(name):
    return os.path.join(HERE, name, f"tune-button-{name}.kicad_pcb")


def free_spans(path, side):
    """Where along a board's left or right edge (y, mm, board coordinates) a tab may go: the straight
    part of the edge, minus wherever a track, via or pad comes within EDGE_CLEAR of it, a part body
    reaches it, or a mounting hole leaves less than 3 mm of board to it."""
    b = pcbnew.LoadBoard(path)
    # The straight part of the vertical edge: the outermost vertical Edge.Cuts segments.
    vertical = [(pcbnew.ToMM(d.GetStart().x), sorted((pcbnew.ToMM(d.GetStart().y), pcbnew.ToMM(d.GetEnd().y))))
                for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts
                and d.GetShape() == pcbnew.SHAPE_T_SEGMENT and d.GetStart().x == d.GetEnd().x]
    x0, x1 = min(v[0] for v in vertical), max(v[0] for v in vertical)
    x = x0 if side == "left" else x1
    spans = [ys for vx, ys in vertical if abs(vx - x) < 0.001]
    def near(xr):  # how far inside the edge a point is
        return xr - x0 if side == "left" else x1 - xr

    blocked = []
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            p, r = t.GetPosition(), pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2
            if near(pcbnew.ToMM(p.x)) - r < EDGE_CLEAR:
                blocked.append((pcbnew.ToMM(p.y) - r - 0.5, pcbnew.ToMM(p.y) + r + 0.5))
            continue
        # A track, sampled along its length: a diagonal leaving the edge only blocks where it is close.
        (xa, ya), (xb, yb) = [(pcbnew.ToMM(v.x), pcbnew.ToMM(v.y)) for v in (t.GetStart(), t.GetEnd())]
        half = pcbnew.ToMM(t.GetWidth()) / 2
        for k in range(101):
            px, py = xa + (xb - xa) * k / 100, ya + (yb - ya) * k / 100
            if near(px) - half < EDGE_CLEAR:
                blocked.append((py - half - 0.3, py + half + 0.3))
    for p in b.GetPads():
        bb = p.GetBoundingBox()
        if near(pcbnew.ToMM(bb.GetLeft() if side == "left" else bb.GetRight())) < EDGE_CLEAR:
            blocked.append((pcbnew.ToMM(bb.GetTop()) - 0.5, pcbnew.ToMM(bb.GetBottom()) + 0.5))
    # Part bodies (their fab outline) only where they reach the edge itself.
    for fp in b.Footprints():
        body = pcbnew.BOX2I()
        for item in fp.GraphicalItems():
            if item.GetLayer() in (pcbnew.F_Fab, pcbnew.B_Fab):
                body.Merge(item.GetBoundingBox())
        if body.GetWidth() and near(pcbnew.ToMM(body.GetLeft() if side == "left" else body.GetRight())) < 0.2:
            blocked.append((pcbnew.ToMM(body.GetTop()) - 0.5, pcbnew.ToMM(body.GetBottom()) + 0.5))
    # Mounting holes near the edge leave a thin web: a tab snapped beside one could crack into it.
    for p in b.GetPads():
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            bb = p.GetBoundingBox()
            if near(pcbnew.ToMM(bb.GetLeft() if side == "left" else bb.GetRight())) < 3.0:
                blocked.append((pcbnew.ToMM(bb.GetTop()) - 2.0, pcbnew.ToMM(bb.GetBottom()) + 2.0))
    free = []
    for a, z in spans:
        cuts = sorted(blocked)
        pos = a
        for ba, bz in cuts:
            if bz <= pos or ba >= z:
                continue
            if ba > pos:
                free.append((pos, ba))
            pos = max(pos, bz)
        if pos < z:
            free.append((pos, z))
    return [(a, z) for a, z in free if z - a >= MIN_TAB + 0.5], x0, x1


def tab_positions(spans, lo, hi):
    """(centre, width) tabs, two on an edge up to 40 mm long and three on a longer one, as near evenly
    spaced over lo..hi as the free spans allow. A full tab is TAB wide with FILLET corners, which
    lengthen its cut, so it needs a span that long; in a shorter span the tab is narrower (down to
    MIN_TAB) and gets no fillets."""
    count = 3 if hi - lo > 40 else 2
    picks = []
    for target in [lo + (hi - lo) * (i + 0.5) / count for i in range(count)]:
        best = None
        for a, z in spans:
            full = z - a >= TAB + 2 * FILLET + 0.5
            width = TAB if full else min(TAB - 0.1, z - a - 0.5)
            reach = width / 2 + (FILLET if full else 0) + 0.25
            c = min(max(target, a + reach), z - reach)
            if best is None or abs(c - target) < abs(best[0] - target):
                best = (c, width)
        if best is not None and all(abs(best[0] - p) > TAB + 2 for p, _ in picks):
            picks.append(best)
    return picks


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

    # Tabs: on each vertical edge that faces a neighbour or a rail, at the same height on both sides
    # of a gap, where both edges are free.
    def spans(name, side, oy):
        return [(a + oy, z + oy) for a, z in free_spans(source(name), side)[0]]

    def overlap(s1, s2):
        return [(max(a, c), min(z, d)) for a, z in s1 for c, d in s2 if min(z, d) - max(a, c) >= MIN_TAB + 0.5]

    tabs = []  # (substrate index, x, y, direction, width), mm
    for i, (name, bx, by, w, h) in enumerate(placed):
        if i == 0:
            tabs += [(i, bx, y, (1, 0), tw) for y, tw in tab_positions(spans(name, "left", by), by, by + h)]
        if i + 1 < len(placed):
            nname, nx, ny, nw, nh = placed[i + 1]
            shared = overlap(spans(name, "right", by), spans(nname, "left", ny))
            for y, tw in tab_positions(shared, max(by, ny), min(by + h, ny + nh)):
                tabs += [(i, bx + w, y, (-1, 0), tw), (i + 1, nx, y, (1, 0), tw)]
        else:
            tabs += [(i, bx + w, y, (-1, 0), tw) for y, tw in tab_positions(spans(name, "right", by), by, by + h)]
    for name, *_ in placed:
        count = sum(1 for i, *_ in tabs if placed[i][0] == name)
        if count < 3:
            sys.exit(f"panel: only {count} tab ends on {name}")

    minx, miny, maxx, maxy = panel.boardsBBox()
    railspace = int(RAIL_GAP * mm)
    ghosts = [polygonToSubstrate(box(minx - 2 * railspace - mm, miny, minx - 2 * railspace, maxy)),
              polygonToSubstrate(box(maxx + 2 * railspace, miny, maxx + 2 * railspace + mm, maxy))]
    panel.buildPartitionLineFromBB(ghosts)
    for i, tx, ty, direction, tw in tabs:
        # Hold the pour back where the bites go, so no hole tears through copper.
        keepout = panel.addKeepout(box(min(tx, tx + 1.2 * direction[0]) * mm, (ty - tw / 2 - 2) * mm,
                                       max(tx, tx + 1.2 * direction[0]) * mm, (ty + tw / 2 + 2) * mm),
                                   noTracks=False, noVias=False, noCopper=True)
        keepout.SetDoNotAllowPads(False)
        keepout.SetDoNotAllowFootprints(False)  # the bites themselves are NPTH footprints
    # Full-width tabs get 1 mm fillets. A narrow tab gets none: a fillet lengthens the cut, and the
    # bites along it would reach the copper that made the tab narrow.
    cuts = []
    for narrow in (False, True):
        panel.clearTabsAnnotations()
        for i, tx, ty, direction, tw in tabs:
            if (tw < TAB) == narrow:
                panel.substrates[i].annotations.append(
                    TabAnnotation(None, (int(tx * mm), int(ty * mm)), direction, int(tw * mm)))
        cuts += panel.buildTabsFromAnnotations(0 if narrow else int(FILLET * mm))
    # A frame: the rails, and bars across the top and bottom joining them, clear of what overhangs
    # the boards (c3-jst's antenna, the USB-C faces), so the rails don't depend on the boards.
    rail = int(RAIL * mm)
    bodies = []
    for fp in panel.board.Footprints():
        body = pcbnew.BOX2I()
        for item in fp.GraphicalItems():
            if item.GetLayer() in (pcbnew.F_Fab, pcbnew.B_Fab):
                body.Merge(item.GetBoundingBox())
        if body.GetWidth():
            bodies.append(body)
    top = min(miny, min(bb.GetTop() for bb in bodies)) - int(FRAME_GAP * mm)
    bottom = max(maxy, max(bb.GetBottom() for bb in bodies)) + int(FRAME_GAP * mm)
    left, right = minx - railspace - rail, maxx + railspace + rail
    for x0 in (left, right - rail):
        panel.appendSubstrate(box(x0, top - rail, x0 + rail, bottom + rail))
    for y0 in (top - rail, bottom):
        panel.appendSubstrate(box(left, y0, right, y0 + rail))
    panel.addMillFillets(int(1 * mm))
    # JLC's 1.152 mm tooling holes (1.448 mm mask opening) in the frame corners, and three fiducials
    # 3.85 mm in from the rails' outer edges (JLC: the 2 mm opening 3.35 mm clear of the edge).
    panel.addCornerTooling(4, int(RAIL / 2 * mm), int(RAIL / 2 * mm), int(1.152 * mm),
                           solderMaskMargin=int(1.448 * mm))
    panel.addCornerFiducials(3, int(3.85 * mm), int(RAIL * mm + 4 * mm), int(1 * mm), int(2 * mm))
    # Bites only across the tab itself (no prolongation: c3-jst's K4 runs close to the edge beside
    # its narrow tab), set 0.25 mm into the board so the snapped edge is at or inside the outline.
    panel.makeMouseBites(cuts, int(0.5 * mm), int(0.8 * mm), int(0.25 * mm), 0)
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
