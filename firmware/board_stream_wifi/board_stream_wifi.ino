// board_stream_wifi - board_stream, over the air.
//
// Same sensing code as firmware/board_stream, byte-for-byte: same pins, same
// CP/PL edge order, same 20 ms frame period, same chain measurement, same
// gate. It prints the same three lines it always did -
//
//     raw = 0xFFFFFFFFFFFFFFFF
//     CHAIN64: PASS
//     STAGES: 3us=64 200us=64 -> 64 bits / 4 boards
//
// - except each line now goes to BOTH the USB serial port and a TCP socket to
// the daemon. USB debugging and firmware/tools/board_state.py keep working
// with no cable-swap dance; the app gets the same stream with no cable at all.
//
// WHAT IS NEW, AND WHY
//   - emit() replaces Serial.printf. One formatted line, written to Serial and
//     to the daemon socket. The text is identical - the daemon's parser is
//     /raw = 0x([0-9A-Fa-f]{4,16})/ and board_state.py's is nearly the same, so
//     "identical" is not a nicety, it is the contract. Do not reformat these.
//   - WiFi STA + a TCP client to SCB_HOST:SCB_PORT (see secrets.h).
//   - mDNS responder: the ESP32 answers to chess-sensor.local.
//   - ArduinoOTA (hostname chess-sensor, no password): future flashes need no
//     cable. The board lives inside a sealed chessboard; plan accordingly.
//   - a plain-text status page on :80. Uptime, RSSI, link state, last gate,
//     frames sent, reconnects, free heap. The no-cable debug surface.
//
// TWO TRAPS, BOTH PAID FOR IN LOST HOURS
//   1. WiFi.setSleep(false). The ESP32 defaults to modem sleep, which parks the
//      radio between DTIM beacons and adds 100 ms+ of jitter to every packet.
//      packages/core debounces a move over 80 ms; with modem sleep on, frames
//      arrive in bursts and a lift/place pair lands inside one debounce window,
//      i.e. moves silently vanish. The sketch reads as if it works. It does not.
//      setSleep(false) costs ~40 mA and is not optional here.
//   2. Housekeeping budget. ArduinoOTA.handle() + server.handleClient() every
//      loop iteration is enough to shred the 50 fps cadence, because a single
//      HTTP client or an OTA probe can sit inside handle() for tens of ms. They
//      run on a 100 ms millis() gate instead, so at most one frame in five pays
//      for them. FRAME_MS stays 20. Everything on the network side is written
//      to fit inside ~50 ms per loop:
//        - the socket write is a raw non-blocking send() on client.fd(), NOT
//          client.write(). NetworkClient::write() retries a 1 s select up to 10
//          times, so a wedged daemon could stall the sensor loop for ten
//          seconds. A line that will not fit is dropped and counted; a PARTIAL
//          write kills the link, because half a line is worse than no line.
//        - the one deliberate exception is MDNS.queryHost() at 300 ms, and it
//          only runs while the daemon link is already down (no frames to
//          deliver anyway), spaced by the reconnect backoff.
//
// FAILURE BEHAVIOUR
//   - WiFi drops: setAutoReconnect keeps trying. Down for >60 s -> ESP.restart(),
//     because a wedged WiFi stack is a real and un-debuggable state and the
//     board is behind a glued-down panel.
//   - daemon drops: reconnect with 1 s -> 5 s backoff. Host resolution is mDNS
//     first, then the last-known-good IP from NVS (Preferences "scb"/"hostip",
//     rewritten after every successful connect) so a host that is up but
//     not answering mDNS yet still gets found. Neither works -> retry in 3 s.
//   - the daemon sends PING\n every 2 s; we read and discard everything it
//     sends so the RX buffer never fills and back-pressures the link.
//   - LED (GPIO2): fast blink = no WiFi. Slow blink = WiFi but no daemon.
//     Solid = streaming. Readable through the board's LED window.
//
// The banner line is the only intentional text change vs board_stream, and
// nothing parses it.
//
// WIRING (unchanged): ESP32 -> board 1 J1: 5V, 3V3, GND, P25(PL), P26(CP),
// P14(SER inject). Each J2 -> next J1, label to label. P27 <- last J2 SER.

