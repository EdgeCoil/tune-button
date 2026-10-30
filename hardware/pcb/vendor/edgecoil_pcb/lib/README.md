# Toolkit library `ec`

Parts the blocks need that KiCad's own libraries lack. A board using them names the library in
`Config(toolkit_libs=("ec",))`; the toolkit then finds the files here, writes the lib-table entries
and points each footprint's 3D model (`${EC_3D}` in the file) at `ec.3dshapes/`.

| Part | Symbol | Footprint | 3D model | Used by |
|---|---|---|---|---|
| LDL1117S33R (ST), LCSC C435835 | `ec:LDL1117S33R` | `ec:SOT-223-4_L6.5-W3.5-P2.30-LS7.0-BR` | `SOT-223-4P_L6.5-W3.5-H1.6-LS7.0-P2.30` (.step, .wrl) | `blocks/ldo-ldl1117` |

## Source and credit

**These come from the JLCEDA/EasyEDA official library** (https://lceda.cn/, https://easyeda.com),
converted to KiCad with easyeda2kicad. Their copyright belongs to JLCEDA/EasyEDA, whose terms ask
that the source be credited as above wherever the library's content is reproduced. They are used
because they are the footprints JLCPCB places these parts by, pad for pad (`jlc_verify` checks it).

Changes here: the symbol's Footprint field and the footprint's model path name this library.
