# Four-key PCBs

Three boards for a four-key tune-button. Two carry four Cherry MX switches in a 2 × 2 grid at the
standard 19.05 mm pitch; the third, `c3-jst/`, is the C3 board's circuit with the switches off the
board, on wires to a JST connector, so it can be much smaller:

| | `xiao/` | `c3/` | `c3-jst/` |
|---|---|---|---|
| Brain | Seeed XIAO ESP32-C3 on two 1 × 7 sockets | ESP32-C3-WROOM-02 module; its PCB antenna sits over a notch cut out of the top-left corner, with no board under it | The same module; its antenna overhangs the top edge, with no board under it |
| Size | 46 × 67 mm | 46 × 69.7 mm | 36 × 50 mm |
| Keys | 4 MX on the board | 4 MX on the back | J3, a 7-pin JST-PH (2 mm): 1 GND, 2–5 K1–K4, 6 LED (through 330 Ω: about 4 mA into a red LED), 7 3V3. Each button goes between its K pin and GND |
| Sides | Everything on top | Keys, LEDs, logo, name and URL on the back (the key side); all the electronics on the front, facing into the case | Every part on the front; logo, name, URL and the J3 pin list on the back, behind J3 |
| USB-C | On the XIAO, top edge | Centre of the bottom edge, about 70 mm from the antenna | Bottom edge, left; J3 beside it on the right, the battery on the right edge |
| Mounting | 4 × M2, all clear of the keycaps | 4 × M2, all clear of the keycaps. Use nylon washers or standoffs: tracks run within 2 mm of H3 (left edge, 23 mm down), where a metal screw head could wear through the mask | 2 × M2. At H2 use a nylon screw, or nylon washers on both faces: K2 (front) and VBUS (back) run 1.6 mm from its centre, under any metal head or nut. H1 has only the ground pour under its head (nearest track or via 2.5 mm out). Support the board behind J2 and J3 in the case, since the holes are 10–15 mm from where the plugs push |
| USB-C, charger, regulator | On the XIAO | On the board: USB-C, TP4054 charger (≈ 200 mA), load sharing, RT9080 3.3 V (600 mA, about 2 µA quiescent) | As `c3/` |
| Battery | JST-PH socket, wired on to the XIAO's BAT pads | JST-PH socket | JST-PH socket |
| Assembly | Hand: 4 SMD passives, an LED, a diode, the battery socket and header, the XIAO sockets, switches (on the panel, JLC fits all but the switches) | Front: single-sided SMD (JLC PCBA or hand). Back, by hand: the 4 MX switches and the 2 LEDs (0805) | Single-sided SMD, all fitted by JLC; nothing to solder by hand. The UART is two test pads (TX, RX) |

On `c3-jst`, J3's key lines have their own ESD array (U5, a second SRV05-4), since they run out on
wires to buttons people touch. J3's 3V3 is the regulator's output, shared with the module's 350 mA
Wi-Fi bursts: keep what hangs on it under about 100 mA. J3's LED pin (6) is the one wire with no
clamp: only R15 and the chip's own protection diodes guard it.

**Rev A is unbuilt and untested.** All three boards pass KiCad's electrical rules check and its design
rules check, with nothing unconnected and the board matching the schematic. No board has been ordered
or powered, and the firmware does not support four keys yet (see *Firmware*).

## Pin map

| Signal | XIAO board | C3 boards | Notes |
|---|---|---|---|
| K1 (top left) | D1 / GPIO3 | GPIO3 | Same as the like button today |
| K2 (top right) | D2 / GPIO4 | GPIO4 | Same as the playlist button today |
| K3 (bottom left) | D3 / GPIO5 | GPIO5 | |
| K4 (bottom right) | D4 / GPIO6, and through D1 (1N4148WS) onto GPIO5 | GPIO0 | See below |
| Battery divider (2 × 220 kΩ) | D0 / GPIO2 | GPIO1 | ADC1 |
| LED (1 kΩ) | D5 / GPIO7 | GPIO10 | |
| USB D− / D+ | (XIAO) | GPIO18 / GPIO19 | Native USB, used for flashing too |
| Straps | (XIAO) | GPIO2 and GPIO8 pulled up 10 kΩ; GPIO9 to BOOT | |