#include <WiFi.h>
#include <ESPmDNS.h>
#include <ArduinoOTA.h>
#include <WebServer.h>
#include <Preferences.h>
#include <lwip/sockets.h>
#include <stdarg.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#warning "no secrets.h - building against secrets.example.h. cp secrets.example.h secrets.h and fill it in, or this firmware will never associate."
#endif

// ---------------------------------------------------------------- sensing --
// Verbatim from firmware/board_stream. Do not retune. The CP/PL edge order and
// the 3 us clock are the result of firmware/read_audit, not taste.

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

// ------------------------------------------------------------------- net ---

static const char *FW_VERSION = "1.0.0";
static const char *OTA_NAME   = "chess-sensor";   // -> chess-sensor.local

static const int PIN_LED = 2;                     // onboard, active HIGH

static const uint32_t HOUSEKEEP_MS   = 100;       // OTA + HTTP budget gate
static const uint32_t WIFI_JOIN_MS   = 15000;     // boot-time association wait
static const uint32_t WIFI_DEAD_MS   = 60000;     // WiFi down this long -> reboot
static const uint32_t BACKOFF_MIN_MS = 1000;
static const uint32_t BACKOFF_MAX_MS = 5000;
static const uint32_t RESOLVE_RETRY_MS = 3000;    // host not found -> try again
static const uint32_t MDNS_QUERY_MS  = 300;       // capped: see trap 2 above
static const uint32_t TCP_CONNECT_MS = 400;
static const uint32_t TCP_IO_MS      = 200;       // bound on any residual read

WiFiClient client;
WebServer server(80);
Preferences prefs;

static volatile bool otaActive = false;   // set in ArduinoOTA.onStart
static bool servicesUp = false;
static bool otaUp = false;

static uint32_t wifiDownSince = 0;        // 0 = WiFi is up
static uint32_t nextAttempt = 0;
static uint32_t backoffMs = BACKOFF_MIN_MS;

static IPAddress daemonIP;
static uint32_t framesSent = 0;
static uint32_t linesDropped = 0;
static uint32_t reconnects = 0;
static uint32_t wifiDrops = 0;
static char lastGateResult[40] = "(pending)";
static char lastStages[24] = "(pending)";

static void dropLink(const char *why);

// Write one already-formatted line to the daemon. Non-blocking by construction:
// see trap 2. Returns true only if the whole line went out.
static bool netWriteLine(const char *buf, int n) {
  if (otaActive || !client.connected()) return false;
  int fd = client.fd();
  if (fd < 0) return false;
  int res = ::send(fd, buf, (size_t)n, MSG_DONTWAIT);
  if (res == n) return true;
  if (res < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
    linesDropped++;                 // daemon is not draining; skip this frame
    return false;
  }
  // partial write or a real error: the line framing is gone. Half a frame is
  // worse than a missing one, so tear the socket down and resync on reconnect.
  dropLink("write");
  return false;
}

// The only printer in this sketch. Serial first (so USB debugging survives a
// dead network), then the daemon. Returns true if the daemon got it.
static bool emit(const char *fmt, ...) {
  char buf[160];
  va_list ap;
  va_start(ap, fmt);
  int n = vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  if (n <= 0) return false;
  if (n > (int)sizeof(buf) - 1) n = (int)sizeof(buf) - 1;
  Serial.write((const uint8_t *)buf, (size_t)n);
  return netWriteLine(buf, n);
}

// Local-only chatter. Prefixed with '#' so it can never be mistaken for a
// frame or a gate line by any of the parsers.
static void note(const char *fmt, ...) {
  char buf[160];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  Serial.printf("# %s\n", buf);
}

