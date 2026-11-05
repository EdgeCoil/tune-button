// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: CERN-OHL-S-2.0
//
// Printed cases for the two MX boards, c3 and xiao, with M3 hardware:
//   base  floor, walls, four board spacers with locating pins, a cell fence, and M3 heat-set
//         inserts in the corners
//   lid   the MX plate as the top face, with a skirt, corner bosses, and posts underneath that
//         press the board down onto the spacers at its mounting holes
//   hood  xiao only: the cover over the XIAO, which stands 13 mm above the board. Open at the
//         front, like the stack's visor. A pocket under its roof takes the XIAO's FPC antenna.
// M3 x 8 socket head cap screws go down into the inserts: through the lid's corners, and on xiao
// through the hood's two back corners, which pass down through notches in the lid. On c3 the
// corner next to the module's antenna has a printed peg instead of a screw and insert.
//
// The board layout, heights, cell, pockets and USB-C slot come from stack.scad, so these cases and
// the acrylic ones hold each board in the same place.
//
//   openscad -D 'variant="c3"' -D 'piece="base"' -o tune-button-c3-base.stl tune-button-printed.scad
//   (pieces: base, lid, hood; no piece: the assembly preview)
//
// The lid and hood STLs come out upside down, ready to print: the lid's top face and the hood's
// roof go on the bed. The base prints floor down. None needs supports. Use 0.2 mm layers and 3+
// perimeters for the bosses.
//
// The plate is 1.5 mm, the thickness the MX clips are made for. Its top is 5.0 mm above the
// board's key face, as in the stack. There is no bezel: the keycaps stand clear of a flat top.
// A bezel above the plate would have to print either as a separate part or over a 38 mm bridge.

include <stack.scad>
variant = "c3";      // the data in stack.scad is selected by this
part = "none";       // stack.scad draws nothing of its own

piece = "assembly";  // "base" | "lid" | "hood" | "assembly" | "none"
// How the switches meet the plate:
//   "over"  the switches are soldered to the board first and the lid goes down over them, so the
//           holes clear the switch's widest part (16.3 mm, measured on the board's switches; 15.6 is the
//           spec top housing, but these measure wider), plus 0.15 a side. The posts clamp the
//           board; the plate doesn't hold the switches.
//   "clip"  the switches are clipped into the plate first and soldered through it (the MX way):
//           14.0 nominal, 14.1 because FDM prints holes small.
mx_fit = "over";
// Not mx_hole: stack.scad (included above) already sets that, and OpenSCAD evaluates a reassigned
// variable at its FIRST assignment, before mx_fit exists, so the "over" size was silently 14.1.
pmx_hole = mx_fit == "over" ? 16.6 : 14.1;

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

/* [Chamfers and fillets, for printing] */
bed_c = 0.6;          // outer edge on the bed (both parts): takes up elephant foot
seam_c = 0.4;         // outer edges at the parting line: a small V hides any step between the parts
root_f = 1.0;         // fillet where spacers and posts meet the floor and plate
lead_c = 0.5;         // lead-ins: insert holes, peg and socket
pin_c = 0.3;          // pin tips, into the board's holes
mx_c = 0.3;           // MX holes at the top face (the switch flange is 15.6, so 0.45 still bears)
mx_relief = 1.0;      // corner reliefs: a printed square hole has rounded corners the switch's
                      // square body jams on; a circle this wide at each corner clears them
membrane = 0.2;       // one layer over each screw hole at the head seat, so the seat bridges
                      // cleanly; push it out with a 3 mm drill or a hot awl

pinner = bbox(cavity);                                    // same cavity as the acrylic rings
pouter = [pinner[0] - pwall, pinner[1] - pwall, pinner[2] + pwall, pinner[3] + pwall];
pr = 3.0;
ci = 3.6;             // corner centres, inset from the outer edges
TL = [pouter[0] + ci, pouter[1] + ci]; TR = [pouter[2] - ci, pouter[1] + ci];
BL = [pouter[0] + ci, pouter[3] - ci]; BR = [pouter[2] - ci, pouter[3] - ci];
// c3: the top-right corner is ~5 mm from the module's antenna: no steel screw or brass insert
// there, but a printed peg. xiao: the FPC antenna under the hood's roof is ~9 mm from TL and TR.
pscrews = variant == "c3" ? [TL, BL, BR] : [TL, TR, BL, BR];
has_peg = variant == "c3";
ppeg = TR;
peg_d = 3.0;
peg_h = 4.0;
corners = has_peg ? concat(pscrews, [ppeg]) : pscrews;

