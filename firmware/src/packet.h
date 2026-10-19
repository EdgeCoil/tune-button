// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
//
// Press-advert encoding (protocol/spec.md). Plain C++ with no Arduino dependency, so the native
// tests can run it on the build host.
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace tb {

constexpr uint16_t COMPANY_ID = 0xFFFF;
constexpr uint8_t VERSION = 1;
constexpr size_t KEY_LEN = 16;
constexpr size_t ID_LEN = 4;
constexpr size_t TAG_LEN = 8;
constexpr size_t AUTH_LEN = 13;                       // magic..battery: what the tag covers
constexpr size_t PAYLOAD_LEN = AUTH_LEN + TAG_LEN + 1; // + age

enum Button : uint8_t { LIKE = 1, PLAYLIST = 2 };
constexpr uint8_t BATTERY_UNKNOWN = 0xFF;

void sha256(const uint8_t *data, size_t len, uint8_t out[32]);
void hmac_sha256(const uint8_t *key, size_t key_len, const uint8_t *data, size_t len, uint8_t out[32]);

// Writes PAYLOAD_LEN bytes (no company id) into out.
void encode_press(const uint8_t device_id[ID_LEN], const uint8_t key[KEY_LEN], uint32_t counter,
                  uint8_t button, uint8_t battery, uint8_t age, uint8_t out[PAYLOAD_LEN]);

// Rewrites only the unauthenticated age byte of an encoded payload.
inline void set_age(uint8_t payload[PAYLOAD_LEN], uint8_t age) { payload[PAYLOAD_LEN - 1] = age; }

// Single-cell LiPo, resting voltage in millivolts → rough percent (0–100).
uint8_t lipo_percent(uint32_t millivolts);

}  // namespace tb
