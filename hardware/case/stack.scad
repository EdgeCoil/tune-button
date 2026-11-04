// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: CERN-OHL-S-2.0
//
// Layered enclosures for the three four-key boards: a stack of laser-cut 3 mm acrylic, through-
// bolted at the corners, with 3D printing only for small parts (board spacers on the MX boards and,
// as an option, the tall wall section of the arcade box).
//
//   variant = "xiao"   : XIAO board, MX keys, a raised visor over the XIAO           (11 layers)
//   variant = "c3"     : C3 board, MX keys on its back face                         (8 layers)
//   variant = "c3-jst" : c3-jst board under four 22 mm arcade buttons on top        (17 layers)
//
// Outputs (build.sh does all of this):
//   openscad -D 'variant="c3"' -D 'part="layer"' -D layer=3 -o L03.svg stack.scad   one layer, 2D
//   openscad -D 'variant="c3"' -D 'part="sheet"' -o c3-sheet.svg stack.scad         all layers
//   openscad -D 'variant="c3"' -D 'part="spacers"' -o c3-spacers.stl stack.scad     printed parts
//   openscad -D 'variant="c3-jst"' -D 'part="wall"' -o c3-jst-wall.stl stack.scad   printed wall option
//   openscad -D 'part="kerf_test"' -o kerf-test.svg stack.scad                      cut this first
//   openscad -D 'variant="c3"' stack.scad                                           3D preview
//
// Coordinates are the TOP VIEW of the finished case, in board millimetres, x right and y DOWN
// (KiCad's convention), with the board origin at the board's top-left corner. The c3 board is
// mounted key side up, so its parts-side coordinates are mirrored (x' = 46 - x). Every layer is
// exported in that same top view: cut them all the same side up and stack them in order.
//
// The geometry comes from the KiCad files in ../pcb at rev A. Values marked ESTIMATE are not
// from those files: measure your parts.

variant = "c3";      // "xiao" | "c3" | "c3-jst"
part = "assembly";   // "assembly" | "layer" | "sheet" | "spacers" | "wall" | "kerf_test"
layer = 0;

/* [Material] */
t = 3.0;             // acrylic sheet; every height below is counted in whole sheets
kerf = 0.10;         // your laser's kerf: outlines grow and holes shrink by kerf / 2. Cut
                     // kerf_test first and adjust until the 14.0 mm switch hole is a firm fit.
$fn = 64;

/* [Fit] */
clear = 0.5;         // board edge to cavity wall
key_clear = 0.75;    // keycap edge to bezel opening
mx_hole = 14.0;      // Cherry MX plate hole. A 3 mm plate is thicker than the 1.5 mm the clips are
                     // made for: they don't latch, the switches are held by their solder joints
usb_slot = [13.0, 8.0];  // USB-C plug overmould clearance, W x H (most cables are within 12 x 7)
cell_slack = 1.0;    // added to the cell's length and width
spacer_d = 5.0;      // printed board spacers (MX boards)
spacer_hole = 5.3;   // their locating holes in the acrylic under the board
pin_d = 1.9;         // spacer pin into the board's 2.2 mm mounting hole
pin_h = 1.2;

// ------------------------------------------------------------------------------------------------
// Per-variant data. rects are [x0, y0, x1, y1].

function sel(x, c3, jst) = variant == "xiao" ? x : variant == "c3" ? c3 : jst;

M = sel("M2", "M2", "M3");                 // through-bolts
bolt_hole = sel(2.4, 2.4, 3.4);
wall = sel(6.0, 6.0, 7.0);

// The cavity around the board, plus side pockets for the JST battery plugs (and, on c3-jst, the
// antenna overhang and the 7-pin button plug).
board = sel([0, 0, 46, 67.05], [0, 0, 46, 69.72], [0, 0, 36, 50]);
pockets = sel(
    [[-6.5, 8, 0, 18]],                         // J3 battery plug, left edge (top side)
    [[-6.5, 38, 0, 49.5]],                      // J2 battery plug, left edge (parts side, mirrored)
    [[0, -7, 36, 0],                            // antenna overhang
     [16.4, 50, 35.6, 56],                      // J3, the 7-pin button plug
     [36, 29.5, 44.5, 38.7],                    // J2 battery plug
     [44, 18.6, 65, 49.6]]);                    // the cell beside the board