/* [xiao: the hood] */
xiao = variant == "xiao";
hood_y = hood[3];                     // the hood covers y < hood_y; the lid's plate starts there
hood_top = N * t;                     // 33, the stack's visor height
cap_t = 3.0;
cap_z = hood_top - cap_t;             // roof underside, 1 mm over the XIAO's USB-C
hood_screws = xiao ? [TL, TR] : [];   // through the hood, down through notches in the lid
lid_screws = xiao ? [BL, BR] : pscrews;
// The XIAO ESP32C3's FPC antenna: 40 x 20 mm (ESTIMATE, from a supplier's spec sheet; measure
// yours), on an 80 mm lead. Its pocket is centred under the roof, away from the screws.
antenna = [40.5, 20.5, 0.4];          // pocket: x, y, depth
antenna_c = [(hood[0] + hood[2]) / 2, (hood[1] + hood_y) / 2];
// The two spacers under the hood are clamped by brackets on the inside of the hood's back wall,
// not by posts from the roof, so the roof is clear for the antenna. Each bracket's top slopes at
// 45 degrees up to the wall, so it prints without support with the hood roof-down.
bracket_d = 4.4;                      // R3 sits at the edge of H2's 5 mm courtyard

lid_h = plate_top_z - part_z;                     // 6.0
engage = screw_len - (lid_h - screw_head[1]);     // screw length below the lid: 5.2

module pout2d() rect(pouter, pr);
module pin2d() rect(pinner, 0.5);
// The outside of a part: the outline extruded to h, chamfered cb at the bottom and ct at the top.
// The outline is convex, so a hull of slices gives the chamfers.
module outer3d(h, cb, ct) hull() {
    linear_extrude(height = 0.01) top_view() offset(r = -cb) pout2d();
    translate([0, 0, cb]) linear_extrude(height = h - cb - ct) top_view() pout2d();
    translate([0, 0, h - 0.01]) linear_extrude(height = 0.01) top_view() offset(r = -ct) pout2d();
}
module corner_bosses(h, cb, ct) bosses_at(corners, h, cb, ct);
// A concave fillet of radius f round a cylinder of radius r, standing on z = 0.
module root_fillet(r, f) rotate_extrude() difference() {
    translate([r - 0.01, 0]) square([f + 0.01, f]);
    translate([r + f, f]) circle(r = f);
}
// A pin or peg of diameter d and height h, its tip chamfered c.
module tipped(d, h, c, fn = 64) {
    cylinder(d = d, h = h - c, $fn = fn);
    translate([0, 0, h - c - 0.001]) cylinder(d1 = d, d2 = d - 2 * c, h = c, $fn = fn);
}
// A hole's countersunk lead-in at z = 0, widening by c each side, opening upwards.
module lead_in(d, c) translate([0, 0, -c]) cylinder(d1 = d, d2 = d + 2 * c + 0.02, h = c + 0.01);
// USB-C opening, the same as the stack's; the parting line runs through it, so each part takes
// a notch open at its edge, and neither has to bridge.
module usb_cut() translate([0, 0, usb[3] - usb_slot[1] / 2]) linear_extrude(height = usb_slot[1])
    top_view() rect([usb[0] - usb_slot[0] / 2, usb[1] > 0 ? usb[2] : pouter[1] - 1,
                     usb[0] + usb_slot[0] / 2, usb[1] > 0 ? pouter[3] + 1 : usb[2]]);
module bosses_at(cs, h, cb, ct) intersection() {
    outer3d(h, cb, ct);
    for (c = cs) translate([c[0], -c[1], 0]) cylinder(d = boss_d, h = h);
}
// A screw's way through a part whose boss bottom is at z = 0: clearance hole, then a membrane,
// then the head's counterbore from z = seat up.
module screw_way(seat) {
    translate([0, 0, -1]) cylinder(d = screw_clear, h = seat - membrane + 1);
    translate([0, 0, seat]) cylinder(d = screw_head[0], h = 50);
}

