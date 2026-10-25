# tune-button wire protocol, version 2

Two things go over the air:

1. **Press adverts.** These are connectionless and sent on every button press. The phone never
   connects to receive them.
2. **Pairing.** This is a short GATT session used once to give the phone the device's key. The
   same session also carries the **key settings**: which keys wait for a hold or a double press.

## Press advert

This is a legacy, non-connectable BLE advertisement (`ADV_NONCONN_IND`). It carries the flags AD
and one *Manufacturer Specific Data* AD (type `0xFF`), and no name or service UUIDs, so a scanner
nearby sees only an anonymous blob.

Company identifier `0xFFFF` is the Bluetooth SIG's value for testing and unassigned use, and is
sent little-endian (`FF FF`). The payload after it is 24 bytes, which with the flags fills 29 of a
legacy advert's 31:

| Offset | Size | Field | Notes |
|---|---|---|---|
| 0 | 2 | magic | `54 42` (`"TB"`) |
| 2 | 1 | version | `02` |
| 3 | 4 | device id | random, chosen at pairing; the phone filters on it |
| 7 | 4 | counter | little-endian `uint32`, +1 per event, never reused (kept in NVS) |
| 11 | 1 | button | the event: key in the low nibble, gesture in the high one (below) |
| 12 | 1 | battery | percent 0–100, `FF` unknown |
| 13 | 2 | history | the button bytes of events `counter − 1` and `counter − 2`, `00` where that event was not sent in this wake |
| 15 | 8 | tag | first 8 bytes of `HMAC-SHA256(key, bytes 0..14)` |
| 23 | 1 | age | time since this event in 100 ms units, saturating at `FF`. **Not authenticated**; diagnostics only |

`key` is 16 random bytes. The tag covers everything except `age`, which changes during a burst
while the authenticated part stays the same, so one event can be recognised however many times
it is heard.

**Button byte.** Keys are numbered 1–4 (the four-key boards: 1 top left, 2 top right, 3 bottom left,
4 bottom right). Gestures are `0` press, `1` hold, `2` double press. So `01` is key 1 pressed,
`13` key 3 held and `24` key 4 double-pressed. `01` and `02` are version 1's like and
add-to-playlist codes. What each event *does* is up to the phone.

**History.** A new event replaces the advert on air at once, so two presses closer together than
the phone's scan gaps would otherwise reach it as one. Each advert therefore also names the two
events before it, and a phone that hears only the newest still acts on all three.

### Version 1

Firmware before four keys sends version `01`: 22 bytes, with no history, the tag at 13 covering
bytes 0..12, and age at 21. Its button byte is `01` or `02`. Receivers may go on accepting it.

### Gestures

Which gestures a key waits for is the device's *key settings* byte (see Pairing): bit `k − 1` set
when key `k` has a hold action, bit `k + 3` when it has a double-press action. The default, `00`,
waits for neither.

- A key with **neither** sends a press the moment it goes down (after a 30 ms debounce).
- With a **hold** action, a press is sent on release; held for 600 ms, a hold is sent instead,
  without waiting for release.
- With a **double-press** action, a press is sent 300 ms after release if no second press came;
  a second press within 300 ms sends a double press as it goes down.
- A key waiting for a second press is settled before another key's press, so that press can't
  overtake it.
- Keys 1 and 2 held together send nothing: that is the pairing chord. (While the device is already
  awake, the first of the two can send its press if the second follows more than 30 ms later.)
- A key that is already down when the device wakes for another reason (a key stuck down, power-on)
  sends nothing until it has been let go.
- The one-button build always waits for release: a release before 600 ms is a press, after it a
  hold, and 5 s is pairing.

### Receiver rules

The phone app enforces these:

- The magic, version and device id must match a paired device. If not, ignore the advert silently.
- The tag is compared in constant time. If it is wrong, ignore the advert. Neighbours can
  broadcast anything.
- `counter` must be **strictly greater** than the last accepted counter for that device. Equal
  means a repeat of this burst, so ignore it. Lower means a replay or a stale advert, so ignore it.
  Accept the advert only after the tag checks out, so a forged high counter cannot block the device.
- When an accepted advert names history events whose counters are also above the last accepted
  one, act on them first, oldest first. Then record the advert's own counter.
- Act on events in order, one at a time.
- `age` is used only to measure detection latency.

A burst lasts `BURST_MS` (firmware build option) after the latest event. Each new event during a
burst gets the next counter.

## Pairing

Hold **keys 1 and 2 for 3 s** (one-button build: hold the button for **5 s**). The device then:

1. generates a **new** device id and key, but keeps them only in RAM,
2. advertises *connectable* for up to 60 s, with the name `tune-button` and service UUID
   `7b1e0001-5f3a-4c1e-9b7a-2e6c0d1a7b00`,
3. exposes one characteristic, `7b1e0002-5f3a-4c1e-9b7a-2e6c0d1a7b00`, that can be read only over an
   **encrypted** link (LE Secure Connections, Just Works, bonded). Reading it triggers pairing on the
   phone. It returns 24 bytes: `device id (4) | key (16) | counter (4, LE)`.
4. exposes a second characteristic, `7b1e0003-5f3a-4c1e-9b7a-2e6c0d1a7b00`, for the key settings.
   It is **not** encrypted, since changing settings shouldn't need a new bond; the tag below proves
   the writer holds the key instead.
   - **Read:** 9 bytes, `nonce (8) | current settings (1)`. The nonce is random and changes after
     every write.
   - **Write:** 9 bytes, `settings (1) | tag (8)`, with tag the first 8 bytes of
     `HMAC-SHA256(key, "TBcfg" | nonce | settings)`. `key` is the paired key, or the newly offered
     one once it has been read in this session. A write with a wrong tag changes nothing.
   - The phone reads it back to confirm the settings byte took.
5. leaves pairing mode 1.5 s after a successful settings write, 5 s after the key is read (for an
   app that sends no settings), or after the 60 s timeout, and goes back to sleep. Only a key read
   stores the new id and key, and from then on the previous phone is no longer accepted. Otherwise
   the old ones stay, so an accidental hold, or a session that only changes settings, unpairs nothing.

The phone pairs by reading the key, then writing the settings. It changes settings later by
writing the settings characteristic alone.

Just Works has no MITM protection, so anyone within range during the 60 s window could also read
the key. (They could not change the settings without it.) This is a deliberate trade-off for a device with no display or keypad. If pairing fails
because someone else connected first, pair again.

## Test vectors

`vectors.json` is generated by `gen_vectors.py` (Python standard library) and is used by the
firmware's native tests and the Android unit tests: version 2 press adverts, version 1 ones, and
settings tags. It also includes the RFC 4231 HMAC-SHA256
cases, because the firmware uses its own SHA-256 implementation.
