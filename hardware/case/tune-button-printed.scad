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
//   openscad -D 'variant="c3"' -D big_button=true -D 'piece="tower"' -o tune-button-c3-btn-tower.stl tune-button-printed.scad
//   (big_button pieces: base, lid, tower)
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
//           spec top housing, but these measure wider). 16.8 is the size the gauge print passed them easily. The posts clamp the
//           board; the plate doesn't hold the switches.
//   "clip"  the switches are clipped into the plate first and soldered through it (the MX way):
//           14.0 nominal, 14.1 because FDM prints holes small.
mx_fit = "over";
// Not mx_hole: stack.scad (included above) already sets that, and OpenSCAD evaluates a reassigned
// variable at its FIRST assignment, before mx_fit exists, so the "over" size was silently 14.1.
pmx_hole = mx_fit == "over" ? 16.8 : 14.1;

// c3 only: big_button = true makes the big-button variant. The case grows to the left (seen from
// above, USB-C at the bottom) into a tower that takes a 22 mm panel-mount push button beside the
// keys, with a 502535 cell on the floor beside it, under the lid. The cell no longer sits under the
// board, so the board drops 6.4 mm and the case is thin over the keys and the cell, stepping up
// only round the button.
// Fit no header at TP1 on this variant: it would hang 8.5 mm below the board. Solder wires to its
// pads instead.
big_button = false;
bigb = big_button && variant == "c3";
// New names, not reassignments of stack.scad's (see pmx_hole above).
pboard_bottom_z = bigb ? 8.0 : board_bottom_z;   // floor 2.0 + the battery socket J2, 4.8, + 1.2
pkey_face_z = pboard_bottom_z + 1.6;
pusb_z = bigb ? pboard_bottom_z - 1.63 : usb[3]; // J1 hangs 3.26 below the board

/* [big_button: the button and the tower] */
btn_hole = 22.4;      // the 22 mm cut-out; FDM prints holes small
btn_depth = 26.0;     // the button below the panel's top face, terminals included
btn_nut_d = 28.5;     // measured: the nut at its widest
btn_head_d = 30.0;    // measured: the head, above the roof
btn_body_d = 26.0;    // ESTIMATE: anything below the nut, switch block and terminals
btn_wire = 3.0;       // under the terminals, for the wires
panel_t = 2.5;        // the tower roof the button clamps on; check your button's panel range
tower_top = 2.0 + btn_wire + btn_depth;   // 31: floor, wire room, button
step_x = -8.0;        // the tower's inner right face; the riser wall stands on the lid from here
riser_t = 2.0;
joint_gap = 0.2;      // between the lid's left end and the tower's walls
// Clear of the battery plug at the board's left edge (it reaches x = -6.5, and its lead leaves to
// the left): the body's right side is 4 mm past it. Its y (btn_c, below) centres it front to back
// on the tower's top face.
btn_x = -6.5 - 4 - btn_body_d / 2;
tower_x0 = btn_x - btn_nut_d / 2 - 1;
// 502535 (25 x 35 x 5, plus slack), lying along the far wall, past the button's body.
pcell = bigb ? [tower_x0, 3.0, tower_x0 + 35 + cell_slack, 3.0 + 25 + cell_slack] : cell;
// The tower covers only the button's corner: its inner back face is just past the cell's fence,
// and behind that the lid runs on over the cell. The riser stands on the lid along both inner edges.
step_y = 30.3;        // board y

/* [raven: the tower as a raven's head] */
// raven = true (with big_button): the tower is the head and the button its eye. A beak runs off the
// tower's right face along the front of the lid, past the keys. It is part of the tower and sits on
// the lid. Printed roof down, the beak's top is an underside, so its sides stay steep (a raven's
// bill is narrow with a sharp ridge on top): every face is 45 degrees or steeper, so no supports.
raven = false;
rvn = bigb && raven;
beak_y = 69.5;        // board y of the beak's centre line: past the keys it clears the keycaps'
                      // travel (to y 64.05) by 1.5 mm
// stations along the beak, from the tower's right face: [x out, ridge height above the lid,
// half width at the lid]; the first is inside the riser, joining the two. The ridge drops faster at the end, into the bill's hooked tip.
beak = [[-14, 12.0, 5.6], [-6, 11.0, 5.5], [0, 10.2, 5.0], [10, 8.0, 4.0], [19, 5.6, 2.9], [25, 3.4, 1.8],
        [28.5, 1.4, 0.8], [30, 0.4, 0.3]];
