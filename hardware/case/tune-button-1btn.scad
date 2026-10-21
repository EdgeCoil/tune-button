// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: CERN-OHL-S-2.0
//
// One-button tune-button: a round puck with a 22 mm panel-mount push button in the middle of the
// top. A base plate carries the LiPo (flat) and the XIAO ESP32-C3 beside it, with USB-C through
// the side wall. The switch hangs from the top above them. Three M2 self-tapping screws hold the
// base on from below.
//
//   openscad -D 'part="body"' -o tune-button-1btn-body.stl tune-button-1btn.scad
//   openscad -D 'part="base"' -o tune-button-1btn-base.stl tune-button-1btn.scad
//   openscad -D 'part="assembly"' tune-button-1btn.scad      (preview only)
//
// Print the body TOP FACE DOWN and the base flat side down, 0.2 mm layers, no supports.
//
// MEASURE FIRST. Values marked "measured" came from calipers. Values marked "ESTIMATE" are
// guesses from photos. Check each one against your parts before printing.

part = "assembly";  // "body" | "base" | "assembly"

/* [Parts] */
battery = [33.64, 42.74, 6.0];  // measured W × L; thickness is an ESTIMATE (603443-class cell)
battery_slack = 1.0;            // added to W and L, plus room for the swelling of a pouch cell
xiao = [21.0, 17.8, 1.2];       // PCB L × W × T; USB-C on a short edge
usbc = [9.0, 3.3];              // receptacle W × H, on top of the PCB
usbc_overhang = 1.0;            // receptacle sticks out this far past the PCB edge
xiao_rail_h = 2.5;              // room under the XIAO for the wires on its BAT pads

switch_thread_d = 21.74;        // measured: the threaded barrel
switch_hole = 22.4;             // panel hole for the 22 mm barrel
switch_cap_d = 28;              // ESTIMATE: the red head, only used for the preview
switch_depth = 32;              // ESTIMATE: collar underside to terminal tips, wires attached
switch_nut_d = 30;              // ESTIMATE: across the nut's corners; keeps posts clear of it

/* [Shell] */
wall = 2.4;
top_t = 3.0;                    // the panel the switch clamps; the thread must be longer than this
base_t = 2.0;
inner_r = 35.5;                 // fits the battery and the XIAO side by side (checked below)
spigot_h = 1.6;                 // ring on the base that locates it inside the wall
gap = 0.3;                      // print clearance
post_d = 6.0;
post_r = inner_r - post_d / 2 + 0.8;  // merged into the wall, never tangent to it
post_angles = [60, 180, 300];         // clear of the XIAO (at 0°) and the battery corners
screw_pilot = 1.6;              // M2 self-tapping
screw_clear = 2.3;
screw_head = 4.2;
usb_lip = 0.6;                  // wall left in front of the receptacle; recessed outside for the plug
plug_recess = [12.5, 7.0];      // clearance for the plug's overmould

$fn = 96;

outer_r = inner_r + wall;
// Floor top to top underside: whatever sits under the switch, plus the switch itself.
under_switch = max(battery[2] + 1.0, xiao_rail_h + xiao[2] + usbc[1]) + 3;  // 3 mm for wire bends
inner_h = under_switch + switch_depth;
body_h = inner_h + top_t;

// XIAO along +x with its receptacle face at the wall; the battery fills the -x side.
xiao_end_x = sqrt(inner_r * inner_r - (xiao[1] / 2 + 0.5) ^ 2) - 0.4;  // receptacle face
xiao_x0 = xiao_end_x - usbc_overhang - xiao[0];                       // PCB inner end
bat = [battery[0] + battery_slack, battery[1] + battery_slack];
bat_x1 = xiao_x0 - 2.4;          // a 1.2 mm cradle wall between the two
bat_x0 = bat_x1 - bat[0];
usb_z = base_t + xiao_rail_h + xiao[2] + usbc[1] / 2;  // receptacle centre, from the base underside

// Fit checks: fail the render rather than print something that can't be assembled.
assert(sqrt(bat_x0 ^ 2 + (bat[1] / 2) ^ 2) < inner_r - 0.5, "battery corner hits the wall: raise inner_r");
assert(switch_thread_d < switch_hole, "switch hole smaller than the thread");
for (a = post_angles) {
  p = [post_r * cos(a), post_r * sin(a)];
  assert(norm(p) - post_d / 2 > switch_nut_d / 2 + 1, "post too close to the switch nut");
}

