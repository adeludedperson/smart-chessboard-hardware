// rail_test - are the 5V and 3V3 rails shorted together on the board?
// Connect ONLY 3 wires:  GND -> J1 pin3,  VIN/5V -> J1 pin1,  GPIO27 <- J2 pin6
// Leave the 3V3 wire OFF.
// If the chips still power up, they can only be getting it from 5V => rails shorted.
const int PIN_SER_OUT=27;
void setup(){ Serial.begin(115200); delay(500);
  Serial.println("\n\n=== RAIL SHORT TEST ===");
  Serial.println("Wires: GND, 5V, and GPIO27<-J2 SER only. NO 3V3 wire.\n");
}
void loop(){
  pinMode(PIN_SER_OUT, INPUT_PULLDOWN); delay(50); int d=digitalRead(PIN_SER_OUT);
  pinMode(PIN_SER_OUT, INPUT_PULLUP);   delay(50); int u=digitalRead(PIN_SER_OUT);
  if(d==1 && u==1)
    Serial.println("SER_OUT HELD HIGH -> chips are powered with NO 3V3 wire.");
  else if(d==0 && u==1)
    Serial.println("SER_OUT floating -> chips have no power. Rails are separate (good).");
  else
    Serial.println("SER_OUT held LOW -> unexpected, check GND wire.");
  delay(700);
}
