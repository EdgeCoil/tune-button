# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Silkscreen: footprint silk kept clear of pads and the edge, part labels placed where they can be
read once the parts are on, and a mark rasterised into back-silk strokes."""
import math
import sys

import pcbnew

from .geom import mm


def trim_silk(board, w, h, pad_gap=0.2, edge_gap=0.25):
    """Keep footprints' silk clear of pads and the board edge. The LCSC footprints draw outlines as
    close as 0.045 mm to a pad; the gerbers clip silk off the mask opening anyway, but JLC's DFM check
    flags anything under 0.18 mm (danger under 0.13), and lines off the edge.

    Outlines are cut back, keeping pieces of 0.2 mm or more. Marks (a polarity "+", a pin-1 triangle:
    anything under 1.5 mm) are never cut, which could turn a "+" into a "-": each cluster is nudged
    away from the pad it is too close to, by up to 0.6 mm, so long as it stays nearer its own part's
    pads than any other part's. A part whose marks can't be kept gets a pin-1 dot instead (pin1_dot),
    and the build stops if there's nowhere to put one."""
    copper = {pcbnew.F_SilkS: pcbnew.F_Cu, pcbnew.B_SilkS: pcbnew.B_Cu}
    # Polygons, not SHAPE.GetClearance: that reports a positive gap for shapes that overlap.
    pads = {l: [(pd, pd.GetEffectivePolygon(c), pd.GetBoundingBox()) for pd in board.GetPads() if pd.IsOnLayer(c)]
            for l, c in copper.items()}
    polys = {l: [poly for _, poly, _ in v] for l, v in pads.items()}
    gap = pcbnew.FromMM(pad_gap)
    edge = board_edge(board, edge_gap)
    clear = lambda item: silk_clear(item, pads, gap, edge)

    def owned(grp, fp, margin=pcbnew.FromMM(0.1)):
        """The marks are nearer their own part's pads than any other part's, by `margin`, edge to edge."""
        pts = []
        for g in grp:
            ps = pcbnew.SHAPE_POLY_SET()
            g.TransformShapeToPolygon(ps, g.GetLayer(), 0, pcbnew.FromMM(0.005), pcbnew.ERROR_OUTSIDE)
            o = ps.Outline(0)
            pts += [pcbnew.VECTOR2I(o.CPoint(i).x, o.CPoint(i).y) for i in range(o.PointCount())]
        reach = pcbnew.BOX2I()
        for g in grp:
            reach.Merge(g.GetBoundingBox())
        reach = reach.GetInflated(pcbnew.FromMM(2))
        own, other = math.inf, math.inf
        for pd, poly, box in pads[grp[0].GetLayer()]:
            if reach.Intersects(box):
                d = min(math.sqrt(poly.SquaredDistance(p)) for p in pts)
                if pd.GetParentFootprint().GetReference() == fp.GetReference():
                    own = min(own, d)
                else:
                    other = min(other, d)
        return own + margin <= other

    dropped, kept = [], []  # kept: other parts' silk segments, so two outlines don't print as one bar

    def crowds(x, y, half, ref):
        for r, a, e, h2 in kept:
            if r == ref:
                continue
            L2 = (e.x - a.x) ** 2 + (e.y - a.y) ** 2
            u = 0 if L2 == 0 else max(0, min(1, ((x - a.x) * (e.x - a.x) + (y - a.y) * (e.y - a.y)) / L2))
            if math.hypot(a.x + u * (e.x - a.x) - x, a.y + u * (e.y - a.y) - y) < half + h2 + pcbnew.FromMM(0.1):
                return True
        return False

    for fp in board.Footprints():
        # Specks (EasyEDA's 0.2 mm circles, sub-0.2 mm dashes) print as dirt, not marks: off to Fab, and
        # a part whose only pin-1 mark was one gets a proper dot.
        for g in list(fp.GraphicalItems()):
            if g.GetLayer() in copper and isinstance(g, pcbnew.PCB_SHAPE):
                b = g.GetBoundingBox()
                if max(b.GetWidth(), b.GetHeight()) < pcbnew.FromMM(0.35):
                    g.SetLayer(pcbnew.F_Fab if g.GetLayer() == pcbnew.F_SilkS else pcbnew.B_Fab)
                    # Still marked if a mark-sized item (0.35-1.5 mm: a dot, an arc, a triangle) is left;
                    # a lens or body circle is bigger and marks nothing.
                    if g.GetShape() == pcbnew.SHAPE_T_CIRCLE and not any(
                            o.GetLayer() in copper and isinstance(o, pcbnew.PCB_SHAPE) and o.GetShape() != pcbnew.SHAPE_T_SEGMENT
                            and pcbnew.FromMM(0.35) <= max(o.GetBoundingBox().GetWidth(), o.GetBoundingBox().GetHeight())
                            < pcbnew.FromMM(1.5) for o in fp.GraphicalItems()):
                        dropped.append(fp)
        silk = [g for g in fp.GraphicalItems() if g.GetLayer() in copper and isinstance(g, pcbnew.PCB_SHAPE)]
        small = lambda g: max(g.GetBoundingBox().GetWidth(), g.GetBoundingBox().GetHeight()) < pcbnew.FromMM(1.5)
        marks = [g for g in silk if small(g)]
        groups = []
        for g in marks:
            hit = [grp for grp in groups if any(g.GetBoundingBox().GetInflated(pcbnew.FromMM(0.05)).Intersects(o.GetBoundingBox())
                                                for o in grp)]
            groups = [grp for grp in groups if grp not in hit] + [[g] + [o for grp in hit for o in grp]]
        lost = False
        for grp in groups:
            if all(clear(g) for g in grp) and owned(grp, fp):
                continue
            box = pcbnew.BOX2I()
            for g in grp:
                box.Merge(g.GetBoundingBox())
            # Away from the nearest pad that is too close, or, if none is, the nearest other part's.
            c = box.GetCenter()
            cands = pads[grp[0].GetLayer()]
            if all(clear(g) for g in grp):
                cands = [pp for pp in cands if pp[0].GetParentFootprint().GetReference() != fp.GetReference()]
            near = min(cands, key=lambda pp: pp[1].SquaredDistance(c))[0]
            dx, dy = c.x - near.GetPosition().x, c.y - near.GetPosition().y
            n = math.hypot(dx, dy) or 1
            for k in range(1, 7):
                v = pcbnew.VECTOR2I(int(dx / n * k * 1e5), int(dy / n * k * 1e5))
                for g in grp:
                    g.Move(v)
                if all(clear(g) for g in grp) and owned(grp, fp):
                    break
                for g in grp:
                    g.Move(pcbnew.VECTOR2I(-v.x, -v.y))
            else:
                for g in grp:
                    g.SetLayer(pcbnew.F_Fab if g.GetLayer() == pcbnew.F_SilkS else pcbnew.B_Fab)
                lost = True
        for item in silk:
            if item in marks:
                continue
            if clear(item) and not (item.GetShape() == pcbnew.SHAPE_T_SEGMENT and any(
                    crowds(p.x, p.y, item.GetWidth() / 2, fp.GetReference()) for p in (item.GetStart(), item.GetEnd(),
                                                                                       (item.GetStart() + item.GetEnd()) / 2))):
                if item.GetShape() == pcbnew.SHAPE_T_SEGMENT:
                    kept.append((fp.GetReference(), item.GetStart(), item.GetEnd(), item.GetWidth() / 2))
                continue
            layer = item.GetLayer()
            fab = pcbnew.F_Fab if layer == pcbnew.F_SilkS else pcbnew.B_Fab
            if item.GetShape() != pcbnew.SHAPE_T_SEGMENT:
                item.SetLayer(fab)
                continue
            half = item.GetWidth() / 2

            def bad(x, y):
                pt = pcbnew.VECTOR2I(int(x), int(y))
                return (not edge(x, y, half) or any(poly.Collide(pt, int(gap + half)) for poly in polys[layer])
                        or crowds(x, y, half, fp.GetReference()))

            a, e = item.GetStart(), item.GetEnd()
            n = max(2, int(math.dist((a.x, a.y), (e.x, e.y)) / 20000))
            pts = [(a.x + (e.x - a.x) * i / n, a.y + (e.y - a.y) * i / n) for i in range(n + 1)]
            ok = [not bad(*pt) for pt in pts]
            runs, start = [], None
            for i, good in enumerate(ok + [False]):
                if good and start is None:
                    start = i
                elif not good and start is not None:
                    if math.dist(pts[start], pts[i - 1]) >= 200000:
                        runs.append((pts[start], pts[i - 1]))
                    start = None
            if not runs:
                item.SetLayer(fab)
                continue
            for k, (p0, p1) in enumerate(runs):
                seg = item if k == 0 else item.Duplicate()
                seg.SetStart(pcbnew.VECTOR2I(int(p0[0]), int(p0[1])))
                seg.SetEnd(pcbnew.VECTOR2I(int(p1[0]), int(p1[1])))
                kept.append((fp.GetReference(), seg.GetStart(), seg.GetEnd(), half))
                if k:
                    fp.Add(seg)
        if lost:
            dropped.append(fp)
    # Short outline lines (a 0603's are 0.5 mm) count as marks above, so two neighbours' can still
    # print as one bar: drop the line of whichever part is farther from the overlap.
    segs = [(fp, g) for fp in board.Footprints() for g in fp.GraphicalItems()
            if g.GetLayer() in copper and isinstance(g, pcbnew.PCB_SHAPE) and g.GetShape() == pcbnew.SHAPE_T_SEGMENT]
    for i, (fa, ga) in enumerate(segs):
        for fb, gb in segs[i + 1:]:
            if (fa.GetReference() == fb.GetReference() or ga.GetLayer() != gb.GetLayer()
                    or ga.GetLayer() not in copper or gb.GetLayer() not in copper):
                continue
            room = (ga.GetWidth() + gb.GetWidth()) / 2 + pcbnew.FromMM(0.1)
            if ga.GetEffectiveShape().Collide(gb.GetEffectiveShape(), int(room - (ga.GetWidth() + gb.GetWidth()) / 2)):
                mid = (ga.GetStart() + ga.GetEnd()) / 2
                dist = lambda f: min(pd.GetEffectivePolygon(copper[ga.GetLayer()]).SquaredDistance(mid) for pd in f.Pads())
                f, g = (fa, ga) if dist(fa) > dist(fb) else (fb, gb)
                g.SetLayer(pcbnew.F_Fab if g.GetLayer() == pcbnew.F_SilkS else pcbnew.B_Fab)
                print(f"{f.GetReference()}: a silk line overlapped another part's; moved to fab", file=sys.stderr)
    seen = set()
    for fp in dropped:
        if fp.GetReference() in seen:
            continue
        seen.add(fp.GetReference())
        # A bare resistor or capacitor has no pin 1 worth marking: its short outline lines only
        # looked like marks (audit round 15, R16).
        if fp.GetReference()[0] in "RC" and len(fp.Pads()) == 2:
            continue
        print(f"{fp.GetReference()}: its silk marks would crowd a pad or another part; marked with a pin-1 dot", file=sys.stderr)
        pin1_dot(board, fp, pads, gap, edge)


