// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
//
// tune-button firmware for the Seeed XIAO ESP32-C3.
//
// The device sleeps in deep sleep. A button press wakes it, and it broadcasts a signed press advert
// (protocol/spec.md) for TB_BURST_MS, then sleeps again. Holding both buttons for 3 s enters pairing.
// With TB_BUTTONS=1 only the like button is fitted: a press likes on release, and a 5 s hold pairs.
#include <Arduino.h>
#include <NimBLEDevice.h>
#include <Preferences.h>
#include <driver/gpio.h>
#include <esp_random.h>
#include <esp_sleep.h>

#include "packet.h"

#ifndef TB_BURST_MS
#define TB_BURST_MS 10000
#endif
#ifndef TB_LED_PIN
#define TB_LED_PIN -1
#endif
#ifndef TB_BUTTONS
#define TB_BUTTONS 2
#endif

namespace {

// Only GPIO0–5 can wake the C3 from deep sleep.
constexpr gpio_num_t PIN_LIKE = GPIO_NUM_3;      // XIAO D1
constexpr gpio_num_t PIN_PLAYLIST = GPIO_NUM_4;  // XIAO D2
constexpr int PIN_VBAT = 2;                      // XIAO A0, via 2 × 220 kΩ divider from BAT+
constexpr bool HAS_PLAYLIST = TB_BUTTONS >= 2;
// One button can't use a two-button chord, so it needs a hold long enough not to happen by accident.
constexpr uint32_t PAIR_HOLD_MS = HAS_PLAYLIST ? 3000 : 5000;
constexpr uint32_t PAIR_WINDOW_MS = 60000;
constexpr uint32_t AGE_UPDATE_MS = 200;

const char *SERVICE_UUID = "7b1e0001-5f3a-4c1e-9b7a-2e6c0d1a7b00";
const char *KEY_CHR_UUID = "7b1e0002-5f3a-4c1e-9b7a-2e6c0d1a7b00";

struct Identity {
  uint8_t id[tb::ID_LEN];
  uint8_t key[tb::KEY_LEN];
  uint32_t counter;
};

Preferences prefs;
Identity ident;

bool down(gpio_num_t pin) { return digitalRead(pin) == LOW; }

void led(bool on) {
  if (TB_LED_PIN >= 0) digitalWrite(TB_LED_PIN, on ? HIGH : LOW);
}

void save_identity() {
  prefs.putBytes("id", ident.id, sizeof ident.id);
  prefs.putBytes("key", ident.key, sizeof ident.key);
}

void new_identity() {
  esp_fill_random(ident.id, sizeof ident.id);
  esp_fill_random(ident.key, sizeof ident.key);
  save_identity();
}

void load_identity() {
  prefs.begin("tb", false);
  ident.counter = prefs.getUInt("ctr", 0);
  if (prefs.getBytes("id", ident.id, sizeof ident.id) != sizeof ident.id ||
      prefs.getBytes("key", ident.key, sizeof ident.key) != sizeof ident.key)
    new_identity();  // unpaired: adverts are sent but no phone accepts them
}

uint32_t next_counter() {
  // Persist before use, so a counter is never broadcast twice even if power drops mid-burst.
  prefs.putUInt("ctr", ++ident.counter);
  return ident.counter;
}

uint8_t battery_percent() {
  uint32_t sum = 0;
  for (int i = 0; i < 8; i++) sum += analogReadMilliVolts(PIN_VBAT);
  uint32_t mv = sum / 8 * 2;
  if (mv < 2500) return tb::BATTERY_UNKNOWN;  // divider not fitted
  return tb::lipo_percent(mv);
}

std::string manufacturer_data(const uint8_t payload[tb::PAYLOAD_LEN]) {
  std::string s;
  s.push_back((char)(tb::COMPANY_ID & 0xFF));
  s.push_back((char)(tb::COMPANY_ID >> 8));
  s.append((const char *)payload, tb::PAYLOAD_LEN);
  return s;
}

void set_press_advert(NimBLEAdvertising *adv, const uint8_t payload[tb::PAYLOAD_LEN]) {
  NimBLEAdvertisementData d;
  d.setFlags(BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP);
  d.setManufacturerData(manufacturer_data(payload));
  adv->setAdvertisementData(d);
}

// Which button a press means. 0 if neither is down.
uint8_t pressed_button() {
  if (down(PIN_LIKE)) return tb::LIKE;
  if (HAS_PLAYLIST && down(PIN_PLAYLIST)) return tb::PLAYLIST;
  return 0;
}

void burst(uint8_t button) {
  uint8_t battery = battery_percent();
  uint8_t payload[tb::PAYLOAD_LEN];
  tb::encode_press(ident.id, ident.key, next_counter(), button, battery, 0, payload);

  NimBLEDevice::init("");
  NimBLEDevice::setPower(3);  // dBm
  NimBLEAdvertising *adv = NimBLEDevice::getAdvertising();
  adv->setConnectableMode(BLE_GAP_CONN_MODE_NON);
  adv->setMinInterval(48);  // 30 ms, in 0.625 ms units
  adv->setMaxInterval(64);  // 40 ms
  set_press_advert(adv, payload);
  adv->start();

  led(true);
  uint32_t pressed_at = millis();
  uint32_t last_update = pressed_at;
  bool was_down = true;
  while (millis() - pressed_at < TB_BURST_MS) {
    delay(10);
    uint8_t b = pressed_button();
    if (b && !was_down) {
      // A new press during the burst: new counter, restart the clock.
      tb::encode_press(ident.id, ident.key, next_counter(), b, battery, 0, payload);
      pressed_at = millis();
      set_press_advert(adv, payload);
      led(true);
    }
    was_down = b != 0;
    if (millis() - pressed_at > 150) led(false);
    if (millis() - last_update >= AGE_UPDATE_MS) {
      uint32_t age = (millis() - pressed_at) / 100;
      tb::set_age(payload, age > 0xFF ? 0xFF : (uint8_t)age);
      set_press_advert(adv, payload);
      last_update = millis();
    }
  }
  adv->stop();
  NimBLEDevice::deinit(true);
}

class KeyCallbacks : public NimBLECharacteristicCallbacks {
 public:
  bool *read_done;
  explicit KeyCallbacks(bool *flag) : read_done(flag) {}
  void onRead(NimBLECharacteristic *, NimBLEConnInfo &info) override {
    if (info.isEncrypted()) *read_done = true;
  }
};

void pairing() {
  // Offer a fresh key, but keep the old one until a phone has read it: an aborted or accidental
  // pairing must not unpair the phone that already works.
  Identity old = ident;
  esp_fill_random(ident.id, sizeof ident.id);
  esp_fill_random(ident.key, sizeof ident.key);
  uint8_t value[tb::ID_LEN + tb::KEY_LEN + 4];
  memcpy(value, ident.id, tb::ID_LEN);
  memcpy(value + tb::ID_LEN, ident.key, tb::KEY_LEN);
  for (int i = 0; i < 4; i++) value[tb::ID_LEN + tb::KEY_LEN + i] = (uint8_t)(ident.counter >> (8 * i));

  bool read_done = false;
  NimBLEDevice::init("tune-button");
  NimBLEDevice::setSecurityAuth(true, false, true);  // bond, no MITM (no I/O), LE Secure Connections
  NimBLEDevice::setSecurityIOCap(BLE_HS_IO_NO_INPUT_OUTPUT);
  NimBLEServer *server = NimBLEDevice::createServer();
  NimBLEService *svc = server->createService(SERVICE_UUID);
  NimBLECharacteristic *chr =
      svc->createCharacteristic(KEY_CHR_UUID, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::READ_ENC);
  chr->setValue(value, sizeof value);
  static KeyCallbacks callbacks(nullptr);
  callbacks.read_done = &read_done;
  chr->setCallbacks(&callbacks);
  svc->start();

  NimBLEAdvertising *adv = NimBLEDevice::getAdvertising();
  adv->setName("tune-button");
  adv->addServiceUUID(SERVICE_UUID);
  adv->enableScanResponse(true);
  adv->start();

  uint32_t start = millis();
  uint32_t done_at = 0;
  while (millis() - start < PAIR_WINDOW_MS) {
    led((millis() / 125) % 2);
    delay(20);
    if (read_done && !done_at) done_at = millis();
    // Give the response time to leave, then stop.
    if (done_at && millis() - done_at > 1500) break;
  }
  memset(value, 0, sizeof value);
  led(false);
  NimBLEDevice::deinit(true);
  if (done_at) {
    save_identity();
    for (int i = 0; i < 3; i++) { led(true); delay(80); led(false); delay(80); }
  } else {
    ident = old;
  }
  memset(&old, 0, sizeof old);
}

[[noreturn]] void sleep_now() {
  // Level-triggered wake: a button still held would wake us at once, so wait for release.
  uint32_t t = millis();
  while (pressed_button() && millis() - t < 10000) delay(10);
  // An unfitted D2 is left out of the wake mask, so a floating pin can never wake the device.
  uint64_t all = (1ULL << PIN_LIKE) | (HAS_PLAYLIST ? 1ULL << PIN_PLAYLIST : 0);
  uint64_t mask = 0;
  if (!down(PIN_LIKE)) mask |= 1ULL << PIN_LIKE;
  if (HAS_PLAYLIST && !down(PIN_PLAYLIST)) mask |= 1ULL << PIN_PLAYLIST;
  if (mask != all)
    esp_sleep_enable_timer_wakeup(60ULL * 1000000);  // a stuck button: look again in a minute
  for (gpio_num_t p : {PIN_LIKE, PIN_PLAYLIST}) {
    gpio_pullup_en(p);
    gpio_pulldown_dis(p);
  }
  if (mask) esp_deep_sleep_enable_gpio_wakeup(mask, ESP_GPIO_WAKEUP_GPIO_LOW);
  prefs.end();
  esp_deep_sleep_start();
}

}  // namespace

