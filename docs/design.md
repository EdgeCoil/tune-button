# Design notes

## Why a companion app, and not a keyboard

The obvious way to make a BLE button do something on a phone is BLE HID, where the device pretends
to be a keyboard. The phone then sees a keyboard, and the button has to be mapped to a media key
or an accessibility shortcut. Spotify has no key for "like" in any case.

The ESP32-C3 has **BLE only** (no Bluetooth Classic, so no AVRCP). The remaining route is a small app
on the phone that listens for the button and calls the Spotify Web API itself. The phone has to be
online to stream anyway, so the API is always reachable when it matters.

## How a press travels

1. A key press pulls its GPIO low, which wakes the C3 from deep sleep.
2. The firmware works out the gesture (press, hold or double press; a key with no hold or double
   action sends at once). It increments a counter that it keeps in NVS, then builds the 24-byte
   press payload ([protocol/spec.md](../protocol/spec.md)) with an HMAC tag. It broadcasts it as a
   non-connectable advert every 30–40 ms until `TB_BURST_MS` after the last event. Each advert
   also names the two events before it, so quick presses aren't lost.
3. On the phone, a scan registered with a `PendingIntent` and a manufacturer-data filter
   (magic + version + device id) is running in the Bluetooth controller. When the advert matches,
   Android starts `PressReceiver`, even if the app process was dead.
4. `PressReceiver` checks the tag and the counter, and queues an expedited WorkManager job for
   each new event, in order.
5. `PressWorker` runs the action set for that key and gesture: for example, it asks Spotify what is
   playing and likes it (`PUT /me/library`), or skips (`POST /me/player/next`). It shows a
   notification, which also buzzes.

The connection is never held open, so the device costs nothing between presses beyond deep-sleep current.

## Latency: the open question (Phase 0)

With the screen off, Android duty-cycles background scans. The scan window and interval are not
public, and Samsung adjusts them further. A press is only heard if the advert is still
being sent when the phone next listens, so `TB_BURST_MS` must exceed the phone's screen-off scan
interval.

The firmware puts an unauthenticated **age** byte in every advert (time since the press, 100 ms
steps). The app logs it as **"heard Xs"**, the delay from press to the phone hearing it, measured with
no clock sync. To measure:

1. Pair, grant permissions, set battery to **Unrestricted**, and on Samsung also add the app to
   *Never sleeping apps*.
2. Swipe the app away and turn the screen off. Press about 10 times, a minute or more apart.
3. Open the app and read the "heard" column. Repeat for each **scan mode** (low power / balanced /
   low latency) and with the screen on.

Pick `TB_BURST_MS` at about 1.5 × the worst "heard" figure in the chosen mode, then rebuild.

### Measurements so far

| Date | Phone | Scan mode | Screen | Presses | Heard |
|---|---|---|---|---|---|
| 2026-10-21 | older Samsung, app 0.1.0, one-button build | Balanced | locked | 1 | 0.83 s |

One press is not a distribution: the 10-press run above is still to do. It does put the first figure
well inside the 10 s burst.

Two outcomes would change the design:

- **Some presses are never heard** (gaps in the counter in the log) at any sane burst length. Then the
  design changes to a held GATT connection: the phone keeps an `autoConnect` link, and the device sits
  in light sleep at a long connection interval. That costs about 1 mA instead of about 45 µA, so the
  battery would last weeks rather than months.
- **Latency is fine, but Samsung kills the receiver after some days.** Look at *Device care →
  Battery → Background usage limits* first.

## Security

The device is used near other people (neighbours, shared spaces). Anyone in range can hear the
adverts, record them, and send their own.

- **Forgery:** an HMAC-SHA256 tag truncated to 64 bits, under a 128-bit per-device key. An attacker
  sending adverts cannot do better than guessing the tag.
- **Replay:** the counter must be strictly greater than the last one accepted. It is persisted on both sides before use.
  A recorded advert replayed later has an old counter and is ignored.
- **Denial:** only verified adverts advance the counter, so a forged one with a huge counter
  changes nothing. Someone can still jam 2.4 GHz, and nothing here defends against that.
- **Privacy:** the advert carries no name or service UUID. The device id is fixed between pairings, though,
  so the device can be recognised. It reveals that the device exists and when it is pressed, not what
  it does. The id changes each time the device is paired.
- **Pairing:** LE Secure Connections, Just Works, because there is no display or keypad. Someone actively
  connecting during the 60 s window could read the key first, and the phone would then fail to pair.
  If pairing fails, pair again, since every pairing makes a new key.
- **Spotify:** OAuth Authorization Code with PKCE, so no client secret exists. The refresh token and the
  device key are AES-GCM encrypted under an Android Keystore key, and `allowBackup` is off.

The firmware has its own SHA-256 (`firmware/src/packet.cpp`) so that the encoder runs and is tested on
the build host. It is checked against the RFC 4231 HMAC vectors.

## Power budget (estimated, not yet measured)

| State | Current | Per day |
|---|---|---|
| Deep sleep, XIAO C3 (Seeed's figure) | ≈ 44 µA | ≈ 1.06 mAh |
| Battery divider | ≈ 8 µA | ≈ 0.2 mAh |
| A press: ~10 s advertising, CPU awake | ≈ 20–25 mA | ≈ 0.07 mAh each |

With 20 presses a day, the total is about 2.7 mAh/day, so a 500 mAh cell lasts roughly **six months**. The deep-sleep
figure dominates, so measure it.

## Bench tests

None of these has been done yet.

| # | Test | Pass |
|---|---|---|
| 1 | Boots and flashes with the battery divider fitted (GPIO2 strapping) | Enumerates, and the log shows a wake |
| 2 | Deep-sleep current from the battery (meter in series with BAT+) | ≤ 60 µA |
| 3 | Each key wakes it and sends the right button byte (nRF Connect shows the payload, byte 11) | 01–04 |
| 3a | Give key 3 a hold and key 4 a double press in the app, send the settings, then hold key 3 and double-press key 4 | 13, then 24; key 1 still sends at once |
| 3b | Press key 3 three times quickly | Three skips (the history bytes) |
| 3c | XIAO board: the quickest tap you can on K4, and a few K3 presses | K4 reads as key 4 (the wake stub); K3 never sends a key 4 as well |
| 3d | Press key 3, then within 10 s hold keys 1 and 2 for 3 s | Pairing mode starts (Bluetooth restarts within one wake) |
| 4 | Holding a key down does not leave it awake, wake-looping or repeating its action | Timer wake once a minute, otherwise asleep, nothing sent |
| 5 | Hold keys 1 and 2 for 3 s (one-button build: hold 5 s) → LED flashes, the app pairs, and the LED triple-flashes | Paired |
| 5a | Hold to pair but don't pair from the app; let the 60 s window lapse | The phone that was already paired still works |
| 6 | Screen off, app swiped away: key 1 likes the current song | Notification, and the song is in Liked Songs |
| 7 | Same for key 2 (playlist), key 3 (skip) and key 4 (play/pause) | Each does its action |
| 8 | Replay: record an advert with nRF Connect and re-broadcast it | Nothing happens; no log entry |
| 9 | Reboot the phone, press without opening the app | Still works (BootReceiver) |
| 10 | Charge from USB-C while running; the charge LED is visible through the case | Charges |
| 11 | The battery % in the app is within about 10 % of a meter reading converted by the same curve | Close |
| 12 | Phase-0 latency table for each scan mode | Recorded here |
