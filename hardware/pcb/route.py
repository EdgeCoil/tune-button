# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Route a generated board, then fill the ground pours.

    python3 route.py <variant>             replay <variant>/routing.json if there is one, else autoroute
    python3 route.py --reroute <variant>   autoroute with Freerouting even so
    python3 route.py --freeze <variant>    record the board's current copper in <variant>/routing.json

(FREEROUTING=path/to/freerouting.jar, JAVA=path/to/java; ROUTE_DEBUG=1 prints why each autoroute
attempt failed.) Freerouting lays the board out afresh on every run, so once a routing has passed
review it is frozen: later builds replay it, and a fix is a small edit to routing.json rather than
a new layout.
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
from collections import Counter

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
JAR = os.environ.get("FREEROUTING", os.path.expanduser("~/.local/opt/freerouting/freerouting-2.1.0.jar"))
JAVA = os.environ.get("JAVA", "java")


def stitch(board, pitch=3.0, via=0.6, drill=0.3):
    """GND vias on a grid wherever both layers' filled pour already surrounds the whole via, so
    each via touches nothing but ground and the two pours become one net."""
    gnd = board.FindNet("GND")
    def pours(margin):
        out = []
        for z in board.Zones():
            if z.GetNetname() != "GND":
                continue
            for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
                if z.IsOnLayer(layer) and z.HasFilledPolysForLayer(layer):
                    poly = pcbnew.SHAPE_POLY_SET(z.GetFilledPolysList(layer))
                    poly.Deflate(pcbnew.FromMM(via / 2 + margin), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,
                                 pcbnew.FromMM(0.01))
                    out.append(poly)
        return out
    fills = pours(0.25)
    if len(fills) < 2:
        return 0

    # Spacing to what is already drilled: vias by copper (a mask web between caps), pads by hole.
    holes = [(t.GetPosition(), t.GetWidth(pcbnew.F_Cu) / 2 + pcbnew.FromMM(via / 2 + 0.2))
             for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    holes += [(p.GetPosition(), max(p.GetDrillSize().x, p.GetDrillSize().y) / 2 + pcbnew.FromMM(drill / 2 + 0.35))
              for p in board.GetPads() if p.HasHole()]

    no_vias = [z for z in board.Zones() if z.GetIsRuleArea() and z.GetDoNotAllowVias()]
    # Keep clear of SMD pads' mask and paste openings, or solder wicks down the via.
    smd = [p.GetBoundingBox() for p in board.GetPads() if not p.HasHole() or p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
    smd += [p.GetBoundingBox() for p in board.GetPads() if p.HasHole() and p.GetDrillSize().x < pcbnew.FromMM(0.4)]
    for b in smd:
        b.Inflate(pcbnew.FromMM(via / 2 + 0.2))

    def clear(p):
        return (all((p - h).EuclideanNorm() >= r for h, r in holes)
                and not any(z.Outline().Collide(p, pcbnew.FromMM(via / 2)) for z in no_vias)
                and not any(b.Contains(p) for b in smd))

    def add(p):
        holes.append((p, pcbnew.FromMM(via + 0.2)))
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
    # Then vias in every island of either layer's pour that has fewer than two (through-hole GND pads
    # count), spread at least 2 mm apart, so no island hangs on a single via. An island that would
    # otherwise get none may take one anywhere the via fits inside both pours (the pour edge is
    # already a clearance away from other copper).
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    loose = pours(0.02)
    anchors = [v.GetPosition() for v in board.GetTracks() if v.GetClass() == "PCB_VIA" and v.GetNetname() == "GND"]
    anchors += [p.GetPosition() for p in board.GetPads() if p.GetNetname() == "GND" and p.HasHole()]
    fine, spread = pcbnew.FromMM(0.25), pcbnew.FromMM(2.0)
    for z in board.Zones():
        if z.GetNetname() != "GND":
            continue
        for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
            if not z.IsOnLayer(layer):
                continue
            raw = z.GetFilledPolysList(layer)
            for i in range(raw.OutlineCount()):
                ib = raw.Outline(i).BBox()
                while True:
                    have = [a for a in anchors if raw.Contains(a, i)]
                    if len(have) >= 2:
                        break
                    spot = None
                    for inside in ([fills, loose] if not have else [fills]):
                        spot = next((pcbnew.VECTOR2I(x, y) for x in range(ib.GetLeft(), ib.GetRight(), fine)
                                     for y in range(ib.GetTop(), ib.GetBottom(), fine)
                                     if raw.Contains(pcbnew.VECTOR2I(x, y), i)
                                     and all(f.Contains(pcbnew.VECTOR2I(x, y)) for f in inside)
                                     and clear(pcbnew.VECTOR2I(x, y))
                                     and all((pcbnew.VECTOR2I(x, y) - a).EuclideanNorm() >= spread for a in have)),
                                    None)
                        if spot is not None:
                            break
                    if spot is None:
                        break
                    vias.append(add(spot))
                    anchors.append(spot)
    return len(vias)


def prune(board):
    """Remove track stubs that end on nothing (Freerouting occasionally leaves one)."""
    removed = 0
    # Zero-length segments join nothing.
    for t in [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetStart() == t.GetEnd()]:
        board.Remove(t)
        removed += 1
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
    if os.environ.get("ROUTE_DEBUG"):
        kinds = Counter(v["type"] for k in ("violations", "unconnected_items", "schematic_parity") for v in data.get(k, []))
        print("  drc:", dict(kinds), file=sys.stderr)
    return dead, problems


def route_once(base, pristine):
    # Load under the real name, so the board picks up (and saves back) the project's design rules.
    shutil.copy(pristine, base + ".kicad_pcb")
    board = pcbnew.LoadBoard(base + ".kicad_pcb")
    fixed = [t for t in board.GetTracks() if t.IsLocked()]  # laid by gen.py; Freerouting keeps them
    for t in list(board.GetTracks()):
        if not t.IsLocked():
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
    lost = {(t.GetClass(), t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y) for t in fixed} - {
        (t.GetClass(), t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y) for t in board.GetTracks()}
    if lost:
        raise SystemExit(f"SES import dropped {len(lost)} locked tracks")
    for f in (dsn, ses):
        os.remove(f)
    prune(board)
    # Stitch with islands kept: a pocket of pour fenced in by tracks is otherwise removed before it
    # can get a via, and the stitcher only places vias where both layers already have pour.
    pours = [z for z in board.Zones() if not z.GetIsRuleArea()]
    for z in pours:
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    stitch(board)
    # Pour the fill drops (islands the stitcher couldn't reach) counts against the attempt, so an
    # attempt that fences off a pocket of the back plane isn't taken as clean; so do crowded pins.
    lost, crowded = lost_pour(board), crowded_pins(board)
    if os.environ.get("ROUTE_DEBUG"):
        print(f"  lost pour {lost:.1f} mm2, crowded pins {crowded or 'none'}", file=sys.stderr)
    lost = lost > LOST_POUR or bool(crowded)
    board.Save(base + ".kicad_pcb")
    # Freerouting can still leave a sliver that KiCad calls dangling; let KiCad's DRC name them.
    for _ in range(3):
        dead, problems = drc(base + ".kicad_pcb")
        if not dead:
            return problems + lost
        board = pcbnew.LoadBoard(base + ".kicad_pcb")
        for t in list(board.GetTracks()):
            if t.m_Uuid.AsString() in dead:
                board.Remove(t)
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        board.Save(base + ".kicad_pcb")
    return drc(base + ".kicad_pcb")[1] + lost


LOST_POUR = 5.0  # mm2 of back-plane ground the fill may drop before an attempt counts as a problem


PIN_GAP = 0.4  # mm from a hand-soldered pin to another net's copper
THREAD_GAP = 0.29  # mm for a track crossing between two neighbouring 2.54 mm header pins (0.295 at best)


def crowded_pins(board):
    """Hand-soldered through-hole pins (parts JLC doesn't fit: no LCSC number) with another net's
    copper close by, where a solder bridge could reach it under mask only. Checked on both layers
    for the switches, and on the solder side only for headers and sockets, whose body covers the
    other. A track crossing a header's row between two pins can't get further than 0.295 mm from
    them, so it is held to THREAD_GAP instead. The pour is held off them by the .kicad_dru rule
    that gen.py writes. (A keepout ring round the pins would do this up
    front, but Freerouting then can't reach them at all.) Returns the offending (ref, pin, net)."""
    out = []
    for fp in board.Footprints():
        if fp.HasFieldByName("LCSC") and fp.GetFieldText("LCSC"):
            continue
        pins = [p for p in fp.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
        if not pins:
            continue
        switch = fp.GetFPIDAsString().startswith("Button_Switch_Keyboard:")
        layers = (pcbnew.F_Cu, pcbnew.B_Cu) if switch else (pcbnew.B_Cu if fp.GetLayer() == pcbnew.F_Cu else pcbnew.F_Cu,)
        pitch = pcbnew.FromMM(2.6)
        for pad in pins:
            # Lines to the neighbouring pins: a track crossing one is threading the row.
            gaps = [pcbnew.SEG(pad.GetPosition(), q.GetPosition()) for q in pins
                    if q is not pad and not switch and (q.GetPosition() - pad.GetPosition()).EuclideanNorm() < pitch]
            for layer in layers:
                shape = pad.GetEffectiveShape(layer)
                for t in board.GetTracks():
                    if t.GetNetCode() == pad.GetNetCode() or not (t.GetClass() == "PCB_VIA" or t.GetLayer() == layer):
                        continue
                    if not shape.Collide(t.GetEffectiveShape(layer), pcbnew.FromMM(PIN_GAP)):
                        continue
                    if (t.GetClass() == "PCB_TRACK" and any(pcbnew.SEG(t.GetStart(), t.GetEnd()).Intersects(g) for g in gaps)
                            and not shape.Collide(t.GetEffectiveShape(layer), pcbnew.FromMM(THREAD_GAP))):
                        continue
                    out.append((fp.GetReference(), pad.GetNumber(), t.GetNetname()))
    return sorted(set(out))


def lost_pour(board):
    """mm2 of back-plane ground the fill drops as islands (pockets fenced off from every via)."""
    pours = [z for z in board.Zones() if not z.GetIsRuleArea()]
    for z in pours:
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    kept = back_pour(board)
    for z in pours:
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    return (kept - back_pour(board)) / 1e12


def back_pour(board):
    return sum(abs(z.GetFilledPolysList(pcbnew.B_Cu).Area()) for z in board.Zones()
               if not z.GetIsRuleArea() and z.GetNetname() == "GND" and z.IsOnLayer(pcbnew.B_Cu))


def dedupe(path):
    """Drop track segments that exactly repeat another (Freerouting sometimes leaves stacked copies),
    and ones under 0.02 mm long.
    Done on the saved file: removing tracks through pcbnew's Python bindings crashes it later."""
    src = open(path).read()
    seen = set()

    def keep(m):
        key = re.sub(r'\(uuid "[^"]*"\)', "", m.group(0))
        s, e = re.search(r"\(start ([^)]*)\)", key).group(1), re.search(r"\(end ([^)]*)\)", key).group(1)
        (sx, sy), (ex, ey) = (map(float, v.split()) for v in (s, e))
        if math.hypot(ex - sx, ey - sy) < 0.02:  # (near) zero length: joins nothing
            return ""
        key = re.sub(r"\((start|end) [^)]*\)", "", key) + "|".join(sorted((s, e)))
        if key in seen:
            return ""
        seen.add(key)
        return m.group(0)
    out = re.sub(r"\t\(segment\n(?:\t\t[^\n]*\n)*?\t\)\n", keep, src)
    if out != src:
        open(path, "w").write(out)


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
        dedupe(base + ".kicad_pcb")
    finally:
        for f in (pristine, best):
            if os.path.exists(f):
                os.remove(f)
    print(f"{name}: routed in {len(scores)} attempt(s); DRC problems per attempt {scores}")


def routing_file(name):
    return os.path.join(HERE, name, "routing.json")


def freeze(name):
    """Write the board's tracks and vias (stitching included) to routing.json, one per line so a
    change reads as a small diff. gen.py's locked copper is left out: gen.py lays that itself."""
    board = pcbnew.LoadBoard(os.path.join(HERE, name, f"tune-button-{name}.kicad_pcb"))
    items = []
    for t in board.GetTracks():
        if t.IsLocked():
            continue
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            items.append({"net": t.GetNetname(), "via": [p.x, p.y], "d": t.GetWidth(pcbnew.F_Cu),
                          "drill": t.GetDrillValue()})
        else:
            a, b = t.GetStart(), t.GetEnd()
            items.append({"net": t.GetNetname(), "layer": board.GetLayerName(t.GetLayer()),
                          "start": [a.x, a.y], "end": [b.x, b.y], "w": t.GetWidth()})
    items.sort(key=lambda i: (i["net"], "via" in i, json.dumps(i)))
    with open(routing_file(name), "w") as f:
        f.write("[\n" + ",\n".join(json.dumps(i) for i in items) + "\n]\n")
    print(f"{name}: froze {len(items)} tracks and vias in {os.path.relpath(routing_file(name), HERE)}")


def replay(name):
    """Lay the frozen copper on the freshly generated board and fill the pours."""
    path = os.path.join(HERE, name, f"tune-button-{name}.kicad_pcb")
    board = pcbnew.LoadBoard(path)
    for i in json.load(open(routing_file(name))):
        net = board.FindNet(i["net"])
        if "via" in i:
            t = pcbnew.PCB_VIA(board)
            t.SetPosition(pcbnew.VECTOR2I(*i["via"])); t.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            t.SetWidth(i["d"]); t.SetDrill(i["drill"])
        else:
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(*i["start"])); t.SetEnd(pcbnew.VECTOR2I(*i["end"]))
            t.SetLayer(board.GetLayerID(i["layer"])); t.SetWidth(i["w"])
        t.SetNet(net)
        board.Add(t)
    # The autoroute rejects attempts that break these; a hand edit has to meet them too.
    lost, crowded = lost_pour(board), crowded_pins(board)
    if lost > LOST_POUR or crowded:
        raise SystemExit(f"{name}: routing.json loses {lost:.1f} mm2 of back pour; pins crowded: {crowded or 'none'}")
    board.Save(path)
    print(f"{name}: replayed {os.path.relpath(routing_file(name), HERE)}")


if __name__ == "__main__":
    args = sys.argv[1:]
    mode = args.pop(0) if args and args[0].startswith("--") else None
    for n in args:
        if mode == "--freeze":
            freeze(n)
        elif mode is None and os.path.exists(routing_file(n)):
            replay(n)
        else:
            main(n)
