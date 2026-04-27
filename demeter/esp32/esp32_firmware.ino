/*
 * ==============================================
 * DEMETER GREENHOUSE — ESP32 FIRMWARE
 * Board: ESP32 DevKitC v4 WROOM-32D
 * ==============================================
 * 
 * Sensors:
 *   - Capacitive Soil Moisture Sensor → GPIO36 (ADC1_CH0)
 *   - DHT22 (Temperature + Humidity)  → GPIO4
 *   - MQ-135 (CO₂ / Air Quality)     → GPIO39 (ADC1_CH3)
 * 
 * Actuators:
 *   - Relay Module (Water Pump)       → GPIO5
 *   - Status LED                      → GPIO2 (onboard)
 * 
 * Communication:
 *   - WiFi → POST JSON to Demeter Server /lapor
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>

// ============================================
// CONFIGURATION — EDIT THESE VALUES
// ============================================

// WiFi
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// Demeter Server
const char* DEMETER_SERVER = "http://192.168.1.100:5000";  // Change to your server IP
const int   REPORT_INTERVAL_MS = 30000;  // Send data every 30 seconds

// Pin Assignments
#define PIN_SOIL_MOISTURE   36   // ADC1_CH0 (VP) — Capacitive Soil Sensor
#define PIN_DHT             4    // Digital — DHT22 Data Pin
#define PIN_MQ135           39   // ADC1_CH3 (VN) — MQ-135 Analog Out
#define PIN_RELAY           5    // Digital — Relay IN (Active LOW)
#define PIN_STATUS_LED      2    // Onboard LED

// DHT Sensor Type
#define DHT_TYPE            DHT22

// Soil Moisture Calibration (raw ADC values)
// Measure these with your specific sensor:
//   DRY_VALUE  = ADC reading when sensor is in air (dry)
//   WET_VALUE  = ADC reading when sensor is submerged in water
#define SOIL_DRY_VALUE      4095
#define SOIL_WET_VALUE      1200

// MQ-135 Calibration
// These are approximate conversion factors. 
// For accurate readings, calibrate with known CO2 levels.
#define MQ135_RZERO         76.63   // Sensor resistance in clean air
#define MQ135_PPM_FACTOR    116.6020682  // Scaling factor
#define MQ135_PPM_EXPONENT  -2.769034857 // Exponent

// ============================================
// GLOBALS
// ============================================

DHT dht(PIN_DHT, DHT_TYPE);

unsigned long lastReportTime = 0;
int  wifiRetryCount = 0;
bool relayActive = false;
unsigned long relayOffTime = 0;

// ============================================
// SETUP
// ============================================

void setup() {
    Serial.begin(115200);
    Serial.println("\n=============================");
    Serial.println("  DEMETER GREENHOUSE v6.2");
    Serial.println("  ESP32 DevKitC v4 WROOM-32D");
    Serial.println("=============================\n");

    // Pin modes
    pinMode(PIN_STATUS_LED, OUTPUT);
    pinMode(PIN_RELAY, OUTPUT);
    pinMode(PIN_SOIL_MOISTURE, INPUT);
    pinMode(PIN_MQ135, INPUT);

    // Relay OFF by default (Active LOW)
    digitalWrite(PIN_RELAY, HIGH);
    digitalWrite(PIN_STATUS_LED, LOW);

    // Initialize DHT sensor
    dht.begin();
    Serial.println("[SENSOR] DHT22 initialized on GPIO" + String(PIN_DHT));

    // Connect to WiFi
    connectWiFi();

    Serial.println("[SYSTEM] Setup complete. Starting main loop...\n");
}

// ============================================
// MAIN LOOP
// ============================================

void loop() {
    // Check WiFi connection
    if (WiFi.status() != WL_CONNECTED) {
        connectWiFi();
    }

    // Check if relay needs to be turned off
    if (relayActive && millis() >= relayOffTime) {
        digitalWrite(PIN_RELAY, HIGH);  // Active LOW — HIGH = OFF
        relayActive = false;
        Serial.println("[RELAY] Pump OFF — Duration complete.");
        digitalWrite(PIN_STATUS_LED, LOW);
    }

    // Report to server at interval
    if (millis() - lastReportTime >= REPORT_INTERVAL_MS) {
        lastReportTime = millis();
        reportToServer();
    }

    delay(100);  // Small delay to prevent watchdog issues
}

// ============================================
// WIFI CONNECTION
// ============================================

void connectWiFi() {
    Serial.print("[WIFI] Connecting to " + String(WIFI_SSID));
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 40) {
        delay(500);
        Serial.print(".");
        attempts++;
        // Blink LED while connecting
        digitalWrite(PIN_STATUS_LED, !digitalRead(PIN_STATUS_LED));
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\n[WIFI] ✓ Connected! IP: " + WiFi.localIP().toString());
        digitalWrite(PIN_STATUS_LED, HIGH);
        delay(500);
        digitalWrite(PIN_STATUS_LED, LOW);
        wifiRetryCount = 0;
    } else {
        Serial.println("\n[WIFI] ✗ Connection failed. Will retry...");
        wifiRetryCount++;
        // Exponential backoff
        delay(min(30000, 1000 * wifiRetryCount));
    }
}

// ============================================
// SENSOR READING FUNCTIONS
// ============================================

float readSoilMoisture() {
    // Read multiple samples and average for stability
    long sum = 0;
    const int samples = 10;
    for (int i = 0; i < samples; i++) {
        sum += analogRead(PIN_SOIL_MOISTURE);
        delay(10);
    }
    int rawValue = sum / samples;

    // Map to percentage (inverted: high ADC = dry, low ADC = wet)
    float percentage = map(rawValue, SOIL_DRY_VALUE, SOIL_WET_VALUE, 0, 100);
    percentage = constrain(percentage, 0.0, 100.0);

    Serial.printf("[SOIL] Raw: %d → %.1f%%\n", rawValue, percentage);
    return percentage;
}

float readTemperature() {
    float temp = dht.readTemperature();
    if (isnan(temp)) {
        Serial.println("[DHT22] ✗ Temperature read failed!");
        return -1;
    }
    Serial.printf("[DHT22] Temperature: %.1f°C\n", temp);
    return temp;
}

float readHumidity() {
    float hum = dht.readHumidity();
    if (isnan(hum)) {
        Serial.println("[DHT22] ✗ Humidity read failed!");
        return -1;
    }
    Serial.printf("[DHT22] Humidity: %.1f%%\n", hum);
    return hum;
}

float readCO2() {
    // Read multiple samples and average
    long sum = 0;
    const int samples = 10;
    for (int i = 0; i < samples; i++) {
        sum += analogRead(PIN_MQ135);
        delay(10);
    }
    int rawValue = sum / samples;

    // Convert raw ADC to estimated PPM
    // This is an approximation — proper calibration recommended
    float voltage = rawValue * (3.3 / 4095.0);
    float resistance = ((3.3 * 10.0) / voltage) - 10.0;  // 10K load resistor
    float ratio = resistance / MQ135_RZERO;
    float ppm = MQ135_PPM_FACTOR * pow(ratio, MQ135_PPM_EXPONENT);
    ppm = constrain(ppm, 0, 5000);

    Serial.printf("[MQ135] Raw: %d, Voltage: %.2fV, PPM: %.0f\n", rawValue, voltage, ppm);
    return ppm;
}

// ============================================
// REPORT TO DEMETER SERVER
// ============================================

void reportToServer() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[REPORT] ✗ No WiFi — skipping report.");
        return;
    }

    // Blink LED — reporting
    digitalWrite(PIN_STATUS_LED, HIGH);

    // Read all sensors
    float moisture = readSoilMoisture();
    float temp     = readTemperature();
    float humidity  = readHumidity();
    float co2      = readCO2();

    // Validate readings
    if (temp < 0) temp = 0;
    if (humidity < 0) humidity = 0;

    // Build JSON payload
    JsonDocument doc;
    doc["moisture"] = round(moisture * 10) / 10.0;  // 1 decimal
    doc["temp"]     = round(temp * 10) / 10.0;
    doc["humidity"] = round(humidity * 10) / 10.0;
    doc["co2"]      = round(co2);

    String jsonPayload;
    serializeJson(doc, jsonPayload);

    Serial.println("\n[REPORT] ▶ Sending to Demeter:");
    Serial.println("  " + jsonPayload);

    // POST to server
    HTTPClient http;
    String url = String(DEMETER_SERVER) + "/lapor";
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(15000);  // 15 second timeout

    int httpCode = http.POST(jsonPayload);

    if (httpCode > 0) {
        String response = http.getString();
        Serial.printf("[REPORT] ✓ Server responded (%d): %s\n", httpCode, response.c_str());

        // Parse response
        JsonDocument resDoc;
        DeserializationError error = deserializeJson(resDoc, response);

        if (!error) {
            const char* action = resDoc["action"] | "DIAM";
            int duration = resDoc["duration_sec"] | 0;

            Serial.printf("[SERVER] Action: %s, Duration: %ds\n", action, duration);

            // Execute action
            if (String(action) == "SIRAM" && duration > 0) {
                activateRelay(duration);
            }
        }
    } else {
        Serial.printf("[REPORT] ✗ HTTP Error: %s\n", http.errorToString(httpCode).c_str());
    }

    http.end();
    digitalWrite(PIN_STATUS_LED, LOW);
}

// ============================================
// RELAY / PUMP CONTROL
// ============================================

void activateRelay(int durationSeconds) {
    Serial.printf("[RELAY] 💦 Pump ON for %d seconds!\n", durationSeconds);
    
    digitalWrite(PIN_RELAY, LOW);   // Active LOW — LOW = ON
    digitalWrite(PIN_STATUS_LED, HIGH);
    relayActive = true;
    relayOffTime = millis() + (durationSeconds * 1000UL);
}
