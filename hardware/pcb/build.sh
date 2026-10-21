#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# Generate, route, check and export both boards (or the ones named):
#
#   ./build.sh [xiao] [c3]
#
# Needs KiCad 9 (kicad-cli and its Python module), its symbol libraries (KICAD_SYMBOL_DIR if they
# are not in /usr/share/kicad/symbols), Java 21 and Freerouting 2.1.0 (FREEROUTING=path/to/jar).
# Fab files land in <variant>/fab/, which is not committed.
set -euo pipefail
cd "$(dirname "$0")"
variants=("$@")
[ ${#variants[@]} -eq 0 ] && variants=(xiao c3)

python3 gen.py "${variants[@]}" 2> >(grep -v -e 'assert' -e '^swig' >&2)
for v in "${variants[@]}"; do
  base="$v/tune-button-$v"
  python3 route.py "$v" 2> >(grep -v -e 'assert' -e '^swig' >&2)
  out="$v/fab"
  rm -rf "$out" && mkdir -p "$out/gerber"

  kicad-cli sch erc --severity-error --exit-code-violations -o "$out/erc.rpt" "$base.kicad_sch" >/dev/null \
    || { echo "$v: ERC errors, see $out/erc.rpt"; exit 1; }
  kicad-cli pcb drc --schematic-parity --severity-all --exit-code-violations -o "$out/drc.rpt" "$base.kicad_pcb" >/dev/null \
    || { echo "$v: DRC, unconnected or parity problems, see $out/drc.rpt"; exit 1; }

  kicad-cli pcb export gerbers --layers F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts \
    --subtract-soldermask -o "$out/gerber/" "$base.kicad_pcb" >/dev/null
  kicad-cli pcb export drill --format excellon --excellon-separate-th --generate-map --map-format gerberx2 \
    -o "$out/gerber/" "$base.kicad_pcb" >/dev/null
  python3 -c "import shutil, sys; shutil.make_archive(sys.argv[1], 'zip', sys.argv[2])" "$out/tune-button-$v-gerbers" "$out/gerber"
  kicad-cli sch export bom --fields 'Reference,Value,Footprint,MPN,${QUANTITY}' \
    --labels 'Designator,Value,Footprint,MPN,Qty' --group-by 'Value,Footprint,MPN' --exclude-dnp \
    -o "$out/tune-button-$v-bom.csv" "$base.kicad_sch" >/dev/null
  kicad-cli pcb export pos --format csv --units mm --side front --exclude-dnp \
    -o "$out/tune-button-$v-cpl.csv" "$base.kicad_pcb" >/dev/null
  kicad-cli sch export pdf -o "$out/tune-button-$v-schematic.pdf" "$base.kicad_sch" >/dev/null
  for side in top bottom; do
    kicad-cli pcb render --side "$side" -w 920 -h 1300 --quality basic -o "$out/tune-button-$v-$side.png" \
      "$base.kicad_pcb" >/dev/null 2>&1
  done
  echo "$v: ERC and DRC clean; fab files in $out"
done
