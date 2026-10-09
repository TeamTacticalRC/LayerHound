// LayerHound LED status light, colored by LayerHound (backend/lightbar.py). One firmware, two shapes
// (platformio.ini): the 12-LED ring (main light, an arc per printer) or the 8-LED bar (an LED each).
//
// - First start (or holding BOOT while plugging in): the light makes a Wi-Fi network called
//   "LayerHound-Light". A phone that joins it gets a setup page: home Wi-Fi, the LayerHound
//   address and a read-only access key (Settings -> Login & users -> Access keys).
// - Then every few seconds it asks LayerHound for /api/lightbar (saying which shape it is) and
//   draws what it says. LayerHound picks the colors and effects, so they can change without
//   reflashing the light.
// - Its own status, when it can't show printers:
//     setup page waiting     all LEDs pulse purple
//     joining Wi-Fi          one white light sweeps back and forth
//     can't reach LayerHound all LEDs blink dim purple (it keeps trying)
//     access key refused     all LEDs solid dim purple (make a new key, hold BOOT, re-enter it)
#include <Arduino.h>
#include <Adafruit_NeoPixel.h>
#include <ArduinoJson.h>
#include <ESPmDNS.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiManager.h>

// ---- Wiring --------------------------------------------------------------------------------
const int LED_PIN = 13;      // ESP32 GPIO13 -> 74AHCT125 1A; 1Y -> 470 ohm -> stick DIN
const int BOOT_PIN = 0;      // the board's BOOT button
#ifndef LEDS
#define LEDS 12              // set per shape in platformio.ini
#endif
#ifndef LAYOUT
#define LAYOUT "ring"
#endif
const char *SETUP_NETWORK = "LayerHound-Light";

// ---- Timing --------------------------------------------------------------------------------
const uint32_t FRAME_MS = 20;          // redraw 50 times a second, for smooth pulses
const uint32_t STALE_MS = 30000;       // older than this, the colors are no longer trusted
const uint32_t HTTP_TIMEOUT_MS = 4000;

Adafruit_NeoPixel strip(LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);
Preferences prefs;
WiFiManager wm;
WiFiManagerParameter urlParam("url", "LayerHound address", "http://layerhound.local", 120);
WiFiManagerParameter keyParam("key", "Access key (from Settings &rarr; Login &amp; users)", "", 80);

enum Mode { SETUP, JOINING, RUNNING };
Mode mode = JOINING;

String baseUrl, accessKey, resolvedUrl;
struct Led { uint8_t r, g, b; char effect; };   // effect: 's'olid, 'p'ulse, 'b'link, 'o'ff
Led leds[LEDS];
uint8_t brightness = 40;          // percent, from LayerHound
uint32_t pollMs = 5000, lastPoll = 0, lastGood = 0;
int lastHttp = 0;                 // last HTTP status (or a negative error), for the status display
bool saveRequested = false;

// ---- Settings ------------------------------------------------------------------------------
String normalizeUrl(String u) {
  u.trim();
  while (u.endsWith("/")) u.remove(u.length() - 1);
  if (u.length() && !u.startsWith("http://") && !u.startsWith("https://")) u = "http://" + u;
  return u;
}

void loadSettings() {
  prefs.begin("lightbar", true);
  baseUrl = prefs.getString("url", "http://layerhound.local");
  accessKey = prefs.getString("key", "");
  prefs.end();
}

void saveSettings() {
  baseUrl = normalizeUrl(urlParam.getValue());
  accessKey = String(keyParam.getValue());
  accessKey.trim();
  prefs.begin("lightbar", false);
  prefs.putString("url", baseUrl);
  prefs.putString("key", accessKey);
  prefs.end();
  resolvedUrl = "";
  Serial.printf("[setup] saved: %s, key %s\n", baseUrl.c_str(), accessKey.length() ? "set" : "missing");
}

// ---- Finding LayerHound ---------------------------------------------------------------------
// The ESP32 can't open ".local" names by itself, so look them up with mDNS first.
String resolve() {
  if (resolvedUrl.length()) return resolvedUrl;
  int start = baseUrl.indexOf("://") + 3;
  int end = baseUrl.indexOf(':', start);
  int slash = baseUrl.indexOf('/', start);
  if (end < 0 || (slash >= 0 && slash < end)) end = slash >= 0 ? slash : baseUrl.length();
  String host = baseUrl.substring(start, end);
  if (!host.endsWith(".local")) return resolvedUrl = baseUrl;
  IPAddress ip = MDNS.queryHost(host.substring(0, host.length() - 6), 2000);
  if (ip == IPAddress()) { Serial.printf("[mdns] couldn't find %s\n", host.c_str()); return ""; }
  return resolvedUrl = baseUrl.substring(0, start) + ip.toString() + baseUrl.substring(end);
}

