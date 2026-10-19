// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: CERN-OHL-S-2.0
//
// tune-button case: a base tray holding a XIAO ESP32-C3 and a 503035 LiPo, and a lid carrying
// two 12 × 12 mm tactile switches (and an optional 3 mm LED). Four M2 self-tapping screws.
// The XIAO's stick-on FPC antenna goes flat against the inside of a long wall at the XIAO end,
// not under the battery.
//
//   openscad -D 'part="base"' -o tune-button-base.stl tune-button.scad
//   openscad -D 'part="lid"'  -o tune-button-lid.stl  tune-button.scad
//   openscad -D 'part="assembly"' tune-button.scad      (preview only)
//
// Print both flat side down, 0.2 mm layers, no supports. Measure your parts first. Every size
// below is a parameter, and the XIAO, battery and switch dimensions vary between batches.

part = "assembly";  // "base" | "lid" | "assembly"

/* [Parts] */
xiao = [21.0, 17.8, 1.2];      // PCB L × W × T; USB-C on a short edge
usbc = [9.0, 3.3];             // receptacle W × H, sitting on top of the PCB
usbc_overhang = 1.2;           // how far the receptacle sticks out past the PCB edge
battery = [35.5, 30.5, 5.5];   // 503035 LiPo, with swelling allowance
switch_body = [12.2, 12.2, 3.8];
switch_cap_d = 11.8;           // hole for the round cap; the cap stands proud of the lid
led_d = 3.1;                   // 0 to omit

/* [Shell] */
wall = 2.0;
floor_t = 1.6;
lid_t = 2.0;
inner_h = 13.0;                // floor to lid underside
corner_r = 4.0;
gap = 0.3;                     // print clearance
post_d = 5.5;
screw_pilot = 1.6;             // M2 self-tapping
screw_clear = 2.3;
screw_head = 4.2;

xiao_rail_h = 2.0;             // room under the XIAO for the battery wires on its BAT pads

$fn = 48;

// Interior: XIAO bay at -x end, battery beside it, posts in the four corners.
inner = [xiao[0] + usbc_overhang + battery[0] + 8, max(battery[1], xiao[1]) + 2 * post_d + 0.5];
outer = [inner[0] + 2 * wall, inner[1] + 2 * wall];
xiao_pos = [wall + usbc_overhang, wall + (inner[1] - xiao[1]) / 2];  // receptacle flush with the inner wall
batt_pos = [wall + xiao[0] + usbc_overhang + 4, wall + (inner[1] - battery[1]) / 2];
post_in = wall + post_d / 2 - 0.6;  // merged into the walls, never tangent to them
posts = [for (x = [post_in, outer[0] - post_in]) for (y = [post_in, outer[1] - post_in]) [x, y]];
// Buttons centred on the lid (their sockets clear the XIAO below), the LED between them.
btn_pitch = 24;
btn_y = outer[1] / 2;
btn_x = [outer[0] / 2 - btn_pitch / 2, outer[0] / 2 + btn_pitch / 2];
led_x = (btn_x[0] + btn_x[1]) / 2;

module rbox(size, h, r) {
  linear_extrude(h) offset(r) offset(-r) square(size);
}

