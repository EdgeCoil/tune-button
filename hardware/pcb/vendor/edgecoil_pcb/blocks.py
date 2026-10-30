# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Circuit blocks: parts with their reviewed copper, placed on a board as one piece.

A block is a directory under blocks/ holding block.json (parts in the block's own frame, its ports,
its copper), model.inc (a SPICE subcircuit) and FINDINGS.md (what audits and simulations found and
what was accepted). A board places it:

    core = blocks.load("esp32-c3-wroom-02")
    parts += core.parts(at=(14.0, 6.8), refs={...}, nets={"3V3": "3V3", ...})
    CFG.blocks.append(core.copper(at=(14.0, 6.8), nets={...}))

The block's copper is laid locked by gen.py (route.py --freeze leaves locked copper out of
routing.json), so the router only joins block to block. A block is cut from a board that has
passed review with `python3 -m edgecoil_pcb.blocks cut`, which also proves the cut: the board
rebuilt from its blocks plus the remaining routing must be canonically identical.

Frames: the block's origin is its anchor part's position; `rot` is 0, 90, 180 or 270 degrees
counter-clockwise as KiCad shows it (y down), the same as a footprint's rotation.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCKS = os.path.join(os.path.dirname(HERE), "blocks")


def _rot(x, y, rot):
    """(x, y) turned by `rot` degrees as KiCad turns a footprint (counter-clockwise on screen, y down)."""
    a = math.radians(rot)
    c, s = round(math.cos(a)), round(math.sin(a))
    return x * c + y * s, -x * s + y * c


class Block:
    def __init__(self, data, path=None):
        self.data, self.path = data, path
        self.name = data["name"]
        self.ports = data["ports"]

    def _net(self, n, nets, prefix):
        if n in self.data.get("optional_ports", ()):
            return nets.get(n, "")  # a pin the block leaves free: no connection unless the board maps it
        if n in self.ports:
            if n not in nets:
                raise SystemExit(f"block {self.name}: port {n} not connected (nets= has {sorted(nets)})")
            return nets[n]
        return prefix + n  # an internal net, kept apart from another instance's

    def parts(self, at, rot=0, refs=None, nets=None, prefix="", libs=None):
        """The block's parts, placed: board refs from `refs` (local -> board), else prefixed. `libs`
        renames library nicknames (a block's part -> a board's own copy of it)."""
        from .parts import Part
        refs, nets, libs = refs or {}, nets or {}, libs or {}

        def lib(lib_id):
            nick, _, name = lib_id.partition(":")
            return f"{libs.get(nick, nick)}:{name}" if name else lib_id
        if rot % 90:
            raise SystemExit(f"block {self.name}: rot must be a multiple of 90")
        out = []
        for p in self.data["parts"]:
            dx, dy = _rot(p["at"][0], p["at"][1], rot)
            out.append(Part(refs.get(p["ref"], prefix + p["ref"]), lib(p["sym"]) if p["sym"] else p["sym"], lib(p["fp"]), p["value"],
                            {k: (self._net(v, nets, prefix) if v else "") for k, v in p["pins"].items()},
                            (round(at[0] + dx, 6), round(at[1] + dy, 6)), (p["rot"] + rot) % 360,
                            mpn=p.get("mpn", ""), note=p.get("note", ""), lcsc=p.get("lcsc", ""),
                            side=p.get("side", "F")))
        return out

    def board_refs(self, key, refs=None, prefix=""):
        """The board references of the block parts listed under `key` in block.json (e.g.
        "esd_ground": the parts for Config.esd_refs)."""
        refs = refs or {}
        return tuple(refs.get(r, prefix + r) for r in self.data.get(key, ()))

    def copper(self, at, rot=0, nets=None, prefix=""):
        """The block's tracks and vias in routing.json's form, board coordinates (nm)."""
        nets = nets or {}
        ox, oy = round(at[0] * 1e6), round(at[1] * 1e6)

        def pt(p):
            x, y = _rot(p[0], p[1], rot)
            return [ox + x, oy + y]
        out = []
        for i in self.data["copper"]:
            j = dict(i, net=self._net(i["net"], nets, prefix))
            for k in ("start", "end", "via"):
                if k in j:
                    j[k] = pt(j[k])
            out.append(j)
        return out


def load(name, root=BLOCKS):
    path = os.path.join(root, name, "block.json")
    return Block(json.load(open(path)), path)


def lay(board, items):
    """Lay block copper on a board, locked."""
    import pcbnew
    for i in items:
        net = board.FindNet(i["net"])
        if net is None:
            raise SystemExit(f"block copper on net {i['net']}, which the board doesn't have")
        if "via" in i:
            t = pcbnew.PCB_VIA(board)
            t.SetPosition(pcbnew.VECTOR2I(*i["via"])); t.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            t.SetWidth(i["d"]); t.SetDrill(i["drill"])
        else:
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(*i["start"])); t.SetEnd(pcbnew.VECTOR2I(*i["end"]))
            t.SetLayer(board.GetLayerID(i["layer"])); t.SetWidth(i["w"])
        t.SetNet(net); t.SetLocked(True)
        board.Add(t)


