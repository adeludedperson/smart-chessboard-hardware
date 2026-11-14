// read_audit - is the "random stuck square" a firmware timing bug or a sensor?
//
// Tests four read variants back to back against the SAME physical board state.
// If they disagree, the problem is in how we clock the 74HC165, not the solder.
//
//   A  CP LOW  across the PL rise, 3us clock    <- what quadrant_diag64 does today
//   B  CP HIGH across the PL rise, 3us clock    <- what the NXP datasheet asks for
//   C  CP HIGH across the PL rise, 200us clock  <- slow: rules out signal integrity
//   D  CP HIGH, 200us clock, 500us load window  <- slow + long settle
//
// Each variant is read 8x. Two masks are reported per variant:
//   unstable = bits that changed between the 8 reads   -> electrical noise
//   vs A     = bits where this variant disagrees with A -> timing bug in A
//
// A bit that is rock-stable in every variant but differs BETWEEN variants is a
// firmware bug. A bit that is unstable within a variant is electrical. A bit
// identical everywhere and wrong is a genuinely dead sensor.

// NBITS is MEASURED at boot, not configured. Unplug a board, hit reset, and
// the tool re-sizes itself. Never edit a constant to match the wiring again.
int NBITS = 64;
int NUM_BOARDS = 4;
const int REPEATS = 8;

const int PIN_PL = 25, PIN_CP = 26, PIN_SER_OUT = 27, PIN_SER_IN = 14;

uint64_t chainMask() { return (NBITS >= 64) ? ~0ULL : ((1ULL << NBITS) - 1); }

// ---------------------------------------------------------------- read core

// cpHighAtLoad: hold CP HIGH across the PL LOW->HIGH edge (datasheet-correct).
// halfUs: clock half period. loadUs: how long PL is held LOW.
uint64_t readFrame(bool cpHighAtLoad, int halfUs, int loadUs) {
  digitalWrite(PIN_SER_IN, LOW);
  digitalWrite(PIN_CP, LOW);
  delayMicroseconds(halfUs);

  digitalWrite(PIN_PL, LOW);              // parallel load is transparent here
  delayMicroseconds(loadUs);

  if (cpHighAtLoad) {
    digitalWrite(PIN_CP, HIGH);           // rising edge lands INSIDE the load
    delayMicroseconds(halfUs);            // window, where it cannot shift
  }
  digitalWrite(PIN_PL, HIGH);             // latch
  delayMicroseconds(halfUs);
  if (cpHighAtLoad) {
    digitalWrite(PIN_CP, LOW);            // falling edge: 165 shifts on rising
    delayMicroseconds(halfUs);
  }

  uint64_t v = 0;
  for (int i = 0; i < NBITS; i++) {
    v = (v << 1) | (digitalRead(PIN_SER_OUT) & 1);   // read BEFORE clocking
    digitalWrite(PIN_CP, HIGH); delayMicroseconds(halfUs);
    digitalWrite(PIN_CP, LOW);  delayMicroseconds(halfUs);
  }
  return v;
}

// ---------------------------------------------------------------- gate test

uint64_t shiftTest(int level) {
  digitalWrite(PIN_PL, HIGH);
  digitalWrite(PIN_SER_IN, level);
  for (int i = 0; i < NBITS; i++) {
    digitalWrite(PIN_CP, HIGH); delayMicroseconds(3);
    digitalWrite(PIN_CP, LOW);  delayMicroseconds(3);
  }
  uint64_t v = 0;
  for (int i = 0; i < NBITS; i++) {
    v = (v << 1) | (digitalRead(PIN_SER_OUT) & 1);
    digitalWrite(PIN_CP, HIGH); delayMicroseconds(3);
    digitalWrite(PIN_CP, LOW);  delayMicroseconds(3);
  }
  return v;
}

bool gate() {
  uint64_t lo = shiftTest(LOW), hi = shiftTest(HIGH);
  bool ok = (lo == 0 && hi == chainMask());
  Serial.printf("GATE: %s   0s->0x%016llX  1s->0x%016llX\n",
                ok ? "PASS" : "FAIL", lo, hi);
  return ok;
}

