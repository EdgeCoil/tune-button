// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: CERN-OHL-S-2.0
//
// Printed case for the c3 four-key board, in two parts:
//   base  floor, walls, four board spacers with locating pins, a cell fence, and three M3
//         heat-set inserts in the corners
//   lid   the MX plate as the top face, with a skirt, corner bosses and four posts underneath.
//         The posts press the board down onto the spacers at its mounting holes.
// Three M3 x 8 socket head cap screws go down through the lid into the inserts. The fourth corner
// is next to the module's antenna, so it has a printed peg instead of a screw and insert.
//
// The board layout, heights, cell, pockets and USB-C slot come from stack.scad, so this case and
// the acrylic one hold the board in the same place.
//
//   openscad -D 'piece="base"' -o tune-button-c3-base.stl tune-button-c3-printed.scad
//   openscad -D 'piece="lid"'  -o tune-button-c3-lid.stl  tune-button-c3-printed.scad
//   openscad tune-button-c3-printed.scad                     (assembly preview)
//
// The lid STL comes out upside down, ready to print: its top face goes on the bed, and the skirt,
// bosses and posts grow up from it. The base prints floor down. Neither needs supports. Use
// 0.2 mm layers and 3+ perimeters for the bosses.
//
// The plate is 1.5 mm, the thickness the MX clips are made for. Its top is 5.0 mm above the
// board's key face, as in the stack. There is no bezel: the keycaps stand clear of a flat top.
// A bezel above the plate would have to print either as a separate part or over a 38 mm bridge.

include <stack.scad>
variant = "c3";      // the data in stack.scad is selected by this
part = "none";       // stack.scad draws nothing of its own

piece = "assembly";  // "base" | "lid" | "assembly" | "none"
mx_hole = 14.1;      // FDM holes print slightly small; 14.0 is the nominal MX plate hole

/* [Shell] */
pwall = 5.5;          // walls; thick enough for an insert boss to clear the board's corner
floor_t = 2.0;
plate_t = 1.5;        // MX plate
plate_top_z = key_face_z + 5.0;           // 21.0: the case's top face
plate_z = plate_top_z - plate_t;          // plate underside: 19.5
part_z = 15.0;        // where lid meets base; the lid's corners are 6 mm thick
fence_h = 3.0;
fence_t = 1.2;
gapf = 0.3;           // print clearance

/* [M3 hardware] */
screw_len = 8;               // M3 x 8 socket head cap screw (ISO 4762)
screw_clear = 3.4;
screw_head = [6.2, 3.2];     // counterbore: the 5.5 x 3.0 head, plus clearance
insert_hole = 4.0;           // for the common M3 x 5.7 x 4.6 OD insert; check your insert's spec
insert_depth = 7.0;          // hole depth, past the insert for the screw tip and melt
boss_d = 7.6;                // corner bosses, base and lid

pinner = bbox(cavity);                                    // same cavity as the acrylic rings
pouter = [pinner[0] - pwall, pinner[1] - pwall, pinner[2] + pwall, pinner[3] + pwall];
pr = 3.0;
ci = 3.6;             // corner centres, inset from the outer edges
pscrews = [[pouter[0] + ci, pouter[1] + ci], [pouter[0] + ci, pouter[3] - ci],
           [pouter[2] - ci, pouter[3] - ci]];
// The top-right corner is ~5 mm from the module's antenna: no steel screw or brass insert there.
ppeg = [pouter[2] - ci, pouter[1] + ci];
peg_d = 3.0;
peg_h = 4.0;
corners = concat(pscrews, [ppeg]);

lid_h = plate_top_z - part_z;                     // 6.0
engage = screw_len - (lid_h - screw_head[1]);     // screw length below the lid: 5.2

module pout2d() rect(pouter, pr);
module pin2d() rect(pinner, 0.5);
module corner_bosses(h) intersection() {
    linear_extrude(height = h) top_view() pout2d();
    for (c = corners) translate([c[0], -c[1], 0]) cylinder(d = boss_d, h = h);
}
// USB-C opening, the same as the stack's; the parting line runs through it, so each part takes
// a notch open at its edge, and neither has to bridge.
module usb_cut() translate([0, 0, usb[3] - usb_slot[1] / 2]) linear_extrude(height = usb_slot[1])
    top_view() rect([usb[0] - usb_slot[0] / 2, usb[2], usb[0] + usb_slot[0] / 2, pouter[3] + 1]);

module base() {
    difference() {
        union() {
            difference() {
                linear_extrude(height = part_z) top_view() pout2d();
                translate([0, 0, floor_t]) linear_extrude(height = part_z) top_view() pin2d();
            }
            corner_bosses(part_z);
            // board spacers, from the floor to the board's underside, with pins for its holes
            for (s = spacers) translate([s[0], -s[1], floor_t]) {
                cylinder(d = spacer_d, h = board_bottom_z - floor_t);
                translate([0, 0, board_bottom_z - floor_t]) cylinder(d = pin_d, h = pin_h, $fn = 24);
            }
            translate([0, 0, floor_t]) linear_extrude(height = fence_h) top_view() difference() {
                rect([cell[0] - fence_t, cell[1] - fence_t, cell[2] + fence_t, cell[3] + fence_t], 1);
                rect(cell, 0.5);
            }
        }
        usb_cut();
        for (s = pscrews) translate([s[0], -s[1], part_z - insert_depth]) cylinder(d = insert_hole, h = insert_depth + 1);
        translate([ppeg[0], -ppeg[1], part_z - peg_h - 0.5]) cylinder(d = peg_d + 2 * gapf, h = peg_h + 1);
    }
}

// The lid in its assembled orientation, z = 0 at the parting line.
module lid() {
    difference() {
        union() {
            translate([0, 0, plate_z - part_z]) linear_extrude(height = plate_t) top_view() pout2d();
            linear_extrude(height = plate_z - part_z) top_view() difference() { pout2d(); pin2d(); }
            corner_bosses(plate_z - part_z);
            // posts down to the board's key face, over the spacers: they clamp the board
            for (s = spacers) translate([s[0], -s[1], key_face_z - part_z])
                cylinder(d = spacer_d, h = plate_z - key_face_z + 0.01);
            translate([ppeg[0], -ppeg[1], -peg_h]) cylinder(d = peg_d, h = peg_h + 0.01);
        }
        translate([0, 0, -part_z]) usb_cut();
        for (c = keys) translate([c[0], -c[1], -1]) linear_extrude(height = lid_h + 2)
            square(mx_hole, center = true);
        for (l = leds) translate([l[0], -l[1], -1]) cylinder(d = led_hole, h = lid_h + 2);
        for (s = pscrews) translate([s[0], -s[1], 0]) {
            translate([0, 0, -1]) cylinder(d = screw_clear, h = lid_h + 2);
            translate([0, 0, lid_h - screw_head[1]]) cylinder(d = screw_head[0], h = 5);
        }
    }
}

echo(str("PRINTED c3: outside ", pouter[2] - pouter[0], " x ", pouter[3] - pouter[1], " x ", plate_top_z,
         " mm; 3 x M3 x ", screw_len, " SHCS, ", engage, " mm into the inserts"));

if (piece == "base") base();
else if (piece == "lid") translate([0, 0, lid_h]) rotate([180, 0, 0]) lid();   // top face on the bed
else if (piece == "assembly") {
    color("#d0d4dc") base();
    color("#4a4f58", 0.85) translate([0, 0, part_z]) lid();
    board3d();
}
