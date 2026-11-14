// Smart Chessboard — Arrival Day Test Sketch
// Tests: ESP32 alive, onboard LED, one A3144 hall sensor.
//
// WIRING (3 wires, no resistor needed — ESP32 internal pull-up is used):
//   A3144 flat face toward you, legs down, pins LEFT to RIGHT: VCC, GND, OUT
//   1. VCC (left)  -> ESP32 "VIN" pin (5V when powered from USB)
//   2. GND (mid)   -> ESP32 "GND"
//   3. OUT (right) -> ESP32 "D27" (GPIO 27)
//
// WHAT YOU SHOULD SEE (Serial Monitor @ 115200):
//   - "no magnet" printed once per second
//   - Bring a magnet close to the sensor's FLAT face ->
//     "MAGNET DETECTED" + onboard blue LED turns on
//   - A3144 only fires on ONE pole. If nothing happens, FLIP the magnet over.
//
// USE THIS TO:
//   1. Screen ~10 sensors for duds (swap sensor, re-test, ~30s each)
//   2. Later: sort ALL magnet poles (mark the face that triggers — that
//      face goes DOWN when glued into piece bases)

const int SENSOR_PIN = 27; // A3144 OUT
const int LED_PIN = 2;     // onboard blue LED

void setup() {
  Serial.begin(115200);
  pinMode(SENSOR_PIN, INPUT_PULLUP); // pull-up to 3.3V — safe, correct
  pinMode(LED_PIN, OUTPUT);
  Serial.println("\n=== Hall sensor test. Bring magnet close. ===");
}

void loop() {
  // A3144 is open-collector: LOW = magnet present
  bool detected = (digitalRead(SENSOR_PIN) == LOW);
  digitalWrite(LED_PIN, detected ? HIGH : LOW);
  Serial.println(detected ? ">>> MAGNET DETECTED <<<" : "no magnet");
  delay(detected ? 150 : 1000);
}
