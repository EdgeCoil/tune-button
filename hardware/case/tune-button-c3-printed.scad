// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: CERN-OHL-S-2.0
//
// Printed case for the c3 four-key board: a base (floor, walls, board spacers, cell fence) and a top
// (MX plate and bezel in one), with three M2 self-tapping screws from above. The board layout,
// heights, cell, pockets and USB-C slot come from stack.scad, so this case and the acrylic one fit the
// board the same way.
//
//   openscad -D 'piece="base"' -o tune-button-c3-base.stl tune-button-c3-printed.scad
//   openscad -D 'piece="top"'  -o tune-button-c3-top.stl  tune-button-c3-printed.scad
//   openscad tune-button-c3-printed.scad                     (assembly preview)
//
// Print the base floor down and the top plate side down (bezel up): no supports. The USB-C slot
// is a 13 mm bridge. 0.2 mm layers, 3+ perimeters for the screw bosses.
//
// The plate is 1.5 mm, the thickness the MX clips are made for, so the switches latch (unlike the
// 3 mm acrylic plate). Its top is 5.0 mm above the board's key face, as in the stack.

include <stack.scad>
variant = "c3";      // the data in stack.scad is selected by this
part = "none";       // stack.scad draws nothing of its own

piece = "assembly";  // "base" | "top" | "assembly"
mx_hole = 14.1;      // FDM holes print slightly small; 14.0 is the nominal MX plate hole

/* [Printed shell] */
pwall = 4.0;          // wall; the corners carry the screw bosses
floor_t = 2.0;
plate_t = 1.5;        // MX plate
bezel_t = 3.0;        // matches the stack's bezel
plate_top_z = key_face_z + 5.0;           // 21.0
plate_z = plate_top_z - plate_t;          // the base's walls end here: 19.5
fence_h = 3.0;
fence_t = 1.2;
screw_pilot = 1.6;    // M2 self-tapping
screw_clear = 2.4;
screw_head = [4.4, 1.6];   // counterbore in the bezel: diameter, depth
screw_depth = 9;      // pilot depth into the base from its top
gapf = 0.3;           // print clearance

pinner = bbox(cavity);                                    // same cavity as the acrylic rings
pouter = [pinner[0] - pwall, pinner[1] - pwall, pinner[2] + pwall, pinner[3] + pwall];
pr = 3.0;
ci = 2.2;             // screw inset from the outer edges
pscrews = [[pouter[0] + ci, pouter[1] + ci], [pouter[0] + ci, pouter[3] - ci],
           [pouter[2] - ci, pouter[3] - ci]];
// The top-right corner is ~4 mm from the module's antenna: no metal screw there. A printed peg on
// the top drops into a socket in the base instead.
ppeg = [pouter[2] - ci, pouter[1] + ci];
peg_d = 2.6;
peg_h = 4.0;

module pout2d() rect(pouter, pr);

module base() {
    difference() {
        union() {
            // floor and walls, up to the plate
            difference() {
                linear_extrude(height = plate_z) top_view() pout2d();
                translate([0, 0, floor_t]) linear_extrude(height = plate_z) top_view() rect(pinner, 0.5);
            }
            // corner bosses, filling the cavity's corners down to the floor
            intersection() {
                linear_extrude(height = plate_z) top_view() pout2d();
                for (s = concat(pscrews, [ppeg])) translate([s[0], -s[1], 0])
                    cylinder(d = 2 * ci + 2.4, h = plate_z);
            }
            // board spacers with locating pins, from the floor
            for (s = spacers) translate([s[0], -s[1], floor_t]) {
                cylinder(d = spacer_d, h = board_bottom_z - floor_t - 0.1);
                translate([0, 0, board_bottom_z - floor_t - 0.1]) cylinder(d = pin_d, h = pin_h, $fn = 24);
            }
            // cell fence
            translate([0, 0, floor_t]) linear_extrude(height = fence_h) top_view() difference() {
                rect([cell[0] - fence_t, cell[1] - fence_t, cell[2] + fence_t, cell[3] + fence_t], 1);
                rect(cell, 0.5);
            }
        }
        // USB-C slot, the same opening as the acrylic stack's
        translate([0, 0, usb[3] - usb_slot[1] / 2]) linear_extrude(height = usb_slot[1]) top_view()
            rect([usb[0] - usb_slot[0] / 2, usb[2], usb[0] + usb_slot[0] / 2, pouter[3] + 1]);
        // screw pilots and the peg socket
        for (s = pscrews) translate([s[0], -s[1], plate_z - screw_depth]) cylinder(d = screw_pilot, h = screw_depth + 1);
        translate([ppeg[0], -ppeg[1], plate_z - peg_h - 0.5]) cylinder(d = peg_d + 2 * gapf, h = peg_h + 1);
    }
}

module top() {
    difference() {
        union() {
            linear_extrude(height = plate_t) top_view() pout2d();                   // plate
            translate([0, 0, plate_t]) linear_extrude(height = bezel_t) top_view()  // bezel
                difference() { pout2d(); key_opening(); }
            translate([ppeg[0], -ppeg[1], -peg_h]) cylinder(d = peg_d, h = peg_h + 0.01);
        }
        for (c = keys) translate([c[0], -c[1], -1]) linear_extrude(height = plate_t + 2)
            square(mx_hole, center = true);
        for (l = leds) translate([l[0], -l[1], -1]) cylinder(d = led_hole, h = plate_t + bezel_t + 2);
        for (s = pscrews) translate([s[0], -s[1], 0]) {
            translate([0, 0, -1]) cylinder(d = screw_clear, h = 10);
            translate([0, 0, plate_t + bezel_t - screw_head[1]]) cylinder(d = screw_head[0], h = 5);
        }
    }
}

echo(str("PRINTED c3: outside ", pouter[2] - pouter[0], " x ", pouter[3] - pouter[1], " x ",
         plate_top_z + bezel_t, " mm; 3 x M2 self-tapping, about ", plate_t + bezel_t + screw_depth - 1, " mm long"));

if (piece == "base") base();
else if (piece == "top") top();
else if (piece == "assembly") {
    color("#d0d4dc") base();
    color("#4a4f58", 0.85) translate([0, 0, plate_z]) top();
    board3d();
}
