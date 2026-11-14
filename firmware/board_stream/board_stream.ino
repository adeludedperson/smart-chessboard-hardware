// board_stream - PRODUCTION firmware. This is what the app talks to.
//
// Emits exactly what app/daemon/src/decode.ts parses:
//     raw = 0xFFFFFFFFFFFFFFFF        (active-low: bit 0 = occupied)
// at ~50 fps, so packages/core's 80 ms debounce has real frames to work with.
// Everything else it prints is ignored by the daemon's regex and is there for
// humans and firmware/tools/board_state.py.
//
// Differences from quadrant_diag64, and why:
//   - chain length is MEASURED at boot, never configured. Unplug a board and
//     reset; it re-sizes. No more editing NUM_BOARDS and forgetting.
//   - 20 ms frame period instead of 400 ms. A piece lift is ~100 ms; at 2.5
//     fps the tracker cannot see a clean lift/place pair.
//   - CP is held HIGH across the PL rising edge, per the NXP 74HC165 note
//     ("either CP or CE should be HIGH before the LOW-to-HIGH transition of
//     PL"). CE is hard-tied to GND on these boards so CP is the only lever.
//     Measured identical to the old CP-low timing on this silicon (see
//     firmware/read_audit), but the datasheet-correct order costs nothing.
//   - the gate re-runs every 5 s and prints CHAINnn: PASS/FAIL. Never trust a
//     frame without it: a dead chain reads 0xFFFF..FF, which is identical to
//     "all squares clear". That trap cost a whole session on 2026-08-22.
//
// WIRING (unchanged): ESP32 -> board 1 J1: 5V, 3V3, GND, P25(PL), P26(CP),
// P14(SER inject). Each J2 -> next J1, label to label. P27 <- last J2 SER.

const int PIN_PL = 25, PIN_CP = 26, PIN_SER_OUT = 27, PIN_SER_IN = 14;

const int FRAME_MS = 20;       // 50 fps
const int GATE_MS = 5000;      // re-gate every 5 s
const int CLK_US = 3;          // clock half period

int NBITS = 64;                // measured at boot
int NBOARDS = 4;

uint64_t chainMask() { return (NBITS >= 64) ? ~0ULL : ((1ULL << NBITS) - 1); }

inline void clk() {
  digitalWrite(PIN_CP, HIGH); delayMicroseconds(CLK_US);
  digitalWrite(PIN_CP, LOW);  delayMicroseconds(CLK_US);
}

uint64_t readFrame() {
  digitalWrite(PIN_SER_IN, LOW);
  digitalWrite(PIN_CP, LOW);
  digitalWrite(PIN_PL, LOW);              // load transparent
  delayMicroseconds(5);
  digitalWrite(PIN_CP, HIGH);             // rising edge lands inside the load
  delayMicroseconds(CLK_US);              // window, where it cannot shift
  digitalWrite(PIN_PL, HIGH);             // latch
  delayMicroseconds(CLK_US);
  digitalWrite(PIN_CP, LOW);              // falling edge: 165 shifts on rising
  delayMicroseconds(CLK_US);

  uint64_t v = 0;
  for (int i = 0; i < NBITS; i++) {
    v = (v << 1) | (digitalRead(PIN_SER_OUT) & 1);   // read BEFORE clocking
    clk();
  }
  return v;
}

uint64_t shiftTest(int level) {
  digitalWrite(PIN_PL, HIGH);
  digitalWrite(PIN_SER_IN, level);
  for (int i = 0; i < NBITS; i++) clk();
  uint64_t v = 0;
  for (int i = 0; i < NBITS; i++) { v = (v << 1) | (digitalRead(PIN_SER_OUT) & 1); clk(); }
  return v;
}

// inject a single 1 and count clocks until it appears: that count IS the
// number of register stages. Unlike the shift gate, this detects a chain
// that is too SHORT.
int chainLen(int halfUs) {
  digitalWrite(PIN_PL, HIGH);
  digitalWrite(PIN_SER_IN, LOW);
  for (int i = 0; i < 200; i++) {
    digitalWrite(PIN_CP, HIGH); delayMicroseconds(halfUs);
    digitalWrite(PIN_CP, LOW);  delayMicroseconds(halfUs);
  }
  digitalWrite(PIN_SER_IN, HIGH);
  digitalWrite(PIN_CP, HIGH); delayMicroseconds(halfUs);
  digitalWrite(PIN_CP, LOW);  delayMicroseconds(halfUs);
  digitalWrite(PIN_SER_IN, LOW);
  for (int n = 1; n <= 200; n++) {
    if (digitalRead(PIN_SER_OUT)) return n;
    digitalWrite(PIN_CP, HIGH); delayMicroseconds(halfUs);
    digitalWrite(PIN_CP, LOW);  delayMicroseconds(halfUs);
  }
  return -1;
}

void measureChain() {
  int a = chainLen(3), b = chainLen(200);
  if (a == b && a > 0 && a % 16 == 0 && a <= 64) {
    NBITS = a;
    NBOARDS = a / 16;
  }
  Serial.printf("STAGES: 3us=%d 200us=%d -> %d bits / %d boards%s\n",
                a, b, NBITS, NBOARDS,
                (a == b) ? "" : "   <-- VARYING, electrical noise");
}

void runGate() {
  uint64_t lo = shiftTest(LOW), hi = shiftTest(HIGH);
  bool ok = (lo == 0 && hi == chainMask());
  Serial.printf("CHAIN%d: %s\n", NBITS, ok ? "PASS" : "FAIL - squares below mean nothing");
}

void setup() {
  Serial.begin(115200); delay(400);
  pinMode(PIN_PL, OUTPUT); pinMode(PIN_CP, OUTPUT);
  pinMode(PIN_SER_IN, OUTPUT); pinMode(PIN_SER_OUT, INPUT);
  digitalWrite(PIN_PL, HIGH); digitalWrite(PIN_CP, LOW);
  Serial.println("\n\n=== board_stream ===");
  measureChain();
  runGate();
}

void loop() {
  static uint32_t lastGate = 0;
  uint32_t now = millis();
  if (now - lastGate >= GATE_MS) {
    lastGate = now;
    measureChain();
    runGate();
  }
  Serial.printf("raw = 0x%0*llX\n", NBITS / 4, readFrame());
  delay(FRAME_MS);
}