Every key switches to ground and uses the chip's internal pull-up, as now.

**The XIAO board's K4 is a compromise.** The C3 can wake from deep sleep only on GPIO0–5, and the
XIAO brings out only GPIO2–5 of those. GPIO2 is needed for the battery reading, which has to be on
ADC1 (GPIO0–4). So K4 is read on D4 and also pulls K3's line low through a diode: a 1N4148WS rated at most 0.715 V at 1 mA (C2128 is), since a Schottky leaks enough when warm to drag D4 low while K3 is held. A K4 press wakes
the chip on GPIO5 with D4 low; a K3 press wakes it on GPIO5 with D4 high. If the key is already
released by the time the firmware reads D4, a quick tap on K4 would read as K3. A deep-sleep wake stub
can read D4 within about a millisecond of waking. The C3 board has GPIO0 and GPIO1 free, so all four
keys are direct wake pins there.

## Before ordering

Check these against the parts in hand. Each is a one-line change in `gen.py`.

1. **XIAO header rows: 15.24 mm apart, centre to centre.** That is the 0.6″ spacing the common
   XIAO footprints use. I took it from those footprints and a Seeed forum answer, not from Seeed's
   drawing. Measure across the two rows of pins on the XIAO.
2. **Battery lead order.** Pin 1 of the battery JST-PH (J2 on `c3-jst`) is marked **+** on the silkscreen. JST-PH LiPo
   leads are not wired consistently between sellers, and no board protects against a reversed
   cell, so check the plug before you plug it in.
3. **C3 regulator.** The RT9080 is rated at 600 mA (its current limit is at least 610 mA) and draws
   about 2 µA when idle, which matters most for a board that sleeps for months. Espressif asks for a
   supply of at least 500 mA, because Wi-Fi transmit peaks run to about 350 mA. Its dropout is
   0.31 V at 600 mA (about 0.2 V at 350 mA), so the rail holds 3.3 V through those peaks down to a
   cell of about 3.5 V. Its input is rated to 5.5 V (6.5 V absolute), which is why C1 has a 1 Ω
   damping resistor against plug-in ringing. The MCP1700 (250 mA, 1.6 µA) is a lower-current alternative in a SOT-23
   footprint, not a drop-in.
4. **Use cells with a protection board.** D4 (a Schottky across the battery FET) keeps the supply
   up for the few ms after USB is unplugged, but its reverse leakage trickles into the cell while
   on USB: negligible at room temperature (net discharge), about +15 µA at 60 °C. Once the charger
   has finished, only the cell's own protection board would stop a hot, permanently plugged-in
   board from slowly overcharging it. Ordinary LiPo cells with a PCM are fine.
5. **MX switches** use the 5-pin PCB-mount footprint, which also takes 3-pin plate-mount switches.
   The boards are not hot-swap. On the C3 board they mount on the back and are soldered from the
   front, where their leads and posts come through between the parts; trim the leads short.
6. **C3 board, front side faces the case floor** (`c3-jst` has nothing on its back, so it can sit either way up). The tallest parts there are the JST socket
   (5.5 mm) and the module and USB-C (about 3.3 mm), so the case needs that much room under the
   board, plus the battery. RESET and BOOT are on that side too, reachable with the case open.
7. **`c3-jst` debug UART.** TP1 (TX) and TP2 (RX) are bare pads; take ground from J3 pin 1 or the
   USB-C shell.

## Firmware

The firmware is written for one or two buttons. Four keys need a build flag per board with the pin
map above, two more button codes in [`protocol/spec.md`](../../protocol/spec.md) (byte 11), and app
actions for them. For the XIAO board, a wake stub should read D4. None of that is written yet.
The existing build's pins don't match either board: `TB_LED_PIN=5` would drive the XIAO board's
K3 line (its LED is on D5, GPIO7), and the C3 board has no build environment (battery on GPIO1,
LED on GPIO10). Below about 3.6 V a Wi-Fi-sized burst sags the C3's 3.3 V rail under 3.0 V (simulated with the routed copper), so the
firmware should stop using radio-heavy features there.

## Rebuilding

