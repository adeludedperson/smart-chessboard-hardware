// quadrant_diag3 - hold PL LOW (transparent load). SER_OUT then mirrors S15 live.
// No clocking involved at all - pure sensor test.
const int PIN_PL=25, PIN_CP=26, PIN_SER_OUT=27, PIN_SER_IN=14;
int last=-1; unsigned long changes=0;
void setup(){
  Serial.begin(115200); delay(400);
  pinMode(PIN_PL,OUTPUT); pinMode(PIN_CP,OUTPUT);
  pinMode(PIN_SER_IN,OUTPUT); pinMode(PIN_SER_OUT,INPUT);
  digitalWrite(PIN_PL,LOW);      // transparent: Q7 follows D7 = SENS_15
  digitalWrite(PIN_CP,LOW);
  digitalWrite(PIN_SER_IN,LOW);
  Serial.println("\n\n=== LIVE S15 SENSOR WATCH ===");
  Serial.println("PL held LOW -> output follows S15 directly, no clock needed.");
  Serial.println("Put the magnet on S15. Try BOTH faces of the magnet.\n");
}
void loop(){
  int v=digitalRead(PIN_SER_OUT);
  if(v!=last){ changes++; last=v;
    Serial.printf("S15 = %s      (changes so far: %lu)\n", v? "EMPTY (high)":"*** MAGNET *** (low)", changes); }
  delay(30);
}
