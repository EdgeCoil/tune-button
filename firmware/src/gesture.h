// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
//
// Turns debounced key states into press / hold / double-press events (protocol/spec.md, byte 11).
// Plain C++ with no Arduino dependency, so the native tests can run it on the build host.
//
// A key waits only for what it needs. With no hold or double action assigned it sends a press the
// moment it goes down, as the two-button firmware always did. With a hold action it sends the press
// on release instead, and the hold when held for hold_ms. With a double action it waits double_ms
// after release for a second press.
#pragma once
#include <stdint.h>

namespace tb {

constexpr int MAX_KEYS = 4;
enum Gesture : uint8_t { PRESS = 0, HOLD = 1, DOUBLE = 2 };

// Byte 11 of a press advert: key 1-4 in the low nibble, gesture in the high one. Key 1 and key 2
// pressed are 0x01 and 0x02, the like and playlist codes of the two-button protocol.
inline uint8_t button_code(uint8_t key, uint8_t gesture) { return (uint8_t)(key | gesture << 4); }

// The key settings byte the phone writes (protocol/spec.md): bit k-1 is set when key k has a hold
// action, bit k+3 when it has a double-press action.
inline bool has_hold(uint8_t config, int key) { return config >> (key - 1) & 1; }
inline bool has_double(uint8_t config, int key) { return config >> (key + 3) & 1; }

struct Event { uint8_t key, gesture; };

class Gestures {
 public:
  // hold_on_release: send a hold when the key is let go, not at hold_ms. The one-button build uses
  // it, since there a hold carries on into the 5 s pairing hold.
  Gestures(uint8_t config, uint32_t hold_ms, uint32_t double_ms, bool hold_on_release = false);

  // Feed the debounced key states (bit k-1 = key k down) at time now. Writes up to MAX_KEYS * 2
  // events to out, in the order they happened, and returns how many.
  int update(uint8_t down, uint32_t now, Event out[]);

  // True when no key is waiting to find out which gesture it is.
  bool settled() const;

  // Forget whatever these keys were doing, as for the pairing chord. The caller then reports them
  // as up until they are really let go, so nothing is sent for them.
  void cancel(uint8_t keys);

 private:
  // SPENT: held, and its gesture already sent. WAIT: let go, waiting for a second press.
  enum State : uint8_t { IDLE, DOWN, SPENT, WAIT };
  uint8_t config_;
  uint32_t hold_ms_, double_ms_;
  bool hold_on_release_;
  uint8_t prev_ = 0;
  State st_[MAX_KEYS] = {};
  uint32_t t_[MAX_KEYS] = {};
};

}  // namespace tb
