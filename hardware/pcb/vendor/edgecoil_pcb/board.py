# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""The board: outline, footprints from the netlist, ground pours, the keepouts every board has
needed (connector shells, hand-soldered pads, artwork), silk clean-up and labels."""
import json
import math
import os
import re

import pcbnew

from .geom import mm
from .parts import MIN_DRILL
from .silk import logo, place_labels, trim_silk
from .symbols import lib_symbol


def outline(board, w, h, notch=None, r=2.5, rn=1.0):
    """Rounded-rectangle board edge, optionally with the top-left corner cut away to `notch` (x, y).
    The notch's corners get a smaller radius; its inside corner is what the router bit leaves anyway."""
    if notch:
        nx, ny = notch
        corners = [((nx, 0), rn), ((w, 0), r), ((w, h), r), ((0, h), r), ((0, ny), rn), ((nx, ny), rn)]
    else:
        corners = [((0, 0), r), ((w, 0), r), ((w, h), r), ((0, h), r)]

    def unit(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = (dx * dx + dy * dy) ** 0.5
        return dx / n, dy / n

    ends = []
    for i, (c, rad) in enumerate(corners):
        d1 = unit(corners[i - 1][0], c)                     # direction arriving at this corner
        d2 = unit(c, corners[(i + 1) % len(corners)][0])    # direction leaving it
        a = (c[0] - d1[0] * rad, c[1] - d1[1] * rad)
        b = (c[0] + d2[0] * rad, c[1] + d2[1] * rad)
        centre = (a[0] + d2[0] * rad, a[1] + d2[1] * rad)
        k = rad / 2 ** 0.5
        mid = (centre[0] + (d1[0] - d2[0]) * k, centre[1] + (d1[1] - d2[1]) * k)
        arc = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC)
        arc.SetArcGeometry(mm(*a), mm(*mid), mm(*b)); arc.SetLayer(pcbnew.Edge_Cuts); arc.SetWidth(pcbnew.FromMM(0.1))
        board.Add(arc)
        ends.append((a, b))
    for i in range(len(ends)):
        seg = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(mm(*ends[i][1])); seg.SetEnd(mm(*ends[(i + 1) % len(ends)][0]))
        seg.SetLayer(pcbnew.Edge_Cuts); seg.SetWidth(pcbnew.FromMM(0.1))
        board.Add(seg)


def usb_crossover(board, fp):
    """Join the USB-C's doubled D+/D- pads, which interleave (B7 A6 A7 B6), so one pair has to cross.
    Freerouting finds this in some runs and not others, with the shell keepout and U2 crowding it,
    so it is laid here and locked: D+ joins across the inner tips, D- drops through two vias at the
    outer tips (inside the open band of the keepout) and joins on the back. The two VBUS pad pairs
    are joined the same way, through vias at their inner tips, so the router has no reason to run
    VBUS along the GND pads and shell legs to reach them."""
    pads = {p.GetNumber(): p for p in fp.Pads()}
    if not {"A6", "A7", "B6", "B7"} <= pads.keys():
        return
    def at(p, side, off):  # a point `off` mm out from the pad's inner (-1) or outer (+1) tip
        box = p.GetBoundingBox()
        y = box.GetTop() - pcbnew.FromMM(off) if side < 0 else box.GetBottom() + pcbnew.FromMM(off)
        return pcbnew.VECTOR2I(p.GetPosition().x, y)
    def track(net, layer, a, b, w=0.25):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(a); t.SetEnd(b); t.SetLayer(layer); t.SetWidth(pcbnew.FromMM(w))
        t.SetNet(board.FindNet(net)); t.SetLocked(True)
        board.Add(t)
    def via(net, p, d=0.6):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(p); v.SetDrill(pcbnew.FromMM(d / 2)); v.SetWidth(pcbnew.FromMM(d))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(board.FindNet(net)); v.SetLocked(True)
        board.Add(v)
    # D+: up from both pads, 0.5 mm clear of A7's tip, and across.
    a, b = at(pads["A6"], -1, 0.5), at(pads["B6"], -1, 0.5)
    track("USB_DP", pcbnew.F_Cu, pads["A6"].GetPosition(), a)
    track("USB_DP", pcbnew.F_Cu, pads["B6"].GetPosition(), b)
    track("USB_DP", pcbnew.F_Cu, a, b)
    # D-: down from both pads to a via each, joined underneath.
    # (0.55 mm out, so the stubs end short of the keepout and only the via caps reach it.)
    a, b = at(pads["B7"], 1, 0.55), at(pads["A7"], 1, 0.55)
    for p, v in ((pads["B7"], a), (pads["A7"], b)):
        track("USB_DN", pcbnew.F_Cu, p.GetPosition(), v)
        via("USB_DN", v)
    track("USB_DN", pcbnew.B_Cu, a, b)
    # VBUS: up from both pairs to a power via each, joined underneath.
    # (Standard 0.6 mm vias, 0.5 mm out: a mask web clear of the pad, and the join still clears
    # the ESD chip's ground via behind the row.)
    a, b = at(pads["A4"], -1, 0.5), at(pads["A9"], -1, 0.5)
    for p, v in ((pads["A4"], a), (pads["A9"], b)):
        track("VBUS", pcbnew.F_Cu, p.GetPosition(), v, 0.4)
        via("VBUS", v)
    track("VBUS", pcbnew.B_Cu, a, b, 0.4)


