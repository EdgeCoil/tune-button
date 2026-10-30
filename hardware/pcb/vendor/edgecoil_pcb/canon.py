# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Canonical dump of a KiCad board: everything that reaches the fab, nothing that doesn't.

Two builds of the same board differ in thousands of lines of .kicad_pcb and gerber text (fresh
UUIDs, item order, timestamps), so a port is proven by comparing these dumps instead:

    python3 -m edgecoil_pcb.canon a.kicad_pcb b.kicad_pcb    exit 0 if identical, else a diff
    python3 -m edgecoil_pcb.canon a.kicad_pcb                print the dump

Coordinates are integer nanometres. Footprints, copper and drawings are sorted. Zone fills are the
one thing compared by geometry, not text: KiCad's fill can differ run to run by a vertex (a collinear
point, a 0.4 mm sliver edge) with the same area (the tune-button panel did, built twice unchanged),
so two fills match when the area of their symmetric difference is under FILL_XOR.
"""
import difflib
import sys

import pcbnew

FILL_XOR = 0.001  # mm2, per zone and layer; two unchanged builds of the tune-button panel measured 0.0


def _xy(p):
    return f"{p.x},{p.y}"


def _layers(lset):
    return "+".join(sorted(pcbnew.BOARD.GetStandardLayerName(l) for l in lset.Seq()))


def _shape(s, origin=""):
    t = s.GetShape()
    layer = s.GetLayerName()
    w = s.GetWidth()
    fill = int(s.IsFilled())
    if t == pcbnew.SHAPE_T_SEGMENT:
        a, b = sorted([_xy(s.GetStart()), _xy(s.GetEnd())])
        g = f"seg {a} {b}"
    elif t == pcbnew.SHAPE_T_RECTANGLE:
        g = f"rect {_xy(s.GetStart())} {_xy(s.GetEnd())}"
    elif t == pcbnew.SHAPE_T_CIRCLE:
        g = f"circle {_xy(s.GetCenter())} r{s.GetRadius()}"
    elif t == pcbnew.SHAPE_T_ARC:
        g = f"arc {_xy(s.GetStart())} {_xy(s.GetArcMid())} {_xy(s.GetEnd())}"
    elif t == pcbnew.SHAPE_T_POLY:
        poly = s.GetPolyShape()
        g = "poly " + " ".join(_xy(poly.CVertex(i)) for i in range(poly.TotalVertices()))
    else:
        g = f"shape{t} {_xy(s.GetStart())} {_xy(s.GetEnd())}"
    return f"{origin}draw {layer} w{w} f{fill} {g}"


def _text(t, origin=""):
    vis = int(t.IsVisible()) if hasattr(t, "IsVisible") else 1
    return (f"{origin}text {t.GetLayerName()} {t.GetText()!r} at {_xy(t.GetPosition())} "
            f"rot{t.GetTextAngleDegrees():g} size{t.GetTextWidth()}x{t.GetTextHeight()} "
            f"th{t.GetTextThickness()} mirror{int(t.IsMirrored())} vis{vis} "
            f"just{t.GetHorizJustify()},{t.GetVertJustify()}")


def _ring(chain):
    """A closed chain's vertices from its smallest one, in one direction: the same polygon can come
    back from a fill starting anywhere round it (the tune-button panel's did, run to run)."""
    pts = [(chain.CPoint(j).x, chain.CPoint(j).y) for j in range(chain.PointCount())]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if not pts:
        return ""
    best = None
    for seq in (pts, pts[::-1]):
        k = seq.index(min(seq))
        cand = seq[k:] + seq[:k]
        best = cand if best is None or cand < best else best
    return " ".join(f"{x},{y}" for x, y in best)


def _polyset(ps):
    out = []
    for i in range(ps.OutlineCount()):
        holes = sorted(_ring(ps.Hole(i, h)) for h in range(ps.HoleCount(i)))
        out.append(_ring(ps.Outline(i)) + "".join(f" | {h}" for h in holes))
    return sorted(out)


def _stackup(path):
    """The stackup block (mask and legend colours, finish), which the Python API doesn't reach."""
    text = open(path).read()
    i = text.find("(stackup")
    if i < 0:
        return ["stackup none"]
    depth, j = 0, i
    while True:
        depth += {"(": 1, ")": -1}.get(text[j], 0)
        j += 1
        if depth == 0:
            break
    return ["stackup " + " ".join(text[i:j].split())]


def dump(path, fills=None):
    """The canonical lines. With `fills` (a dict), zone fills are left out of the text and collected
    there by (zone, layer) for compare()."""
    board = pcbnew.LoadBoard(path)
    lines = _stackup(path)
    ds = board.GetDesignSettings()
    lines.append(f"board layers{board.GetCopperLayerCount()} thickness{ds.GetBoardThickness()}")
    for name in ("m_TrackMinWidth", "m_ViasMinSize", "m_MinThroughDrill", "m_MinClearance",
                 "m_CopperEdgeClearance", "m_HoleClearance", "m_SolderMaskExpansion",
                 "m_SolderMaskMinWidth"):
        if hasattr(ds, name):
            lines.append(f"rule {name} {getattr(ds, name)}")

    # Each footprint is one block, the blocks sorted: a panel repeats references (every board has a
    # C1), so the reference alone doesn't fix an order.
    blocks = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        o = f"fp {ref} "
        out = []
        out.append(f"{o}id {fp.GetFPIDAsString()} value {fp.GetValue()!r} side {fp.GetLayerName()} "
                     f"at {_xy(fp.GetPosition())} rot{fp.GetOrientationDegrees():g} attrs{fp.GetAttributes()}")
        for field in sorted(fp.GetFields(), key=lambda f: f.GetName()):
            if field.GetName() in ("Reference", "Value"):
                out.append(_text(field, f"{o}field {field.GetName()} "))
            elif field.GetText():
                out.append(f"{o}field {field.GetName()} {field.GetText()!r}")
        for pad in sorted(fp.Pads(), key=lambda p: (p.GetNumber(), p.GetPosition().x, p.GetPosition().y)):
            d = pad.GetDrillSize()
            out.append(f"{o}pad {pad.GetNumber()} net {pad.GetNetname()!r} at {_xy(pad.GetPosition())} "
                         f"size{_xy(pad.GetSize(pcbnew.F_Cu))} shape{pad.GetShape(pcbnew.F_Cu)} "
                         f"rot{pad.GetOrientationDegrees():g} drill{_xy(d)} attr{pad.GetAttribute()} "
                         f"layers {_layers(pad.GetLayerSet())}")
        items = []
        for g in fp.GraphicalItems():
            if isinstance(g, pcbnew.PCB_SHAPE):
                items.append(_shape(g, o))
            elif isinstance(g, pcbnew.PCB_TEXT):
                items.append(_text(g, o))
        out += sorted(items)
        for m in fp.Models():
            out.append(f"{o}model {m.m_Filename} show{int(m.m_Show)}")
        blocks.append(out)
    for out in sorted(blocks):
        lines += out

    copper = []
    for t in board.GetTracks():
        net = t.GetNetname()
        if isinstance(t, pcbnew.PCB_VIA):
            copper.append(f"via {_xy(t.GetPosition())} d{t.GetWidth(pcbnew.F_Cu)} drill{t.GetDrillValue()} "
                          f"net {net!r} {t.TopLayer()}-{t.BottomLayer()} type{t.GetViaType()}")
        elif isinstance(t, pcbnew.PCB_ARC):
            copper.append(f"arc {t.GetLayerName()} w{t.GetWidth()} {_xy(t.GetStart())} {_xy(t.GetMid())} "
                          f"{_xy(t.GetEnd())} net {net!r}")
        else:
            a, b = sorted([_xy(t.GetStart()), _xy(t.GetEnd())])
            copper.append(f"track {t.GetLayerName()} w{t.GetWidth()} {a} {b} net {net!r}")
    lines += sorted(copper)

    drawings = []
    for d in board.GetDrawings():
        if isinstance(d, pcbnew.PCB_SHAPE):
            drawings.append(_shape(d))
        elif isinstance(d, pcbnew.PCB_TEXT):
            drawings.append(_text(d))
        else:
            drawings.append(f"other {d.GetClass()} {d.GetLayerName()} {_xy(d.GetPosition())}")
    lines += sorted(drawings)

    zones = []
    for z in board.Zones():
        head = (f"zone net {z.GetNetname()!r} layers {_layers(z.GetLayerSet())} prio{z.GetAssignedPriority()} "
                f"clear{z.GetLocalClearance()} minw{z.GetMinThickness()} pad{z.GetPadConnection()} "
                f"keepout{int(z.GetIsRuleArea())}")
        if z.GetIsRuleArea():
            head += (f" no:tracks{int(z.GetDoNotAllowTracks())} vias{int(z.GetDoNotAllowVias())} "
                     f"pads{int(z.GetDoNotAllowPads())} fp{int(z.GetDoNotAllowFootprints())} "
                     f"pour{int(z.GetDoNotAllowCopperPour())}")
        block = [head] + [f"  outline {p}" for p in _polyset(z.Outline())]
        if fills is None:
            for layer in z.GetLayerSet().Seq():
                if z.HasFilledPolysForLayer(layer):
                    for p in _polyset(z.GetFilledPolysList(layer)):
                        block.append(f"  fill {pcbnew.BOARD.GetStandardLayerName(layer)} {p}")
        else:
            for layer in z.GetLayerSet().Seq():
                if z.HasFilledPolysForLayer(layer):
                    key = (head, pcbnew.BOARD.GetStandardLayerName(layer))
                    fills.setdefault(key, pcbnew.SHAPE_POLY_SET()).Append(z.GetFilledPolysList(layer))
                    block.append(f"  fill {key[1]} (compared by geometry)")
        zones.append("\n".join(block))
    lines += sorted(zones)
    return lines, board


def compare(pa, pb):
    """(text diff lines, fill mismatches). Both empty means the boards are the same."""
    fa, fb = {}, {}
    (a, _ba), (b, _bb) = dump(pa, fa), dump(pb, fb)  # keep the boards alive while their polygons are used
    diff = list(difflib.unified_diff(a, b, pa, pb, n=0, lineterm="")) if a != b else []
    bad = []
    for key in sorted(set(fa) | set(fb)):
        if key not in fa or key not in fb:
            bad.append(f"{key[1]} fill of {key[0]!r} only in {'the second' if key in fb else 'the first'}")
            continue
        # KiCad stores fills fractured (holes joined to the outline by zero-width bridges); booleans
        # want them whole.
        pa_, pb_ = pcbnew.SHAPE_POLY_SET(fa[key]), pcbnew.SHAPE_POLY_SET(fb[key])
        pa_.Unfracture(); pb_.Unfracture()
        x = pcbnew.SHAPE_POLY_SET(pa_)
        x.BooleanXor(pb_)
        area = x.Area() / 1e12
        if area > FILL_XOR:
            bad.append(f"{key[1]} fill of {key[0]!r} differs by {area:.4f} mm2")
    return diff, bad, len(a), len(fa)


def main(argv):
    if len(argv) == 1:
        print("\n".join(dump(argv[0])[0]))
        return 0
    if len(argv) != 2:
        raise SystemExit(__doc__)
    diff, bad, n, nf = compare(*argv)
    if not diff and not bad:
        print(f"identical: {n} canonical lines, {nf} zone fills to {FILL_XOR} mm2")
        return 0
    sys.stdout.writelines(l + "\n" for l in diff + bad)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
