// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
#include <string>
#include <unity.h>

#include "../../src/gesture.h"

using tb::Gestures;

void setUp() {}
void tearDown() {}

constexpr uint32_t HOLD = 600, DBL = 300;
constexpr uint8_t HOLD_K1 = 0x01, DOUBLE_K1 = 0x10, HOLD_K3 = 0x04, DOUBLE_K2 = 0x20;

// Plays a script of (time, keys down) steps, sampling every 5 ms like the firmware, and returns the
// events as "k1p k2d k3h ..." (p press, h hold, d double) with the time each was sent.
struct Step { uint32_t t; uint8_t down; };
static std::string play(Gestures &g, std::initializer_list<Step> steps, uint32_t until) {
  std::string out;
  tb::Event ev[tb::MAX_KEYS * 2];
  auto it = steps.begin();
  uint8_t down = 0;
  for (uint32_t now = 0; now <= until; now += 5) {
    while (it != steps.end() && it->t <= now) down = (it++)->down;
    int n = g.update(down, now, ev);
    for (int i = 0; i < n; i++) {
      if (!out.empty()) out += ' ';
      out += 'k' + std::to_string(ev[i].key) + "phd"[ev[i].gesture] + '@' + std::to_string(now);
    }
  }
  return out;
}

static void test_codes() {
  TEST_ASSERT_EQUAL_HEX8(0x01, tb::button_code(1, tb::PRESS));  // the old "like"
  TEST_ASSERT_EQUAL_HEX8(0x02, tb::button_code(2, tb::PRESS));  // the old "add to playlist"
  TEST_ASSERT_EQUAL_HEX8(0x13, tb::button_code(3, tb::HOLD));
  TEST_ASSERT_EQUAL_HEX8(0x24, tb::button_code(4, tb::DOUBLE));
}

static void test_plain_key_sends_on_press() {
  Gestures g(0, HOLD, DBL);
  // Nothing assigned to hold or double: sent the moment it goes down, however long it is held.
  TEST_ASSERT_EQUAL_STRING("k1p@100", play(g, {{100, 1}, {1500, 0}}, 2000).c_str());
}

static void test_hold() {
  Gestures g(HOLD_K1, HOLD, DBL);
  TEST_ASSERT_EQUAL_STRING("k1p@200", play(g, {{100, 1}, {200, 0}}, 1000).c_str());
  Gestures h(HOLD_K1, HOLD, DBL);
  TEST_ASSERT_EQUAL_STRING("k1h@700", play(h, {{100, 1}, {2000, 0}}, 2500).c_str());
}

static void test_hold_on_release() {
  Gestures g(HOLD_K1, HOLD, DBL, true);
  TEST_ASSERT_EQUAL_STRING("k1h@2000", play(g, {{100, 1}, {2000, 0}}, 2500).c_str());
}

static void test_double() {
  Gestures g(DOUBLE_K1, HOLD, DBL);
  // One press: sent DBL after release, once no second press has come.
  TEST_ASSERT_EQUAL_STRING("k1p@450", play(g, {{100, 1}, {150, 0}}, 1000).c_str());
  Gestures d(DOUBLE_K1, HOLD, DBL);
  // A second press within DBL: one double, sent as it goes down; nothing for its release.
  TEST_ASSERT_EQUAL_STRING("k1d@300", play(d, {{100, 1}, {150, 0}, {300, 1}, {400, 0}}, 1500).c_str());
  Gestures t(DOUBLE_K1, HOLD, DBL);
  // Too slow for a double: two presses.
  TEST_ASSERT_EQUAL_STRING("k1p@450 k1p@1050",
                           play(t, {{100, 1}, {150, 0}, {500, 1}, {750, 0}}, 1500).c_str());
}

static void test_hold_and_double_on_one_key() {
  Gestures g(HOLD_K1 | DOUBLE_K1, HOLD, DBL);
  TEST_ASSERT_EQUAL_STRING("k1h@700", play(g, {{100, 1}, {1000, 0}}, 1500).c_str());
  Gestures d(HOLD_K1 | DOUBLE_K1, HOLD, DBL);
  TEST_ASSERT_EQUAL_STRING("k1d@250", play(d, {{100, 1}, {150, 0}, {250, 1}, {1400, 0}}, 1500).c_str());
}

static void test_waiting_key_goes_first() {
  // Key 2 waits for a second press; key 3 pressed meanwhile. Key 2's press is sent first.
  Gestures g(DOUBLE_K2, HOLD, DBL);
  TEST_ASSERT_EQUAL_STRING("k2p@200 k3p@200",
                           play(g, {{100, 0b010}, {150, 0}, {200, 0b100}, {260, 0}}, 1000).c_str());
}

static void test_other_keys_unaffected() {
  Gestures g(HOLD_K3, HOLD, DBL);
  TEST_ASSERT_EQUAL_STRING("k4p@100 k3h@800",
                           play(g, {{100, 0b1000}, {150, 0}, {200, 0b0100}, {1000, 0}}, 1200).c_str());
}

static void test_settled() {
  Gestures g(DOUBLE_K1, HOLD, DBL);
  tb::Event ev[8];
  TEST_ASSERT_TRUE(g.settled());
  g.update(1, 0, ev);
  TEST_ASSERT_FALSE(g.settled());  // down: could still be a hold or double
  g.update(0, 50, ev);
  TEST_ASSERT_FALSE(g.settled());  // waiting for a second press
  TEST_ASSERT_EQUAL(1, g.update(0, 400, ev));
  TEST_ASSERT_TRUE(g.settled());
}

static void test_cancel() {
  Gestures g(HOLD_K1, HOLD, DBL);
  tb::Event ev[8];
  g.update(0b11, 0, ev);  // K2 (nothing assigned) sends at once; K1 waits
  g.cancel(0b11);
  TEST_ASSERT_TRUE(g.settled());
  // The caller reports cancelled keys as up until they are let go: nothing more is sent.
  TEST_ASSERT_EQUAL(0, g.update(0, 1000, ev));
  TEST_ASSERT_EQUAL(0, g.update(0, 5000, ev));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_codes);
  RUN_TEST(test_plain_key_sends_on_press);
  RUN_TEST(test_hold);
  RUN_TEST(test_hold_on_release);
  RUN_TEST(test_double);
  RUN_TEST(test_hold_and_double_on_one_key);
  RUN_TEST(test_waiting_key_goes_first);
  RUN_TEST(test_other_keys_unaffected);
  RUN_TEST(test_settled);
  RUN_TEST(test_cancel);
  return UNITY_END();
}
