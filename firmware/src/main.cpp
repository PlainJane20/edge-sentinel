// Edge Sentinel firmware: reads the ESP32's on-chip temperature sensor plus a
// hall reading, then POSTs JSON to the gateway every 5 seconds.
// Wi-Fi credentials and gateway URL come from env vars at build time
// (see platformio.ini), so no secrets live in source.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>

static const uint32_t REPORT_INTERVAL_MS = 5000;

static void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print('.');
  }
  Serial.printf("\nConnected, IP %s\n", WiFi.localIP().toString().c_str());
}

static void report() {
  JsonDocument doc;
  doc["device_id"] = WiFi.macAddress();
  doc["temperature_c"] = temperatureRead();  // on-chip sensor
  doc["rssi"] = WiFi.RSSI();
  doc["uptime_s"] = millis() / 1000;
  doc["free_heap"] = ESP.getFreeHeap();

  String body;
  serializeJson(doc, body);

  HTTPClient http;
  http.begin(String(GATEWAY_URL) + "/readings");
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(body);
  Serial.printf("POST %s -> %d\n", body.c_str(), code);
  if (code > 0) {
    Serial.println(http.getString());  // gateway's decision
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  connectWifi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWifi();
  report();
  delay(REPORT_INTERVAL_MS);
}