def silk_clear(item, pads, gap, edge):
    """True if a silk shape is on the board, `edge`'s margin in, and `gap` (nm) from every pad."""
    b = item.GetBoundingBox()
    half = item.GetWidth() / 2
    if not all(edge(x, y, half) for x in (b.GetLeft(), b.GetRight()) for y in (b.GetTop(), b.GetBottom())):
        return False
    grown = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(grown, item.GetLayer(), gap, pcbnew.FromMM(0.005), pcbnew.ERROR_OUTSIDE)
    reach = b.GetInflated(gap + pcbnew.FromMM(0.1))
    for _, poly, box in pads[item.GetLayer()]:
        if reach.Intersects(box):
            x = pcbnew.SHAPE_POLY_SET(grown)
            x.BooleanIntersection(poly)
            if x.Area() > 0:
                return False
    return True


def board_edge(board, gap):
    """A test that a point (and a line half-width round it) is on the board and `gap` mm from its edge,
    rounded corners included."""
    outline = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline)
    chain = outline.Outline(0)
    # Plain numbers: the chain belongs to `outline`, and pcbnew frees both once this returns.
    pts = [(chain.CPoint(i).x, chain.CPoint(i).y) for i in range(chain.PointCount())]
    edges = [(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
    g = pcbnew.FromMM(gap)

    def dist(x, y, a, b):
        L2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
        u = 0 if L2 == 0 else max(0, min(1, ((x - a[0]) * (b[0] - a[0]) + (y - a[1]) * (b[1] - a[1])) / L2))
        return math.hypot(a[0] + u * (b[0] - a[0]) - x, a[1] + u * (b[1] - a[1]) - y)

    def inside(x, y):
        crossings = sum(1 for a, b in edges if (a[1] > y) != (b[1] > y)
                        and x < a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]))
        return crossings % 2 == 1

    def ok(x, y, half=0):
        return inside(x, y) and all(dist(x, y, a, b) >= g + half for a, b in edges)
    return ok


