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
constexpr uint8_t VERSION = 2;
constexpr size_t KEY_LEN = 16;
constexpr size_t ID_LEN = 4;
constexpr size_t TAG_LEN = 8;
constexpr size_t HISTORY = 2;                         // earlier presses carried in each advert
constexpr size_t AUTH_LEN = 13 + HISTORY;             // magic..history: what the tag covers
constexpr size_t PAYLOAD_LEN = AUTH_LEN + TAG_LEN + 1; // + age

constexpr size_t NONCE_LEN = 8;
constexpr uint8_t BATTERY_UNKNOWN = 0xFF;

void sha256(const uint8_t *data, size_t len, uint8_t out[32]);
void hmac_sha256(const uint8_t *key, size_t key_len, const uint8_t *data, size_t len, uint8_t out[32]);

// Writes PAYLOAD_LEN bytes (no company id) into out. history[i] is the button code of press
// counter - 1 - i, or 0 if that press was not made in this wake.
void encode_press(const uint8_t device_id[ID_LEN], const uint8_t key[KEY_LEN], uint32_t counter,
                  uint8_t button, uint8_t battery, const uint8_t history[HISTORY], uint8_t age,
                  uint8_t out[PAYLOAD_LEN]);

// Rewrites only the unauthenticated age byte of an encoded payload.
inline void set_age(uint8_t payload[PAYLOAD_LEN], uint8_t age) { payload[PAYLOAD_LEN - 1] = age; }

// The tag a phone sends with new key settings: first TAG_LEN bytes of
// HMAC-SHA256(key, "TBcfg" | nonce | config).
void settings_tag(const uint8_t key[KEY_LEN], const uint8_t nonce[NONCE_LEN], uint8_t config,
                  uint8_t out[TAG_LEN]);

// Single-cell LiPo, resting voltage in millivolts → rough percent (0–100).
uint8_t lipo_percent(uint32_t millivolts);

}  // namespace tb