// The head rises from the tower's footprint on the lid and rounds inward to its crown. Printed roof
// down, its sides may lean in at most 45 degrees, so it is near upright at the bottom and leans most
// just under the crown. head_prof: [height above the lid, blend 0..1 from footprint to crown];
// head_in: how far each side comes in at blend 1 (left, back, right, front); head_r: the crown's
// corner radius at blend 1. The steepest corner comes in 11.6 mm at blend 1, so the blend's rate
// times 11.6 is its lean: here it goes from 0.25 at the lid to 0.95 at the crown (under 45 deg).
// One slice sits at the roof's underside (13.9), so the button's panel stays panel_t thick.
function head_t(z) = (0.25 * z + 0.35 * z * z / 16.4) / 11.6;
head_prof = [for (z = concat([for (i = [0 : 11]) 13.9 * i / 11], [15.15, 16.4])) [z, head_t(z)]];
head_in = [2.75, 5.2, 0, 5.2];
head_r = 14;
head_wall = 2.0;
// The tower's screws come up from under the base into inserts in the tower, so the head has no
// holes in it. tseat: the heads' seat in the base, for the same 5.2 mm engagement as the others.
eye_ring = [15.4, 16.0, 0.6];         // a groove round the button's head: inner, outer radius, depth

/* [Shell] */
pwall = 5.5;          // walls; thick enough for an insert boss to clear the board's corner
floor_t = 2.0;
plate_t = 1.5;        // MX plate
plate_top_z = pkey_face_z + 5.0;          // 21.0 (big_button 14.6): the top face over the keys
plate_z = plate_top_z - plate_t;          // plate underside: 19.5
part_z = plate_top_z - 6.0;   // where lid meets base (15.0); the lid's corners are 6 mm thick
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

pinner_s = bbox(cavity);                                  // same cavity as the acrylic rings
pinner = bigb ? [tower_x0, pinner_s[1], pinner_s[2], pinner_s[3]] : pinner_s;
pouter = [pinner[0] - pwall, pinner[1] - pwall, pinner[2] + pwall, pinner[3] + pwall];
pr = 3.0;
// the button, centred front to back on the tower's top face (riser's back edge to the front wall)
btn_c = [btn_x, (step_y - riser_t + pouter[3]) / 2];
ci = 3.6;             // corner centres, inset from the outer edges
// big_button: the tower's far corners sit further in. Their counterbores are 20 mm shafts down
// the tower, and at 3.6 the shaft leaves ~0.5 mm to the corner, which the slicer drops on the
// roof's first layer (as it did on the lid's corners); a slot out through the corner would run the
// tower's full height.
cif = bigb ? 5.0 : ci;
TL = [pouter[0] + cif, pouter[1] + cif]; TR = [pouter[2] - ci, pouter[1] + ci];
BL = [pouter[0] + cif, pouter[3] - cif]; BR = [pouter[2] - ci, pouter[3] - ci];
// c3: the top-right corner is ~5 mm from the module's antenna: no steel screw or brass insert
// there, but a printed peg. xiao: the FPC antenna under the hood's roof is ~9 mm from TL and TR.
// big_button: TM, mid back wall, holds the lid's long back edge. The tower has four: BL, BM at its
// front right corner, LM on the left wall just inside its back face, clear of the cell's fence and
// 5.6 mm clear of the nut (as a circle across its corners), and RM in its inner back corner.
TM = [step_x - boss_d / 2 - 0.3, pouter[1] + ci]; BM = [TM[0], pouter[3] - (rvn ? cif : ci)];
LM = [pouter[0] + cif, step_y + boss_d / 2 + 0.3];
// RM: the tower's inner back corner, its boss tangent to both riser faces (and 0.2 clear of the
// lid's cut edges below them). In the base it is joined to the cell's fence by a web.
RM = [step_x - boss_d / 2, step_y + boss_d / 2];
pscrews = bigb ? [TL, LM, BL, TM, BM, RM, BR] : variant == "c3" ? [TL, BL, BR] : [TL, TR, BL, BR];
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
lid_screws = xiao ? [BL, BR] : bigb ? [TL, TM, BR] : pscrews;
tower_screws = bigb ? [LM, BL, BM, RM] : [];
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
tseat = part_z + engage - screw_len;              // raven: tower screws' heads, from below: 5.8

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
module usb_cut() translate([0, 0, pusb_z - usb_slot[1] / 2]) linear_extrude(height = usb_slot[1])
    top_view() rect([usb[0] - usb_slot[0] / 2, usb[1] > 0 ? usb[2] : pouter[1] - 1,
                     usb[0] + usb_slot[0] / 2, usb[1] > 0 ? pouter[3] + 1 : usb[2]]);
