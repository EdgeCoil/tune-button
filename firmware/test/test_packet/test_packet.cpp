// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
#include <string.h>
#include <unity.h>

#include "../../src/packet.h"
#include "vectors.h"

void setUp() {}
void tearDown() {}

static void test_hmac_rfc4231() {
  for (const auto &v : HMAC_VECTORS) {
    uint8_t mac[32];
    tb::hmac_sha256(v.key, v.key_len, v.data, v.data_len, mac);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(v.mac, mac, 32);
  }
}

static void test_sha256_multiblock() {
  // "abc" repeated past one 64-byte block; expected = hashlib.sha256(b"abc" * 66 + b"ab").
  uint8_t data[200];
  for (size_t i = 0; i < sizeof data; i++) data[i] = "abc"[i % 3];
  static const uint8_t expect[32] = {0xaa, 0xbe, 0x61, 0x4a, 0x10, 0x97, 0x00, 0x5a, 0x5a, 0xce, 0xc2,
                                     0x9c, 0x91, 0x39, 0x4f, 0x2e, 0xbd, 0xd6, 0xea, 0x34, 0xf6, 0xcc,
                                     0x8c, 0xbe, 0xac, 0x51, 0x2b, 0x5a, 0x58, 0xe4, 0x71, 0xa6};
  uint8_t out[32];
  tb::sha256(data, sizeof data, out);
  TEST_ASSERT_EQUAL_HEX8_ARRAY(expect, out, 32);
}

static void test_press_vectors() {
  for (const auto &v : PRESS_VECTORS) {
    uint8_t out[tb::PAYLOAD_LEN];
    tb::encode_press(v.device_id, v.key, v.counter, v.button, v.battery, v.history, v.age, out);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(v.payload, out, tb::PAYLOAD_LEN);
  }
}

static void test_settings_vectors() {
  for (const auto &v : SETTINGS_VECTORS) {
    uint8_t tag[tb::TAG_LEN];
    tb::settings_tag(v.key, v.nonce, v.config, tag);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(v.tag, tag, tb::TAG_LEN);
  }
}

static void test_fits_legacy_advert() {
  // Flags AD (3) + manufacturer data AD header (2) + company id (2) + payload, in 31 bytes.
  TEST_ASSERT_TRUE(3 + 2 + 2 + tb::PAYLOAD_LEN <= 31);
}

static void test_age_outside_tag() {
  const auto &v = PRESS_VECTORS[0];
  uint8_t a[tb::PAYLOAD_LEN], b[tb::PAYLOAD_LEN];
  tb::encode_press(v.device_id, v.key, v.counter, v.button, v.battery, v.history, 0, a);
  tb::encode_press(v.device_id, v.key, v.counter, v.button, v.battery, v.history, 200, b);
  TEST_ASSERT_EQUAL_HEX8_ARRAY(a, b, tb::PAYLOAD_LEN - 1);
  tb::set_age(a, 200);
  TEST_ASSERT_EQUAL_HEX8_ARRAY(b, a, tb::PAYLOAD_LEN);
}

static void test_lipo_percent() {
  TEST_ASSERT_EQUAL_UINT8(0, tb::lipo_percent(3000));
  TEST_ASSERT_EQUAL_UINT8(50, tb::lipo_percent(3850));
  TEST_ASSERT_EQUAL_UINT8(100, tb::lipo_percent(4250));
  uint8_t last = 0;
  for (uint32_t mv = 3200; mv <= 4300; mv += 10) {
    uint8_t p = tb::lipo_percent(mv);
    TEST_ASSERT_TRUE(p >= last);
    last = p;
  }
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_hmac_rfc4231);
  RUN_TEST(test_sha256_multiblock);
  RUN_TEST(test_press_vectors);
  RUN_TEST(test_settings_vectors);
  RUN_TEST(test_fits_legacy_advert);
  RUN_TEST(test_age_outside_tag);
  RUN_TEST(test_lipo_percent);
  return UNITY_END();
}