def renetted(path, items):
    """Laid copper whose net changed on the way to the file. KiCad renames a track or via whose only
    connection is another net's pad to that net when the board is saved, silently, so a frozen item
    placed onto the wrong pad would leave its record and the board disagreeing (found 2026-10-30 by a
    planted track that DRC then never saw). Returns [(item's net, the board's, where)]."""
    import pcbnew
    board = pcbnew.LoadBoard(path)
    found = {}
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            key = ("via", t.GetPosition().x, t.GetPosition().y)
        else:
            a, b = (t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)
            key = ("seg", board.GetLayerName(t.GetLayer())) + tuple(sorted([a, b]))
        found.setdefault(key, []).append(t.GetNetname())
    out = []
    for i in items:
        if "via" in i:
            key = ("via", i["via"][0], i["via"][1])
        else:
            key = ("seg", i["layer"]) + tuple(sorted([tuple(i["start"]), tuple(i["end"])]))
        nets = found.get(key, [])
        if i["net"] not in nets:
            where = i.get("via") or i["start"]
            out.append((i["net"], nets[0] if nets else "missing", (where[0] / 1e6, where[1] / 1e6)))
    return out


# ------------------------------------------------------------------------------------------- cutting

def _regions(board, refs, grow=250000):
    """Each block part's courtyard (or pads, if it has none), grown by `grow` nm: where its copper may lie."""
    import pcbnew
    boxes = []
    for fp in board.GetFootprints():
        if fp.GetReference() not in refs:
            continue
        box = pcbnew.BOX2I()
        for g in fp.GraphicalItems():
            if g.GetLayer() in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
                box.Merge(g.GetBoundingBox())
        if not box.GetWidth():
            for p in fp.Pads():
                box.Merge(p.GetBoundingBox())
        boxes.append((box.GetLeft() - grow, box.GetTop() - grow, box.GetRight() + grow, box.GetBottom() + grow))
    return boxes


def _inside(p, boxes):
    return any(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for x0, y0, x1, y1 in boxes)


def cut(board_path, routing, refs, anchor):
    """Split `routing` into (block copper, the rest) for the parts `refs` of a board, and the block's
    port and internal nets.

    Block copper is every item on an internal net, and on each port net the copper that joins the
    block's own pads to each other: the net's copper is cut wherever it reaches another part's pad,
    then dead ends (items joined to at most one other item or block pad) are pruned until none is
    left. What survives lies on a path from one block pad to another; the branches out to the rest
    of the board are the joins, and stay with the board's routing. (Keeping only copper inside the
    parts' courtyards, as a first version did, dropped every track crossing the gap between two of
    the block's own parts: the LDO's output to its capacitor.)"""
    import pcbnew
    board = pcbnew.LoadBoard(board_path)
    pads_by_net = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            n = p.GetNetname()
            if n and not n.startswith("unconnected-"):
                pads_by_net.setdefault(n, []).append((fp.GetReference(), p))
    nets = {n for n, ps in pads_by_net.items() if any(r in refs for r, _ in ps)}
    internal = {n for n in nets if all(r in refs for r, _ in pads_by_net[n])}
    ports = sorted(nets - internal)

    def ends(i):
        return [tuple(i["via"])] if "via" in i else [tuple(i["start"]), tuple(i["end"])]

    def layers(i):
        return {"F.Cu", "B.Cu"} if "via" in i else {i["layer"]}

    def on_pad(e, p, lay):
        names = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}
        return any(p.IsOnLayer(names[l]) for l in lay) and p.HitTest(pcbnew.VECTOR2I(int(e[0]), int(e[1])))

    block = []
    for net in sorted(nets):
        items = [i for i in routing if i["net"] == net]
        if net in internal:
            block += items
            continue
        mine = [p for r, p in pads_by_net[net] if r in refs]
        theirs = [p for r, p in pads_by_net[net] if r not in refs]
        # For each end of each item: the block pads it lands on, else the other items sharing that point
        # on a common layer. An end inside another part's pad leads nowhere: the copper is cut there.
        # Junctions are points, not item-to-item links: three tracks meeting at one point would
        # otherwise link in a triangle, a cycle no pruning removes.
        at = []
        for k, i in enumerate(items):
            row = []
            for e in ends(i):
                if any(on_pad(e, p, layers(i)) for p in theirs):
                    row.append(("cut", set()))
                    continue
                hit = {n for n, p in enumerate(mine) if on_pad(e, p, layers(i))}
                row.append(("pad", hit) if hit else
                           ("pt", {m for m, j in enumerate(items) if m != k and layers(i) & layers(j) and e in ends(j)}))
            at.append(row)
        via_pads = {k: {n for n, p in enumerate(mine) if on_pad(ends(i)[0], p, layers(i))}
                    for k, i in enumerate(items) if "via" in i}
        alive = set(range(len(items)))

        def live_ends(k):
            return sum(1 for kind, x in at[k] if kind == "pad" or (kind == "pt" and x & alive))

        changed = True
        while changed:
            changed = False
            for k in list(alive):
                i = items[k]
                if "via" in i:
                    # A via joins layers: it is on a path if two live things meet at it (block pads
                    # under it, and live items ending on it).
                    meet = {m for m in alive if m != k and ends(i)[0] in ends(items[m])}
                    dead = len(via_pads[k]) + len(meet) < 2
                else:
                    dead = live_ends(k) < 2  # a track lies on a path only if both its ends lead somewhere
                if dead:
                    alive.discard(k)
                    changed = True
        block += [items[k] for k in sorted(alive)]
    taken = {json.dumps(i, sort_keys=True) for i in block}
    rest = [i for i in routing if json.dumps(i, sort_keys=True) not in taken]
    a = board.FindFootprintByReference(anchor).GetPosition()
    return block, rest, ports, sorted(internal), (a.x, a.y)