module bosses_at(cs, h, cb, ct) intersection() {
    outer3d(h, cb, ct);
    for (c = cs) translate([c[0], -c[1], 0]) cylinder(d = boss_d, h = h);
}
// A screw's way through a part whose boss bottom is at z = 0: clearance hole, then a membrane,
// then the head's counterbore from z = seat up.
// A screw's way through a corner: the clearance hole, and the head's counterbore from `seat` up.
// The counterbore leaves only ~0.5 mm of wall to the outer corner, less than the bed chamfer, so
// the slicer drops that sliver on the first layer and flags the next as floating (and a printed
// one chipped off): the counterbore opens out through the corner instead (`out`, the corner's
// direction). The head still bears on its whole seat.
module screw_way(seat, out = [0, 0]) {
    translate([0, 0, -1]) cylinder(d = screw_clear, h = seat - membrane + 1);
    translate([0, 0, seat]) hull() {
        cylinder(d = screw_head[0], h = 50);
        translate(out * 4) cylinder(d = screw_head[0], h = 50);
    }
}
// The outward direction of a corner, in the scad frame (board y runs down, scad y up).
function corner_out(c) = let(mx = (pouter[0] + pouter[2]) / 2, my = (pouter[1] + pouter[3]) / 2)
    [sign(c[0] - mx), -sign(c[1] - my)] / sqrt(2);

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
            // raven: the through bosses are wider, round their counterbores
            if (rvn) intersection() { outer3d(part_z, bed_c, seam_c);
                for (c = tower_screws) translate([c[0], -c[1], 0]) cylinder(d = 9.0, h = part_z); }
            // big_button: RM's boss stands 0.1 mm off the cell's fence; a web joins them
            if (bigb) translate([0, 0, floor_t - 0.01]) linear_extrude(height = part_z - floor_t + 0.01) top_view()
                rect([RM[0] - boss_d / 2, pcell[3], RM[0] + boss_d / 2, RM[1]]);
            // board spacers, from the floor to the board's underside, with pins for its holes
            for (s = spacers) translate([s[0], -s[1], floor_t]) {
                cylinder(d = spacer_d, h = pboard_bottom_z - floor_t);
                root_fillet(spacer_d / 2, root_f);
                translate([0, 0, pboard_bottom_z - floor_t - 0.01]) tipped(pin_d, pin_h + 0.01, pin_c, 24);
            }
            translate([0, 0, floor_t]) linear_extrude(height = fence_h) top_view() difference() {
                rect([pcell[0] - fence_t, pcell[1] - fence_t, pcell[2] + fence_t, pcell[3] + fence_t], 1);
                rect(pcell, 0.5);
            }
        }
        usb_cut();
        for (s = rvn ? lid_screws : pscrews) translate([s[0], -s[1], 0]) {
            translate([0, 0, part_z - insert_depth]) cylinder(d = insert_hole, h = insert_depth + 1);
            translate([0, 0, part_z]) lead_in(insert_hole, lead_c);
        }
        // raven: the tower's screws go up through the base, heads in counterbores from below; one
        // layer closes each counterbore's top, so it bridges (push it out as for the others)
        if (rvn) for (s = tower_screws) translate([s[0], -s[1], 0]) {
            translate([0, 0, -1]) cylinder(d = screw_head[0], h = tseat + 1);
            translate([0, 0, tseat + membrane]) cylinder(d = screw_clear, h = part_z);
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
                translate([0, 0, pkey_face_z - part_z]) cylinder(d = spacer_d, h = plate_z - pkey_face_z + 0.01);
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
        // big_button: the button's corner is the tower's, walls and all
        if (bigb) {
            translate([0, 0, -1]) linear_extrude(height = lid_h + 2) top_view()
                rect([pouter[0] - 1, step_y - joint_gap, step_x + joint_gap, pouter[3] + 1]);
            // the cut edges on the top face are on the bed when printing: chamfer them, for elephant foot
            intersection() {
                yrun(step_x + joint_gap) polygon([[-0.01, lid_h + 0.01], [bed_c, lid_h + 0.01], [-0.01, lid_h - bed_c]]);
                translate([0, 0, -1]) linear_extrude(height = lid_h + 2) top_view()
                    rect([pouter[0] - 1, step_y - joint_gap, pouter[2] + 1, pouter[3] + 1]);
            }
            intersection() {
                xrun(step_y - joint_gap) polygon([[0.01, lid_h + 0.01], [-bed_c, lid_h + 0.01], [0.01, lid_h - bed_c]]);
                translate([0, 0, -1]) linear_extrude(height = lid_h + 2) top_view()
                    rect([pouter[0] - 1, pouter[1] - 1, step_x + joint_gap, pouter[3] + 1]);
            }
            joint_vees(0, plate_top_z - part_z);
        }
        translate([0, 0, -part_z]) usb_cut();
        for (c = keys) translate([c[0], -c[1], 0]) mx_cut(lid_h);
        for (l = leds) translate([l[0], -l[1], -1]) cylinder(d = led_hole, h = lid_h + 2);
        for (c = lid_screws) translate([c[0], -c[1], 0]) screw_way(lid_h - screw_head[1], c == TM ? [0, 1] : corner_out(c));
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
                translate([0, 0, pkey_face_z]) linear_extrude(height = plate_top_z - pkey_face_z) hull() {
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

// big_button: the tower, in assembled coordinates. Its outer walls stand on the base's, left of
// the step; its riser stands on the lid's left edge and clamps it; the roof takes the button. Four
// M3 screws, down deep shafts, clamp it to the base. Printed roof down.
module xband3d(x0, x1, z0, z1) translate([0, 0, z0]) linear_extrude(height = z1 - z0) top_view()
    rect([x0, pouter[1] - 1, x1, pouter[3] + 1]);
// A 2D profile in (x, z), placed at x and run the full length of the case in y.
module yrun(x) translate([x, -pouter[1] + 1, 0]) rotate([90, 0, 0])
    linear_extrude(height = pouter[3] - pouter[1] + 2) children();
// The same in (board y, z), placed at board y and run the full width of the case in x. Profile x
// is board y: positive runs toward the USB end.
module xrun(y) translate([pouter[0] - 1, -y, 0]) rotate([90, 0, 90]) mirror([1, 0, 0])
    linear_extrude(height = pouter[2] - pouter[0] + 2) children();
// V-grooves where the lid meets the tower's walls, on the two outer faces (the front face at the
// step, the left face at the back of the tower), between z0 and z1 (the part's own frame): as at
// the parting line, a small step between the parts reads as a groove.
module joint_vees(z0, z1) for (p = [[step_x + joint_gap / 2, pouter[3]], [pouter[0], step_y - joint_gap / 2]])
    translate([p[0], -p[1], (z0 + z1) / 2]) rotate([0, 0, 45])
        cube([(2 * seam_c + joint_gap) / sqrt(2), (2 * seam_c + joint_gap) / sqrt(2), z1 - z0 + 0.02], center = true);
// The tower's footprint in board coordinates: its walls (to the base) and its riser (on the lid).
twall = [pouter[0] - 1, step_y, step_x, pouter[3] + 1];
triser = [pouter[0] - 1, step_y - riser_t, step_x + riser_t, pouter[3] + 1];
tin = [pinner[0], step_y, step_x, pinner[3]];
module tband3d(r, z0, z1) translate([0, 0, z0]) linear_extrude(height = z1 - z0) top_view() rect(r);
// raven: one station of the beak, a thin triangle across y at x (assembled coordinates)
module beak_station(st) translate([step_x + riser_t + st[0], -beak_y, plate_top_z])
    rotate([90, 0, 90]) linear_extrude(height = 0.01)
        polygon([[-st[2], 0], [st[2], 0], [0, st[1]]]);
module beak3d() for (i = [0 : len(beak) - 2]) hull() { beak_station(beak[i]); beak_station(beak[i + 1]); }
// raven: the head's outline (board coordinates) at blend t, from the footprint (0) to the crown (1).
// The front-left corner is the case's own, so it keeps at least the case's corner radius.
module rrect4(b, rs) hull() for (i = [0 : 3]) {
    c = [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]][i];
    sg = [[1, 1], [-1, 1], [-1, -1], [1, -1]][i];
    translate(c + sg * rs[i]) circle(r = rs[i], $fn = 48);
}
module head2d(t) let(f = [pouter[0], step_y - riser_t, step_x + riser_t, pouter[3]], r = max(0.01, t * head_r))
    rrect4([f[0] + t * head_in[0], f[1] + t * head_in[1], f[2] - t * head_in[2], f[3] - t * head_in[3]],
           [r, r, r, max(pr, r)]);
module head_inner2d(t) intersection() { rect(tin, 0.5); offset(delta = -head_wall) head2d(t); }
module head_slice(k, inner = false) translate([0, 0, plate_top_z + head_prof[k][0] - (k == 0 && inner ? 0.01 : 0)])  // the outer starts flush with the lid's top
    linear_extrude(height = 0.01) top_view() if (inner) head_inner2d(head_prof[k][1]); else head2d(head_prof[k][1]);
module head_outer() union() {
    intersection() { translate([0, 0, part_z]) outer3d(plate_top_z - part_z + 0.02, seam_c, 0);
                     tband3d(twall, part_z, plate_top_z + 0.01); }
    for (k = [0 : len(head_prof) - 2]) hull() { head_slice(k); head_slice(k + 1); }
}
module raven_tower() {
    roof_z = tower_top - panel_t;
    difference() {
        union() { head_outer(); beak3d(); }
        // the inside: the tower's below the lid, then shrinking with the head up to the roof
        translate([0, 0, part_z - 1]) linear_extrude(height = plate_top_z - part_z + 1.01) top_view() rect(tin, 0.5);
        for (k = [0 : len(head_prof) - 2]) if (plate_top_z + head_prof[k + 1][0] <= roof_z + 0.01)
            hull() { head_slice(k, true); head_slice(k + 1, true); }
    }
    // the screw columns, roof to base, and RM's corner fill; inside the head's outline
    difference() {
        intersection() {
            head_outer();
            union() {
                for (c = tower_screws) translate([c[0], -c[1], part_z]) cylinder(d = boss_d, h = tower_top - part_z);
                tband3d([RM[0], step_y, step_x, RM[1]], part_z, tower_top);
            }
        }
        for (c = tower_screws) translate([c[0], -c[1], part_z - 0.01]) {
            cylinder(d = insert_hole, h = insert_depth);
            translate([0, 0, 0.01]) mirror([0, 0, 1]) lead_in(insert_hole, lead_c);
        }
    }
}
module tower() if (rvn) difference() {
    raven_tower();
    translate([btn_c[0], -btn_c[1], 0]) {
        translate([0, 0, tower_top - panel_t - 1]) cylinder(d = btn_hole, h = panel_t + 2, $fn = 128);
        translate([0, 0, tower_top - mx_c]) cylinder(d1 = btn_hole, d2 = btn_hole + 2 * mx_c + 0.02, h = mx_c + 0.01, $fn = 128);
    }
    translate([btn_c[0], -btn_c[1], tower_top - eye_ring[2]]) difference() {
        cylinder(r = eye_ring[1], h = eye_ring[2] + 0.01, $fn = 128);
        translate([0, 0, -0.01]) cylinder(r = eye_ring[0], h = eye_ring[2] + 0.03, $fn = 128);
    }
    joint_vees(part_z, plate_top_z);
} else plain_tower();
module plain_tower() {
    roof_z = tower_top - panel_t;
    difference() {
        union() {
            difference() {
                intersection() {
                    translate([0, 0, part_z]) outer3d(tower_top - part_z, seam_c, bed_c);
                    union() {
                        tband3d(twall, part_z, tower_top);
                        tband3d(triser, plate_top_z, tower_top);
                    }
                }
                translate([0, 0, part_z - 1]) linear_extrude(height = roof_z - part_z + 1) top_view()
                    rect(tin, 0.5);
            }
            intersection() { translate([0, 0, part_z]) bosses_at(tower_screws, tower_top - part_z, seam_c, bed_c);
                             tband3d(twall, part_z, tower_top); }
            // RM's boss fills the inner back corner, so it joins the riser along both faces
            tband3d([RM[0], step_y, step_x, RM[1]], part_z, tower_top - 0.01);
            // 45-degree fillets inside, where the roof meets the walls and the riser: the button's
            // presses go through the roof into them. root_f (1.0) is all the room the nut leaves
            // at the left wall (1.0), the riser (1.25) and the back (1.0).
            difference() {
                translate([0, 0, roof_z - root_f]) linear_extrude(height = root_f + 0.01) top_view()
                    rect(tin, 0.5);
                hull() {
                    translate([0, 0, roof_z - root_f - 0.01]) linear_extrude(height = 0.01) top_view()
                        rect(tin, 0.5);
                    translate([0, 0, roof_z]) linear_extrude(height = 0.02) top_view()
                        rect([tin[0] + root_f, tin[1] + root_f, tin[2] - root_f, tin[3] - root_f], 0.5);
                }
            }
        }
        // the button's hole, its top edge chamfered (the bed face as printed)
        translate([btn_c[0], -btn_c[1], 0]) {
            translate([0, 0, roof_z - 1]) cylinder(d = btn_hole, h = panel_t + 2, $fn = 128);
            translate([0, 0, tower_top - mx_c]) cylinder(d1 = btn_hole, d2 = btn_hole + 2 * mx_c + 0.02, h = mx_c + 0.01, $fn = 128);
        }
        for (c = tower_screws) translate([c[0], -c[1], part_z]) screw_way(lid_h - screw_head[1]);
        // the riser's top outer edges are on the bed when printing: chamfer them as the others are
        yrun(step_x + riser_t) polygon([[0.01, tower_top + 0.01], [-bed_c, tower_top + 0.01], [0.01, tower_top - bed_c]]);
        xrun(step_y - riser_t) polygon([[-0.01, tower_top + 0.01], [bed_c, tower_top + 0.01], [-0.01, tower_top - bed_c]]);
        joint_vees(part_z, plate_top_z);
    }
}

top_z = xiao ? hood_top : bigb ? tower_top : plate_top_z;
// for check-stack.py
if (bigb) echo(str("BIGBUTTON ", btn_c[0], " ", btn_c[1], " ", tower_top, " ", btn_depth, " ", btn_nut_d, " ",
                   btn_body_d, " ", panel_t, " ", pcell[0], " ", pcell[1], " ", pcell[2], " ", pcell[3]));
echo(str("PRINTED ", variant, bigb ? " big_button" : "", rvn ? " raven" : "", ": outside ", pouter[2] - pouter[0], " x ", pouter[3] - pouter[1], " x ", top_z,
         " mm; ", len(pscrews), " x M3 x ", screw_len, " SHCS, ", engage, " mm into the inserts"));

if (piece == "base") base();
else if (piece == "lid") translate([0, 0, lid_h]) rotate([180, 0, 0]) lid();   // top face on the bed
else if (piece == "hood" && xiao) translate([0, 0, hood_top]) rotate([180, 0, 0]) hood();   // roof on the bed
else if (piece == "tower" && bigb) translate([0, 0, tower_top]) rotate([180, 0, 0]) tower();  // roof on the bed
else if (piece == "assembly") {
    color("#d0d4dc") base();
    color("#4a4f58", 0.85) translate([0, 0, part_z]) lid();
    if (xiao) color("#6a7080", 0.85) hood();
    if (bigb) {
        color("#6a7080", 0.85) tower();
        color("#b8b8c8", 0.9) translate([pcell[0] + 0.5, -pcell[3] + 0.5, floor_t]) cube([pcell[2] - pcell[0] - 1, pcell[3] - pcell[1] - 1, 5]);
        translate([btn_c[0], -btn_c[1], 0]) {
            color("#c0392b") translate([0, 0, tower_top]) cylinder(d = btn_head_d, h = 6);
            color("#555") translate([0, 0, tower_top - panel_t - 4]) cylinder(d = btn_nut_d, h = 4, $fn = 6);
            color("#555") translate([0, 0, tower_top - btn_depth]) cylinder(d = 22, h = btn_depth);
        }
    }
    if (!bigb) board3d();
    else {   // stack.scad's board3d draws the stack's cell and spacers, at the stack's heights
        color("#1a1a1a") translate([board[0], -board[3], pboard_bottom_z]) cube([board[2] - board[0], board[3] - board[1], 1.6]);
        for (k = keys) translate([k[0], -k[1], pkey_face_z]) {
            color("#e8e8e8") translate([-7, -7, 0]) cube([14, 14, 11.6]);
            color("#4a6fa5") translate([-9, -9, 11.6]) cube([18, 18, 7.5]);
        }
    }
}