void setup() {
  pinMode(PIN_LIKE, INPUT_PULLUP);
  pinMode(PIN_PLAYLIST, INPUT_PULLUP);
  if (TB_LED_PIN >= 0) pinMode(TB_LED_PIN, OUTPUT);
  led(false);
  load_identity();

  bool woke_by_button = esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_GPIO;
  uint64_t wake_pins = woke_by_button ? esp_sleep_get_gpio_wakeup_status() : 0;
  delay(30);  // debounce

  if (HAS_PLAYLIST && down(PIN_LIKE) && down(PIN_PLAYLIST)) {
    uint32_t t = millis();
    while (down(PIN_LIKE) && down(PIN_PLAYLIST) && millis() - t < PAIR_HOLD_MS) delay(10);
    if (millis() - t >= PAIR_HOLD_MS) {
      pairing();
      sleep_now();
    }
  }
  if (!HAS_PLAYLIST && woke_by_button && down(PIN_LIKE)) {
    // A press and the start of a pairing hold look the same, so wait for release (or the hold).
    uint32_t t = millis();
    while (down(PIN_LIKE) && millis() - t < PAIR_HOLD_MS) delay(10);
    if (millis() - t >= PAIR_HOLD_MS) {
      pairing();
      sleep_now();
    }
  }

  uint8_t button = 0;
  if (wake_pins & (1ULL << PIN_LIKE)) button = tb::LIKE;
  else if (HAS_PLAYLIST && (wake_pins & (1ULL << PIN_PLAYLIST))) button = tb::PLAYLIST;
  else if (woke_by_button) button = pressed_button();
  // A cold boot (battery connected, USB plugged, reset) is not a press.
  if (button) burst(button);
  sleep_now();
}

void loop() {}