// ---- Asking LayerHound ----------------------------------------------------------------------
void poll() {
  String root = resolve();
  if (!root.length()) { lastHttp = -1; return; }
  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.setConnectTimeout(HTTP_TIMEOUT_MS);
  if (!http.begin(root + "/api/lightbar?layout=" LAYOUT "&leds=" + String(LEDS))) { lastHttp = -2; return; }
  http.addHeader("Authorization", "Bearer " + accessKey);
  lastHttp = http.GET();
  if (lastHttp == 200) {
    JsonDocument doc;
    if (!deserializeJson(doc, http.getString())) {
      brightness = constrain(doc["brightness"] | 40, 0, 100);
      pollMs = constrain((doc["poll"] | 5) * 1000, 2000, 60000);
      JsonArray list = doc["leds"];
      for (int i = 0; i < LEDS; i++) {
        JsonObject l = list[i];
        const char *effect = l["effect"] | "off";
        leds[i] = { (uint8_t)(l["rgb"][0] | 0), (uint8_t)(l["rgb"][1] | 0), (uint8_t)(l["rgb"][2] | 0), effect[0] };
      }
      lastGood = millis();
    }
  } else {
    Serial.printf("[poll] %s/api/lightbar -> %d\n", root.c_str(), lastHttp);
    if (lastHttp < 0) resolvedUrl = "";   // the board may have a new address; look it up again
  }
  http.end();
}

// ---- Drawing ----------------------------------------------------------------------------------
uint32_t scaled(uint8_t r, uint8_t g, uint8_t b, float level) {
  level = constrain(level, 0.0f, 1.0f);
  return strip.Color(r * level, g * level, b * level);
}

float pulse(uint32_t now, float period) { return 0.2f + 0.8f * (0.5f + 0.5f * sinf(now * 6.2832f / period)); }

void drawPrinters(uint32_t now) {
  float k = brightness / 100.0f;
  bool blinkOn = (now / 500) % 2 == 0;
  for (int i = 0; i < LEDS; i++) {
    const Led &l = leds[i];
    float level = l.effect == 'p' ? pulse(now, 2000) : l.effect == 'b' ? (blinkOn ? 1.0f : 0.08f) : l.effect == 'o' ? 0 : 1;
    strip.setPixelColor(i, scaled(l.r, l.g, l.b, level * k));
  }
}

void drawAll(uint32_t color) { for (int i = 0; i < LEDS; i++) strip.setPixelColor(i, color); }

void draw(uint32_t now) {
  const uint8_t P[] = { 120, 0, 255 };   // purple: the bar talking about itself, never a printer state
  if (mode == SETUP) drawAll(scaled(P[0], P[1], P[2], 0.25f * pulse(now, 2500)));
  else if (mode == JOINING) {
    strip.clear();
    int pos = (now / 120) % (2 * LEDS - 2);
    strip.setPixelColor(pos < LEDS ? pos : 2 * LEDS - 2 - pos, scaled(255, 255, 255, 0.25f));
  }
  else if (lastGood && now - lastGood < STALE_MS) drawPrinters(now);
  else if (lastHttp == 401 || lastHttp == 403) drawAll(scaled(P[0], P[1], P[2], 0.2f));
  else drawAll((now / 700) % 2 ? scaled(P[0], P[1], P[2], 0.15f) : 0);
  strip.show();
}

// ---- Start and run ----------------------------------------------------------------------------
void startSetup() {
  mode = SETUP;
  Serial.printf("[setup] join the Wi-Fi network %s from a phone\n", SETUP_NETWORK);
  wm.startConfigPortal(SETUP_NETWORK);
}

void setup() {
  Serial.begin(115200);
  pinMode(BOOT_PIN, INPUT_PULLUP);
  strip.begin(); strip.clear(); strip.show();
  for (Led &l : leds) l = { 0, 0, 0, 'o' };
  loadSettings();
  urlParam.setValue(baseUrl.c_str(), 120);
  keyParam.setValue(accessKey.c_str(), 80);

  WiFi.mode(WIFI_STA);
  WiFi.setHostname("layerhound-light");
  wm.setConfigPortalBlocking(false);       // keep the LEDs animating while the setup page is up
  wm.setTitle("LayerHound status light");
  wm.addParameter(&urlParam);
  wm.addParameter(&keyParam);
  wm.setSaveParamsCallback([] { saveRequested = true; });
  wm.setSaveConfigCallback([] { saveRequested = true; });
  wm.setConnectTimeout(30);

  bool forceSetup = digitalRead(BOOT_PIN) == LOW;   // BOOT held while plugging in
  if (forceSetup || !accessKey.length()) startSetup();
  else if (!wm.autoConnect(SETUP_NETWORK)) mode = SETUP;   // couldn't join: setup page opens itself
}

void loop() {
  uint32_t now = millis();
  wm.process();
  if (saveRequested) { saveRequested = false; saveSettings(); }
  if (mode != RUNNING && WiFi.status() == WL_CONNECTED && accessKey.length()) {
    mode = RUNNING;
    MDNS.begin("layerhound-light");
    Serial.printf("[wifi] connected as %s\n", WiFi.localIP().toString().c_str());
    lastPoll = now - pollMs;   // ask right away
  }
  if (mode == RUNNING && now - lastPoll >= pollMs) { lastPoll = now; poll(); }
  static uint32_t lastFrame = 0;
  if (now - lastFrame >= FRAME_MS) { lastFrame = now; draw(now); }
}
