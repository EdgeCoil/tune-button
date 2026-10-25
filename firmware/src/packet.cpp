// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
#include "packet.h"

#include <string.h>

namespace tb {
namespace {

const uint32_t K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};

inline uint32_t rotr(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }

struct Sha256 {
  uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                   0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  uint8_t buf[64];
  size_t buf_len = 0;
  uint64_t total = 0;

  void block(const uint8_t *p) {
    uint32_t w[64];
    for (int i = 0; i < 16; i++)
      w[i] = (uint32_t)p[4 * i] << 24 | (uint32_t)p[4 * i + 1] << 16 | (uint32_t)p[4 * i + 2] << 8 | p[4 * i + 3];
    for (int i = 16; i < 64; i++) {
      uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
      uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
    for (int i = 0; i < 64; i++) {
      uint32_t t1 = hh + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i];
      uint32_t t2 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
      hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
  }

  void update(const uint8_t *p, size_t n) {
    total += n;
    while (n) {
      size_t take = 64 - buf_len < n ? 64 - buf_len : n;
      memcpy(buf + buf_len, p, take);
      buf_len += take; p += take; n -= take;
      if (buf_len == 64) { block(buf); buf_len = 0; }
    }
  }

  void finish(uint8_t out[32]) {
    uint64_t bits = total * 8;
    uint8_t pad = 0x80;
    update(&pad, 1);
    uint8_t zero = 0;
    while (buf_len != 56) update(&zero, 1);
    uint8_t len[8];
    for (int i = 0; i < 8; i++) len[i] = (uint8_t)(bits >> (56 - 8 * i));
    update(len, 8);
    for (int i = 0; i < 8; i++) {
      out[4 * i] = h[i] >> 24; out[4 * i + 1] = h[i] >> 16; out[4 * i + 2] = h[i] >> 8; out[4 * i + 3] = h[i];
    }
  }
};

}  // namespace

void sha256(const uint8_t *data, size_t len, uint8_t out[32]) {
  Sha256 s;
  s.update(data, len);
  s.finish(out);
}

void hmac_sha256(const uint8_t *key, size_t key_len, const uint8_t *data, size_t len, uint8_t out[32]) {
  uint8_t k[64] = {0};
  if (key_len > 64) sha256(key, key_len, k);
  else memcpy(k, key, key_len);
  uint8_t pad[64];
  Sha256 inner;
  for (int i = 0; i < 64; i++) pad[i] = k[i] ^ 0x36;
  inner.update(pad, 64);
  inner.update(data, len);
  uint8_t ih[32];
  inner.finish(ih);
  Sha256 outer;
  for (int i = 0; i < 64; i++) pad[i] = k[i] ^ 0x5c;
  outer.update(pad, 64);
  outer.update(ih, 32);
  outer.finish(out);
}

void encode_press(const uint8_t device_id[ID_LEN], const uint8_t key[KEY_LEN], uint32_t counter,
                  uint8_t button, uint8_t battery, const uint8_t history[HISTORY], uint8_t age,
                  uint8_t out[PAYLOAD_LEN]) {
  out[0] = 'T';
  out[1] = 'B';
  out[2] = VERSION;
  memcpy(out + 3, device_id, ID_LEN);
  for (int i = 0; i < 4; i++) out[7 + i] = (uint8_t)(counter >> (8 * i));
  out[11] = button;
  out[12] = battery;
  memcpy(out + 13, history, HISTORY);
  uint8_t mac[32];
  hmac_sha256(key, KEY_LEN, out, AUTH_LEN, mac);
  memcpy(out + AUTH_LEN, mac, TAG_LEN);
  out[PAYLOAD_LEN - 1] = age;
}

void settings_tag(const uint8_t key[KEY_LEN], const uint8_t nonce[NONCE_LEN], uint8_t config,
                  uint8_t out[TAG_LEN]) {
  uint8_t msg[5 + NONCE_LEN + 1] = {'T', 'B', 'c', 'f', 'g'};
  memcpy(msg + 5, nonce, NONCE_LEN);
  msg[5 + NONCE_LEN] = config;
  uint8_t mac[32];
  hmac_sha256(key, KEY_LEN, msg, sizeof msg, mac);
  memcpy(out, mac, TAG_LEN);
}

uint8_t lipo_percent(uint32_t mv) {
  // Approximate resting curve for a single LiPo cell under light load.
  static const uint16_t MV[] = {3300, 3500, 3600, 3700, 3750, 3800, 3850, 3900, 4000, 4100, 4200};
  static const uint8_t PCT[] = {0, 5, 10, 20, 30, 40, 50, 60, 75, 90, 100};
  if (mv <= MV[0]) return 0;
  for (size_t i = 1; i < sizeof MV / sizeof MV[0]; i++)
    if (mv <= MV[i]) return PCT[i - 1] + (uint8_t)((mv - MV[i - 1]) * (PCT[i] - PCT[i - 1]) / (MV[i] - MV[i - 1]));
  return 100;
}

}  // namespace tb
