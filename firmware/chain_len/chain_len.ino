// chain_len - measure the ACTUAL number of 74HC165 stages in the chain,
// at several clock speeds.
//
// Why this exists: the shift-only gate test in quadrant_diag* passes for any
// chain of N stages or FEWER, because it flushes with a level and then reads
// that same level back. A chain that is short by one chip still "PASSES", and
// the missing stages show up as whatever level P14 is injecting - which during
// parallelRead is LOW, i.e. a block of phantom "magnet present" squares at the
// END of the word. This sketch removes that ambiguity.
//
// Method: flush the whole chain with 0s, inject exactly ONE 1, then count the
// clocks until it appears at P27. That count IS the number of stages.
//   Expect 16 per board: 1 board = 16, 2 = 32, 3 = 48, 4 = 64.
//
// The speed sweep separates two failure modes:
//   - count stable across all speeds        -> structural (wiring/board)
//   - count changes as the clock slows down -> electrical (ringing, a floating
//     CLK-INH pin 15, missing decoupling) adding phantom clock edges
//
// Wiring is the same as quadrant_diag*: harness on the FIRST board's J1,
// P27 on the LAST board's J2 SER.

const int PIN_PL = 25, PIN_CP = 26, PIN_SER_OUT = 27, PIN_SER_IN = 14;
const int MAXSTAGES = 200;

// microseconds per half clock period
const int SPEEDS[] = {3, 20, 100, 500, 2000};
const int NSPEEDS = sizeof(SPEEDS) / sizeof(SPEEDS[0]);

int halfPeriod = 3;

void clockPulse() {
  digitalWrite(PIN_CP, HIGH); delayMicroseconds(halfPeriod);
  digitalWrite(PIN_CP, LOW);  delayMicroseconds(halfPeriod);
}

int measureStages() {
  digitalWrite(PIN_PL, HIGH);               // shift mode, never load
  digitalWrite(PIN_SER_IN, LOW);
  for (int i = 0; i < MAXSTAGES; i++) clockPulse();   // flush chain with 0s

  digitalWrite(PIN_SER_IN, HIGH);           // inject a single 1
  clockPulse();
  digitalWrite(PIN_SER_IN, LOW);

  for (int k = 0; k < MAXSTAGES; k++) {
    if (digitalRead(PIN_SER_OUT)) return k + 1;
    clockPulse();
  }
  return -1;                                 // never arrived
}

void setup() {
  Serial.begin(115200); delay(400);
  pinMode(PIN_PL, OUTPUT); pinMode(PIN_CP, OUTPUT);
  pinMode(PIN_SER_IN, OUTPUT); pinMode(PIN_SER_OUT, INPUT);
  digitalWrite(PIN_PL, HIGH); digitalWrite(PIN_CP, LOW);
  Serial.println("\n\n=== CHAIN LENGTH vs CLOCK SPEED ===\n");
}

void loop() {
  for (int s = 0; s < NSPEEDS; s++) {
    halfPeriod = SPEEDS[s];
    // three passes per speed - catches intermittent/noisy behaviour
    int a = measureStages(), b = measureStages(), c = measureStages();
    Serial.printf("half-period %5d us -> stages %3d %3d %3d", halfPeriod, a, b, c);
    if (a == b && b == c) {
      if (a % 16 == 0) Serial.printf("   (%d boards, clean)\n", a / 16);
      else             Serial.printf("   <-- not a whole board\n");
    } else {
      Serial.println("   <-- UNSTABLE (electrical noise)");
    }
  }
  Serial.println();
  delay(2000);
}