def to_local(items, anchor, rot=0):
    """Board copper to the block's frame (the inverse of Block.copper at rot=0)."""
    out = []
    for i in items:
        j = dict(i)
        for k in ("start", "end", "via"):
            if k in j:
                j[k] = [j[k][0] - anchor[0], j[k][1] - anchor[1]]
        out.append(j)
    return out


def selftest(block, cfg_libs=None, at=(60.0, 60.0)):
    """Place the block alone at each rotation and check its copper still does its job: every internal
    net is one connected piece (pads and copper), and every copper item touches its own net's pads or
    copper. Returns a list of problems; empty is a pass."""
    import pcbnew
    from .config import Config
    from .geom import mm
    cfg = Config(project="selftest", here=os.path.dirname(block.path), ns=__import__("uuid").uuid4(), variants={},
                 local_libs=cfg_libs or {})
    problems = []
    for rot in (0, 90, 180, 270):
        board = pcbnew.BOARD()
        nets = {p: p for p in block.ports}
        parts = block.parts(at, rot, nets=nets)
        names = sorted({n for p in parts for n in p.pins.values() if n})
        for n in names:
            board.Add(pcbnew.NETINFO_ITEM(board, n))
        for p in parts:
            lib, fpname = p.fp.split(":")
            fp = pcbnew.FootprintLoad(os.path.join(cfg.lib_dir(lib) or cfg.footprint_dir, lib + ".pretty"), fpname)
            fp.SetReference(p.ref)
            board.Add(fp)
            fp.SetPosition(mm(*p.at)); fp.SetOrientationDegrees(p.rot)
            if p.side == "B":
                fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
            for pad in fp.Pads():
                n = p.pins.get(pad.GetNumber(), "")
                if n:
                    pad.SetNet(board.FindNet(n))
        lay(board, block.copper(at, rot, nets=nets))
        # Union-find over pads and copper, joined where copper ends meet pads, each other or vias.
        nodes = [("pad", p) for p in board.GetPads() if p.GetNetname()] + [("cu", t) for t in board.GetTracks()]
        parent = list(range(len(nodes)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def ends(t):
            return [t.GetPosition()] if t.GetClass() == "PCB_VIA" else [t.GetStart(), t.GetEnd()]

        def layers(o):
            return {l for l in (pcbnew.F_Cu, pcbnew.B_Cu) if o.IsOnLayer(l)}

        for i, (ki, a) in enumerate(nodes):
            if ki != "cu":
                continue
            for j, (kj, b) in enumerate(nodes):
                if i == j or a.GetNetname() != b.GetNetname() or not (layers(a) & layers(b)):
                    continue
                hit = (any(b.HitTest(e) for e in ends(a)) if kj == "pad"
                       else any(b.HitTest(e) for e in ends(a)) or any(a.HitTest(e) for e in ends(b)))
                if hit:
                    parent[find(i)] = find(j)
        for net in block.data.get("internal", []):
            members = [i for i, (_, o) in enumerate(nodes) if o.GetNetname() == net]
            roots = {find(i) for i in members}
            if len(roots) > 1:
                problems.append(f"rot {rot}: internal net {net} in {len(roots)} pieces")
        for i, (k, o) in enumerate(nodes):
            if k == "cu" and not any(find(j) == find(i) for j, (kj, _) in enumerate(nodes) if kj == "pad"):
                e = ends(o)[0]
                problems.append(f"rot {rot}: {o.GetNetname()} copper at ({e.x / 1e6:.3f}, {e.y / 1e6:.3f}) reaches no pad")
    return problems


if __name__ == "__main__":
    # python3 -m edgecoil_pcb.blocks selftest <block dir> [lib nickname=dir ...]
    if len(sys.argv) >= 3 and sys.argv[1] == "selftest":
        d = os.path.abspath(sys.argv[2])
        libs = dict(a.split("=", 1) for a in sys.argv[3:])
        b = Block(json.load(open(os.path.join(d, "block.json"))), os.path.join(d, "block.json"))
        probs = selftest(b, {k: (os.path.relpath(v, d), "") for k, v in libs.items()})
        print("\n".join(probs) if probs else f"{b.name}: copper connected at 0/90/180/270")
        sys.exit(1 if probs else 0)
    sys.exit(__doc__)