module base() {
  usb_z = floor_t + xiao_rail_h + xiao[2] + usbc[1] / 2;
  difference() {
    union() {
      difference() {
        rbox(outer, floor_t + inner_h, corner_r);
        translate([wall, wall, floor_t]) rbox(inner, inner_h + 1, corner_r - wall);
      }
      for (p = posts) translate([p[0], p[1], 0]) cylinder(d = post_d, h = floor_t + inner_h);
      // XIAO rails along its long edges, with a back stop so the plug can't push it in.
      for (y = [xiao_pos[1], xiao_pos[1] + xiao[1] - 1.5])
        translate([wall - 0.5, y, 0]) cube([xiao[0] + usbc_overhang + 0.5, 1.5, floor_t + xiao_rail_h]);
      translate([wall + usbc_overhang + xiao[0] + gap, xiao_pos[1], 0])
        cube([1.5, xiao[1], floor_t + xiao_rail_h + xiao[2] + 1.5]);
      // Battery fence.
      translate([batt_pos[0] - 1.5, batt_pos[1], 0]) cube([1.2, battery[1], floor_t + 3]);
    }
    for (p = posts) translate([p[0], p[1], floor_t]) cylinder(d = screw_pilot, h = inner_h + 1);
    // USB-C opening, generous enough for most plug overmoulds' noses.
    translate([-1, outer[1] / 2, usb_z]) rotate([0, 90, 0])
      linear_extrude(wall + 2) offset(1.2) square([usbc[1], usbc[0]], center = true);
    // Window to see the charge LED next to the USB-C socket.
    translate([-1, outer[1] / 2 + usbc[0] / 2 + 2.5, usb_z - 0.5]) rotate([0, 90, 0]) cylinder(d = 1.6, h = wall + 2);
  }
}

module lid() {
  difference() {
    union() {
      rbox(outer, lid_t, corner_r);
      // Lip that locates the lid inside the walls.
      difference() {
        translate([wall + gap, wall + gap, -1.5]) difference() {
          rbox([inner[0] - 2 * gap, inner[1] - 2 * gap], 1.5, corner_r - wall);
          translate([1.2, 1.2, -1]) rbox([inner[0] - 2 * gap - 2.4, inner[1] - 2 * gap - 2.4], 3, corner_r - wall);
        }
        for (p = posts) translate([p[0], p[1], -2]) cylinder(d = post_d + 2 * gap, h = 3);
      }
      // Switch sockets: the body presses in from below, legs bent flat and wired.
      for (x = btn_x) translate([x - switch_body[0] / 2 - 1.2, btn_y - switch_body[1] / 2 - 1.2, -switch_body[2]])
        difference() {
          cube([switch_body[0] + 2.4, switch_body[1] + 2.4, switch_body[2]]);
          translate([1.2, 1.2, -1]) cube([switch_body[0], switch_body[1], switch_body[2] + 1.01]);
          // Leg slots on two sides.
          translate([-1, 1.2 + 2, -1]) cube([switch_body[0] + 5, switch_body[1] - 4, 2.2]);
        }
    }
    for (p = posts) translate([p[0], p[1], -2]) {
      cylinder(d = screw_clear, h = lid_t + 4);
      translate([0, 0, 2 + lid_t - 1.2]) cylinder(d1 = screw_clear, d2 = screw_head, h = 1.21);  // countersink
    }
    for (x = btn_x) translate([x, btn_y, -1]) cylinder(d = switch_cap_d, h = lid_t + 2);
    if (led_d > 0) translate([led_x, btn_y, -1]) cylinder(d = led_d, h = lid_t + 2);
    // Labels: heart = like (left), plus = playlist (right).
    translate([btn_x[0], btn_y - switch_cap_d / 2 - 3.2, lid_t - 0.4]) linear_extrude(1)
      text("♥", size = 3.4, halign = "center", valign = "center", font = "DejaVu Sans");
    translate([btn_x[1], btn_y - switch_cap_d / 2 - 3.2, lid_t - 0.4]) linear_extrude(1)
      text("+", size = 4, halign = "center", valign = "center", font = "DejaVu Sans:style=Bold");
  }
}

module ghosts() {
  %translate([xiao_pos[0], xiao_pos[1], floor_t + xiao_rail_h]) {
    cube(xiao);
    translate([-usbc_overhang, (xiao[1] - usbc[0]) / 2, xiao[2]]) cube([7.4, usbc[0], usbc[1]]);
  }
  %translate([batt_pos[0], batt_pos[1], floor_t]) cube(battery);
}

if (part == "base") base();
else if (part == "lid") translate([0, outer[1], lid_t]) rotate([180, 0, 0]) lid();
else {
  base();
  ghosts();
  translate([0, 0, floor_t + inner_h]) lid();
}

echo(outer_size = [outer[0], outer[1], floor_t + inner_h + lid_t]);
