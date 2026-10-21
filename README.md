# tune-button

A two-button pocket remote for Spotify on Android. **♥** likes the song that is playing; **+** adds
it to a playlist you choose. It runs on a battery for months and charges over USB-C.

It is **not a Bluetooth keyboard**. Nothing gets remapped on the phone. The button sends a small
signed Bluetooth LE broadcast; a companion app hears it in the background and calls the Spotify Web
API.

```
 button ──wake──► XIAO ESP32-C3 ──signed BLE advert──► Android app ──HTTPS──► Spotify Web API
                  (deep sleep)                         (background scan,       like / add to playlist
                                                        HMAC + replay check)
```

> **Status: built and unit-tested, not yet tried on hardware.** The firmware and app compile, and
> both sides pass tests against shared protocol vectors. Nothing has run on a real XIAO or phone yet.
> In particular, how quickly a phone with its screen off hears a press is unmeasured. See
> [*Latency*](docs/design.md#latency-the-open-question-phase-0) and the bench tests in
> [`docs/design.md`](docs/design.md).

## Repository layout

| Path | What it is |
|---|---|
| [`protocol/`](protocol/) | The wire format, plus `gen_vectors.py`, which generates the test vectors both sides check against |
| [`firmware/`](firmware/) | PlatformIO / Arduino firmware for the XIAO ESP32-C3 (NimBLE) |
| [`android/`](android/) | The companion app (Kotlin, Android 8+) |
| [`hardware/`](hardware/) | Wiring, parts list, a parametric OpenSCAD case with ready STLs, and two four-key PCBs (KiCad, generated) |
| [`docs/design.md`](docs/design.md) | How it works, security, power budget, bench tests |

## What you need

- A Seeed Studio XIAO ESP32-C3, a small LiPo, two 12 mm tactile switches: see
  [`hardware/wiring.md`](hardware/wiring.md)
- An Android phone (8.0 or later)
- **Spotify Premium.** Spotify's developer mode requires it on the account that owns the developer
  app, and allows up to five users per app.

## Set up

### 1. Spotify developer app

1. Sign in at [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and create
   an app. Tick **Web API**.
2. Add the redirect URI **`tunebutton://callback`**.
3. Copy the **Client ID**. No client secret is needed (the app uses PKCE).

### 2. Firmware

```bash
cd firmware
pio test -e native          # packet encoder and HMAC against protocol vectors
pio run                     # build
pio run -t upload           # flash over USB-C
# or, for a single image to flash anywhere:
sh scripts/merge.sh         # → tune-button-c3.bin, flash at offset 0x0
```

Without PlatformIO, flash `tune-button-c3.bin` at offset `0x0` with
[esptool-js](https://espressif.github.io/esptool-js/) in Chrome, or with
`esptool.py --chip esp32c3 write_flash 0 tune-button-c3.bin`.

**The firmware spends almost all its time in deep sleep, where the USB port disappears.** To flash it
again, hold **BOOT** (the small button next to USB-C) while plugging it in. Pressing a button also brings the port
back for the 10 s the device stays awake, which is long enough for an upload that is already waiting.

**Flashing the merged image at `0x0` erases the stored pairing** (the gap it fills covers the NVS
partition), so pair again afterwards. `pio run -t upload` leaves NVS alone.

Build options in `platformio.ini`: `TB_BURST_MS` (how long a press is broadcast) and
`TB_LED_PIN`.

**One button only?** Build `pio run -e xiao_esp32c3_1btn` (or `sh scripts/merge.sh xiao_esp32c3_1btn`
for a single image) and wire just the like button to D1. A press likes the song when you let go.
Holding the button for 5 seconds pairs it instead. The app needs no change; leave the playlist unset.

### 3. App

```bash
cd android
./gradlew test assembleDebug      # JDK 17+ with javac; Android SDK 35
# → app/build/outputs/apk/debug/app-debug.apk, sideload it
```

In the app, work through the screen top to bottom:

1. Paste the client ID and **Sign in to Spotify**.
2. **Choose playlist** for the + button.
3. **Pair**: hold both buttons for 3 seconds (on the one-button build, hold the button for 5 seconds)
   until the LED flickers, then tap Pair. Accept the Bluetooth pairing prompt if one appears. Each
   pairing makes a fresh key, so the previous phone stops working. A pairing that no phone completes
   changes nothing.
4. Fix everything listed under *Keep listening in the background*. **On Samsung phones, also add the
   app to *Never sleeping apps*.** Otherwise presses stop being heard after a while.
5. Use **Test without the device** to check the Spotify side on its own.

The *Recent presses* list shows, for each press, how long the phone took to hear it, how long Spotify
took, the battery level, and the result.

## Using it

Press **♥** or **+**. Within a few seconds the phone shows a notification ("♥ Liked — Title · Artist")
and buzzes once. A failure buzzes twice and says why (nothing playing, signed out, a local file, …).
Episodes work too.

## Licence

| What | Licence |
|---|---|
| The case and PCBs: `hardware/case/`, `hardware/pcb/` (OpenSCAD and KiCad sources, STLs) | [CERN-OHL-S-2.0](LICENSES/CERN-OHL-S-2.0.txt) |
| Firmware, app, protocol tools | [MIT](LICENSES/MIT.txt) |
| The Gradle wrapper (`android/gradlew*`, `android/gradle/wrapper/`), as shipped by Gradle | [Apache-2.0](LICENSES/Apache-2.0.txt) |
| Documentation (`README.md`, `docs/`, `hardware/wiring.md`, `protocol/spec.md`) | [CC BY 4.0](LICENSES/CC-BY-4.0.txt) |

Each source file carries an SPDX header, and [`REUSE.toml`](REUSE.toml) covers the rest by path.

Spotify is a trademark of Spotify AB. This project is not affiliated with or endorsed by Spotify.