cell = sel([7.5, 13, 38.5, 54],                 // 503040 (30 x 40) under the board, + slack
           [7.5, 22, 38.5, 63],                 // 503040 under the board (a 503035 fits too)
           [44, 18.6, 65, 49.6]);               // 502030 (20 x 30) beside the board

// Board z, from the stack. On the MX boards the plate's top must be 5.0 mm above the board's key
// face (the Cherry MX spec): with the plate as layer 6, the key face is at 6t + 3 - 5 = 16.
key_face_z = sel(16.0, 16.0, 7.6);
board_bottom_z = sel(14.4, 14.4, 6.0);

spacers = sel([[3.5, 3.5], [42.5, 3.5], [3.5, 64.05], [42.5, 64.05]],
              [[3.5, 66.55], [42.5, 66.55], [43.0, 23.0], [2.4, 31.0]],
              []);
board_screws = sel([], [], [[3.0, 29.0], [17.0, 31.0]]);  // c3-jst: M2 from below; NYLON at [17, 31]

keys = sel([[13.475, 33.5], [32.525, 33.5], [13.475, 52.55], [32.525, 52.55]],
           [[13.475, 36.0], [32.525, 36.0], [13.475, 55.05], [32.525, 55.05]],
           []);
leds = sel([], [[12.0, 20.0], [6.0, 20.0]], []);   // c3: D3 and D1, on the key face
led_hole = 2.5;
// c3 only: the optional UART header TP1 hangs below the parts side, beside the cell.
infill_relief = sel([], [[40.9, 38.9, 45.1, 45.65]], []);   // its courtyard + 0.3

// USB-C: [x centre, edge (-1 top, +1 bottom), y where the slot starts, z centre]
usb = sel([23.0, -1, 0.3, 27.35],     // the XIAO's own socket, on 8.5 mm sockets
          [23.0, 1, 69.7, 12.8],      // J1, parts side down
          [7.5, 1, 50.5, 9.2]);       // J1

// XIAO only: the visor over the XIAO, its sockets, J3 and J4 (J4's pins stand 8.5 mm tall).
hood = [-6.5, -0.5, 46.5, 23.75];
// J4's body reaches 24.8, past the visor's front edge: relieve the plate and bezel around it.
hood_relief = [1.7, 18.2, 6.3, 25.3];

// c3-jst only: the arcade-button chamber and its buttons.
arcade_pitch = 34;                    // a 30 mm nut (ESTIMATE, across corners) plus 4 mm
arcade_hole = 22.4;                   // for the measured 21.74 mm barrel
arcade_depth = 32;                    // ESTIMATE: collar underside to terminal tips, wired
arcade_cap_d = 28;                    // ESTIMATE: preview only
upper = [-0.5, -9.5, 65.5, 56.5];     // 66 x 66: two pitches' worth of nuts
arcade = [for (dx = [-1, 1], dy = [-1, 1])
    [(upper[0] + upper[2]) / 2 + dx * arcade_pitch / 2, (upper[1] + upper[3]) / 2 + dy * arcade_pitch / 2]];

// The layers, bottom up. Layer i spans z = [i t, (i + 1) t].
layers = sel(
    ["base", "infill", "infill", "ring", "ring", "ring", "plate", "bezel", "hood", "hood", "hood_cap"],
    ["base", "infill", "infill", "ring", "ring", "ring", "plate", "bezel"],
    concat(["base", "lower", "ring", "ring", "ring"],
           [for (i = [5:15]) "upper"], ["top"]));
N = len(layers);

// Cavity and outline.
cavity = concat([[board[0] - clear, board[1] - clear, board[2] + clear, board[3] + clear]], pockets);
function bbox(rs) = [min([for (r = rs) r[0]]), min([for (r = rs) r[1]]),
                     max([for (r = rs) r[2]]), max([for (r = rs) r[3]])];
inner = variant == "c3-jst" ? upper : bbox(cavity);
outer = [inner[0] - wall, inner[1] - wall, inner[2] + wall, inner[3] + wall];
outer_r = 4.0;

