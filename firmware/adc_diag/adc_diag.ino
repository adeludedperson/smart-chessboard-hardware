// Analog diagnostic on GPIO27 (ADC2_CH7, works since WiFi is off).
// Measures real pin voltage under: no bias, pullup, pulldown.
// Interpretation:
//  - strong drive HIGH: ~3300mV in all three modes
//  - leak/weak source: sags toward 0 under pulldown (mid values)
//  - proper A3144 idle (open collector + pullup): 3300 w/ pullup, ~0 w/ pulldown
//  - magnet triggering: drops to <300mV in pullup mode
const int PIN = 27;
const int LED = 2;

int mv(int mode) {
  pinMode(PIN, mode);
  delayMicroseconds(500);
  long acc = 0;
  for (int i = 0; i < 16; i++) acc += analogReadMilliVolts(PIN);
  return acc / 16;
}

void setup() {
  Serial.begin(115200);
  pinMode(LED, OUTPUT);
  analogSetPinAttenuation(PIN, ADC_11db); // full 0-3.3V range
}

void loop() {
  int f = mv(INPUT);
  int u = mv(INPUT_PULLUP);
  int dwn = mv(INPUT_PULLDOWN);
  const char* verdict;
  if (u > 3000 && dwn > 3000)      verdict = "STRONG HIGH source (push-pull idle OR 3V3 into pin)";
  else if (u > 3000 && dwn < 300)  verdict = "OPEN/IDLE open-collector or floating";
  else if (u < 300)                verdict = ">>> PULLED LOW - SENSOR TRIGGERED <<<";
  else                             verdict = "WEAK/LEAKY source (partial sag - mirrored sensor?)";
  Serial.printf("float=%4dmV  pullup=%4dmV  pulldown=%4dmV  | %s\n", f, u, dwn, verdict);
  digitalWrite(LED, u < 300 ? HIGH : LOW);
  delay(500);
}