def esd_ground(board, ref="U2"):
    """The ESD array's GND pin sits between its two signal pins, where its pour island is too small
    for the stitcher: give it its own via just off the pin's tip, on the connector side (the pin
    rows are too close for one between them), so the clamp current goes straight down to the plane."""
    fp = board.FindFootprintByReference(ref)
    if not fp:
        return
    gnd = next(p for p in fp.Pads() if p.GetNetname() == "GND")
    c, g = fp.GetPosition(), gnd.GetPosition()
    tip = gnd.GetBoundingBox().GetBottom() if g.y > c.y else gnd.GetBoundingBox().GetTop()
    off = pcbnew.FromMM(0.3 + 0.3)  # via radius plus a mask web from the pad
    at = pcbnew.VECTOR2I(g.x, tip + off if g.y > c.y else tip - off)
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(g); t.SetEnd(at); t.SetLayer(pcbnew.F_Cu); t.SetWidth(pcbnew.FromMM(0.4))
    t.SetNet(gnd.GetNet()); t.SetLocked(True)
    board.Add(t)
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(at); v.SetDrill(pcbnew.FromMM(0.3)); v.SetWidth(pcbnew.FromMM(0.6))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(gnd.GetNet()); v.SetLocked(True)
    board.Add(v)


def zone(board, net, layer, pts, keepout=False, part_free=False, via_free=False, gap_free=False,
         track_free=False, hole=None):
    z = pcbnew.ZONE(board)
    if gap_free or track_free:
        # gap_free: between a hand-soldered part's pads, on its own side: nothing a solder bridge
        # could reach. track_free: under a metal-bodied part, where only mask would insulate a
        # track (a tented via is a flat cap, so it may sit there).
        z.SetIsRuleArea(True)
        side = pcbnew.LSET(); side.AddLayer(layer)
        z.SetLayerSet(side)
        z.SetDoNotAllowTracks(True); z.SetDoNotAllowVias(gap_free); z.SetDoNotAllowPads(False)
        fills = gap_free
        z.SetDoNotAllowZoneFills(fills) if hasattr(z, "SetDoNotAllowZoneFills") else z.SetDoNotAllowCopperPour(fills)
        z.SetDoNotAllowFootprints(False)
    elif via_free:
        # Under silkscreen artwork: a via's hole would punch through the print.
        z.SetIsRuleArea(True)
        z.SetLayerSet(pcbnew.LSET.AllCuMask())
        z.SetDoNotAllowTracks(False); z.SetDoNotAllowVias(True); z.SetDoNotAllowPads(False)
        z.SetDoNotAllowZoneFills(False) if hasattr(z, "SetDoNotAllowZoneFills") else z.SetDoNotAllowCopperPour(False)
        z.SetDoNotAllowFootprints(False)
    elif part_free:
        # Front-side parts only: tracks, vias and copper are fine here.
        z.SetIsRuleArea(True)
        front = pcbnew.LSET(); front.AddLayer(pcbnew.F_Cu)
        z.SetLayerSet(front)
        z.SetDoNotAllowTracks(False); z.SetDoNotAllowVias(False); z.SetDoNotAllowPads(False)
        z.SetDoNotAllowZoneFills(False) if hasattr(z, "SetDoNotAllowZoneFills") else z.SetDoNotAllowCopperPour(False)
        z.SetDoNotAllowFootprints(True)
    elif keepout:
        z.SetIsRuleArea(True)
        z.SetLayerSet(pcbnew.LSET.AllCuMask())
        z.SetDoNotAllowTracks(True); z.SetDoNotAllowVias(True); z.SetDoNotAllowPads(False)
        z.SetDoNotAllowZoneFills(True) if hasattr(z, "SetDoNotAllowZoneFills") else z.SetDoNotAllowCopperPour(True)
        z.SetDoNotAllowFootprints(False)
    else:
        z.SetLayer(layer); z.SetNet(net)
        z.SetLocalClearance(pcbnew.FromMM(0.3)) if hasattr(z, "SetLocalClearance") else None
        z.SetMinThickness(pcbnew.FromMM(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)  # spokes on every pad: even reflow, easy rework
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetThermalReliefGap(pcbnew.FromMM(0.4)); z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.4))
    ol = z.Outline(); ol.NewOutline()
    for p in pts:
        ol.Append(mm(*p))
    if hole:
        ol.NewHole()
        for p in hole:
            ol.Append(mm(*p))
    board.Add(z)