// Through-bolts: [x, y, top layer], one in each corner. The corner nearest each ESP32-C3 module's
// antenna takes a NYLON bolt (c3: top right, ~5 mm from the antenna). Moving it along the wall
// instead was tried and leaves ~1.6 mm of acrylic beside the cavity. On c3-jst the nearest corner
// (top left) is ~11 mm from the antenna: metal is probably fine; use nylon if range is poor.
bi = sel(3.2, 3.2, 3.6);
bl = outer[0] + bi; br = outer[2] - bi; bt = outer[1] + bi; bb = outer[3] - bi;
bolts = sel(
    [[bl, bt, 10], [br, bt, 10], [bl, bb, 7], [br, bb, 7]],
    [[bl, bt, 7], [br, bt, 7], [bl, bb, 7], [br, bb, 7]],
    [[bl, bt, N - 1], [br, bt, N - 1], [bl, bb, N - 1], [br, bb, N - 1]]);
nylon_bolt = sel(-1, 1, -1);   // index into bolts, or -1

// ------------------------------------------------------------------------------------------------
// 2D helpers

module rect(r, rad = 0) {
    if (rad <= 0) translate([r[0], r[1]]) square([r[2] - r[0], r[3] - r[1]]);
    else translate([r[0] + rad, r[1] + rad]) offset(r = rad)
        square([r[2] - r[0] - 2 * rad, r[3] - r[1] - 2 * rad]);
}
module outline() rect(outer, outer_r);
module cavity2d() for (r = cavity) rect(r, 0.5);
module bolt_holes(i) for (b = bolts) if (i <= b[2]) translate([b[0], b[1]]) circle(d = bolt_hole);
module usb_slot2d(i) {
    lo = usb[3] - usb_slot[1] / 2; hi = usb[3] + usb_slot[1] / 2;
    if (min(hi, (i + 1) * t) - max(lo, i * t) >= 0.5) {
        y0 = usb[1] > 0 ? usb[2] : outer[1] - 1;
        y1 = usb[1] > 0 ? outer[3] + 1 : usb[2];
        rect([usb[0] - usb_slot[0] / 2, y0, usb[0] + usb_slot[0] / 2, y1]);
    }
}
module key_opening() if (len(keys) > 0) rect(
    [min([for (k = keys) k[0]]) - 9 - key_clear, min([for (k = keys) k[1]]) - 9 - key_clear,
     max([for (k = keys) k[0]]) + 9 + key_clear, max([for (k = keys) k[1]]) + 9 + key_clear], 1.0);
module hood_band() rect([outer[0] - 1, outer[1] - 1, outer[2] + 1, hood[3]]);

module layer2d(i) {
    k = layers[i];
    offset(delta = kerf / 2) difference() {
        if (k == "hood" || k == "hood_cap") intersection() { outline(); hood_band(); }
        else outline();
        bolt_holes(i);
        usb_slot2d(i);
        if (k == "base") for (s = board_screws) translate(s) circle(d = 2.4);
        if (k == "infill") {
            rect(cell, 0.5);
            for (s = spacers) translate(s) circle(d = spacer_hole);
            for (r = infill_relief) rect(r, 0.5);
        }
        if (k == "lower") {
            rect(cell, 0.5);
            for (s = board_screws) translate(s) circle(d = 2.4);
        }
        if (k == "ring") cavity2d();
        if (k == "plate") {
            for (c = keys) translate(c) square(mx_hole, center = true);
            for (l = leds) translate(l) circle(d = led_hole);
            if (variant == "xiao") { rect(hood, 0.5); rect(hood_relief, 0.5); }
        }
        if (k == "bezel") {
            key_opening();
            for (l = leds) translate(l) circle(d = led_hole);
            if (variant == "xiao") { rect(hood, 0.5); rect(hood_relief, 0.5); }
        }
        if (k == "hood") rect(hood, 0.5);
        if (k == "upper") rect(upper, 1.0);
        if (k == "top") for (a = arcade) translate(a) circle(d = arcade_hole);
    }
}

// The finished case is seen from above with y down; OpenSCAD's y is up, so flip for output.
module top_view() mirror([0, 1]) children();

// ------------------------------------------------------------------------------------------------
// Printed parts

module spacer() {
    h = board_bottom_z - t - 0.1;   // base top to board underside, 0.1 short
    cylinder(d = spacer_d, h = h);
    translate([0, 0, h]) cylinder(d = pin_d, h = pin_h, $fn = 24);
}

// c3-jst option: layers 5-15 as one printed part, same footprint and bolt holes.
module printed_wall() {
    linear_extrude(height = 11 * t) top_view() difference() {
        outline();
        rect(upper, 1.0);
        bolt_holes(5);
    }
}

