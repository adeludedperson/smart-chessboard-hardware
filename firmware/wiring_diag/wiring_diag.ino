// Wiring diagnostic: probes GPIO27 with internal pull-up vs pull-down
// to infer what's electrically connected.
const int PIN = 27;
const int LED = 2;

void setup() {
  Serial.begin(115200);
  pinMode(LED, OUTPUT);
}

void loop() {
  pinMode(PIN, INPUT_PULLUP);
  delay(20);
  int up = digitalRead(PIN);
  pinMode(PIN, INPUT_PULLDOWN);
  delay(20);
  int down = digitalRead(PIN);

  Serial.printf("pullup=%d pulldown=%d -> ", up, down);
  if (up == HIGH && down == LOW)  Serial.println("FLOATING or SENSOR-IDLE (can't distinguish; magnet test decides)");
  if (up == LOW  && down == LOW)  Serial.println("PIN HELD LOW: sensor active (magnet!) or OUT shorted to GND");
  if (up == HIGH && down == HIGH) Serial.println("PIN HELD HIGH: miswired - something drives 27 high");
  if (up == LOW  && down == HIGH) Serial.println("ERRATIC: loose contact");
  digitalWrite(LED, !digitalRead(LED)); // heartbeat blink
  delay(700);
}