void measureChain() {
  int a = chainLen(3), b = chainLen(200);
  if (a == b && a > 0 && a % 16 == 0 && a <= 64) {
    NBITS = a;
    NBOARDS = a / 16;
  }
  emit("STAGES: 3us=%d 200us=%d -> %d bits / %d boards%s\n",
       a, b, NBITS, NBOARDS,
       (a == b) ? "" : "   <-- VARYING, electrical noise");
  snprintf(lastStages, sizeof(lastStages), "%d bits / %d boards", NBITS, NBOARDS);
}

void runGate() {
  uint64_t lo = shiftTest(LOW), hi = shiftTest(HIGH);
  bool ok = (lo == 0 && hi == chainMask());
  emit("CHAIN%d: %s\n", NBITS, ok ? "PASS" : "FAIL - squares below mean nothing");
  snprintf(lastGateResult, sizeof(lastGateResult), "CHAIN%d %s", NBITS, ok ? "PASS" : "FAIL");
}

static void dropLink(const char *why) {
  if (client.connected() || client.fd() >= 0) {
    client.stop();
    note("daemon link dropped (%s)", why);
  }
  backoffMs = BACKOFF_MIN_MS;
  nextAttempt = millis() + backoffMs;
}

// SCB_HOST is "chessboard.local"; queryHost() wants the label without .local
static const char *stripLocal(const char *name) {
  static char label[64];
  strncpy(label, name, sizeof(label) - 1);
  label[sizeof(label) - 1] = 0;
  char *dot = strstr(label, ".local");
  if (dot) *dot = 0;
  return label;
}

static bool resolveDaemon(IPAddress &out) {
  // (a) mDNS. Authoritative and survives a DHCP lease change on the host,
  //     which is the whole reason we prefer it over a hardcoded address.
  //
  //     Two names are tried because a Mac's Bonjour name is whatever
  //     `scutil --set LocalHostName` last said, and this board has to work on
  //     both sides of that rename: SCB_HOST is the name we want and
  //     SCB_HOST_ALT (optional) is the name the host had before the rename.
  //     Whichever answers first wins. Without this, flashing before the rename and renaming
  //     after the flash each strand the board on the fallback address.
  IPAddress ip = MDNS.queryHost(stripLocal(SCB_HOST), MDNS_QUERY_MS);
  if ((uint32_t)ip != 0) { out = ip; return true; }
#ifdef SCB_HOST_ALT
  ip = MDNS.queryHost(stripLocal(SCB_HOST_ALT), MDNS_QUERY_MS);
  if ((uint32_t)ip != 0) { out = ip; return true; }
#endif
  // (b) last-known-good from NVS. Covers "mini is up, Bonjour is not yet".
  uint32_t saved = prefs.getUInt("hostip", 0);
  if (saved) { out = IPAddress(saved); return true; }
  // (c) the literal address from secrets.h. Only ever matters on the very
  //     first boot of a fresh chip: NVS is empty, so without this the board
  //     cannot start at all if mDNS is slow or the host's Bonjour name
  //     has not been set to SCB_HOST yet. After one successful connect (b)
  //     takes over and this line never runs again.
#ifdef SCB_FALLBACK_IP
  {
    IPAddress fb;
    if (fb.fromString(SCB_FALLBACK_IP)) { out = fb; return true; }
  }
#endif
  return false;   // (d) caller retries in RESOLVE_RETRY_MS
}

