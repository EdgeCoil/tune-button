#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# Generate, route, check and export all three boards (or the ones named):
#
#   ./build.sh [xiao] [c3] [c3-jst]
#
# Needs KiCad 9 (kicad-cli and its Python module), its symbol libraries (KICAD_SYMBOL_DIR if they
# are not in /usr/share/kicad/symbols), Java 21 and Freerouting 2.1.0 (FREEROUTING=path/to/jar).
# Fab files land in <variant>/fab/, which is not committed.
set -euo pipefail
# Gerber, drill and job files stamp the local time with its offset: build in UTC so they carry no
# timezone (+11:00 here would point at a place).
export TZ=UTC
cd "$(dirname "$0")"
variants=("$@")
[ ${#variants[@]} -eq 0 ] && variants=(xiao c3 c3-jst)

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

  kicad-cli pcb export gerbers --layers F.Cu,B.Cu,F.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts \
    --subtract-soldermask -o "$out/gerber/" "$base.kicad_pcb" >/dev/null
  kicad-cli pcb export drill --format excellon --excellon-separate-th \
    -o "$out/gerber/" "$base.kicad_pcb" >/dev/null
  python3 -c "import shutil, sys; shutil.make_archive(sys.argv[1], 'zip', sys.argv[2])" "$out/tune-button-$v-gerbers" "$out/gerber"
  kicad-cli sch export bom --fields 'Reference,Value,Footprint,MPN,LCSC,${QUANTITY}' \
    --labels 'Designator,Value,Footprint,MPN,LCSC,Qty' --group-by 'Value,Footprint,MPN,LCSC' --exclude-dnp \
    -o "$out/tune-button-$v-bom.csv" "$base.kicad_sch" >/dev/null
  kicad-cli pcb export pos --format csv --units mm --side front --exclude-dnp \
    -o "$out/tune-button-$v-pos.csv" "$base.kicad_pcb" >/dev/null
  # JLCPCB assembly: only the parts with an LCSC number, in JLC's column names.
  kicad-cli sch export bom --fields 'Value,Reference,Footprint,LCSC' --group-by 'Value,Footprint,LCSC' \
    --ref-range-delimiter "" --exclude-dnp -o "$out/kicad-bom-lcsc.csv" "$base.kicad_sch" >/dev/null
  PYTHONPATH="vendor${PYTHONPATH:+:$PYTHONPATH}" python3 -m edgecoil_pcb.jlc "$out/kicad-bom-lcsc.csv" "$out/tune-button-$v-pos.csv" \
    "$out/tune-button-$v-jlc-bom.csv" "$out/tune-button-$v-jlc-cpl.csv"
  rm "$out/kicad-bom-lcsc.csv"
  kicad-cli sch export pdf -o "$out/tune-button-$v-schematic.pdf" "$base.kicad_sch" >/dev/null
  for side in top bottom; do
    kicad-cli pcb render --side "$side" -w 920 -h 1300 --quality basic -o "$out/tune-button-$v-$side.png" \
      "$base.kicad_pcb" >/dev/null 2>&1
  done
  echo "$v: ERC and DRC clean; fab files in $out"
done
