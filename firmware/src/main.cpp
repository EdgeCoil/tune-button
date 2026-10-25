// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
//
// tune-button firmware for the ESP32-C3: a hand-wired XIAO, or the four-key boards in hardware/pcb.
//
// The device sleeps in deep sleep. A key press wakes it, and it broadcasts a signed press advert
// (protocol/spec.md) for TB_BURST_MS after the last press, then sleeps again. Each key can send a
// press, a hold and a double press; which keys wait for a hold or a second press is set by the
// phone (gesture.h). Holding keys 1 and 2 for 3 s enters pairing, which is also how the phone
// updates those settings. With TB_BUTTONS=1 only key 1 is fitted: a press is sent on release, and
// a 5 s hold pairs.
#include <Arduino.h>
#include <NimBLEDevice.h>
#include <Preferences.h>
#include <driver/gpio.h>
#include <esp_random.h>
#include <esp_sleep.h>
#include <soc/gpio_reg.h>
#include <soc/io_mux_reg.h>

#include "gesture.h"
#include "packet.h"

#ifndef TB_BURST_MS
#define TB_BURST_MS 10000
#endif
#ifndef TB_BUTTONS
#define TB_BUTTONS 2
#endif

namespace {

// Pin maps: hardware/pcb/README.md, "Pin map". Only GPIO0-5 can wake the C3 from deep sleep.
#if defined(TB_BOARD_C3)  // the c3 and c3-jst boards
constexpr int KEYS = 4;
constexpr gpio_num_t KEY_PIN[KEYS] = {GPIO_NUM_3, GPIO_NUM_4, GPIO_NUM_5, GPIO_NUM_0};
constexpr int PIN_VBAT = 1;
constexpr int DEFAULT_LED = 10;
constexpr bool K4_ON_K3 = false;
#elif defined(TB_BOARD_XIAO)  // the XIAO four-key board
constexpr int KEYS = 4;
constexpr gpio_num_t KEY_PIN[KEYS] = {GPIO_NUM_3, GPIO_NUM_4, GPIO_NUM_5, GPIO_NUM_6};
constexpr int PIN_VBAT = 2;
constexpr int DEFAULT_LED = 7;
// GPIO6 can't wake the chip, so K4 also pulls K3's line low through a diode: GPIO5 low with GPIO6
// high is K3, GPIO6 low is K4.
constexpr bool K4_ON_K3 = true;
#else  // a hand-wired XIAO: like on D1, playlist on D2 (hardware/wiring.md)
constexpr int KEYS = TB_BUTTONS;
constexpr gpio_num_t KEY_PIN[2] = {GPIO_NUM_3, GPIO_NUM_4};
constexpr int PIN_VBAT = 2;  // XIAO A0, via 2 x 220 kOhm divider from BAT+
constexpr int DEFAULT_LED = -1;
constexpr bool K4_ON_K3 = false;
#endif
static_assert(KEYS >= 1 && KEYS <= tb::MAX_KEYS, "TB_BUTTONS is 1 or 2");

#ifdef TB_LED_PIN
constexpr int LED_PIN = TB_LED_PIN;  // active high, through 1 kOhm; -1 for none
#else
constexpr int LED_PIN = DEFAULT_LED;
#endif

constexpr bool SINGLE = KEYS == 1;
// The pairing chord: keys 1 and 2. One key can't make a chord, so it needs a hold long enough not
// to happen by accident.
constexpr uint8_t CHORD = SINGLE ? 0b01 : 0b11;
constexpr uint32_t PAIR_HOLD_MS = SINGLE ? 5000 : 3000;
constexpr uint32_t PAIR_WINDOW_MS = 60000;
constexpr uint32_t HOLD_MS = 600;
constexpr uint32_t DOUBLE_MS = 300;
constexpr uint32_t AGE_UPDATE_MS = 200;
constexpr uint32_t DEBOUNCE_MS = 30;

const char *SERVICE_UUID = "7b1e0001-5f3a-4c1e-9b7a-2e6c0d1a7b00";
const char *KEY_CHR_UUID = "7b1e0002-5f3a-4c1e-9b7a-2e6c0d1a7b00";
const char *SETTINGS_CHR_UUID = "7b1e0003-5f3a-4c1e-9b7a-2e6c0d1a7b00";

struct Identity {
  uint8_t id[tb::ID_LEN];
  uint8_t key[tb::KEY_LEN];
  uint32_t counter;
};

Preferences prefs;
Identity ident;
uint8_t settings;  // which keys wait for a hold or a double press (gesture.h)

// GPIO_IN as the wake stub read it, within about a millisecond of waking: by the time setup() runs,
// a quick tap on the XIAO board's K4 may be over, and without this it would read as K3. All ones
// when the stub hasn't run (cold boot, or a stub that never ran), which reads as "K4 not down".
RTC_DATA_ATTR uint32_t wake_gpio_in = ~0u;

bool pin_down(gpio_num_t pin) { return digitalRead(pin) == LOW; }

// Bit k-1 set while key k is down.
uint8_t read_keys() {
  uint8_t m = 0;
  for (int i = 0; i < KEYS; i++)
    if (pin_down(KEY_PIN[i])) m |= 1 << i;
  if (K4_ON_K3 && (m & 0b1000)) m &= ~0b0100;  // K4 also holds K3's line low
  return m;
}

void led(bool on) {
  if (LED_PIN >= 0) digitalWrite(LED_PIN, on ? HIGH : LOW);
}

void blink(int n) {
  for (int i = 0; i < n; i++) { led(true); delay(80); led(false); delay(80); }
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
  settings = prefs.getUChar("keys", 0);
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

// Broadcasts presses until TB_BURST_MS after the last one. The radio starts only with the first
// press, so a wake that sends nothing (a cold boot, a cancelled chord) costs no airtime.
class Burst {
 public:
  void send(uint8_t code) {
    if (!adv_) start();
    tb::encode_press(ident.id, ident.key, next_counter(), code, battery_, history_, 0, payload_);
    // Each advert also names the two presses before it, so presses closer together than the
    // phone's scan gaps are still all heard (protocol/spec.md).
    history_[1] = history_[0];
    history_[0] = code;
    set_press_advert(adv_, payload_);
    last_ = last_age_ = millis();
    led(true);
  }

  // Keeps the age byte current and the LED timed. False once the burst is over (or never began).
  bool tick() {
    if (!adv_) return false;
    uint32_t now = millis();
    if (now - last_ > 150) led(false);
    if (now - last_age_ >= AGE_UPDATE_MS) {
      uint32_t age = (now - last_) / 100;
      tb::set_age(payload_, age > 0xFF ? 0xFF : (uint8_t)age);
      set_press_advert(adv_, payload_);
      last_age_ = now;
    }
    return now - last_ < TB_BURST_MS;
  }

  void stop() {
    if (!adv_) return;
    adv_->stop();
    NimBLEDevice::deinit(true);
    adv_ = nullptr;
    led(false);
  }

 private:
  void start() {
    battery_ = battery_percent();  // before the radio starts, which disturbs the ADC
    NimBLEDevice::init("");
    NimBLEDevice::setPower(3);  // dBm
    adv_ = NimBLEDevice::getAdvertising();
    adv_->setConnectableMode(BLE_GAP_CONN_MODE_NON);
    adv_->setMinInterval(48);  // 30 ms, in 0.625 ms units
    adv_->setMaxInterval(64);  // 40 ms
    adv_->start();
  }

  NimBLEAdvertising *adv_ = nullptr;
  uint8_t payload_[tb::PAYLOAD_LEN] = {};
  uint8_t history_[tb::HISTORY] = {};
  uint8_t battery_ = tb::BATTERY_UNKNOWN;
  uint32_t last_ = 0, last_age_ = 0;
};

class PairCallbacks : public NimBLECharacteristicCallbacks {
 public:
  const Identity *offered = nullptr;
  bool key_read = false;
  bool settings_written = false;
  uint8_t nonce[tb::NONCE_LEN];

  void onRead(NimBLECharacteristic *chr, NimBLEConnInfo &info) override {
    if (chr->getUUID() == NimBLEUUID(KEY_CHR_UUID) && info.isEncrypted()) key_read = true;
  }

  // New key settings, tagged with the paired key, or with the offered one once it has been read.
  void onWrite(NimBLECharacteristic *chr, NimBLEConnInfo &) override {
    NimBLEAttValue v = chr->getValue();
    const uint8_t *d = v.data();
    if (v.size() != 1 + tb::TAG_LEN) return;
    const uint8_t *keys[2] = {ident.key, key_read ? offered->key : nullptr};
    uint8_t want[tb::TAG_LEN];
    bool ok = false;
    for (const uint8_t *key : keys) {
      if (!key) continue;
      tb::settings_tag(key, nonce, d[0], want);
      uint8_t diff = 0;
      for (size_t i = 0; i < tb::TAG_LEN; i++) diff |= want[i] ^ d[1 + i];
      ok |= diff == 0;
    }
    if (ok) {
      settings = d[0];
      prefs.putUChar("keys", settings);
      settings_written = true;
    }
    publish(chr);  // a fresh nonce either way, so no write can be replayed
  }

  // The settings characteristic reads as nonce | current settings.
  void publish(NimBLECharacteristic *chr) {
    esp_fill_random(nonce, sizeof nonce);
    uint8_t value[tb::NONCE_LEN + 1];
    memcpy(value, nonce, tb::NONCE_LEN);
    value[tb::NONCE_LEN] = settings;
    chr->setValue(value, sizeof value);
  }
};

// Pairing mode, also used to change the key settings: protocol/spec.md, "Pairing".
void pairing() {
  // Offer a fresh key, but keep the old one until a phone has read it: an aborted or accidental
  // pairing must not unpair the phone that already works.
  Identity offered = ident;
  esp_fill_random(offered.id, sizeof offered.id);
  esp_fill_random(offered.key, sizeof offered.key);
  uint8_t value[tb::ID_LEN + tb::KEY_LEN + 4];
  memcpy(value, offered.id, tb::ID_LEN);
  memcpy(value + tb::ID_LEN, offered.key, tb::KEY_LEN);
  for (int i = 0; i < 4; i++) value[tb::ID_LEN + tb::KEY_LEN + i] = (uint8_t)(ident.counter >> (8 * i));

  NimBLEDevice::init("tune-button");
  NimBLEDevice::setSecurityAuth(true, false, true);  // bond, no MITM (no I/O), LE Secure Connections
  NimBLEDevice::setSecurityIOCap(BLE_HS_IO_NO_INPUT_OUTPUT);
  NimBLEServer *server = NimBLEDevice::createServer();
  NimBLEService *svc = server->createService(SERVICE_UUID);
  static PairCallbacks callbacks;
  callbacks = PairCallbacks();
  callbacks.offered = &offered;
  NimBLECharacteristic *key_chr =
      svc->createCharacteristic(KEY_CHR_UUID, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::READ_ENC);
  key_chr->setValue(value, sizeof value);
  key_chr->setCallbacks(&callbacks);
  // Not encrypted: changing settings needs no new bond, and the tag already proves the writer
  // holds the key.
  NimBLECharacteristic *set_chr =
      svc->createCharacteristic(SETTINGS_CHR_UUID, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::WRITE);
  set_chr->setCallbacks(&callbacks);
  callbacks.publish(set_chr);
  svc->start();

  NimBLEAdvertising *adv = NimBLEDevice::getAdvertising();
  adv->setName("tune-button");
  adv->addServiceUUID(SERVICE_UUID);
  adv->enableScanResponse(true);
  adv->start();

  uint32_t start = millis();
  uint32_t read_at = 0, written_at = 0;
  while (millis() - start < PAIR_WINDOW_MS) {
    led((millis() / 125) % 2);
    delay(20);
    if (callbacks.key_read && !read_at) read_at = millis();
    if (callbacks.settings_written && !written_at) written_at = millis();
    // Give the last response time to leave, then stop. A phone that pairs sends its settings next;
    // an older app doesn't, so a read alone also ends it.
    if (written_at && millis() - written_at > 1500) break;
    if (read_at && millis() - read_at > 5000) break;
  }
  memset(value, 0, sizeof value);
  led(false);
  NimBLEDevice::deinit(true);
  if (read_at) {
    ident = offered;
    save_identity();
    blink(3);
  } else if (written_at) {
    blink(2);
  }
  memset(&offered, 0, sizeof offered);
}

[[noreturn]] void sleep_now() {
  // Level-triggered wake: a key still held would wake us at once, so wait for release.
  uint32_t t = millis();
  while (read_keys() && millis() - t < 10000) delay(10);
  uint64_t all = 0, mask = 0;
  for (int i = 0; i < KEYS; i++) {
    gpio_num_t p = KEY_PIN[i];
    if (p > GPIO_NUM_5) continue;  // not a wake pin (the XIAO board's K4 wakes through K3's)
    all |= 1ULL << p;
    // An unfitted D2 is never in KEY_PIN, so a floating pin can never wake the device.
    if (!pin_down(p)) mask |= 1ULL << p;
    gpio_pullup_en(p);
    gpio_pulldown_dis(p);
  }
  if (mask != all)
    esp_sleep_enable_timer_wakeup(60ULL * 1000000);  // a stuck key: look again in a minute
  if (mask) esp_deep_sleep_enable_gpio_wakeup(mask, ESP_GPIO_WAKEUP_GPIO_LOW);
  prefs.end();
  esp_deep_sleep_start();
}

// Which key woke the chip, or 0.
uint8_t wake_key() {
  uint32_t stub_in = wake_gpio_in;
  wake_gpio_in = ~0u;  // so a later wake without the stub can't reuse this reading
  if (esp_sleep_get_wakeup_cause() != ESP_SLEEP_WAKEUP_GPIO) return 0;
  uint64_t pins = esp_sleep_get_gpio_wakeup_status();
  for (int i = 0; i < KEYS; i++) {
    if (!(pins >> KEY_PIN[i] & 1)) continue;
    if (K4_ON_K3 && i == 2 && (pin_down(KEY_PIN[3]) || !(stub_in >> KEY_PIN[3] & 1))) return 4;
    return i + 1;
  }
  return 0;
}

}  // namespace

#if defined(TB_BOARD_XIAO)
// Runs from RTC memory straight out of deep sleep, long before setup(). Pads come out of sleep
// with input and pull-up off, so turn them on for GPIO6 before reading it.
extern "C" void RTC_IRAM_ATTR esp_wake_deep_sleep(void) {
  esp_default_wake_deep_sleep();
  PIN_INPUT_ENABLE(IO_MUX_GPIO6_REG);
  PIN_PULLUP_EN(IO_MUX_GPIO6_REG);
  for (volatile int i = 0; i < 200; i++) {}  // a few microseconds for the pull-up
  wake_gpio_in = REG_READ(GPIO_IN_REG);
}
#endif

void setup() {
  for (int i = 0; i < KEYS; i++) pinMode(KEY_PIN[i], INPUT_PULLUP);
  if (LED_PIN >= 0) pinMode(LED_PIN, OUTPUT);
  led(false);
  load_identity();
  uint8_t woke_by = wake_key();
  delay(DEBOUNCE_MS);

  // The one-button build always waits for release, since a press and the start of a pairing hold
  // look the same.
  tb::Gestures gestures(SINGLE ? (settings | 0b1) : settings, HOLD_MS, DOUBLE_MS, SINGLE);
  tb::Event events[tb::MAX_KEYS * 2];
  Burst burst;
  auto send = [&](int n) {
    for (int i = 0; i < n; i++) burst.send(tb::button_code(events[i].key, events[i].gesture));
  };

  uint8_t stable = read_keys(), raw = stable;
  // Keys already down that didn't wake us (a timer wake with a key stuck down, a key held at power-on)
  // stay quiet until let go, or a stuck key would send its action every wake. The chord still counts.
  uint8_t muted = stable & ~(woke_by ? 1 << (woke_by - 1) : 0);
  uint32_t raw_since = millis(), chord_since = 0, changed = millis();
  // A tap that was over before we could look still counts.
  if (woke_by && !(stable >> (woke_by - 1) & 1)) send(gestures.update(1 << (woke_by - 1), millis(), events));

  for (;;) {
    uint32_t now = millis();
    uint8_t r = read_keys();
    if (r != raw) { raw = r; raw_since = now; }
    // Debounced: a switch bounces on press and on release, and an undebounced edge sent each
    // physical press as up to three presses (bench, 2026-10-21).
    if (raw != stable && now - raw_since >= DEBOUNCE_MS) { stable = raw; changed = now; }

    // The pairing chord. Checked before the keys' own gestures, so keys 1 and 2 pressed together
    // send nothing.
    if ((stable & CHORD) == CHORD) {
      if (!chord_since) {
        chord_since = now ? now : 1;
        if (!SINGLE) { gestures.cancel(CHORD); muted |= CHORD; }
      }
      if (now - chord_since >= PAIR_HOLD_MS) {
        burst.stop();
        pairing();
        sleep_now();
      }
    } else {
      chord_since = 0;
    }
    muted &= stable;  // a muted key speaks again once let go

    send(gestures.update(stable & ~muted, now, events));
    bool on_air = burst.tick();
    if (gestures.settled() && !chord_since && !on_air && !stable) break;
    if (stable && now - changed > 15000) break;  // a key stuck down: sleep_now() copes with it
    delay(5);
  }
  burst.stop();
  sleep_now();
}

void loop() {}
