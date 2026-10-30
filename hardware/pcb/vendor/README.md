# Vendored: edgecoil_pcb

The shared board pipeline, copied from [EdgeCoil/edgecoil-pcb](https://github.com/EdgeCoil/edgecoil-pcb) at commit
`798a589` (MIT). `gen.py`, `route.py` and `panel.py` import it from here, so the
boards build with nothing else installed. Don't edit it here: change `edgecoil-pcb`, copy the
package over, and prove each board unchanged with
`PYTHONPATH=vendor python3 -m edgecoil_pcb.canon committed.kicad_pcb rebuilt.kicad_pcb`.
