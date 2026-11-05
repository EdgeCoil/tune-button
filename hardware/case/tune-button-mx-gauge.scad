// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: CERN-OHL-S-2.0
//
// MX hole gauge: four switch holes, 14.0 to 14.3 mm, cut the same way as the printed lid's plate
// (1.5 mm, corner reliefs, the chamfer on the bed face). Print it with the same filament and
// settings as the lid, press a switch into each, and set mx_hole in tune-button-printed.scad to
// the smallest size the switch goes fully into, clips latched.
//
//   openscad -o tune-button-mx-gauge.stl tune-button-mx-gauge.scad
include <tune-button-printed.scad>
piece = "none";

sizes = [14.0, 14.1, 14.2, 14.3];
labels = ["14.0", "14.1", "14.2", "14.3"];
pitch = 19.05;
t = plate_t;
w = len(sizes) * pitch + 4;
d = pitch + 6;

// Built upright (top face at z = t), then turned over: the top face prints on the bed, as on the lid.
translate([0, 0, t]) rotate([180, 0, 0]) difference() {
    translate([-w / 2, -d / 2, 0]) cube([w, d, t]);
    for (i = [0 : len(sizes) - 1]) translate([(i - (len(sizes) - 1) / 2) * pitch, 2.5, 0]) mx_cut(t, sizes[i]);
    // each size engraved under its hole, on the underside (the side facing up as printed)
    for (i = [0 : len(sizes) - 1]) translate([(i - (len(sizes) - 1) / 2) * pitch, -d / 2 + 2.6, -0.01])
        mirror([0, 1, 0]) linear_extrude(height = 0.6) text(labels[i], size = 3, halign = "center", valign = "center");
}
