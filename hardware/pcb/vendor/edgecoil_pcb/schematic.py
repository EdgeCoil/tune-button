# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""The schematic, written from the same netlist as the board: one symbol per part in a grid, a
global label on every pin, so KiCad's parity check compares the two."""
import sys

from .symbols import lib_symbol


def fmt(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def write_schematic(cfg, name, parts, path):
    uid = cfg.uid
    sheet_w, sheet_h = cfg.sheet()
    bottom = cfg.sheet_bottom if cfg.sheet_bottom is not None else sheet_h - 20
    root = uid(name, "root")

    def on_sheet(ok, msg):
        if not ok:
            if not cfg.off_sheet_ok:
                raise SystemExit(f"{name}: {msg}")
            print(f"{name}: {msg}", file=sys.stderr)
    used = {}
    for p in parts:
        if p.sym:
            used[p.sym] = lib_symbol(p.sym, cfg)
    used["power:PWR_FLAG"] = lib_symbol("power:PWR_FLAG", cfg)
    title = cfg.title(name) if cfg.title else name
    company = f'\n\t\t(company "{cfg.company}")' if cfg.company else ""
    comment = f'\n\t\t(comment 1 "{cfg.comment}")' if cfg.comment else ""
    out = [f'(kicad_sch\n\t(version 20250114)\n\t(generator "{cfg.generator or cfg.project + "-gen"}")\n\t(generator_version "9.0")'
           f'\n\t(uuid "{root}")\n\t(paper "{cfg.paper}")',
           f'\t(title_block\n\t\t(title "{title}"){company}{comment}\n\t)',
           "\t(lib_symbols"]
    out += ["\t\t" + s.replace("\n", "\n\t\t") for s, _ in used.values()]
    out.append("\t)")

    project = cfg.instance_project(name) if cfg.instance_project else name

    def instance(lib_id, ref, value, fp, x, y, pins, extra=()):
        su = uid(name, "sym", ref)
        s = [f'\t(symbol\n\t\t(lib_id "{lib_id}")\n\t\t(at {fmt(x)} {fmt(y)} 0)\n\t\t(unit 1)'
             # Test pads are bare copper, not parts: out of the BOM, as their footprint already is.
             f'\n\t\t(exclude_from_sim no)\n\t\t(in_bom {"no" if ref.startswith("#") or lib_id == "Connector:TestPoint" else "yes"})'
             f'\n\t\t(on_board {"no" if ref.startswith("#") else "yes"})\n\t\t(dnp no)\n\t\t(uuid "{su}")']
        hide = " (hide yes)" if ref.startswith("#") else ""
        # An IC's value (its part number) printed over its pin names (audit rounds 12-13): hidden on the
        # sheet; it stays in the field, the MPN and the BOM.
        vhide = " (hide yes)" if cfg.hide_ic_values and ref.startswith("U") else ""
        for k, v, dy, h in [("Reference", ref, -2.54, hide), ("Value", value, 2.54, vhide),
                            ("Footprint", fp, 5.08, " (hide yes)"), ("Datasheet", "", 0, " (hide yes)")] + list(extra):
            s.append(f'\t\t(property "{k}" "{v}"\n\t\t\t(at {fmt(x)} {fmt(y + dy)} 0)\n\t\t\t(effects (font (size 1.27 1.27)){h})\n\t\t)')
        for num in pins:
            s.append(f'\t\t(pin "{num}" (uuid "{uid(name, "pin", ref, num)}"))')
        s.append(f'\t\t(instances\n\t\t\t(project "{project}"\n\t\t\t\t(path "/{root}"\n\t\t\t\t\t'
                 f'(reference "{ref}")\n\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)')
        return "\n".join(s)

    def labels(x, y, pins, nets):
        s = []
        for num, locs in pins.items():
            net = nets.get(num, "")
            for (px, py, ang, _) in locs[:1]:
                ax, ay = round(x + px, 2), round(y - py, 2)
                if not net:
                    s.append(f'\t(no_connect (at {fmt(ax)} {fmt(ay)}) (uuid "{uid(name, "nc", str(x), str(y), num)}"))')
                    continue
                la = {0: 180, 180: 0, 90: 270, 270: 90}[ang]
                just = "right" if la in (180, 270) else "left"
                # Global labels, so the nets keep their bare names (a local label's net is "/NAME").
                s.append(f'\t(global_label "{net}"\n\t\t(shape passive)\n\t\t(at {fmt(ax)} {fmt(ay)} {la})'
                         f'\n\t\t(fields_autoplaced yes)\n\t\t(effects (font (size 1.27 1.27)) (justify {just}))'
                         f'\n\t\t(uuid "{uid(name, "lbl", str(x), str(y), num)}")'
                         f'\n\t\t(property "Intersheetrefs" "${{INTERSHEET_REFS}}"\n\t\t\t(at {fmt(ax)} {fmt(ay)} 0)'
                         f'\n\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n\t\t)\n\t)')
        return s

    # Grid placement: big symbols in the first row, everything else after. A2 (594 x 420 mm), so every
    # column lands inside the border; A3 left 11 parts off the page (audit round 12).
    x, y, col = 40.64, 50.8, 0
    order = sorted([p for p in parts if p.sym], key=lambda p: (0 if p.ref.startswith(("U", "J")) else 1, p.ref))
    for p in order:
        _, pins = used[p.sym]
        ys = [loc[1] for locs in pins.values() for loc in locs]
        span = (max(ys) - min(ys)) if ys else 0
        cell_h = max(25.4, span + 17.78)
        if y + cell_h > bottom:
            x, y = x + 76.2, 50.8
        cy = round((y + span / 2 + 5.08) / 2.54) * 2.54
        extra = [("MPN", p.mpn, 7.62, " (hide yes)")] if p.mpn else []
        extra += [("LCSC", p.lcsc, 10.16, " (hide yes)")] if p.lcsc else []
        out.append(instance(p.sym, p.ref, p.value, p.fp, x, cy, pins, extra))
        out += labels(x, cy, pins, p.pins)
        y += cell_h
        on_sheet(x + 40 < sheet_w - 10 and cy + span < sheet_h - 10, f"{p.ref} drawn off the {cfg.paper} sheet at ({x}, {cy})")
    # PWR_FLAGs on the supply nets, so ERC knows they are driven.
    # (Not on nets a power-output pin already drives: the charger's VBAT and the regulator's 3V3.)
    driven = {"3V3", "VBAT"} if "VBUS" in {n for p in parts for n in p.pins.values()} else set()
    supplies = sorted(({n for p in parts for n in p.pins.values()} & {"GND", "VBAT", "VBUS", "VSYS", "3V3"}) - driven)
    _, fpins = used["power:PWR_FLAG"]
    for i, net in enumerate(supplies):
        fx, fy = (cfg.flag_x if cfg.flag_x is not None else x + 76.2), 50.8 + i * 15.24
        on_sheet(fx + 10 < sheet_w - 10 and fy < sheet_h - 10, f"PWR_FLAG {net} drawn off the {cfg.paper} sheet at ({fx}, {fy})")
        out.append(instance("power:PWR_FLAG", f"#FLG0{i + 1}", "PWR_FLAG", "", fx, fy, fpins))
        out += labels(fx, fy, fpins, {"1": net})
    out.append(f'\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)')
    open(path, "w").write("\n".join(out) + "\n")
    return root