// One MX switch hole through a plate of height h, top face at z = h: the square, its corner
// reliefs, and the chamfer on the top face (the bed face as printed, where the first layer squashes).
module mx_cut(h, hole = pmx_hole) {
    translate([0, 0, -1]) linear_extrude(height = h + 2) {
        square(hole, center = true);
        for (x = [-1, 1], y = [-1, 1]) translate([x, y] * hole / 2) circle(d = mx_relief, $fn = 16);
    }
    translate([0, 0, h + 0.01]) mirror([0, 0, 1])
        linear_extrude(height = mx_c + 0.01, scale = hole / (hole + 2 * mx_c))
        square(hole + 2 * mx_c, center = true);
}

module base() {
    difference() {
        union() {
            difference() {
                outer3d(part_z, bed_c, seam_c);
                translate([0, 0, floor_t]) linear_extrude(height = part_z) top_view() pin2d();
            }
            corner_bosses(part_z, bed_c, seam_c);
            // board spacers, from the floor to the board's underside, with pins for its holes
            for (s = spacers) translate([s[0], -s[1], floor_t]) {
                cylinder(d = spacer_d, h = board_bottom_z - floor_t);
                root_fillet(spacer_d / 2, root_f);
                translate([0, 0, board_bottom_z - floor_t - 0.01]) tipped(pin_d, pin_h + 0.01, pin_c, 24);
            }
            translate([0, 0, floor_t]) linear_extrude(height = fence_h) top_view() difference() {
                rect([cell[0] - fence_t, cell[1] - fence_t, cell[2] + fence_t, cell[3] + fence_t], 1);
                rect(cell, 0.5);
            }
        }
        usb_cut();
        for (s = pscrews) translate([s[0], -s[1], 0]) {
            translate([0, 0, part_z - insert_depth]) cylinder(d = insert_hole, h = insert_depth + 1);
            translate([0, 0, part_z]) lead_in(insert_hole, lead_c);
        }
        if (has_peg) translate([ppeg[0], -ppeg[1], 0]) {
            translate([0, 0, part_z - peg_h - 0.5]) cylinder(d = peg_d + 2 * gapf, h = peg_h + 1);
            translate([0, 0, part_z]) lead_in(peg_d + 2 * gapf, lead_c);
        }
    }
}

// The lid in its assembled orientation, z = 0 at the parting line.
module lid() {
    difference() {
        union() {
            difference() {     // plate and skirt
                outer3d(lid_h, seam_c, bed_c);
                translate([0, 0, -1]) linear_extrude(height = plate_z - part_z + 1) top_view() pin2d();
            }
            bosses_at(has_peg ? concat(lid_screws, [ppeg]) : lid_screws, plate_z - part_z + 0.01, seam_c, 0);
            // posts down to the board's key face, over the spacers: they clamp the board
            for (s = spacers) if (!xiao || s[1] > hood_y) translate([s[0], -s[1], 0]) {
                translate([0, 0, key_face_z - part_z]) cylinder(d = spacer_d, h = plate_z - key_face_z + 0.01);
                translate([0, 0, plate_z - part_z + 0.01]) mirror([0, 0, 1]) root_fillet(spacer_d / 2, root_f);
            }
            if (has_peg) translate([ppeg[0], -ppeg[1], 0.01]) mirror([0, 0, 1]) tipped(peg_d, peg_h + 0.01, lead_c);
        }
        if (xiao) {
            // under the hood the lid is only its walls: the plate is open over the XIAO, and J4's
            // pins stand through a relief just in front of it
            translate([0, 0, -1]) linear_extrude(height = lid_h + 2) top_view() { rect(hood, 0.5); rect(hood_relief, 0.5); }
            // the back wall is the hood's (the notches would cut it off from the lid)
            translate([0, 0, -1]) linear_extrude(height = lid_h + 2) top_view()
                rect([pouter[0] - 1, pouter[1] - 1, pouter[2] + 1, pinner[1]]);
            // notches for the hood's corner bosses
            for (c = hood_screws) translate([c[0], -c[1], -1]) cylinder(d = boss_d + 2 * gapf, h = lid_h + 2);
        }
        translate([0, 0, -part_z]) usb_cut();
        for (c = keys) translate([c[0], -c[1], 0]) mx_cut(lid_h);
        for (l = leds) translate([l[0], -l[1], -1]) cylinder(d = led_hole, h = lid_h + 2);
        for (c = lid_screws) translate([c[0], -c[1], 0]) screw_way(lid_h - screw_head[1]);
    }
}

