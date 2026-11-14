// quadrant_diag32 - gate test for TWO chained quadrant boards (32 stages).
//
// WIRING (13 wires):
//   ESP32 -> board A J1: 5V, 3V3, GND, P25(PL), P26(CP), P14(SER inject)
//   board A J2 -> board B J1: all 6, label to label (5V,3V3,GND,PL,CP,SER)
//   ESP32 P27 <- board B J2 SER pin
//
// Shift-only test: PL stays HIGH so nothing loads from sensors. The level
// held on P14 must walk through all 32 register stages (4x 74HC165) and
// appear at P27 after 32 clocks. 0s -> 0x00000000, 1s -> 0xFFFFFFFF.

const int PIN_PL = 25, PIN_CP = 26, PIN_SER_OUT = 27, PIN_SER_IN = 14;

void clockPulse() {
  digitalWrite(PIN_CP, HIGH); delayMicroseconds(3);
  digitalWrite(PIN_CP, LOW);  delayMicroseconds(3);
}

uint32_t shiftTest(int level) {
  digitalWrite(PIN_PL, HIGH);
  digitalWrite(PIN_SER_IN, level);
  for (int i = 0; i < 32; i++) clockPulse();   // flush the whole chain
  uint32_t v = 0;
  for (int i = 0; i < 32; i++) {
    v = (v << 1) | (digitalRead(PIN_SER_OUT) & 1);
    clockPulse();
  }
  return v;
}

uint32_t parallelRead() {
  digitalWrite(PIN_PL, LOW);  delayMicroseconds(5);
  digitalWrite(PIN_PL, HIGH); delayMicroseconds(5);
  uint32_t v = 0;
  for (int i = 0; i < 32; i++) {
    v = (v << 1) | (digitalRead(PIN_SER_OUT) & 1);
    clockPulse();
  }
  return v;
}

void runChainTest() {
  uint32_t lo = shiftTest(LOW);
  uint32_t hi = shiftTest(HIGH);
  Serial.printf("shift 0s -> 0x%08X  (want 0x00000000)\n", lo);
  Serial.printf("shift 1s -> 0x%08X  (want 0xFFFFFFFF)\n", hi);
  if (lo == 0x00000000 && hi == 0xFFFFFFFF)
    Serial.println("CHAIN32: PASS - all 4 chips, both boards, and the A->B bridge work.");
  else if (lo == 0xFFFFFFFF && hi == 0xFFFFFFFF)
    Serial.println("CHAIN32: FAIL - no data moving. Check CP wire in the A->B bridge, and P14 on A J1 SER.");
  else if ((lo & 0xFFFF0000) == 0 && (hi & 0xFFFF0000) == 0xFFFF0000
        && (lo & 0xFFFF) != 0)
    Serial.println("CHAIN32: FAIL in the SECOND half - board A's chips or the A->B SER wire.");
  else if ((lo & 0xFFFF) == 0 && (hi & 0xFFFF) == 0xFFFF)
    Serial.println("CHAIN32: FAIL in the FIRST half - board B's chips or P27 on B J2 SER.");
  else
    Serial.println("CHAIN32: FAIL - partial. Re-check every bridge wire label-to-label.");
  Serial.println();
}

void setup() {
  Serial.begin(115200); delay(400);
  pinMode(PIN_PL, OUTPUT); pinMode(PIN_CP, OUTPUT);
  pinMode(PIN_SER_IN, OUTPUT); pinMode(PIN_SER_OUT, INPUT);
  digitalWrite(PIN_PL, HIGH); digitalWrite(PIN_CP, LOW);

  Serial.println("\n\n=== 32-BIT CHAIN DIAGNOSTIC (2 boards) ===\n");
  runChainTest();
}

void loop() {
  static int n = 0;
  digitalWrite(PIN_SER_IN, LOW);
  uint32_t v = parallelRead();
  Serial.printf("sensors raw = 0x%08X\n", v);
  if (++n % 10 == 0) runChainTest();   // re-run gate every ~4 s
  delay(400);
}