def pin1_dot(board, fp, pads, gap, edge, r=0.25):
    """A filled dot by pad 1, nearer it than any other pad, clear of pads, the edge and other silk."""
    layer = pcbnew.F_SilkS if fp.GetLayer() == pcbnew.F_Cu else pcbnew.B_SilkS
    one = [pd for pd in fp.Pads() if pd.GetNumber() == "1"]
    if not one:
        raise SystemExit(f"{fp.GetReference()}: lost its silk marks and has no pad 1 to mark")
    c = one[0].GetPosition()
    others = [d.GetBoundingBox().GetInflated(pcbnew.FromMM(0.15)) for d in board.Drawings() if d.GetLayer() == layer]
    others += [g.GetBoundingBox().GetInflated(pcbnew.FromMM(0.15)) for f in board.Footprints() for g in f.GraphicalItems()
               if g.GetLayer() == layer and isinstance(g, pcbnew.PCB_SHAPE)]
    body = pcbnew.BOX2I()  # under the part, the dot would vanish once it's placed
    for g in fp.GraphicalItems():
        if g.GetLayer() in (pcbnew.F_Fab, pcbnew.B_Fab) and isinstance(g, pcbnew.PCB_SHAPE) and g.GetShape() != pcbnew.SHAPE_T_CIRCLE:
            body.Merge(g.GetBoundingBox())
    others.append(body)
    rr = pcbnew.FromMM(r)
    for ring in range(4, 31):
        for step in range(0, 360, 15):
            x = c.x + pcbnew.FromMM(ring / 10) * math.cos(math.radians(step))
            y = c.y + pcbnew.FromMM(ring / 10) * math.sin(math.radians(step))
            centre = pcbnew.VECTOR2I(int(x), int(y))
            s = pcbnew.PCB_SHAPE(fp, pcbnew.SHAPE_T_CIRCLE)
            s.SetLayer(layer); s.SetFilled(True); s.SetWidth(pcbnew.FromMM(0.1))
            s.SetCenter(centre); s.SetEnd(pcbnew.VECTOR2I(int(x + rr - pcbnew.FromMM(0.05)), int(y)))
            d = sorted((math.sqrt(pp[1].SquaredDistance(centre)), pp[0]) for pp in pads[layer])
            near, margin = d[0][1], d[1][0] - d[0][0]  # it must read as pin 1's, not the pair's
            if (near.GetNumber() == "1" and near.GetParentFootprint().GetReference() == fp.GetReference()
                    and margin >= pcbnew.FromMM(0.3)
                    and not any(s.GetBoundingBox().Intersects(o) for o in others) and silk_clear(s, pads, gap, edge)):
                fp.Add(s)
                return
    raise SystemExit(f"{fp.GetReference()}: lost its silk marks and there is no clear spot for a pin-1 dot")