Everything is generated: [`gen.py`](gen.py) holds the parts, nets and placement for all three boards.
It writes the schematic, with a label on every pin, and an unrouted board from the same netlist.
[`route.py`](route.py) lays the copper and fills the pours. The routing is frozen: each board's
`routing.json` holds its reviewed tracks and vias, and `route.py` replays it onto the generated
board, so a fix is a small edit to that file rather than a new layout. `route.py --reroute <board>`
autoroutes afresh with Freerouting instead, adding ground stitching vias and retrying until KiCad's
DRC is clean; `route.py --freeze <board>` then records the result. A reroute changes the whole
layout, so it needs a fresh review. Moving a part in `gen.py` also needs one, or the frozen copper
no longer meets its pads; DRC catches that. [`build.sh`](build.sh) runs both steps, then ERC and DRC
with the schematic parity check, then exports gerbers, drill files, BOM, pick-and-place, a schematic
PDF and renders into `<board>/fab/`.

```sh
KICAD_SYMBOL_DIR=/path/to/kicad/symbols FREEROUTING=/path/to/freerouting-2.1.0.jar ./build.sh
```

It needs KiCad 9, Java 21 and Freerouting 2.1.0 (later Freerouting releases need Java 25). Edit
`gen.py` and rebuild rather than editing the KiCad files: a rebuild overwrites them. To hand-route
instead, stop after `gen.py` and open the project in KiCad.

For JLCPCB, upload `fab/tune-button-<board>-gerbers.zip` (2 layers, 1.6 mm, **black** mask, white legend, **lead-free HASL**: Economic assembly offers that
for 2–50 boards, while ENIG would force green). Under *Mark on PCB*, choose *Specify a location*:
the `JLCJLCJLCJLC` marker puts their order number on the electronics side (C3) or the back (XIAO, `c3-jst`),
away from the logo. Add a remark that the C3's module antenna and USB-C overhang the edge by
design. For their
assembly service, add `-jlc-bom.csv` and `-jlc-cpl.csv`. They list only the parts JLC fits, each with
its LCSC number; the MX switches, back-side LEDs, keycaps, UART header and battery are left for you
(on `c3-jst`, JLC fits every part and only the battery and buttons are left).
Order **top-side assembly only**. `fab_jlc.py` corrects the rotations and the USB-C origin where JLC's
footprint differs from KiCad's (RT9080, AO3401A, SRV05-4, TP4054, USB-C, the 7-pin JST, the XIAO board's
sockets and header), checked against JLC's own
footprints; still check the placement in JLC's preview before paying, since a wrong SRV05-4 rotation
(U2, and U5 on `c3-jst`) shorts the 3V3 rail.

The C3 board is under JLC's 70 × 70 mm minimum for Standard assembly, so order Economic, or ask
for a panel. Its USB-C, battery socket and module sit closer to the edges than JLC's 2.5 mm assembly
rule, so if JLC asks for rails, have them on the **left and right edges only**: the USB-C overhangs
the bottom edge and the antenna overhangs the notch at the top. `c3-jst` (36 × 50 mm) is the same:
Economic, and rails on the left and right only, its antenna overhanging the top edge. For either C3
board, ask for mouse-bite rails rather than V-cut: the ground pour runs 0.3 mm from the edges, which
meets JLC's routed-edge rule but not its 0.4 mm V-cut one. On `c3-jst`, add a remark placing the tabs:
on the left edge only between 14 and 25 mm from the top (below that, a mounting hole, a VBUS track
0.7 mm in and C1, a capacitor that cracks if the board flexes next to it), and on the right edge between
3 and 8, 25 and 29, or 39 and 45 mm. The 25-29 and 39-45 mm windows are within 2 mm of J2's and J3's
anchor pads: cut tabs there with flush cutters rather than snapping them.

### All three on one panel (Standard assembly)