// measure ACTUAL stage count: inject a single 1, count clocks until it lands
int chainLen(int halfUs) {
  digitalWrite(PIN_PL, HIGH);
  digitalWrite(PIN_SER_IN, LOW);
  for (int i = 0; i < 200; i++) {                   // flush with zeros
    digitalWrite(PIN_CP, HIGH); delayMicroseconds(halfUs);
    digitalWrite(PIN_CP, LOW);  delayMicroseconds(halfUs);
  }
  digitalWrite(PIN_SER_IN, HIGH);                   // one 1 in
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

// ---------------------------------------------------------------- reporting

struct Variant { const char *name; bool cpHigh; int halfUs; int loadUs; };
Variant VAR[] = {
  {"A  CP-low  @3us   load 5us  (current firmware)", false, 3,   5},
  {"B  CP-high @3us   load 5us  (datasheet)",        true,  3,   5},
  {"C  CP-high @200us load 5us  (slow clock)",       true,  200, 5},
  {"D  CP-high @200us load 500us(slow + settle)",    true,  200, 500},
};
const int NVAR = sizeof(VAR) / sizeof(VAR[0]);

void printBits(const char *label, uint64_t m) {
  if (!m) return;
  Serial.printf("      %s:", label);
  for (int i = 0; i < NBITS; i++)
    if ((m >> (NBITS - 1 - i)) & 1) Serial.printf(" b%d", i);
  Serial.println();
}

// re-measure the chain and resize. returns false if the chain is unusable.
bool autosize() {
  int a = chainLen(3), b = chainLen(20), c = chainLen(200);
  bool agree = (a == b && b == c && a > 0);
  if (agree && a % 16 == 0 && a <= 64) {
    NBITS = a;
    NUM_BOARDS = a / 16;
  }
  Serial.printf("STAGES: 3us=%d 20us=%d 200us=%d -> %s", a, b, c,
                agree ? "stable" : "VARYING (electrical noise)");
  if (agree && a % 16) Serial.printf("  <-- NOT a multiple of 16, partial board");
  Serial.printf("   using %d bits / %d boards\n", NBITS, NUM_BOARDS);
  return agree;
}

void setup() {
  Serial.begin(115200); delay(400);
  pinMode(PIN_PL, OUTPUT); pinMode(PIN_CP, OUTPUT);
  pinMode(PIN_SER_IN, OUTPUT); pinMode(PIN_SER_OUT, INPUT);
  digitalWrite(PIN_PL, HIGH); digitalWrite(PIN_CP, LOW);
  Serial.println("\n\n=== READ AUDIT - chain length is measured, not configured ===");
}

void loop() {
  Serial.println("\n---------------------------------------------------------");
  autosize();
  gate();

  uint64_t modal[NVAR];
  for (int v = 0; v < NVAR; v++) {
    uint64_t first = readFrame(VAR[v].cpHigh, VAR[v].halfUs, VAR[v].loadUs);
    uint64_t unstable = 0;
    for (int r = 1; r < REPEATS; r++)
      unstable |= first ^ readFrame(VAR[v].cpHigh, VAR[v].halfUs, VAR[v].loadUs);
    modal[v] = first;
    Serial.printf("  %-46s 0x%016llX  unstable=0x%016llX %s\n",
                  VAR[v].name, first, unstable,
                  unstable ? "<-- ELECTRICAL" : "stable");
    printBits("unstable bits", unstable);
  }

  Serial.println("  --- variant disagreement (stable but different = FIRMWARE BUG) ---");
  for (int v = 1; v < NVAR; v++) {
    uint64_t d = modal[0] ^ modal[v];
    Serial.printf("    A vs %c : 0x%016llX %s\n", VAR[v].name[0], d,
                  d ? "<-- READ TIMING CHANGES THE ANSWER" : "identical");
    printBits("differing bits", d);
  }

  // is A's frame simply B's frame shifted by one? that is the phantom clock.
  uint64_t a = modal[0], b = modal[1];
  bool leftShift  = ((b << 1) & chainMask()) == (a & chainMask() & ~1ULL);
  bool rightShift = (b >> 1) == (a >> 1 & (chainMask() >> 1));
  if (a != b)
    Serial.printf("    off-by-one check: A==B<<1 %s | A==B>>1 %s\n",
                  leftShift ? "YES <-- PHANTOM CLOCK ON PL RISE" : "no",
                  rightShift ? "YES" : "no");

  delay(1500);
}
