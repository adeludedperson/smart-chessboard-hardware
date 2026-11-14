// quad_probe: read all 4 input-only ADC1 pins (GPIO 34,35,36,39) with min/max.
// Purpose: find which pin the sense wire is REALLY on, and spot floating pins.
// A connected node reads steady; a floating pin reads noisy/drifting.
const int PINS[4] = {34, 35, 36, 39};
const char* NAMES[4] = {"P34", "P35", "SVP(36)", "SVN(39)"};

void setup() {
  Serial.begin(115200);
  for (int i = 0; i < 4; i++) {
    pinMode(PINS[i], INPUT);
    analogSetPinAttenuation(PINS[i], ADC_11db);
  }
  Serial.println("=== QUAD PROBE ===");
}

void loop() {
  for (int i = 0; i < 4; i++) {
    int lo = 9999, hi = -1; long acc = 0;
    for (int k = 0; k < 48; k++) {
      int v = analogReadMilliVolts(PINS[i]);
      acc += v; if (v < lo) lo = v; if (v > hi) hi = v;
    }
    int avg = acc / 48;
    const char* tag = (avg < 60) ? "  << LOW (connected to GND path!)" :
                      (hi - lo > 220) ? "  (noisy - probably floating)" : "";
    Serial.printf("%-8s avg=%4d mV  span=%4d%s\n", NAMES[i], avg, hi - lo, tag);
  }
  Serial.println("---");
  delay(900);
}
