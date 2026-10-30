# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""The KiCad project file (design rules, net classes), library tables and custom DRC rules, and
`build`, which writes every variant."""
import json
import os
import sys

from .board import write_board
from .parts import MIN_DRILL
from .schematic import write_schematic


def write_project(cfg, name, path):
    """Design rules sized for a 2-layer JLCPCB/PCBWay order, and a wider class for the supply nets
    the board names in `cfg.power_nets`."""
    uid = cfg.uid
    pro = {
        "board": {"design_settings": {
            "defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.2, "copper_text_size_h": 1.5,
                         "silk_line_width": 0.15, "silk_text_size_h": 1.0, "silk_text_size_v": 1.0},
            "rules": {"min_clearance": 0.2, "min_track_width": 0.2, "min_via_diameter": 0.6,
                      "min_through_hole_diameter": MIN_DRILL, "min_copper_edge_clearance": 0.3,
                      "min_hole_to_hole": 0.25, "min_hole_clearance": 0.25, "min_silk_clearance": 0.0},
            "rule_severities": {"silk_overlap": "ignore", "silk_over_copper": "ignore",
                                "silk_edge_clearance": "ignore", "lib_footprint_mismatch": "ignore",
                                "lib_footprint_issues": "ignore", "text_height": "ignore",
                                "courtyards_overlap": "error"},
            "track_widths": [0.0, 0.25, 0.5], "via_dimensions": [{"diameter": 0.0, "drill": 0.0},
                                                                   {"diameter": 0.6, "drill": 0.3}],
        }},
        "meta": {"filename": os.path.basename(path), "version": 3},
        "net_settings": {
            "classes": [
                {"name": "Default", "clearance": 0.2, "track_width": 0.25, "via_diameter": 0.6, "via_drill": 0.3,
                 "diff_pair_width": 0.2, "diff_pair_gap": 0.25, "microvia_diameter": 0.3, "microvia_drill": 0.1,
                 "wire_width": 6, "bus_width": 12, "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)",
                 "schematic_color": "rgba(0, 0, 0, 0.000)", "priority": 2147483647},
                {"name": "Power", "clearance": 0.2, "track_width": 0.4, "via_diameter": 0.8, "via_drill": 0.4,
                 "diff_pair_width": 0.2, "diff_pair_gap": 0.25, "microvia_diameter": 0.3, "microvia_drill": 0.1,
                 "wire_width": 6, "bus_width": 12, "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)",
                 "schematic_color": "rgba(0, 0, 0, 0.000)", "priority": 0},
            ],
            "meta": {"version": 4},
            "netclass_patterns": [{"netclass": "Power", "pattern": n} for n in cfg.power_nets],
        },
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [[uid(name, "root"), "Root"]],
    }
    open(path, "w").write(json.dumps(pro, indent=2) + "\n")
    # The only through-hole pads off the GND net are hand-soldered pins (switches, sockets, headers):
    # hold the pour as far from them as route.py holds other nets' tracks (PIN_GAP).
    d = os.path.dirname(path)
    for kind, ext in (("sym", ".kicad_sym"), ("fp", ".pretty")) if cfg.local_libs else ():
        libs = "".join(
            f'  (lib (name "{nick}")(type "KiCad")(uri "${{KIPRJMOD}}/../{rel}/{nick}{ext}")(options "")(descr "{descr}"))\n'
            for nick, (rel, descr) in cfg.local_libs.items())
        open(os.path.join(d, f"{kind}-lib-table"), "w").write(f'({kind}_lib_table\n  (version 7)\n{libs})\n')
    open(path[:-len(".kicad_pro")] + ".kicad_dru", "w").write(
        '(version 1)\n(rule "hand-soldered pins to pour"\n  (constraint clearance (min 0.4mm))\n'
        '  (condition "A.Pad_Type == \'Through-hole\' && B.Type == \'Zone\'"))\n')



def build(cfg, names=None):
    """Write the project, schematic and unrouted board of each named variant (all if none)."""
    for name in names or list(cfg.variants):
        parts, h, keepouts, silk, extras = cfg.variants[name]()
        os.makedirs(os.path.join(cfg.here, name), exist_ok=True)
        base = cfg.base(name)
        write_project(cfg, name, base + ".kicad_pro")
        root = write_schematic(cfg, name, parts, base + ".kicad_sch")
        write_board(cfg, name, parts, h, keepouts, silk, extras, base + ".kicad_pcb", root)
        write_project(cfg, name, base + ".kicad_pro")  # Save() may have rewritten it
        print(f"{name}: {extras.get('width', cfg.width):.1f} x {h:.1f} mm, {len(parts)} footprints")