// ------------------------------------------------------------------------------------------------
// Preview stand-ins (not to be printed)

module board3d() {
    color("#1a1a1a") translate([board[0], -board[3], board_bottom_z])
        cube([board[2] - board[0], board[3] - board[1], 1.6]);
    // keys: MX housing above the plate and a 1u cap
    for (k = keys) translate([k[0], -k[1], key_face_z]) {
        color("#e8e8e8") translate([-7, -7, 0]) cube([14, 14, 11.6]);
        color("#4a6fa5") translate([-9, -9, 11.6]) cube([18, 18, 7.5]);
    }
    // cell
    color("#b8b8c8", 0.9) translate([cell[0] + 0.5, -cell[3] + 0.5, t + 0.5])
        cube([cell[2] - cell[0] - 1, cell[3] - cell[1] - 1, 5]);
    // USB-C receptacle
    color("silver") translate([usb[0] - 4.5, -(usb[2] + (usb[1] > 0 ? -7.3 : 0)) - (usb[1] > 0 ? 0 : 7.3), usb[3] - 1.6])
        cube([9, 7.3, 3.2]);
    if (variant == "xiao") color("#2f7d32")
        translate([23 - 8.9, -(0.3 + 1.2 + 21), key_face_z + 8.5]) cube([17.8, 21, 1.2]);
    if (variant == "c3-jst") for (a = arcade) translate([a[0], -a[1], N * t - t]) {
        color("#c0392b") translate([0, 0, t]) cylinder(d = arcade_cap_d, h = 8);
        color("#555") translate([0, 0, -arcade_depth]) cylinder(d = 24, h = arcade_depth);
    }
    for (s = spacers) color("orange") translate([s[0], -s[1], t]) spacer();
}

module assembly() {
    for (i = [0:N - 1]) {
        k = layers[i];
        c = k == "plate" || k == "top" ? [0.85, 0.85, 0.9, 0.55]
          : k == "base" ? [0.3, 0.3, 0.32, 0.9] : [0.75, 0.85, 0.95, 0.30];
        color(c) translate([0, 0, i * t]) linear_extrude(height = t - 0.02) top_view() layer2d(i);
    }
    board3d();
}

// ------------------------------------------------------------------------------------------------
// Sheet: every layer, laid out in a grid, for one cutting job. A layer number is NOT engraved;
// keep the stack in order with the layer files (Lnn) or mark the protective film.

module sheet() {
    w = outer[2] - outer[0]; h = outer[3] - outer[1]; gap = 3;
    cols = ceil(sqrt(N));
    for (i = [0:N - 1]) translate([(i % cols) * (w + gap) - outer[0], -floor(i / cols) * (h + gap)])
        top_view() translate([0, 0]) layer2d(i);
}

// A small test piece: a switch hole, a bolt hole of each size, a spacer hole and an arcade hole.
module kerf_test() offset(delta = kerf / 2) difference() {
    rect([0, 0, 64, 30], 2);
    translate([10, 15]) square(mx_hole, center = true);
    translate([24, 8]) circle(d = 2.4);
    translate([24, 22]) circle(d = 3.4);
    translate([31, 15]) circle(d = spacer_hole);
    translate([50, 15]) circle(d = arcade_hole);
}

// ------------------------------------------------------------------------------------------------

echo(str("VARIANT ", variant, ": ", N, " layers, outside ", outer[2] - outer[0], " x ",
         outer[3] - outer[1], " x ", N * t, " mm; ", M, " bolts: ",
         [for (b = bolts) str(M, " x ", (b[2] + 1) * t, " stack")]));

function joined(v, i = 0) = i >= len(v) ? "" : str(v[i], i < len(v) - 1 ? " " : "", joined(v, i + 1));
echo(str("LAYERS ", joined(layers)));
if (nylon_bolt >= 0) echo(str("NYLON bolt at ", bolts[nylon_bolt]));

if (part == "assembly") assembly();
else if (part == "layer") top_view() layer2d(layer);
else if (part == "sheet") sheet();
else if (part == "spacers") {
    for (i = [0:len(spacers) - 1]) translate([i * 8, 0, 0]) spacer();
}
else if (part == "wall") printed_wall();
else if (part == "kerf_test") kerf_test();
