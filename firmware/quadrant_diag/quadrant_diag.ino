// quadrant_diag - split the failure: is it the shift chain, or the sensors?
//
// WIRING (7 wires now):
//   VIN/5V -> J1 pin1 (5V)      GND -> J1 pin3 (GND)
//   3V3    -> J1 pin2 (3V3)
//   GPIO25 -> J1 pin4 (PL)      GPIO26 -> J1 pin5 (CP)
//   GPIO14 -> J1 pin6 (SER)     <-- NEW, injects a test pattern
//   GPIO27 <- J2 pin6 (SER)     <-- reads the far end of the chain

const int PIN_PL = 25, PIN_CP = 26, PIN_SER_OUT = 27, PIN_SER_IN = 14;

const uint8_t CHAIN_ORDER[16] = {15,14,11,10,2,3,6,7,13,12,9,8,0,1,4,5};

void clockPulse() {
  digitalWrite(PIN_CP, HIGH); delayMicroseconds(3);
  digitalWrite(PIN_CP, LOW);  delayMicroseconds(3);
}

// Shift-only: PL stays HIGH so nothing loads. Whatever we hold on SER_IN
// must walk through all 16 stages and appear at SER_OUT after 16 clocks.
uint16_t shiftTest(int level) {
  digitalWrite(PIN_PL, HIGH);
  digitalWrite(PIN_SER_IN, level);
  for (int i = 0; i < 16; i++) clockPulse();   // flush the chain
  uint16_t v = 0;
  for (int i = 0; i < 16; i++) {
    v = (v << 1) | (digitalRead(PIN_SER_OUT) & 1);
    clockPulse();
  }
  return v;
}

uint16_t parallelRead() {
  digitalWrite(PIN_PL, LOW);  delayMicroseconds(5);
  digitalWrite(PIN_PL, HIGH); delayMicroseconds(5);
  uint16_t v = 0;
  for (int i = 0; i < 16; i++) {
    v = (v << 1) | (digitalRead(PIN_SER_OUT) & 1);
    clockPulse();
  }
  return v;
}

void setup() {
  Serial.begin(115200); delay(400);
  pinMode(PIN_PL, OUTPUT); pinMode(PIN_CP, OUTPUT);
  pinMode(PIN_SER_IN, OUTPUT); pinMode(PIN_SER_OUT, INPUT);
  digitalWrite(PIN_PL, HIGH); digitalWrite(PIN_CP, LOW);

  Serial.println("\n\n=== QUADRANT DIAGNOSTIC ===\n");

  uint16_t lo = shiftTest(LOW);
  uint16_t hi = shiftTest(HIGH);
  Serial.printf("shift 0s -> 0x%04X  (want 0x0000)\n", lo);
  Serial.printf("shift 1s -> 0x%04X  (want 0xFFFF)\n", hi);
  if (lo == 0x0000 && hi == 0xFFFF)
    Serial.println("CHAIN: PASS - PL, CP, both chips and the J1->U1->U2->J2 path all work.");
  else if (lo == 0xFFFF)
    Serial.println("CHAIN: FAIL - data is not moving. Check CP (pin5) and the GPIO14->J1 SER wire.");
  else
    Serial.println("CHAIN: FAIL - partial. Check for a solder bridge or a bad chip.");
  Serial.println();
}

void loop() {
  digitalWrite(PIN_SER_IN, LOW);
  uint16_t v = parallelRead();
  int n = 0;
  for (int i = 0; i < 16; i++) if (!((v >> (15 - i)) & 1)) n++;

  Serial.printf("sensors raw = 0x%04X   detected = %d   ", v, n);
  if (v == 0xFFFF)      Serial.print("(all empty)");
  else if (v == 0x0000) Serial.print("(ALL LOW - check 3V3 / GND)");
  else {
    Serial.print(" ->");
    for (int i = 0; i < 16; i++)
      if (!((v >> (15 - i)) & 1)) Serial.printf(" S%d", CHAIN_ORDER[i]);
  }
  Serial.println();
  delay(400);
}
