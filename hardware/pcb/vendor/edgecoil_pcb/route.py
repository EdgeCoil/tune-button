# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Route a generated board, then fill the ground pours.

    python3 route.py <variant>             replay <variant>/routing.json if there is one, else autoroute
    python3 route.py --reroute <variant>   autoroute with Freerouting even so
    python3 route.py --freeze <variant>    record the board's current copper in <variant>/routing.json
    python3 route.py --patch <variant>     replay all but ROUTE_RIP and autoroute only what that leaves

(FREEROUTING=path/to/freerouting.jar, JAVA=path/to/java; ROUTE_DEBUG=1 prints why each autoroute
attempt failed. ROUTE_RIP, for --patch: "NET,NET;NET:x0,y0,x1,y1" in mm, whole nets before the
semicolon, then each net's copper inside the box: tracks crossing its edge are cut there and the
outside pieces kept.) Freerouting lays the board out afresh on every run, so once a routing has passed
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

JAR = os.environ.get("FREEROUTING", os.path.expanduser("~/.local/opt/freerouting/freerouting-2.1.0.jar"))
JAVA = os.environ.get("JAVA", "java")
ROUTE_TIMEOUT = int(os.environ.get("ROUTE_TIMEOUT", "600"))


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
    # Heap capped: uncapped, a long run grew until the container's OOM killer took it (8 GB host).
    # And a time limit, since Freerouting 2.1 goes on passing forever when it can't finish: that
    # attempt just scores as failed.
    try:
        subprocess.run([JAVA, "-Xmx2500m", "-jar", JAR, "-de", dsn, "-do", ses, "-mp", "100", "-mt", "1",
                        "--gui.enabled=false"], check=True, stdout=subprocess.DEVNULL, timeout=ROUTE_TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f"  attempt gave up after {ROUTE_TIMEOUT} s", file=sys.stderr)
        return 999
    if not pcbnew.ImportSpecctraSES(board, ses):
        raise SystemExit("SES import failed")
    lost = {(t.GetClass(), t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y) for t in fixed} - {
        (t.GetClass(), t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y) for t in board.GetTracks()}
    if lost:
        raise SystemExit(f"SES import dropped {len(lost)} locked tracks")
    for f in (dsn, ses):
        os.remove(f)
    # Reload from disk: after the SES import the SWIG wrappers sometimes hand back bare SwigPyObjects
    # for the zones (cec-bridge, 2026-10-25), which then have no methods.
    board.Save(base + ".kicad_pcb")
    board = pcbnew.LoadBoard(base + ".kicad_pcb")
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
    """Through-hole pins soldered by iron or wave (by hand, or by JLC on the panel), not reflowed in
    paste like the USB-C's shell legs, with another net's copper close by, where a solder bridge
    could reach it under mask only. Checked on both layers
    for the switches, and on the solder side only for headers and sockets, whose body covers the
    other. A track crossing a header's row between two pins can't get further than 0.295 mm from
    them, so it is held to THREAD_GAP instead. The pour is held off them by the .kicad_dru rule
    that gen.py writes. (A keepout ring round the pins would do this up
    front, but Freerouting then can't reach them at all.) Returns the offending (ref, pin, net)."""
    out = []
    for fp in board.Footprints():
        pins = [p for p in fp.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
        # Skip reflowed parts: pin-in-paste legs (the USB-C shell) and SMD parts whose plated holes are
        # thermal vias (the module's ground pad).
        if (not pins or any(p.IsOnLayer(pcbnew.F_Paste) for p in pins)
                or any(p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD for p in fp.Pads())):
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


def autoroute(cfg, name, attempts=8):
    """Freerouting's result varies from run to run, so route until KiCad finds nothing to complain
    about, keeping the best attempt if none is clean."""
    base = cfg.base(name)
    pristine, best = base + "-unrouted.kicad_pcb", base + "-best.kicad_pcb"
    shutil.copy(base + ".kicad_pcb", pristine)
    scores = []
    try:
        for n in range(attempts):
            try:
                problems = route_once(base, pristine)
            except (AttributeError, subprocess.CalledProcessError) as e:
                print(f"  attempt failed: {e}", file=sys.stderr)
                problems = 999
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


def routing_file(cfg, name):
    return os.path.join(cfg.here, name, "routing.json")


def freeze(cfg, name):
    """Write the board's tracks and vias (stitching included) to routing.json, one per line so a
    change reads as a small diff. gen.py's locked copper is left out: gen.py lays that itself."""
    board = pcbnew.LoadBoard(cfg.base(name) + ".kicad_pcb")
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
    with open(routing_file(cfg, name), "w") as f:
        f.write("[\n" + ",\n".join(json.dumps(i) for i in items) + "\n]\n")
    print(f"{name}: froze {len(items)} tracks and vias in {os.path.relpath(routing_file(cfg, name), cfg.here)}")


def redundant(items, tol=2000):
    """Segments that add no copper: under 0.05 mm, or lying wholly along another of the same net and
    layer: inside its copper, or at least a track width long and less than a quarter width off its
    centreline (Freerouting leaves both, and dedupe only catches exact copies; cec-bridge's --patch
    left a 0.5 mm one 0.05 mm off). A short jog to a via or pad beside a track is not redundant."""
    segs = [i for i in items if "start" in i]

    def along(pt, a, b, w):
        length = math.dist(a, b)
        t = ((pt[0] - a[0]) * (b[0] - a[0]) + (pt[1] - a[1]) * (b[1] - a[1])) / length ** 2
        off = abs((b[0] - a[0]) * (a[1] - pt[1]) - (a[0] - pt[0]) * (b[1] - a[1])) / length
        return -1e-6 <= t <= 1 + 1e-6 and off <= max(tol, w)

    def lim(s, o, n):  # how far off o's centreline s may lie and still add nothing
        return max((o["w"] - s["w"]) / 2, s["w"] / 4 if n >= s["w"] else 0)

    out = []
    for k, s in enumerate(segs):
        n = math.dist(s["start"], s["end"])
        if n < 50000 or any(o is not s and o["net"] == s["net"] and o["layer"] == s["layer"] and o["w"] >= s["w"]
                            # longer, or an exact copy listed earlier (round 18: a --patch left one)
                            and (math.dist(o["start"], o["end"]) > n
                                 or (j < k and {tuple(o["start"]), tuple(o["end"])} == {tuple(s["start"]), tuple(s["end"])}))
                            and along(s["start"], o["start"], o["end"], lim(s, o, n)) and along(s["end"], o["start"], o["end"], lim(s, o, n))
                            for j, o in enumerate(segs)):
            out.append((s["net"], [round(v / 1e6, 3) for v in s["start"] + s["end"]]))
    return out


def cap_joints(board, tol=1000):
    """Track ends joined to their net only by overlapping copper: not on another same-net track's end
    or centreline, a via or a pad. KiCad's DRC counts them as connected and routecheck can't see them;
    they are the shape a dropped sliver or a nudged end leaves behind (cec-bridge audit rounds 16-17).
    Checked on the whole board, so the generator's locked copper and every pad count too."""
    def seg_dist(p, a, b):
        l2 = (b.x - a.x) ** 2 + (b.y - a.y) ** 2
        u = 0 if l2 == 0 else max(0, min(1, ((p.x - a.x) * (b.x - a.x) + (p.y - a.y) * (b.y - a.y)) / l2))
        return math.hypot(p.x - (a.x + u * (b.x - a.x)), p.y - (a.y + u * (b.y - a.y)))
    tracks = [t for t in board.GetTracks() if t.GetClass() != "PCB_VIA"]
    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    pads = list(board.GetPads())
    out = []
    for t in tracks:
        net, layer = t.GetNetCode(), t.GetLayer()
        for e in (t.GetStart(), t.GetEnd()):
            if not (any(o is not t and o.GetNetCode() == net and o.GetLayer() == layer
                        and seg_dist(e, o.GetStart(), o.GetEnd()) <= tol for o in tracks)
                    or any(v.GetNetCode() == net and math.hypot(e.x - v.GetPosition().x, e.y - v.GetPosition().y)
                           <= v.GetWidth(layer) / 2 for v in vias)
                    or any(p.GetNetCode() == net and p.IsOnLayer(layer) and p.HitTest(e) for p in pads)):
                out.append((t.GetNetname(), round(pcbnew.ToMM(e.x), 3), round(pcbnew.ToMM(e.y), 3)))
    return out


def replay(cfg, name):
    """Lay the frozen copper on the freshly generated board and fill the pours."""
    path = cfg.base(name) + ".kicad_pcb"
    board = pcbnew.LoadBoard(path)
    items = json.load(open(routing_file(cfg, name)))
    def refuse(msg):
        if cfg.replay_checks:
            raise SystemExit(f"{name}: {msg}")
        print(f"{name}: {msg} (replay_checks off: kept)", file=sys.stderr)
    if redundant(items):
        refuse(f"routing.json has redundant segments: {redundant(items)}")
    for i in items:
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
    if cap_joints(board):
        refuse(f"track ends joined only by overlapping copper: {cap_joints(board)}")
    lost, crowded = lost_pour(board), crowded_pins(board)
    if lost > LOST_POUR or crowded:
        raise SystemExit(f"{name}: routing.json loses {lost:.1f} mm2 of back pour; pins crowded: {crowded or 'none'}")
    board.Save(path)
    from .blocks import renetted
    moved = renetted(path, items)
    if moved:
        refuse(f"routing.json items changed net on save (each touches another net's pad): {moved}")
    print(f"{name}: replayed {os.path.relpath(routing_file(cfg, name), cfg.here)}")


def rip_spec():
    whole, _, boxed = os.environ["ROUTE_RIP"].partition(";")
    nets, box = boxed.split(":") if boxed else ("", "0,0,0,0")
    return set(filter(None, whole.split(","))), set(filter(None, nets.split(","))), [float(v) * 1e6 for v in box.split(",")]


def patch(cfg, name, attempts):
    """After a small placement change: keep the frozen copper outside the change, locked, so
    Freerouting routes only what was ripped; the next audit then reviews the patched corner."""
    whole, nets, (x0, y0, x1, y1) = rip_spec()
    path = cfg.base(name) + ".kicad_pcb"
    board = pcbnew.LoadBoard(path)
    key = lambda t: (t.GetClass(), t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y)
    generated = {key(t) for t in board.GetTracks() if t.IsLocked()}
    unknown = sorted(n for n in whole | nets if board.FindNet(n) is None)
    if unknown:
        raise SystemExit(f"ROUTE_RIP names nets the board doesn't have: {unknown}")
    inside = lambda p: x0 <= p[0] <= x1 and y0 <= p[1] <= y1

    def outside_parts(i):
        """The pieces of a segment outside the box (clipped at its edge), so Freerouting only has to
        join stubs that end on the box rather than re-route whole nets across the board."""
        (ax, ay), (bx, by) = i["start"], i["end"]
        lo, hi = 0.0, 1.0  # Liang-Barsky: the part of the segment inside the box is t in [lo, hi]
        for p, q in ((ax - bx, ax - x0), (bx - ax, x1 - ax), (ay - by, ay - y0), (by - ay, y1 - ay)):
            if p == 0:
                if q < 0:
                    return [i]
                continue
            t = q / p
            lo, hi = (max(lo, t), hi) if p < 0 else (lo, min(hi, t))
        if lo > hi:
            return [i]
        at = lambda t: [round(ax + (bx - ax) * t), round(ay + (by - ay) * t)]
        return [dict(i, start=s, end=e) for s, e in ((i["start"], at(lo)), (at(hi), i["end"]))
                if math.dist(s, e) >= 50000]

    keep = []
    for i in json.load(open(routing_file(cfg, name))):
        if i["net"] in whole:
            continue
        if i["net"] in nets:
            if "via" in i:
                if not inside(i["via"]):
                    keep.append(i)
            else:
                keep += outside_parts(i)
            continue
        keep.append(i)
    for i in keep:
        if "via" in i:
            t = pcbnew.PCB_VIA(board)
            t.SetPosition(pcbnew.VECTOR2I(*i["via"])); t.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            t.SetWidth(i["d"]); t.SetDrill(i["drill"])
        else:
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(*i["start"])); t.SetEnd(pcbnew.VECTOR2I(*i["end"]))
            t.SetLayer(board.GetLayerID(i["layer"])); t.SetWidth(i["w"])
        t.SetNet(board.FindNet(i["net"]))
        t.SetLocked(True)
        board.Add(t)
    board.Save(path)
    print(f"{name}: kept {len(keep)} frozen items, autorouting the rest", file=sys.stderr)
    autoroute(cfg, name, attempts)
    board = pcbnew.LoadBoard(path)
    for t in board.GetTracks():
        if key(t) not in generated:
            t.SetLocked(False)
    board.Save(path)
    # Freerouting may still add copper outside what was ripped (round 8: two stray segments on an
    # unripped net, stitching vias elsewhere): name it, so it is reviewed rather than frozen unseen.
    kept = {(i["net"], tuple(i.get("via", ())), tuple(sorted([tuple(i.get("start", ())), tuple(i.get("end", ()))]))) for i in keep}
    ripped = whole | nets
    for t in board.GetTracks():
        if key(t) in generated:
            continue
        a, b = t.GetStart(), t.GetEnd()
        if t.GetClass() == "PCB_VIA":
            k = (t.GetNetname(), (a.x, a.y), ((), ()))
            outside = not inside((a.x, a.y))
        else:
            k = (t.GetNetname(), (), tuple(sorted([(a.x, a.y), (b.x, b.y)])))
            # Any piece of it outside the box, not only a segment with both ends out.
            outside = bool(outside_parts({"start": [a.x, a.y], "end": [b.x, b.y]}))
        if k not in kept and (t.GetNetname() not in ripped or outside):
            print(f"  new copper outside the rip: {t.GetNetname()} {t.GetClass()} "
                  f"({a.x / 1e6:.3f}, {a.y / 1e6:.3f})-({b.x / 1e6:.3f}, {b.y / 1e6:.3f})", file=sys.stderr)


def cli(cfg, args):
    """The board's route.py: `python3 route.py [--freeze|--patch|--reroute] <variant>...`."""
    args = list(args)
    mode = args.pop(0) if args and args[0].startswith("--") else None
    for n in args:
        if mode == "--freeze":
            freeze(cfg, n)
        elif mode == "--patch":
            patch(cfg, n, int(os.environ.get("ROUTE_ATTEMPTS", "8")))
        elif mode is None and os.path.exists(routing_file(cfg, n)):
            replay(cfg, n)
        else:
            autoroute(cfg, n, int(os.environ.get("ROUTE_ATTEMPTS", "8")))
