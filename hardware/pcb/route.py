# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Autoroute a generated board with Freerouting, then fill the ground pours.

    python3 route.py <variant>     (FREEROUTING=path/to/freerouting.jar, JAVA=path/to/java)
"""
import json
import os
import shutil
import subprocess
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
JAR = os.environ.get("FREEROUTING", os.path.expanduser("~/.local/opt/freerouting/freerouting-2.1.0.jar"))
JAVA = os.environ.get("JAVA", "java")


def stitch(board, pitch=3.0, via=0.6, drill=0.3):
    """GND vias on a grid wherever both layers' filled pour already surrounds the whole via, so
    each via touches nothing but ground and the two pours become one net."""
    gnd = board.FindNet("GND")
    fills = []
    for z in board.Zones():
        if z.GetNetname() != "GND":
            continue
        for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
            if z.IsOnLayer(layer) and z.HasFilledPolysForLayer(layer):
                poly = pcbnew.SHAPE_POLY_SET(z.GetFilledPolysList(layer))
                poly.Deflate(pcbnew.FromMM(via / 2 + 0.25), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, pcbnew.FromMM(0.01))
                fills.append(poly)
    if len(fills) < 2:
        return 0

    holes = [(t.GetPosition(), t.GetDrill() / 2) for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    holes += [(p.GetPosition(), max(p.GetDrillSize().x, p.GetDrillSize().y) / 2) for p in board.GetPads() if p.HasHole()]
    gap = pcbnew.FromMM(drill / 2 + 0.35)

    no_vias = [z for z in board.Zones() if z.GetIsRuleArea() and z.GetDoNotAllowVias()]

    def clear(p):
        return (all((p - h).EuclideanNorm() >= r + gap for h, r in holes)
                and not any(z.Outline().Collide(p, pcbnew.FromMM(via / 2)) for z in no_vias))

    def add(p):
        holes.append((p, pcbnew.FromMM(drill / 2)))
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(p); v.SetWidth(pcbnew.FromMM(via)); v.SetDrill(pcbnew.FromMM(drill)); v.SetNet(gnd)
        board.Add(v)
        return v

    bb = board.GetBoardEdgesBoundingBox()
    step = pcbnew.FromMM(pitch)
    vias = [add(pcbnew.VECTOR2I(x, y))
            for x in range(bb.GetLeft() + step // 2, bb.GetRight(), step)
            for y in range(bb.GetTop() + step // 2, bb.GetBottom(), step)
            if all(f.Contains(pcbnew.VECTOR2I(x, y)) for f in fills) and clear(pcbnew.VECTOR2I(x, y))]
    # Then one via in every island of either layer's pour that the grid missed.
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    anchors = [v.GetPosition() for v in vias] + [p.GetPosition() for p in board.GetPads()
                                                  if p.GetNetname() == "GND" and p.HasHole()]
    fine = pcbnew.FromMM(0.25)
    for z in board.Zones():
        if z.GetNetname() != "GND":
            continue
        for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
            if not z.IsOnLayer(layer):
                continue
            raw = z.GetFilledPolysList(layer)
            for i in range(raw.OutlineCount()):
                if any(raw.Contains(a, i) for a in anchors):
                    continue
                ib = raw.Outline(i).BBox()
                spot = next((pcbnew.VECTOR2I(x, y) for x in range(ib.GetLeft(), ib.GetRight(), fine)
                             for y in range(ib.GetTop(), ib.GetBottom(), fine)
                             if raw.Contains(pcbnew.VECTOR2I(x, y), i)
                             and all(f.Contains(pcbnew.VECTOR2I(x, y)) for f in fills)
                             and clear(pcbnew.VECTOR2I(x, y))), None)
                if spot is not None:
                    vias.append(add(spot))
                    anchors.append(spot)
    return len(vias)


def prune(board):
    """Remove track stubs that end on nothing (Freerouting occasionally leaves one)."""
    removed = 0
    while True:
        tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
        ends = {}
        for t in tracks:
            for p in (t.GetStart(), t.GetEnd()):
                ends[(t.GetNetCode(), p.x, p.y)] = ends.get((t.GetNetCode(), p.x, p.y), 0) + 1
        vias = {(v.GetNetCode(), v.GetPosition().x, v.GetPosition().y) for v in board.GetTracks() if v.GetClass() == "PCB_VIA"}
        pads = list(board.GetPads())

        def anchored(t, p):
            k = (t.GetNetCode(), p.x, p.y)
            return ends[k] > 1 or k in vias or any(
                o is not t and o.GetNetCode() == t.GetNetCode() and o.GetLayer() == t.GetLayer() and o.HitTest(p)
                for o in tracks) or any(
                pd.GetNetCode() == t.GetNetCode() and pd.IsOnLayer(t.GetLayer()) and pd.HitTest(p) for pd in pads)
        dead = [t for t in tracks if not (anchored(t, t.GetStart()) and anchored(t, t.GetEnd()))]
        if not dead:
            return removed
        for t in dead:
            board.Remove(t)
        removed += len(dead)


def drc(pcb):
    """(dangling track uuids, number of problems) from KiCad's own DRC with schematic parity."""
    rpt = pcb + ".drc.json"
    subprocess.run(["kicad-cli", "pcb", "drc", "--schematic-parity", "--severity-all", "--format", "json",
                    "-o", rpt, pcb], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    data = json.load(open(rpt))
    os.remove(rpt)
    dead = {i["uuid"] for v in data.get("violations", []) if v["type"] == "track_dangling" for i in v["items"][:1]}
    problems = sum(len(data.get(k, [])) for k in ("violations", "unconnected_items", "schematic_parity"))
    return dead, problems


def route_once(base, pristine):
    # Load under the real name, so the board picks up (and saves back) the project's design rules.
    shutil.copy(pristine, base + ".kicad_pcb")
    board = pcbnew.LoadBoard(base + ".kicad_pcb")
    for t in list(board.GetTracks()):
        board.Remove(t)
    dsn, ses = base + ".dsn", base + ".ses"
    # Export without the top pour: Freerouting treats a pour as a solid plane, so top-side GND pads
    # would count as connected through it and get no via. With only the bottom plane, each one is
    # dropped through to it.
    top = [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetLayer() == pcbnew.F_Cu]
    for z in top:
        board.Remove(z)
    if not pcbnew.ExportSpecctraDSN(board, dsn):
        raise SystemExit("DSN export failed")
    for z in top:
        board.Add(z)
    subprocess.run([JAVA, "-jar", JAR, "-de", dsn, "-do", ses, "-mp", "100", "-mt", "1", "--gui.enabled=false"],
                   check=True, stdout=subprocess.DEVNULL)
    if not pcbnew.ImportSpecctraSES(board, ses):
        raise SystemExit("SES import failed")
    for f in (dsn, ses):
        os.remove(f)
    prune(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    stitch(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(base + ".kicad_pcb")
    # Freerouting can still leave a sliver that KiCad calls dangling; let KiCad's DRC name them.
    for _ in range(3):
        dead, problems = drc(base + ".kicad_pcb")
        if not dead:
            return problems
        board = pcbnew.LoadBoard(base + ".kicad_pcb")
        for t in list(board.GetTracks()):
            if t.m_Uuid.AsString() in dead:
                board.Remove(t)
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        board.Save(base + ".kicad_pcb")
    return drc(base + ".kicad_pcb")[1]


def main(name, attempts=8):
    """Freerouting's result varies from run to run, so route until KiCad finds nothing to complain
    about, keeping the best attempt if none is clean."""
    base = os.path.join(HERE, name, f"tune-button-{name}")
    pristine, best = base + "-unrouted.kicad_pcb", base + "-best.kicad_pcb"
    shutil.copy(base + ".kicad_pcb", pristine)
    scores = []
    try:
        for n in range(attempts):
            problems = route_once(base, pristine)
            scores.append(problems)
            if problems == min(scores):
                shutil.copy(base + ".kicad_pcb", best)
            if problems == 0:
                break
        shutil.copy(best, base + ".kicad_pcb")
    finally:
        for f in (pristine, best):
            if os.path.exists(f):
                os.remove(f)
    print(f"{name}: routed in {len(scores)} attempt(s); DRC problems per attempt {scores}")


if __name__ == "__main__":
    for n in sys.argv[1:]:
        main(n)