If the ESP32 module needs Standard assembly, which wants at least 70 × 70 mm, order the three boards
as one panel: [`panel.py`](panel.py) builds `panel/tune-button-panel.kicad_pcb` (148 × 87 mm) from
the routed boards with [KiKit](https://github.com/yaqwsx/KiKit) 1.8, and writes `panel/fab/`. Run
`./build.sh` first, then `python3 panel.py` with KiKit 1.8.1 installed where Python can also see KiCad's
`pcbnew` module (for example a venv made with `--system-site-packages`, then `pip install kikit==1.8.1`):
the panel depends on KiKit's internals, such as how it spaces the bites.

- The boards sit side by side (XIAO, C3, `c3-jst`) in a 6 mm frame: rails on the left and right,
  and bars across the top and bottom. The bars stay at least 2.5 mm from every board edge and
  1.5 mm from anything overhanging one (`c3-jst`'s antenna, the USB-C faces). The frame carries
  JLC's four 1.152 mm tooling holes in its corners, and three fiducials 4.35 mm in from the rails'
  outer edges.
- Mouse-bite tabs join the boards to each other and to the frame. They go only where no track,
  via or pad comes within 1 mm of the edge, at least 2 mm from a mounting hole, and never under an
  overhanging part. Each tab has 1 mm fillets with bites round them: 0.5 mm holes at about 0.8 mm
  pitch, set 0.25 mm inside the board.
  The ground pour is held back around each tab. `panel.py` checks that each board is joined to the
  panel only at its tabs.
- `c3-jst` has six tabs: one on its left to the C3, three to the right rail, one to the top bar and
  one to the bottom bar. Most of its left edge is closed to tabs: a mounting hole, a VBUS track 0.7 mm in,
  and C1 (no tab comes within 3 mm of an 0805 or larger ceramic capacitor, which cracks when the board
  flexes). Its top edge carries the antenna. A tab goes at least 2 mm from a connector's pads (JLC's
  keep-out) wherever its edge allows; two can't: c3-jst's lower right-edge tabs end 1.2-1.3 mm from
  the anchor pads of the battery socket J2 and of J3. Their bites sit outside the board edge instead
  (so they stop where the fillets start), and **cut those two tabs with flush cutters rather than
  snapping them**, so the bending doesn't crack the connectors' joints. File the tab remnants flush.
- Upload `panel/fab/tune-button-panel-gerbers.zip` as one design with **Panel by customer**, and
  `-jlc-bom.csv` and `-jlc-cpl.csv` for **Standard** PCBA, **top side only**. Add a remark that the
  modules' antennas and the USB-C sockets overhang their boards' edges by design. JLC charges a
  small fee for the different designs on the panel. Each designator is prefixed with its board
  (`XIAO_`, `C3_`, `JST_`), and each part's placement is that board's own, moved by the board's
  place in the panel.
- On the panel, JLC also fits the XIAO board's parts: its passives, diode, LED, battery socket, the
  two 1 × 7 sockets and the 2-pin battery header. The sockets and header are through-hole, soldered
  by JLC for a hand-soldering fee (about $3.50) plus a per-joint rate. Left for you: the MX switches on both keyboard boards, the C3's two
  back-side LEDs and its UART header, the XIAO itself, and the batteries and buttons.
- Only the C3's `JLCJLCJLCJLC` marker is kept on the panel. Under *Mark on PCB*, choose
  *Specify a location*.

Parts are chosen to keep JLC's per-type fee down: every passive, the LED, the MOSFET, the diodes
and the tact switches are JLC **Basic** parts, and the charger (TP4054) and USB ESD part (SRV05-4)
are **Preferred** parts, which also carry no fee. Four types are **Extended**, at a fee per type per
order: the ESP32-C3-WROOM-02 module, the USB-C socket, the JST battery socket and the RT9080
regulator. `c3-jst` adds a fifth, the 7-pin JST button socket; its LEDs are Basic parts (C84256),
since JLC fits them there. On the panel, the XIAO board's 1 × 7 sockets (C2932672, 8.5 mm tall) and
2-pin header (C492401) are two more Extended types. Catalogue status changes; the build doesn't check it.

The EdgeCoil mark, name and URL on the back silkscreen are not covered by the board licence (see
[`LICENSES/LicenseRef-EdgeCoil-Mark.txt`](../../LICENSES/LicenseRef-EdgeCoil-Mark.txt)). To build
boards to share or sell, remove the `logo` and the `edgecoil.dev` text from `gen.py` and rebuild.
