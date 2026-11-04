#!/bin/sh
# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# Builds the layered cases from stack.scad into stack/<variant>/:
#   Lnn-<kind>.svg   one file per laser layer, bottom (L00) up, all in the same top view
#   sheet.svg/.dxf   every layer on one sheet, for one cutting job
#   spacers.stl      printed board spacers (xiao, c3)
#   wall.stl         c3-jst only: layers 5-15 as one printed part, if you'd rather not cut 11 rings
#   preview.png      assembly render (needs xvfb-run when headless)
# and stack/kerf-test.svg, plus the printed c3 case (tune-button-c3-{base,top}.stl). Requires OpenSCAD 2021.01 or later.
set -eu
cd "$(dirname "$0")"
scad=stack.scad
mkdir -p stack
openscad -q -D 'part="kerf_test"' -o stack/kerf-test.svg "$scad"
for v in xiao c3 c3-jst; do
    out="stack/$v"
    rm -rf "$out"; mkdir -p "$out"
    kinds=$( (openscad -D "variant=\"$v\"" -D 'part="none"' -o "$out/.layers.echo" "$scad" >/dev/null 2>&1; cat "$out/.layers.echo") \
            | sed -n 's/^ECHO: "LAYERS \(.*\)"$/\1/p')
    rm -f "$out/.layers.echo"
    i=0
    for k in $kinds; do
        n=$(printf '%02d' "$i")
        openscad -q -D "variant=\"$v\"" -D 'part="layer"' -D "layer=$i" -o "$out/L$n-$k.svg" "$scad"
        i=$((i + 1))
    done
    openscad -q -D "variant=\"$v\"" -D 'part="sheet"' -o "$out/sheet.svg" "$scad"
    openscad -q -D "variant=\"$v\"" -D 'part="sheet"' -o "$out/sheet.dxf" "$scad"
    if [ "$v" = c3-jst ]; then
        openscad -q -D "variant=\"$v\"" -D 'part="wall"' -o "$out/wall.stl" "$scad"
    else
        openscad -q -D "variant=\"$v\"" -D 'part="spacers"' -o "$out/spacers.stl" "$scad"
    fi
    if command -v xvfb-run >/dev/null 2>&1; then run="xvfb-run -a"; else run=""; fi
    $run openscad -q -D "variant=\"$v\"" -o "$out/preview.png" --imgsize=1200,900 --viewall \
        --autocenter --camera=0,0,0,55,0,25,0 --colorscheme=Tomorrow "$scad" || true
    echo "$v: $i layers -> $out"
done
# The printed c3 case, which takes its geometry from stack.scad.
openscad -q -D 'piece="base"' -o tune-button-c3-base.stl tune-button-c3-printed.scad
openscad -q -D 'piece="top"' -o tune-button-c3-top.stl tune-button-c3-printed.scad
$run openscad -q -o stack/c3/printed-preview.png --imgsize=1200,900 --viewall --autocenter \
    --camera=0,0,0,55,0,25,0 --colorscheme=Tomorrow tune-button-c3-printed.scad || true
echo "c3 printed: tune-button-c3-base.stl, tune-button-c3-top.stl"
