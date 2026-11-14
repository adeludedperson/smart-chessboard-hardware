// quadrant_test - read one 16-square quadrant board via 2x 74HC165
//
// WIRING (6 jumper wires):
//   ESP32 VIN/5V  -> J1 pin 1  (5V)    powers the A3144 sensors
//   ESP32 3V3     -> J1 pin 2  (3V3)   powers the pull-ups + shift registers
//   ESP32 GND     -> J1 pin 3  (GND)
//   ESP32 GPIO25  -> J1 pin 4  (PL)
//   ESP32 GPIO26  -> J1 pin 5  (CP)
//   ESP32 GPIO27  <- J2 pin 6  (SER)   <-- data comes OUT of J2, not J1
//
// J1 pin order printed on the silkscreen: 5V 3V3 GND PL CP SER
//
// Sensor logic: A3144 output is open-collector.
//   magnet present -> output pulled LOW  -> bit 0 -> shown as [X]
//   empty square   -> 10k pull-up HIGH   -> bit 1 -> shown as [ ]

const int PIN_PL  = 25;   // parallel load, active LOW
const int PIN_CP  = 26;   // clock
const int PIN_SER = 27;   // serial data in, from J2

// Order the 16 bits arrive in, first bit -> last.
// Chain is J1.SER -> U1.DS, U1.Q7' -> U2.DS, U2.Q7 -> J2.SER
// so U2 shifts out first, D7 first. Extracted from chess_quadrant.kicad_pcb.
const uint8_t CHAIN_ORDER[16] = {
  15, 14, 11, 10,  2,  3,  6,  7,
  13, 12,  9,  8,  0,  1,  4,  5
};

bool square[16];          // true = piece detected
uint16_t rawBits = 0;

void readQuadrant() {
  // latch all 16 sensor states at once
  digitalWrite(PIN_PL, LOW);
  delayMicroseconds(5);
  digitalWrite(PIN_PL, HIGH);
  delayMicroseconds(5);

  rawBits = 0;
  for (int i = 0; i < 16; i++) {
    int bit = digitalRead(PIN_SER);
    rawBits = (rawBits << 1) | (bit & 1);
    square[CHAIN_ORDER[i]] = (bit == 0);   // LOW = magnet = occupied

    digitalWrite(PIN_CP, HIGH);
    delayMicroseconds(2);
    digitalWrite(PIN_CP, LOW);
    delayMicroseconds(2);
  }
}

void setup() {
  Serial.begin(115200);
  delay(400);

  pinMode(PIN_PL, OUTPUT);
  pinMode(PIN_CP, OUTPUT);
  pinMode(PIN_SER, INPUT);

  digitalWrite(PIN_PL, HIGH);
  digitalWrite(PIN_CP, LOW);

  Serial.println();
  Serial.println("=== QUADRANT TEST ===");
  Serial.println("Board as you look at the TOP (component) side,");
  Serial.println("with J1 on your left and the title text at the bottom.");
  Serial.println();
  Serial.println("[X] = magnet detected     [ ] = empty");
  Serial.println("If ALL squares read [X] with no magnet -> check GND / 3V3 wiring.");
  Serial.println("If NO square ever reads [X] -> check 5V, or the magnet pole.");
  Serial.println();
}

void loop() {
  readQuadrant();

  Serial.println("      c0    c1    c2    c3");
  for (int r = 0; r < 4; r++) {
    Serial.printf("r%d  ", r);
    for (int c = 0; c < 4; c++) {
      int i = r * 4 + c;
      Serial.print(square[i] ? " [X] " : " [ ] ");
    }
    Serial.printf("   S%-2d..S%-2d\n", r * 4, r * 4 + 3);
  }

  int count = 0;
  for (int i = 0; i < 16; i++) if (square[i]) count++;

  Serial.printf("\nraw = 0x%04X   detected = %d square(s)\n", rawBits, count);
  Serial.println("--------------------------------------------");

  delay(300);
}