module body() {
  difference() {
    union() {
      difference() {
        cylinder(r = outer_r, h = body_h);
        translate([0, 0, -1]) cylinder(r = inner_r, h = inner_h + 1);
      }
      // Screw posts run the full height, so they print upside down without overhangs.
      for (a = post_angles) rotate(a) translate([post_r, 0, 0]) cylinder(d = post_d, h = body_h);
    }
    // Switch hole and the pilot holes.
    translate([0, 0, inner_h - 1]) cylinder(d = switch_hole, h = top_t + 2);
    for (a = post_angles) rotate(a) translate([post_r, 0, -1]) cylinder(d = screw_pilot, h = 12);
    // USB-C: slot through a thin lip, with a recess outside for the plug's overmould.
    translate([0, 0, usb_z - base_t]) rotate([0, 90, 0]) {
      linear_extrude(outer_r + 1) offset(usbc[1] / 2 + 0.2) square([0.01, usbc[0] - usbc[1]], center = true);
      translate([0, 0, inner_r + usb_lip])
        linear_extrude(wall + 1) offset(1.5) square([plug_recess[1] - 3, plug_recess[0] - 3], center = true);
    }
    // Chamfer on the top edge.
    translate([0, 0, body_h - 1]) difference() {
      cylinder(r = outer_r + 1, h = 2);
      cylinder(r1 = outer_r, r2 = outer_r - 1.2, h = 1.2);
    }
  }
}

module base() {
  difference() {
    union() {
      cylinder(r = outer_r, h = base_t);
      // Spigot inside the wall, notched around the posts.
      difference() {
        cylinder(r = inner_r - gap, h = base_t + spigot_h);
        translate([0, 0, -1]) cylinder(r = inner_r - gap - 1.6, h = base_t + spigot_h + 2);
        for (a = post_angles) rotate(a) translate([post_r, 0, -1]) cylinder(d = post_d + 2 * gap, h = 10);
      }
      // Battery cradle: low walls, with a gap at the +y end beside the XIAO, where the cell's leads leave
      // its short edge. Turn the cell round if its leads are at the other end.
      translate([0, 0, base_t]) difference() {
        translate([bat_x0 - 1.2, -bat[1] / 2 - 1.2]) cube([bat[0] + 2.4, bat[1] + 2.4, 3]);
        translate([bat_x0, -bat[1] / 2, -1]) cube([bat[0], bat[1], 5]);
        translate([bat_x1 - 14, bat[1] / 2 - 1, -1]) cube([14 + 2, 3, 5]);
      }
      // XIAO rails along its long edges, and a stop at its inner end. The plug pushes it into the stop.
      translate([0, 0, base_t]) {
        for (s = [-1, 1]) translate([xiao_x0, s > 0 ? xiao[1] / 2 - 2 : -xiao[1] / 2, 0]) cube([xiao[0], 2, xiao_rail_h]);
        translate([xiao_x0 - 1.4, -xiao[1] / 2, 0]) cube([1.4, xiao[1], xiao_rail_h + xiao[2] + 1.5]);
        // Side guides hold it straight.
        for (s = [-1, 1]) translate([xiao_x0 + 4, s > 0 ? xiao[1] / 2 + gap : -xiao[1] / 2 - gap - 1.2, 0])
          cube([xiao[0] - 6, 1.2, xiao_rail_h + xiao[2] + 1]);
      }
    }
    for (a = post_angles) rotate(a) translate([post_r, 0, 0]) {
      translate([0, 0, -1]) cylinder(d = screw_clear, h = base_t + spigot_h + 2);
      translate([0, 0, -1]) cylinder(d1 = screw_head + 2, d2 = screw_clear, h = 1 + (screw_head + 2 - screw_clear) / 2);
    }
  }
}

module switch_preview() {
  color("silver") translate([0, 0, body_h - switch_depth - top_t]) cylinder(d = switch_thread_d, h = switch_depth);
  color("red") translate([0, 0, body_h]) cylinder(d = switch_cap_d, h = 8);
}

if (part == "body") translate([0, 0, body_h]) rotate([180, 0, 0]) body();  // print orientation
else if (part == "base") base();
else {
  color("gold") base();
  color("silver", 0.6) translate([bat_x0 + 0.5, -battery[1] / 2, base_t]) cube(battery);
  color("darkgreen") translate([xiao_x0, -xiao[1] / 2, base_t + xiao_rail_h]) cube(xiao);
  color("orange", 0.5) translate([0, 0, base_t]) difference() { body(); translate([0, -100, -1]) cube(200); }
  translate([0, 0, base_t]) switch_preview();
}
echo(str("outer Ø ", 2 * outer_r, " mm, height ", body_h + base_t, " mm, interior ", inner_h, " mm"));
