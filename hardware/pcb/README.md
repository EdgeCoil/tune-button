# Four-key PCBs

Two boards for a four-key tune-button, each with four Cherry MX switches in a 2 × 2 grid at the
standard 19.05 mm pitch:

| | `xiao/` | `c3/` |
|---|---|---|
| Brain | Seeed XIAO ESP32-C3 on two 1 × 7 sockets | ESP32-C3-WROOM-02 module; its PCB antenna sits over a notch cut out of the top-left corner, with no board under it |
| Size | 46 × 67 mm | 46 × 69.5 mm |
| Sides | Everything on top | Keys, LEDs, logo, name and URL on the back (the key side); all the electronics on the front, facing into the case |
| USB-C | On the XIAO, top edge | Centre of the bottom edge, about 70 mm from the antenna |
| Mounting | 4 × M2, all clear of the keycaps | 4 × M2, all clear of the keycaps |
| USB-C, charger, regulator | On the XIAO | On the board: USB-C, TP4054 charger (≈ 200 mA), load sharing, MCP1700 3.3 V (250 mA, about 1.6 µA quiescent) |
| Battery | JST-PH socket, wired on to the XIAO's BAT pads | JST-PH socket |
| Assembly | Hand: 6 SMD passives, a diode, sockets, switches | Front: single-sided SMD (JLC PCBA or hand). Back, by hand: the 4 MX switches and the 2 LEDs (0805) |

**Rev A is unbuilt and untested.** Both boards pass KiCad's electrical rules check and its design
rules check, with nothing unconnected and the board matching the schematic. No board has been ordered
or powered, and the firmware does not support four keys yet (see *Firmware*).

## Pin map

| Signal | XIAO board | C3 board | Notes |
|---|---|---|---|
| K1 (top left) | D1 / GPIO3 | GPIO3 | Same as the like button today |
| K2 (top right) | D2 / GPIO4 | GPIO4 | Same as the playlist button today |
| K3 (bottom left) | D3 / GPIO5 | GPIO5 | |
| K4 (bottom right) | D4 / GPIO6, and through D1 (BAT54W) onto GPIO5 | GPIO0 | See below |
| Battery divider (2 × 220 kΩ) | D0 / GPIO2 | GPIO1 | ADC1 |
| LED (1 kΩ) | D5 / GPIO7 | GPIO10 | |
| USB D− / D+ | (XIAO) | GPIO18 / GPIO19 | Native USB, used for flashing too |
| Straps | (XIAO) | GPIO2 and GPIO8 pulled up 10 kΩ; GPIO9 to BOOT | |

Every key switches to ground and uses the chip's internal pull-up, as now.

**The XIAO board's K4 is a compromise.** The C3 can wake from deep sleep only on GPIO0–5, and the
XIAO brings out only GPIO2–5 of those. GPIO2 is needed for the battery reading, which has to be on
ADC1 (GPIO0–4). So K4 is read on D4 and also pulls K3's line low through a Schottky. A K4 press wakes
the chip on GPIO5 with D4 low; a K3 press wakes it on GPIO5 with D4 high. If the key is already
released by the time the firmware reads D4, a quick tap on K4 would read as K3. A deep-sleep wake stub
can read D4 within about a millisecond of waking. The C3 board has GPIO0 and GPIO1 free, so all four
keys are direct wake pins there.

## Before ordering

Check these against the parts in hand. Each is a one-line change in `gen.py`.

1. **XIAO header rows: 15.24 mm apart, centre to centre.** That is the 0.6″ spacing the common
   XIAO footprints use. I took it from those footprints and a Seeed forum answer, not from Seeed's
   drawing. Measure across the two rows of pins on the XIAO.
2. **Battery lead order.** Pin 1 of the JST-PH is marked **+** on the silkscreen. JST-PH LiPo
   leads are not wired consistently between sellers, and neither board protects against a reversed
   cell, so check the plug before you plug it in.
