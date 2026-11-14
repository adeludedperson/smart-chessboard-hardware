// quadrant_diag2 - find which wire is not connected
const int PIN_PL=25, PIN_CP=26, PIN_SER_OUT=27, PIN_SER_IN=14;

void probe(const char* nm, int pin){
  pinMode(pin, INPUT_PULLDOWN); delay(30); int d = digitalRead(pin);
  pinMode(pin, INPUT_PULLUP);   delay(30); int u = digitalRead(pin);
  pinMode(pin, INPUT);          delay(30);
  Serial.printf("%-8s pulldown=%d pullup=%d  -> ", nm, d, u);
  if (d==1 && u==1)      Serial.println("HELD HIGH by the board  (wire OK, chip driving it)");
  else if (d==0 && u==0) Serial.println("HELD LOW by the board   (wire OK, tied to GND)");
  else                   Serial.println("FLOATING - this wire is NOT connected");
}
void setup(){
  Serial.begin(115200); delay(500);
  Serial.println("\n\n=== WIRE PROBE ===\n");
  pinMode(PIN_PL, INPUT); pinMode(PIN_CP, INPUT); pinMode(PIN_SER_IN, INPUT);
  delay(50);
  probe("SER_OUT", PIN_SER_OUT);   // GPIO27 <- J2 SER : should be HELD HIGH
  Serial.println("\n(PL/CP go to chip inputs which are high-impedance,");
  Serial.println(" so they read FLOATING even when correctly wired.)");
  probe("PL", PIN_PL);
  probe("CP", PIN_CP);
  probe("SER_IN", PIN_SER_IN);
  Serial.println("\nOnly SER_OUT is conclusive. If SER_OUT says FLOATING,");
  Serial.println("the GPIO27 <- J2 wire or the J2 solder joints are the problem.");
}
void loop(){ delay(1000); }