static void connectDaemon() {
  IPAddress ip;
  uint32_t now = millis();
  if (!resolveDaemon(ip)) {
    note("cannot resolve %s (no mDNS answer, no saved IP)", SCB_HOST);
    nextAttempt = now + RESOLVE_RETRY_MS;
    return;
  }
  if (!client.connect(ip, SCB_PORT, TCP_CONNECT_MS)) {
    client.stop();
    backoffMs = (backoffMs * 2 > BACKOFF_MAX_MS) ? BACKOFF_MAX_MS : backoffMs * 2;
    nextAttempt = millis() + backoffMs;
    note("connect %s:%d failed, retry in %lu ms",
         ip.toString().c_str(), (int)SCB_PORT, (unsigned long)backoffMs);
    return;
  }
  client.setNoDelay(true);            // Nagle would batch frames: 40 ms of lie
  client.setConnectionTimeout(TCP_IO_MS);
  daemonIP = ip;
  reconnects++;
  backoffMs = BACKOFF_MIN_MS;
  if (prefs.getUInt("hostip", 0) != (uint32_t)ip) prefs.putUInt("hostip", (uint32_t)ip);

  char hello[128];
  int n = snprintf(hello, sizeof(hello), "HELLO board_stream_wifi %s %s %s\n",
                   FW_VERSION, WiFi.macAddress().c_str(),
                   WiFi.localIP().toString().c_str());
  netWriteLine(hello, n);             // daemon's raw-line regex ignores this
  note("daemon link up: %s:%d", ip.toString().c_str(), (int)SCB_PORT);
}

static void handleRoot() {
  uint32_t up = millis() / 1000;
  char body[900];
  snprintf(body, sizeof(body),
           "board_stream_wifi %s\n"
           "uptime      %lud %02lu:%02lu:%02lu\n"
           "wifi        %s  rssi %d dBm  ip %s\n"
           "mac         %s\n"
           "daemon      %s  %s:%d\n"
           "gate        %s\n"
           "stages      %s\n"
           "frames      %lu sent, %lu dropped\n"
           "reconnects  %lu tcp, %lu wifi\n"
           "heap        %lu bytes free\n"
           "ota         %s\n",
           FW_VERSION,
           (unsigned long)(up / 86400), (unsigned long)((up / 3600) % 24),
           (unsigned long)((up / 60) % 60), (unsigned long)(up % 60),
           WIFI_SSID, (int)WiFi.RSSI(), WiFi.localIP().toString().c_str(),
           WiFi.macAddress().c_str(),
           client.connected() ? "streaming" : "down",
           ((uint32_t)daemonIP != 0) ? daemonIP.toString().c_str() : "(unresolved)",
           (int)SCB_PORT,
           lastGateResult, lastStages,
           (unsigned long)framesSent, (unsigned long)linesDropped,
           (unsigned long)reconnects, (unsigned long)wifiDrops,
           (unsigned long)ESP.getFreeHeap(),
           otaActive ? "IN PROGRESS" : "idle");
  server.send(200, "text/plain", body);
}

static void startServices() {
  MDNS.end();
  if (MDNS.begin(OTA_NAME)) {
    MDNS.addService("http", "tcp", 80);
    note("mdns: %s.local", OTA_NAME);
  }
  if (!otaUp) {
    ArduinoOTA.setHostname(OTA_NAME);   // no password: this is a LAN toy, and a
                                        // forgotten password means a glued-shut
                                        // board that can never be reflashed
    ArduinoOTA.onStart([]() {
      otaActive = true;                 // pauses the sensor loop and TCP writes
      client.stop();
      digitalWrite(PIN_LED, HIGH);
      Serial.println("# OTA start - sensor loop paused");
    });
    ArduinoOTA.onEnd([]() { Serial.println("# OTA done, rebooting"); });
    ArduinoOTA.onError([](ota_error_t e) {
      otaActive = false;
      Serial.printf("# OTA error %u\n", (unsigned)e);
    });
    ArduinoOTA.begin();
    server.on("/", handleRoot);
    server.onNotFound(handleRoot);
    server.begin();
    otaUp = true;
  }
  servicesUp = true;
  note("http://%s/ and http://%s.local/", WiFi.localIP().toString().c_str(), OTA_NAME);
}

// Fast blink = no WiFi. Slow blink = WiFi but no daemon. Solid = streaming.
static void ledTick() {
  uint32_t period;
  if (WiFi.status() != WL_CONNECTED)      period = 100;
  else if (!client.connected())           period = 500;
  else { digitalWrite(PIN_LED, HIGH); return; }
  digitalWrite(PIN_LED, ((millis() / period) & 1) ? HIGH : LOW);
}