3. **C3 regulator headroom.** The MCP1700 was chosen for its quiescent current (about 1.6 µA),
   which matters more than anything else for a board that sleeps for months. It is rated at 250 mA.
   That covers BLE with room to spare, and the 22 µF bulk capacitor is there for the start-up
   calibration burst and Wi-Fi transmit peaks, which run past 250 mA for a few hundred microseconds.
   The XC6206 (JLC Basic, same pinout, 200 mA) is the cheaper fallback. In simulation, BLE events
   (about 100 mA) hold 3.3 V down to a 3.4 V cell, but 350 mA Wi-Fi bursts pull it to about 2.97 V
   even on a full cell, near the brown-out threshold. For Wi-Fi, a 500 mA low-Iq part (such as the
   RT9080) is the step up. Treat 3.5 V as the cell's usable cut-off.
4. **MX switches** use the 5-pin PCB-mount footprint, which also takes 3-pin plate-mount switches.
   The boards are not hot-swap. On the C3 board they mount on the back and are soldered from the
   front, where their leads and posts come through between the parts; trim the leads short.
5. **C3 board, front side faces the case floor.** The tallest parts there are the JST socket
   (4.8 mm) and the module and USB-C (about 3.3 mm), so the case needs that much room under the
   board, plus the battery. RESET and BOOT are on that side too, reachable with the case open.

## Firmware

The firmware is written for one or two buttons. Four keys need a build flag per board with the pin
map above, two more button codes in [`protocol/spec.md`](../../protocol/spec.md) (byte 11), and app
actions for them. For the XIAO board, a wake stub should read D4. None of that is written yet.

## Rebuilding

Everything is generated: [`gen.py`](gen.py) holds the parts, nets and placement for both boards.
It writes the schematic, with a label on every pin, and an unrouted board from the same netlist.
[`route.py`](route.py) autoroutes with Freerouting, adds ground stitching vias and fills the pours.
It retries until KiCad's DRC is clean. [`build.sh`](build.sh) runs both steps, then ERC and DRC
with the schematic parity check, then exports gerbers, drill files, BOM, pick-and-place, a schematic
PDF and renders into `<board>/fab/`.

```sh
KICAD_SYMBOL_DIR=/path/to/kicad/symbols FREEROUTING=/path/to/freerouting-2.1.0.jar ./build.sh
```

It needs KiCad 9, Java 21 and Freerouting 2.1.0 (later Freerouting releases need Java 25). Edit
`gen.py` and rebuild rather than editing the KiCad files: a rebuild overwrites them. To hand-route
instead, stop after `gen.py` and open the project in KiCad.

For JLCPCB, upload `fab/tune-button-<board>-gerbers.zip` (2 layers, 1.6 mm, any colour). For their
assembly service, add `-jlc-bom.csv` and `-jlc-cpl.csv`. They list only the parts JLC fits, each with
its LCSC number; the MX switches, back-side LEDs, keycaps, UART header and battery are left for you.
Order **top-side assembly only**. `fab_jlc.py` corrects the rotations and the USB-C origin where JLC's
footprint differs from KiCad's (MCP1700, AO3401A, SRV05-4, TP4054, USB-C), checked against JLC's own
footprints; still check the placement in JLC's preview before paying, since a wrong SRV05-4 rotation
shorts VBUS.

The C3 board is under JLC's 70 × 70 mm minimum for Standard assembly, so order Economic, or ask
for a panel. Its USB-C, battery socket and module sit closer to the edges than JLC's 2.5 mm assembly
rule, so if JLC asks for rails, have them on the **left and right edges only**: the USB-C overhangs
the bottom edge and the antenna overhangs the notch at the top.

Parts are chosen to keep JLC's per-type fee down: every passive, the LED, the MOSFET, the diode
and the tact switches are JLC **Basic** parts, and the charger (TP4054) and USB ESD part (SRV05-4)
are **Preferred** parts, which also carry no fee. Four types are **Extended**, at a fee per type per
order: the ESP32-C3-WROOM-02 module, the USB-C socket, the JST battery socket and the MCP1700
regulator. Catalogue status changes; the build doesn't check it.

The EdgeCoil mark, name and URL on the back silkscreen are not covered by the board licence (see
[`LICENSES/LicenseRef-EdgeCoil-Mark.txt`](../../LICENSES/LicenseRef-EdgeCoil-Mark.txt)). To build
boards to share or sell, remove the `logo` and the `edgecoil.dev` text from `gen.py` and rebuild.
