# Wiring

Everything hangs off a stock **Seeed Studio XIAO ESP32-C3**. No custom board. For four MX keys on a
PCB instead, see [`pcb/`](pcb/).

```
                 XIAO ESP32-C3 (top view, USB-C at the top)
                  ┌──────────┐
            D0/A0 │●        ●│ 5V
   like ──── D1   │●        ●│ GND ─── both buttons, divider, LED
   list ──── D2   │●        ●│ 3V3
   LED ───── D3   │●        ●│ D10
             D4   │●        ●│ D9
             D5   │●        ●│ D8
             D6   │●        ●│ D7
                  └──────────┘
         back: BAT+ / BAT− pads, U.FL antenna socket

  BAT+ ──┬── LiPo +  (through the optional slide switch)
         └── 220 kΩ ──┬── 220 kΩ ── GND
                      ├── A0 (D0)
                      └── 100 nF ── GND
  BAT− ──── LiPo −

  D1 ── [like button] ── GND          D3 ── 1 kΩ ── LED ▷| ── GND   (optional)
  D2 ── [list button] ── GND
```

| XIAO pin | GPIO | Connects to | Why this pin |
|---|---|---|---|
| D1 | 3 | Like button → GND | The C3 can wake from deep sleep only on GPIO0–5 |
| D2 | 4 | Playlist button → GND | Same |
| A0 (D0) | 2 | Battery divider midpoint | ADC1. GPIO2 is a strapping pin, and the divider holds it at about half the battery voltage, which sits at 1.5–2.1 V, below the high threshold. That is fine: on the C3, GPIO2 does not select the boot mode (GPIO8 and GPIO9 do). **Check that it still boots with the divider fitted.** |
| D3 | 5 | Optional LED via 1 kΩ | Digital only. GPIO5 is ADC2, which is unreliable on the C3, so it can't be the battery input |
| BAT+ / BAT− (back pads) | | LiPo | The XIAO's charger fills the cell from USB-C |

**One button:** wire only the like button to D1 and build the `xiao_esp32c3_1btn` firmware
environment. Leave D2 unconnected; that build never wakes on it.

The buttons use the chip's internal pull-ups, so nothing else is needed. If the bench shows spurious
wakes, add a 100 kΩ pull-up from each button pin to 3V3.

**Fit the antenna.** The XIAO ESP32-C3 has no on-board antenna; without the supplied U.FL antenna its
range is a few centimetres.

The divider draws about 8 µA continuously. Leave it out and the app shows the battery as unknown;
the firmware detects that and sends `FF`.

## Parts

| Qty | Part | Notes |
|---|---|---|
| 1 | Seeed Studio XIAO ESP32-C3 | Comes with the U.FL FPC antenna |
| 1 | LiPo 503035, 3.7 V ~500 mAh, **with protection board** | Any cell up to 35.5 × 30.5 × 5.5 mm fits the case as drawn |
| 2 | Tactile switch 12 × 12 × 7.3 mm + round cap | Body presses into the lid sockets |
| 2 | 220 kΩ resistor | Battery divider |
| 1 | 100 nF capacitor | Steadies the ADC reading |
| 0–1 | 3 mm LED + 1 kΩ | Optional press indicator |
| 0–1 | Small slide switch | Optional, in series with LiPo + for storage |
| 4 | M2 × 6 self-tapping screws | Lid |

## Assembly

1. Solder the LiPo leads to the BAT pads on the back. **Mind the polarity, as the board has no protection
   against reversal.** Run them out sideways, since the XIAO sits on 2 mm rails.
2. Solder the divider "dead bug" style straight onto A0 and GND, and add a short lead to BAT+.
3. Press the switches into the lid sockets from below, bend the legs flat, and wire one side of each to GND and
   the other to D1 / D2. Each 12 × 12 switch has two pairs of legs that are joined internally. Use
   one leg from each pair.
4. Plug the antenna in and stick it flat against the inside of a long wall at the XIAO end.
5. Slide the XIAO onto its rails with USB-C into the end opening, the battery into its bay, and screw the lid on.

Print files: [`case/`](case/).

## Case for the one-button build

[`case/tune-button-1btn.scad`](case/tune-button-1btn.scad) is a round puck, Ø 76 × 47 mm, for a
**22 mm panel-mount push button** in the middle of the top. It suits a big anti-vandal or mushroom
button rather than a 12 mm tactile switch. The base plate holds the LiPo flat and the XIAO beside it on
rails, with USB-C through the side wall. The button hangs from the top above them. Three M2 × 6
self-tapping screws hold the base on from below.

- **Print** the body top face down and the base flat side down, with no supports.
- **Check the dimensions first.** The cell's width and length and the button's thread diameter were
  measured. The cell thickness and the button's depth behind the panel are estimates, marked
  `ESTIMATE` in the source. The file stops with an error, rather than producing a case that can't be
  assembled, if the battery or the posts would collide.
- **Keep the antenna off the switch.** A steel switch body right next to the FPC antenna detunes it.
  Stick the antenna flat on the inside wall, in the upper half, on the side away from the USB-C.
- **Hold the XIAO in place.** A dab of hot glue or a foam pad on top keeps it on its rails. The plug
  pushes it into the stop at the rails' inner end.
- **Check the panel thickness.** The top is 3 mm thick, which suits most 22 mm buttons. If the nut
  won't catch, reduce `top_t`. The OpenSCAD source is parametric, so measure your parts and adjust.
