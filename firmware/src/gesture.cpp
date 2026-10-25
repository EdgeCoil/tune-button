// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
#include "gesture.h"

namespace tb {

Gestures::Gestures(uint8_t config, uint32_t hold_ms, uint32_t double_ms, bool hold_on_release)
    : config_(config), hold_ms_(hold_ms), double_ms_(double_ms), hold_on_release_(hold_on_release) {}

int Gestures::update(uint8_t down, uint32_t now, Event out[]) {
  int n = 0;
  auto emit = [&](int i, uint8_t g) { out[n++] = {(uint8_t)(i + 1), g}; };
  uint8_t pressed = down & ~prev_;

  // A key still waiting for a second press is settled first, so its press goes out before
  // anything another key does now.
  for (int i = 0; i < MAX_KEYS; i++) {
    if (st_[i] != WAIT) continue;
    bool again = pressed >> i & 1;
    if (!again && (pressed || now - t_[i] >= double_ms_)) { emit(i, PRESS); st_[i] = IDLE; }
  }

  for (int i = 0; i < MAX_KEYS; i++) {
    int key = i + 1;
    bool d = down >> i & 1, was = prev_ >> i & 1;
    if (d && !was) {
      if (st_[i] == WAIT) { emit(i, DOUBLE); st_[i] = SPENT; }
      else if (!has_hold(config_, key) && !has_double(config_, key)) { emit(i, PRESS); st_[i] = SPENT; }
      else { st_[i] = DOWN; t_[i] = now; }
    } else if (d) {
      if (st_[i] == DOWN && has_hold(config_, key) && !hold_on_release_ && now - t_[i] >= hold_ms_) {
        emit(i, HOLD);
        st_[i] = SPENT;
      }
    } else if (was) {
      if (st_[i] == DOWN) {
        if (has_hold(config_, key) && now - t_[i] >= hold_ms_) { emit(i, HOLD); st_[i] = IDLE; }
        else if (has_double(config_, key)) { st_[i] = WAIT; t_[i] = now; }
        else { emit(i, PRESS); st_[i] = IDLE; }
      } else if (st_[i] == SPENT) {
        st_[i] = IDLE;
      }
    }
  }
  prev_ = down;
  return n;
}

bool Gestures::settled() const {
  for (State s : st_)
    if (s == DOWN || s == WAIT) return false;
  return true;
}

void Gestures::cancel(uint8_t keys) {
  for (int i = 0; i < MAX_KEYS; i++)
    if (keys >> i & 1) st_[i] = IDLE;
  prev_ &= ~keys;
}

}  // namespace tb
