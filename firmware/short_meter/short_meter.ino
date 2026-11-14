// short_meter: measure the resistance of the 3V3->GND short on the quadrant PCB
// using the ESP32 ADC and a known series resistor. No multimeter needed.
//
// Wiring (breadboard):
//   ESP32 3V3    -> series resistor (10k first, 330R for a finer reading)
//   resistor     -> J1 pin 2  (board 3V3 rail)  <- this junction is the NODE
//   ESP32 GPIO34 -> NODE (same junction)
//   ESP32 GND    -> J1 pin 3  (board GND)
//
// V(node) = 3300 * Rshort / (Rshort + Rseries)
// => Rshort = Rseries * V / (3300 - V)
//
// Interpretation:
//   ~0 mV        -> hard short (<50R): solder bridge, fab defect, wire sliver
//   50-1000 mV   -> resistive fault: damaged chip or cap leaking
//   ~3300 mV     -> no short at all; rail is fine
const int PIN = 34;              // input-only, ADC1

int mv() {
  long acc = 0;
  for (int i = 0; i < 64; i++) acc += analogReadMilliVolts(PIN);
  return acc / 64;
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN, INPUT);
  analogSetPinAttenuation(PIN, ADC_11db);   // full 0-3.3V range
  Serial.println("=== SHORT METER (GPIO34) ===");
}

void report(int v, float rs, const char* name) {
  if (v >= 3200) { Serial.printf("  [%s] rail looks OPEN/normal, no short\n", name); return; }
  float rshort = rs * v / (3300.0 - v);
  Serial.printf("  [%s] Rshort ~ %.1f ohm\n", name, rshort);
}

void loop() {
  int v = mv();
  Serial.printf("node = %4d mV   |", v);
  report(v, 10000, "if 10k");
  report(v,   330, "if 330R");
  if (v < 25)       Serial.println("  verdict: HARD SHORT (bridge / fab defect / metal sliver)");
  else if (v < 3000) Serial.println("  verdict: RESISTIVE fault - suspect a damaged 74HC165 or cap");
  else              Serial.println("  verdict: NO SHORT on this rail");
  delay(700);
}