def write_board(cfg, name, parts, h, keepouts, silk, extras, path, root):
    uid = cfg.uid
    board = pcbnew.BOARD()
    board.SetFileName(path)
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    nets = {}
    for netname in sorted({n for p in parts for n in p.pins.values() if n}):
        ni = pcbnew.NETINFO_ITEM(board, netname)
        board.Add(ni)
        nets[netname] = ni
    for p in parts:
        lib, fpname = p.fp.split(":")
        fp = pcbnew.FootprintLoad(os.path.join(cfg.lib_dir(lib) or cfg.footprint_dir, lib + ".pretty"), fpname)
        fp.SetFPIDAsString(p.fp)
        fp.SetReference(p.ref)
        fp.SetValue(p.value)
        # The test pads' silk square sits 0.12 mm from the pad, which JLC's DFM check flags; the TX/RX
        # legend names them, so the square moves to the fab layer.
        if p.fp.startswith("TestPoint:"):
            for item in fp.GraphicalItems():
                if item.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                    item.SetLayer(pcbnew.F_Fab if item.GetLayer() == pcbnew.F_SilkS else pcbnew.B_Fab)
        # JLC's standard holes start at 0.3 mm; anything smaller is a costlier option (2-layer: $20 ->
        # $70 for this panel). The module's footprint has 0.2 mm thermal vias in its ground pad.
        for pad in fp.Pads():
            if 0 < pad.GetDrillSize().x < mm(MIN_DRILL, 0).x:
                pad.SetDrillSize(mm(MIN_DRILL, MIN_DRILL))
        if not p.sym:
            fp.SetBoardOnly(True)  # mounting holes have no symbol
            fp.Reference().SetVisible(False)
        if p.sym:
            fp.SetPath(pcbnew.KIID_PATH(f"/{uid(name, 'sym', p.ref)}"))
            fp.SetSheetname("Root"); fp.SetSheetfile(os.path.basename(cfg.base(name)) + ".kicad_sch")
        board.Add(fp)
        fp.SetPosition(mm(*p.at))
        fp.SetOrientationDegrees(p.rot)
        if p.side == "B":
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        pins = lib_symbol(p.sym, cfg)[1] if p.sym else {}
        for pad in fp.Pads():
            num = pad.GetNumber()
            net = p.pins.get(num, "")
            if not net and num in pins:
                # The name KiCad's schematic gives an unconnected pin's net, so parity checks pass.
                net = f"unconnected-({p.ref}-{pins[num][0][3]}-Pad{num})"
                if net not in nets:
                    nets[net] = pcbnew.NETINFO_ITEM(board, net)
                    board.Add(nets[net])
            if net:
                pad.SetNet(nets[net])
        if p.mpn:
            fp.SetField("MPN", p.mpn)
            fp.GetFieldByName("MPN").SetVisible(False)
        if p.lcsc:
            fp.SetField("LCSC", p.lcsc)
            fp.GetFieldByName("LCSC").SetVisible(False)
            # Slotted legs (the USB-C shell) on a reflowed part: paste them, overprinted 0.12 mm (which
            # leaves a 0.15 mm stencil web to the next pad), so
            # they solder in reflow.
            for pad in fp.Pads():
                if pad.HasHole() and pad.GetDrillShape() == pcbnew.PAD_DRILL_SHAPE_OBLONG:
                    layers = pad.GetLayerSet(); layers.AddLayer(pcbnew.F_Paste); pad.SetLayerSet(layers)
                    pad.SetLocalSolderPasteMargin(pcbnew.FromMM(0.12))
        # JLC's minimum legend line is 0.15 mm; library footprints draw 0.12.
        for item in fp.GraphicalItems():
            if item.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS) and isinstance(item, pcbnew.PCB_SHAPE):
                item.SetWidth(max(item.GetWidth(), pcbnew.FromMM(0.15)))
    w = extras.get("width", cfg.width)
    outline(board, w, h, extras.get("notch"))
    inset = [(0.3, 0.3), (w - 0.3, 0.3), (w - 0.3, h - 0.3), (0.3, h - 0.3)]
    zone(board, nets["GND"], pcbnew.F_Cu, inset)
    back = inset
    if "back_pour_notch" in extras:  # (x0, x1, y): no back pour above y between x0 and x1
        x0, x1, y = extras["back_pour_notch"]
        back = [(0.3, 0.3), (x0, 0.3), (x0, y), (x1, y), (x1, 0.3)] + inset[1:]
    zone(board, nets["GND"], pcbnew.B_Cu, back)
    for k in keepouts:
        zone(board, None, None, k, keepout=True)
    for cx, cy, r in extras.get("part_free", []):
        circle = [(cx + r * math.cos(a * math.pi / 8), cy + r * math.sin(a * math.pi / 8)) for a in range(16)]
        zone(board, None, None, circle, part_free=True)
    # The USB-C's shell sits flat on the board, grounded: no tracks under its body (ground pour is
    # fine), where nothing but mask would separate them. Its metal floor starts about 0.75 mm past
    # the pad tips (HRO: 6.28 mm plate in a 7.35 mm body); up to there stays open for the crossover.
    for fp in board.Footprints():
        if not fp.GetFPIDAsString().startswith("Connector_USB:"):
            continue
        body = pcbnew.BOX2I()
        for item in fp.GraphicalItems():
            if item.GetLayer() == pcbnew.F_Fab and isinstance(item, pcbnew.PCB_SHAPE):
                body.Merge(item.GetBoundingBox())
        row = max(pd.GetBoundingBox().GetBottom() for pd in fp.Pads() if pd.GetAttribute() == pcbnew.PAD_ATTRIB_SMD)
        x0, y0, x1, y1 = (v / 1e6 for v in (body.GetLeft(), row + pcbnew.FromMM(0.7), body.GetRight(), body.GetBottom()))
        zone(board, None, pcbnew.F_Cu, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], track_free=True)
        usb_crossover(board, fp)
    # Shells and other board-specific keepouts (a connector whose footprint draws no body, say).
    for hook in cfg.board_hooks:
        hook(board)
    esd_ground(board)
    # Back-side SMD parts are soldered by hand: keep tracks and vias out from between their pads.
    for fp in board.Footprints():
        smd = [pd.GetBoundingBox() for pd in fp.Pads() if pd.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
        if fp.GetLayer() != pcbnew.B_Cu or len(smd) != 2:
            continue
        a, b = sorted(smd, key=lambda r: (r.GetCenter().x, r.GetCenter().y))
        m = pcbnew.FromMM(0.5)
        if a.GetRight() < b.GetLeft():
            box = (a.GetRight(), min(a.GetTop(), b.GetTop()) - m, b.GetLeft(), max(a.GetBottom(), b.GetBottom()) + m)
        else:
            a, b = sorted(smd, key=lambda r: r.GetCenter().y)
            box = (min(a.GetLeft(), b.GetLeft()) - m, a.GetBottom(), max(a.GetRight(), b.GetRight()) + m, b.GetTop())
        x0, y0, x1, y1 = (v / 1e6 for v in box)
        zone(board, None, pcbnew.B_Cu, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], gap_free=True)
        # And no via hard up against either pad. (Vias are tented, so beyond this margin one is no
        # worse than a track; at 0.6 mm the router ran out of room.)
        whole = pcbnew.BOX2I(a.GetPosition(), a.GetSize()); whole.Merge(b); whole.Inflate(pcbnew.FromMM(0.25))
        x0, y0, x1, y1 = (v / 1e6 for v in (whole.GetLeft(), whole.GetTop(), whole.GetRight(), whole.GetBottom()))
        zone(board, None, None, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], via_free=True)
    for item in silk:
        if item[0] == "rect":
            x0, y0, x1, y1 = item[1:]
            r = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_RECT)
            r.SetStart(mm(x0, y0)); r.SetEnd(mm(x1, y1)); r.SetLayer(pcbnew.F_SilkS); r.SetWidth(pcbnew.FromMM(0.15))
            board.Add(r)
        else:
            t = pcbnew.PCB_TEXT(board)
            t.SetText(item[3]); t.SetPosition(mm(item[1], item[2])); t.SetLayer(pcbnew.F_SilkS)
            t.SetTextSize(mm(1.0, 1.0)); t.SetTextThickness(pcbnew.FromMM(0.15))
            if len(item) > 4:
                t.SetTextAngleDegrees(item[4])
            board.Add(t)
    default = cfg.back_text(name, w, h) if cfg.back_text else [(w / 2, h - 6.0, f"{name}\nrev A", 1.0)]
    back_text = extras.get("back_text", default)
    for x, y, text, size in back_text:
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text); t.SetPosition(mm(x, y)); t.SetLayer(pcbnew.B_SilkS); t.SetMirrored(True)
        t.SetTextSize(mm(size, size)); t.SetTextThickness(pcbnew.FromMM(max(0.15, size * 0.15)))
        board.Add(t)
    if "logo" in extras:
        if not cfg.logo_svg:
            raise SystemExit(f"{name}: extras['logo'] given but the project has no logo_svg")
        logo(board, *extras["logo"], svg=cfg.logo_svg)
    art, logo_box = [], pcbnew.BOX2I()
    # Keep vias out from under the back-side text.
    for d in board.Drawings():
        if d.GetLayer() == pcbnew.B_SilkS:
            if isinstance(d, pcbnew.PCB_SHAPE) and d.GetShape() == pcbnew.SHAPE_T_SEGMENT:
                logo_box.Merge(d.GetBoundingBox())
            else:
                art.append(d.GetBoundingBox())
    if logo_box.GetWidth():
        art.append(logo_box)
        # And no back tracks under the logo: they fence off pockets of the ground plane there that
        # can't take a via (the logo keeps vias out), and the fill removes them, which shows
        # through the mask.
        b = pcbnew.BOX2I(logo_box.GetPosition(), logo_box.GetSize()); b.Inflate(pcbnew.FromMM(0.4))
        x0, y0, x1, y1 = (pcbnew.ToMM(v) for v in (b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom()))
        zone(board, None, pcbnew.B_Cu, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], track_free=True)
    for b in art:
        b.Inflate(pcbnew.FromMM(0.4))
        # Footprint holes (the module's ground-pad vias, switch pins) can't be routed around.
        for pad in board.GetPads():
            if pad.HasHole() and b.Intersects(pad.GetBoundingBox()):
                raise SystemExit(f"{name}: hole in {pad.GetParentFootprint().GetReference()} under back artwork")
        b.Inflate(pcbnew.FromMM(0.6))  # vias 1 mm clear, so none reads as part of the print
        x0, y0, x1, y1 = (pcbnew.ToMM(v) for v in (b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom()))
        zone(board, None, None, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], via_free=True)
    for ref in extras.get("hide_refs", []):
        board.FindFootprintByReference(ref).Reference().SetVisible(False)
    # Labels keep off the vias too (the frozen ones from routing.json and gen.py's own), since each label
    # gets a via-free zone below.
    frozen = os.path.join(cfg.here, name, "routing.json")
    vias = [(i["via"][0], i["via"][1], i["d"]) for i in (json.load(open(frozen)) if os.path.exists(frozen) else [])
            if "via" in i]
    vias += [(t.GetPosition().x, t.GetPosition().y, t.GetWidth(pcbnew.F_Cu)) for t in board.GetTracks()
             if t.GetClass() == "PCB_VIA"]
    if cfg.trim_silk:
        trim_silk(board, w, h)
    if cfg.title_block:
        tb = board.GetTitleBlock()
        tb.SetTitle(name); tb.SetRevision("A")
    place_labels(cfg, board, w, h, extras.get("notch"), extras.get("label_margin", 0.25), vias)
    # No via under a part label or front text (BOOT, the JLC mark...) either: a via cap breaks up
    # 1 mm text.
    boxes = [fp.Reference().GetBoundingBox() for fp in board.Footprints()
             if fp.Reference().IsVisible() and not fp.GetFPIDAsString().startswith("Button_Switch_Keyboard:")]
    boxes += [d.GetBoundingBox() for d in board.Drawings()
              if isinstance(d, pcbnew.PCB_TEXT) and d.GetLayer() == pcbnew.F_SilkS]
    for b in boxes:
        b.Inflate(pcbnew.FromMM(0.1))
        x0, y0, x1, y1 = (pcbnew.ToMM(v) for v in (b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom()))
        zone(board, None, None, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], via_free=True)
    board.Save(path)
    set_stackup(path)


# Black solder mask, white legend, 1.6 mm FR4. The Python API doesn't reach the stackup, so it is
# written into the file; KiCad's renders and the gerber job file take their colours from it.
STACKUP = """\t\t(stackup
\t\t\t(layer "F.SilkS" (type "Top Silk Screen") (color "White"))
\t\t\t(layer "F.Paste" (type "Top Solder Paste"))
\t\t\t(layer "F.Mask" (type "Top Solder Mask") (color "Black") (thickness 0.01))
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 1" (type "core") (color "FR4 natural") (thickness 1.51) (material "FR4")
\t\t\t\t(epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "B.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (color "Black") (thickness 0.01))
\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))
\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen") (color "White"))
\t\t\t(copper_finish "HAL lead-free")
\t\t\t(dielectric_constraints no)
\t\t)
"""


def set_stackup(path):
    src = open(path).read()
    src = re.sub(r"\t\t\(stackup\n.*?\n\t\t\)\n", "", src, flags=re.S)
    open(path, "w").write(src.replace("\t(setup\n", "\t(setup\n" + STACKUP, 1))