// xiao: the hood, in assembled coordinates. Its side walls sit on the lid's; its back wall and two
// corner bosses go down to the base (the bosses through notches in the lid), and the screws
// through them clamp the hood and the back of the lid. Brackets on the back wall clamp the board.
module band3d(z0, z1) translate([0, 0, z0]) linear_extrude(height = z1 - z0) top_view()
    rect([pouter[0] - 1, pouter[1] - 1, pouter[2] + 1, hood_y]);
module hood() {
    difference() {
        union() {
            difference() {
                intersection() { translate([0, 0, plate_top_z]) outer3d(hood_top - plate_top_z, 0, bed_c);
                                 band3d(plate_top_z, hood_top); }
                translate([0, 0, plate_top_z - 1]) linear_extrude(height = cap_z - plate_top_z + 1)
                    top_view() rect(hood, 0.5);
            }
            intersection() { translate([0, 0, part_z]) bosses_at(hood_screws, hood_top - part_z, seam_c, bed_c);
                             band3d(part_z, hood_top); }
            // the back wall's lower part, down to the base
            intersection() {
                translate([0, 0, part_z]) outer3d(plate_top_z - part_z + 0.01, seam_c, 0);
                translate([0, 0, part_z]) linear_extrude(height = plate_top_z - part_z + 0.01) top_view()
                    rect([pouter[0] - 1, pouter[1] - 1, pouter[2] + 1, pinner[1]]);
            }
            // brackets down to the board's key face, over the two spacers under the hood
            for (sp = spacers) if (sp[1] < hood_y) top_view() hull() {
                translate([0, 0, key_face_z]) linear_extrude(height = plate_top_z - key_face_z) hull() {
                    translate(sp) circle(d = bracket_d);
                    rect([sp[0] - bracket_d / 2, pinner[1] - 1.5, sp[0] + bracket_d / 2, pinner[1]]);
                }
                translate([0, 0, plate_top_z + (sp[1] + bracket_d / 2 - pinner[1])]) linear_extrude(height = 0.01)
                    rect([sp[0] - bracket_d / 2, pinner[1] - 1.5, sp[0] + bracket_d / 2, pinner[1]]);
            }
        }
        usb_cut();
        for (c = hood_screws) translate([c[0], -c[1], part_z]) screw_way(lid_h - screw_head[1]);
        // the antenna's pocket, under the roof
        translate([antenna_c[0], -antenna_c[1], cap_z - 0.01]) linear_extrude(height = antenna[2] + 0.01)
            square([antenna[0], antenna[1]], center = true);
        // the roof's open front edge is on the bed when printing: chamfer it as the others are
        translate([pouter[0] - 1, 0, 0]) rotate([90, 0, 90]) linear_extrude(height = pouter[2] - pouter[0] + 2)
            polygon([[-hood_y - 0.01, hood_top + 0.01], [-hood_y + bed_c, hood_top + 0.01], [-hood_y - 0.01, hood_top - bed_c]]);
    }
}

top_z = xiao ? hood_top : plate_top_z;
echo(str("PRINTED ", variant, ": outside ", pouter[2] - pouter[0], " x ", pouter[3] - pouter[1], " x ", top_z,
         " mm; ", len(pscrews), " x M3 x ", screw_len, " SHCS, ", engage, " mm into the inserts"));

if (piece == "base") base();
else if (piece == "lid") translate([0, 0, lid_h]) rotate([180, 0, 0]) lid();   // top face on the bed
else if (piece == "hood" && xiao) translate([0, 0, hood_top]) rotate([180, 0, 0]) hood();   // roof on the bed
else if (piece == "assembly") {
    color("#d0d4dc") base();
    color("#4a4f58", 0.85) translate([0, 0, part_z]) lid();
    if (xiao) color("#6a7080", 0.85) hood();
    board3d();
}