// Everything network, on the 100 ms budget. Worst case here is one mDNS query
// (MDNS_QUERY_MS) plus one TCP connect (TCP_CONNECT_MS), and only while the
// daemon link is already down.
static void serviceNet() {
  uint32_t now = millis();

  if (WiFi.status() != WL_CONNECTED) {
    if (wifiDownSince == 0) { wifiDownSince = now; wifiDrops++; note("wifi down"); }
    if (client.connected()) client.stop();
    servicesUp = false;
    if (now - wifiDownSince > WIFI_DEAD_MS) {
      // 60 s of nothing. A wedged WiFi stack is not debuggable from inside a
      // sealed board; a reboot costs one second of frames.
      Serial.println("# wifi dead 60s - restarting");
      Serial.flush();
      ESP.restart();
    }
    return;
  }

  if (wifiDownSince != 0) {
    wifiDownSince = 0;
    WiFi.setSleep(false);        // re-assert after every (re)association
    note("wifi up: %s rssi %d", WiFi.localIP().toString().c_str(), (int)WiFi.RSSI());
  }
  if (!servicesUp) startServices();

  if (client.connected()) {
    uint8_t junk[64];            // the daemon PINGs every 2 s: drain or the RX
    while (client.available() > 0) {   // buffer fills and stalls the link
      int n = client.read(junk, sizeof(junk));
      if (n <= 0) break;
    }
    return;
  }

  if (client.fd() >= 0) client.stop();          // half-open socket: release fd
  if ((int32_t)(now - nextAttempt) < 0) return;
  connectDaemon();
}

// ------------------------------------------------------------------ main ---

void setup() {
  Serial.begin(115200); delay(400);
  pinMode(PIN_PL, OUTPUT); pinMode(PIN_CP, OUTPUT);
  pinMode(PIN_SER_IN, OUTPUT); pinMode(PIN_SER_OUT, INPUT);
  pinMode(PIN_LED, OUTPUT); digitalWrite(PIN_LED, LOW);
  digitalWrite(PIN_PL, HIGH); digitalWrite(PIN_CP, LOW);
  Serial.println("\n\n=== board_stream_wifi ===");

  // sensors first: a board with no network is still a board with a gate result
  measureChain();
  runGate();

  prefs.begin("scb", false);

  WiFi.persistent(false);        // stop rewriting NVS on every begin()
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);          // TRAP 1. See the header. Not optional.
  WiFi.setAutoReconnect(true);
  WiFi.setHostname(OTA_NAME);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < WIFI_JOIN_MS) {
    ledTick();
    delay(10);
  }
  if (WiFi.status() == WL_CONNECTED) {
    WiFi.setSleep(false);
    note("wifi up: %s rssi %d", WiFi.localIP().toString().c_str(), (int)WiFi.RSSI());
    startServices();
  } else {
    wifiDownSince = millis();
    note("wifi join timed out - streaming to serial only, retrying in loop");
  }
}

void loop() {
  static uint32_t lastGate = 0;
  static uint32_t lastHouse = 0;

  // OTA owns the CPU while it runs: sensing and TCP are paused (onStart), and
  // handle() gets every iteration so the flash finishes in seconds not minutes.
  if (otaActive) { ArduinoOTA.handle(); return; }

  uint32_t now = millis();

  // TRAP 2: housekeeping on a 100 ms gate, never every frame.
  if (now - lastHouse >= HOUSEKEEP_MS) {
    lastHouse = now;
    ArduinoOTA.handle();
    server.handleClient();
    serviceNet();
    ledTick();
    if (otaActive) return;
    now = millis();
  }

  if (now - lastGate >= GATE_MS) {
    lastGate = now;
    measureChain();
    runGate();
  }
  if (emit("raw = 0x%0*llX\n", NBITS / 4, readFrame())) framesSent++;
  delay(FRAME_MS);
}
