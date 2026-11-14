// quadrant_diag64 - gate test for N chained quadrant boards (16 stages each).
// Set NUM_BOARDS below: 3 = 48-square chain, 4 = full 64-square board.
//
// WIRING (6 + 6*(N-1) + 1 wires):
//   ESP32 -> FIRST board J1: 5V, 3V3, GND, P25(PL), P26(CP), P14(SER inject)
//   each board J2 -> next board J1: all 6, label to label (mirror flip)
//   ESP32 P27 <- LAST board's J2 SER pin (the read point)
//
// Shift-only gate test: PL stays HIGH so nothing loads from sensors. The
// level held on P14 must walk through all NUM_BOARDS*16 register stages and
// appear at P27. 0s -> all zero, 1s -> all ones (masked to chain length).
//
// Bit order (proven on the 32-chain): first 16 bits read = LAST board in
// the chain (the one P27 reads from), then backward toward the harness.

const int NUM_BOARDS = 4;          // <-- 3 now; set to 4 for the full board
const int NBITS = NUM_BOARDS * 16;

const int PIN_PL = 25, PIN_CP = 26, PIN_SER_OUT = 27, PIN_SER_IN = 14;

uint64_t chainMask() { return (NBITS >= 64) ? ~0ULL : ((1ULL << NBITS) - 1); }

void clockPulse() {
  digitalWrite(PIN_CP, HIGH); delayMicroseconds(3);
  digitalWrite(PIN_CP, LOW);  delayMicroseconds(3);
}

uint64_t shiftTest(int level) {
  digitalWrite(PIN_PL, HIGH);
  digitalWrite(PIN_SER_IN, level);
  for (int i = 0; i < NBITS; i++) clockPulse();   // flush the whole chain
  uint64_t v = 0;
  for (int i = 0; i < NBITS; i++) {
    v = (v << 1) | (digitalRead(PIN_SER_OUT) & 1);
    clockPulse();
  }
  return v;
}

uint64_t parallelRead() {
  digitalWrite(PIN_PL, LOW);  delayMicroseconds(5);
  digitalWrite(PIN_PL, HIGH); delayMicroseconds(5);
  uint64_t v = 0;
  for (int i = 0; i < NBITS; i++) {
    v = (v << 1) | (digitalRead(PIN_SER_OUT) & 1);
    clockPulse();
  }
  return v;
}

// Board label for a 16-bit group. Group 0 = first bits read = LAST board.
// Boards are numbered 1..N from the harness end, so group g = board N-g.
int groupToBoard(int g) { return NUM_BOARDS - g; }

void runChainTest() {
  uint64_t mask = chainMask();
  uint64_t lo = shiftTest(LOW);
  uint64_t hi = shiftTest(HIGH);
  int hexw = NBITS / 4;
  Serial.printf("shift 0s -> 0x%0*llX  (want 0x%0*llX)\n", hexw, lo, hexw, 0ULL);
  Serial.printf("shift 1s -> 0x%0*llX  (want 0x%0*llX)\n", hexw, hi, hexw, mask);
  if (lo == 0 && hi == mask) {
    Serial.printf("CHAIN%d: PASS - all %d chips, %d boards, every bridge works.\n",
                  NBITS, NUM_BOARDS * 2, NUM_BOARDS);
  } else if (lo == mask && hi == mask) {
    Serial.printf("CHAIN%d: FAIL - no data moving. Check CP wires in the bridges and P14 on the first board's J1 SER.\n", NBITS);
  } else {
    Serial.printf("CHAIN%d: FAIL - per-board result (board 1 = harness end):\n", NBITS);
    for (int g = 0; g < NUM_BOARDS; g++) {
      int shift = NBITS - 16 * (g + 1);
      uint16_t glo = (lo >> shift) & 0xFFFF;
      uint16_t ghi = (hi >> shift) & 0xFFFF;
      bool ok = (glo == 0x0000 && ghi == 0xFFFF);
      Serial.printf("  board %d: 0s->0x%04X 1s->0x%04X  %s\n",
                    groupToBoard(g), glo, ghi, ok ? "ok" : "<-- BAD (this board's chips, or the SER wire feeding it)");
    }
  }
  Serial.println();
}

void setup() {
  Serial.begin(115200); delay(400);
  pinMode(PIN_PL, OUTPUT); pinMode(PIN_CP, OUTPUT);
  pinMode(PIN_SER_IN, OUTPUT); pinMode(PIN_SER_OUT, INPUT);
  digitalWrite(PIN_PL, HIGH); digitalWrite(PIN_CP, LOW);

  Serial.printf("\n\n=== %d-BIT CHAIN DIAGNOSTIC (%d boards) ===\n\n", NBITS, NUM_BOARDS);
  runChainTest();
}

void loop() {
  static int n = 0;
  digitalWrite(PIN_SER_IN, LOW);
  uint64_t v = parallelRead();
  Serial.printf("sensors raw = 0x%0*llX\n", NBITS / 4, v);
  if (++n % 10 == 0) runChainTest();   // re-run gate every ~4 s
  delay(400);
}