def logo(board, cx, cy, width, svg, stroke=0.15, res=0.025):
    """The EdgeCoil mark in back silkscreen, `width` mm wide, centred on (cx, cy), mirrored so it reads
    from the back. It is drawn as horizontal 0.15 mm strokes, one row every 0.15 mm so the rows tile
    without overlap, each run shortened by the stroke's round caps. So the print covers what the mark
    covers and its gaps keep their drawn size, to the 0.15 mm the legend can resolve."""
    import subprocess
    import tempfile
    from PIL import Image
    def render(px):
        with tempfile.NamedTemporaryFile(suffix=".png") as png:
            subprocess.run(["rsvg-convert", "-w", str(px), "-o", png.name, svg], check=True)
            im = Image.open(png.name).convert("RGBA")
        return im.crop(im.getchannel("A").point(lambda a: 255 if a >= 128 else 0).getbbox())
    # The SVG's canvas has margins: scale so the mark itself, not the canvas, is `width` wide.
    px = round(width / res)
    img = render(round(px * px / render(px).width))
    w, h = img.size
    alpha = img.getchannel("A").load()
    x0, y0 = cx - width / 2, cy - h * res / 2
    step = round(stroke / res)
    for row in range(step // 2, h, step):  # sample each 0.15 mm band at its centre
        runs, col = [], 0
        while col < w:
            if alpha[col, row] < 128:
                col += 1
                continue
            start = col
            while col < w and alpha[col, row] >= 128:
                col += 1
            runs.append([x0 + start * res, x0 + col * res])  # the run covers [start, col) pixels
        # A gap narrower than the legend can print would fill in: open it to `stroke`.
        for left, right in zip(runs, runs[1:]):
            short = stroke - (right[0] - left[1])
            if short > 0:
                left[1] -= short / 2; right[0] += short / 2
        for ra, rb in runs:
            # The stroke's round caps add stroke/2 at each end.
            a, b = ra + stroke / 2, rb - stroke / 2
            if b < a:
                a = b = (a + b) / 2
            # Mirror x about the centre: the back is seen from the other side.
            xa, xb = 2 * cx - a, 2 * cx - b
            y = y0 + (row + 0.5) * res
            seg = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
            seg.SetStart(mm(xa, y)); seg.SetEnd(mm(xb - (0.001 if xa == xb else 0), y))
            seg.SetLayer(pcbnew.B_SilkS); seg.SetWidth(pcbnew.FromMM(stroke))
            board.Add(seg)


def place_labels(cfg, board, w, h, notch=None, margin=0.25, vias=()):
    """Put each part's reference in the first spot beside it that covers no pad, no part body and no
    other label, so the silkscreen stays readable once the parts are on. MX switch labels stay where
    the footprint puts them: their caps cover that whole area anyway."""
    def grow(b, d):
        b = pcbnew.BOX2I(b.GetPosition(), b.GetSize())
        b.Inflate(pcbnew.FromMM(d))
        return b

    # A part's body is its fab-layer outline and its pads. (Not the courtyard: the module's takes in
    # the antenna clearance, which is the whole column beside it.)
    # Each side is placed against its own parts and silkscreen; pads (through-hole ones come through)
    # count on both.
    bodies = {pcbnew.F_SilkS: {}, pcbnew.B_SilkS: {}}
    side_of = {}
    for fp in board.Footprints():
        back = fp.GetLayer() == pcbnew.B_Cu
        fab, silk = (pcbnew.B_Fab, pcbnew.B_SilkS) if back else (pcbnew.F_Fab, pcbnew.F_SilkS)
        box = pcbnew.BOX2I()
        for item in list(fp.GraphicalItems()) + list(fp.Pads()):
            if item.IsOnLayer(fab) or isinstance(item, pcbnew.PAD):
                box.Merge(item.GetBoundingBox())
        bodies[silk][fp.GetReference()] = box
        side_of[fp.GetReference()] = silk
    # Keycaps on front-mounted switches cover an 18 mm square round the centre post.
    for fp in board.Footprints():
        if fp.GetFPIDAsString().startswith("Button_Switch_Keyboard:") and fp.GetLayer() == pcbnew.F_Cu:
            post = max(fp.Pads(), key=lambda p: p.GetDrillSize().x).GetPosition()
            half = pcbnew.FromMM(cfg.keycap / 2)
            bodies[pcbnew.F_SilkS][f"cap-{fp.GetReference()}"] = pcbnew.BOX2I(
                pcbnew.VECTOR2I(post.x - half, post.y - half), pcbnew.VECTOR2I(2 * half, 2 * half))
    # A silkscreen outline marks something that sits over the board (the XIAO): nothing goes under it.
    for d in board.Drawings():
        if isinstance(d, pcbnew.PCB_SHAPE) and d.GetLayer() in bodies and d.GetShape() == pcbnew.SHAPE_T_RECT:
            bodies[d.GetLayer()][f"outline-{len(bodies[d.GetLayer()])}"] = d.GetBoundingBox()
    if notch:  # no board there
        for layer in bodies:
            bodies[layer]["notch"] = pcbnew.BOX2I(mm(0, 0), mm(notch[0] + 0.5, notch[1] + 0.5))
    pads = [grow(p.GetBoundingBox(), 0.15) for p in board.GetPads()]
    pads += [grow(pcbnew.BOX2I(pcbnew.VECTOR2I(x - d // 2, y - d // 2), pcbnew.VECTOR2I(d, d)), 0.1) for x, y, d in vias]
    texts = {layer: [grow(d.GetBoundingBox(), 0.1) for d in board.Drawings()
                     if d.GetLayer() == layer and (isinstance(d, pcbnew.PCB_TEXT) or d.GetShape() == pcbnew.SHAPE_T_SEGMENT)]
             for layer in bodies}
    # Footprints' own silk marks (a polarity "+", a pin-1 dot) are as much in the way as a label.
    for fp in (board.Footprints() if cfg.labels_avoid_marks else ()):
        for item in fp.GraphicalItems():
            b = item.GetBoundingBox()
            if (item.GetLayer() in texts and isinstance(item, pcbnew.PCB_SHAPE)
                    and max(b.GetWidth(), b.GetHeight()) < pcbnew.FromMM(1.5)):  # marks, not outlines
                texts[item.GetLayer()].append(grow(b, 0.1))
    area = pcbnew.BOX2I(mm(0.6, 0.6), mm(w - 1.2, h - 1.2))

    def owner(b, layer):
        """The part whose body is clearly nearest the label (by `margin` mm), so it reads as its own part's."""
        def dist(box):  # edge to edge
            dx = max(box.GetLeft() - b.GetRight(), 0, b.GetLeft() - box.GetRight())
            dy = max(box.GetTop() - b.GetBottom(), 0, b.GetTop() - box.GetBottom())
            return math.hypot(dx, dy)
        parts = sorted((dist(v), r) for r, v in bodies[layer].items() if r in side_of)
        if len(parts) > 1 and parts[1][0] - parts[0][0] < pcbnew.FromMM(margin):
            return None
        return parts[0][1]
    # Small parts first: they have the fewest places to go.
    order = sorted((fp for fp in board.Footprints() if fp.Reference().IsVisible()),
                   key=lambda fp: bodies[side_of[fp.GetReference()]][fp.GetReference()].GetArea())
    for fp in order:
        ref = fp.Reference()
        layer = side_of[fp.GetReference()]
        if fp.GetFPIDAsString().startswith("Button_Switch_Keyboard:"):
            texts[layer].append(grow(ref.GetBoundingBox(), 0.1))
            continue
        ref.SetTextSize(mm(1.0, 1.0)); ref.SetTextThickness(pcbnew.FromMM(0.15))
        ref.SetKeepUpright(True)
        body = bodies[layer][fp.GetReference()]
        c, half_w, half_h = body.GetCenter(), body.GetWidth() // 2, body.GetHeight() // 2
        gap = pcbnew.FromMM(0.25)

        def spots():
            # Horizontal above, below and beside; then vertical beside (for parts in a narrow column).
            for angle in (0, 90):
                ref.SetTextAngleDegrees(angle)
                ref.SetPosition(c)
                tw, th = ref.GetBoundingBox().GetWidth() // 2, ref.GetBoundingBox().GetHeight() // 2
                ox, oy = half_w + tw + gap, half_h + th + gap
                near = [(0, -oy), (0, oy), (-ox, 0), (ox, 0)] if angle == 0 else [(-ox, 0), (ox, 0)]
                near += [(sx * ox, sy * oy) for sx in (-1, 1) for sy in (-1, 1)]
                near += [(sx * pcbnew.FromMM(d), sy * oy) for d in (1, 2, 3) for sx in (-1, 1) for sy in (-1, 1)]
                near += [(sx * ox, sy * pcbnew.FromMM(d)) for d in (1, 2, 3) for sx in (-1, 1) for sy in (-1, 1)]
                for dx, dy in near:
                    yield angle, dx, dy

        own = [grow(g.GetBoundingBox(), 0.1) for g in fp.GraphicalItems()
               if g.GetLayer() == layer and isinstance(g, pcbnew.PCB_SHAPE)] if cfg.labels_avoid_own_outline else []
        for angle, dx, dy in spots():
            ref.SetTextAngleDegrees(angle)
            ref.SetPosition(pcbnew.VECTOR2I(c.x + dx, c.y + dy))
            b = ref.GetBoundingBox()
            if (area.Contains(b.GetOrigin()) and area.Contains(b.GetEnd())
                    and not any(b.Intersects(o) for o in pads + texts[layer] + own)
                    and not any(b.Intersects(v) for v in bodies[layer].values())
                    and owner(b, layer) == fp.GetReference()):
                break
        else:
            print(f"{fp.GetReference()}: no clear spot for its label; hidden", file=sys.stderr)
            ref.SetVisible(False)
            continue
        texts[layer].append(grow(ref.GetBoundingBox(), 0.1))

