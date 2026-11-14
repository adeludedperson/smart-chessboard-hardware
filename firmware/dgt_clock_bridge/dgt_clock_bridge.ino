// dgt_clock_bridge - DGT 3000 chess clock <-> host, line based.
//
// The app daemon (app/daemon) owns all clock logic (time control, increment,
// whose turn); the clock is a display + 7 buttons + lever. This sketch is the
// wire between them.
//
// TWO TRANSPORTS, ONE PROTOCOL
//   1. USB serial, 115200 raw. Always on.
//   2. Wi-Fi: the bridge dials INTO the daemon over TCP on SCB_CLOCK_PORT
//      (8796, see secrets.h). Bidirectional: host commands arrive on the
//      socket and go through the same handleLine() as serial.
//   Every protocol line goes to BOTH (emit()). Local chatter (wifi/link
//   up/down) is Serial-only and starts with '#' (note()), so no parser can
//   mistake it for a protocol line.
//
// Bridge -> host:
//   ready                                   once at boot
//   clock connected | clock disconnected    on state change
//   clk L=h:mm:ss R=h:mm:ss run=<lr>,<rr>   on change (max 4/s) + 1/s heartbeat
//   btn back|minus|play|plus|fwd|onoff|lever_left|lever_right
//   err <text>
//   pong                                    reply to ping
//   version dgt_clock_bridge <ver>          reply to version
//   hello dgt_clock_bridge <ver> <mac> <ip> Wi-Fi only, first line after every
//                                           TCP connect, followed by the current
//                                           clock connected|disconnected line and,
//                                           if connected, a clk line
//   pins ... / dbg ... / debug on|off       diagnostics
// Host -> bridge:
//   disp <text>[|<beep 0-48>]   up to 11 chars on the LCD
//   end                         back to clock display
//   set lh lm ls rh rm rs lr rr set times and run (0 stop, 1 down, 2 up)
//   ping -> pong                the daemon pings every 2 s on the socket
//   wake                        force a full reconnect now
//   version                     -> version line
//   debug                       toggle dbg hex packet logs (Serial only: they
//                               are printed inside dgt3000.cpp)
//
// WI-FI (ported from firmware/board_stream_wifi, read its header for the why)
//   - WiFi.setSleep(false): modem sleep adds 100 ms+ jitter per packet.
//   - mDNS + ArduinoOTA hostname chess-clock (-> chess-clock.local), no
//     password. Plain-text status page on :80.
//   - daemon resolution: mDNS SCB_HOST, SCB_HOST_ALT -> NVS "scbclk"/"hostip"
//     (last good) -> SCB_FALLBACK_IP. Reconnect with 1 s -> 5 s backoff.
//   - socket writes are raw non-blocking send(MSG_DONTWAIT): a full buffer
//     drops the line (counted), a PARTIAL write drops the link.
//   - nothing from the daemon for 10 s (it pings every 2 s) -> drop the link
//     and redial; catches half-open sockets.
//   - OTA, HTTP and connect work run on a 100 ms gate. The only long blocking
//     calls are the mDNS query (300 ms x2) and TCP connect (400 ms), and only
//     while the daemon link is down. OTA pauses the I2C loop entirely.
//   - Wi-Fi down >60 s after having been up once -> ESP.restart(). A bridge
//     that never joined (USB-only use, placeholder secrets) never reboots.
//   - LED GPIO2: fast blink = no Wi-Fi, slow blink = no daemon, solid = linked.
//
// run=<lr>,<rr> is what WE last told the clock (the time message carries no
// run flags we trust), so it is only as current as the last `set`.
//
// WIRING (3.5 mm jack on the clock, 3.3 V logic, no level shifter):
//   tip  (L) = SCL -> GPIO22 (bit-banged master) + GPIO19 (hardware I2C slave, Wire1)
//   ring (R) = SDA -> GPIO21 (bit-banged master) + GPIO18 (hardware I2C slave, Wire1)
//   sleeve   = GND
//
// Every step of loop() is bounded: the longest single I2C transaction is
// ~75 ms (address switch + 50 ms ack wait). Retries are spread over loops.

#include "dgt3000.h"

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
#warning "no secrets.h - building against secrets.example.h. cp secrets.example.h secrets.h and fill it in, or this bridge will never join Wi-Fi (USB still works)."
#endif

const int M_SDA = 21, M_SCL = 22;  // bit-banged master
const int S_SDA = 18, S_SCL = 19;  // hardware I2C slave (Wire1)

const uint32_t RECONNECT_MS = 2000;
const uint32_t CFG_GAP_MS = 25;       // Tortue95 DGT3000_COMMAND_DELAY_MS
const uint32_t RETRY_GAP_MS = 100;    // Tortue95 DGT3000_RETRY_DELAY_MS
const uint32_t PING_WAIT_MS = 100;    // Tortue95 waits 2 x ack timeout
const uint32_t SILENCE_MS = 3000;     // no clock traffic -> probe
const uint32_t CLK_MIN_GAP_MS = 250;  // max 4 clk lines/s
const uint32_t CLK_HEARTBEAT_MS = 1000;
const uint8_t MAX_TRIES = 3;

Dgt3000 dgt;

// ---- clock state ----
uint8_t tm[6] = {0};          // L h m s, R h m s (decimal)
uint8_t runL = 0, runR = 0;   // last run modes we sent
bool clkDirty = true;
uint32_t lastClkPrint = 0;

// ---- connection state machine ----
enum ConnState { C_IDLE, C_PING_WAIT, C_SETCC, C_CS, C_SNR, C_UP };
ConnState conn = C_IDLE;
bool connected = false;
uint32_t nextStepAt = 0;
uint8_t tries = 0;
uint32_t pingDeadline = 0;
uint32_t connectedAt = 0;

// ---- host input: one line accumulator per transport ----
// (Types used in function signatures must be declared before the first
// function: the Arduino builder inserts auto-prototypes there.)
struct LineBuf {
  char buf[96];
  int len;
  bool overflow;
};
LineBuf serialIn = {{0}, 0, false};
LineBuf sockIn = {{0}, 0, false};

// ---- outgoing command queue (only drained while connected) ----
struct OutCmd {
  uint8_t pkt[20];
  uint8_t len;
  uint8_t ackAddr;
  uint8_t ackCmd;  // 0 = no ack expected
};
const int QN = 8;
OutCmd outq[QN];
int qHead = 0, qTail = 0;
uint8_t qTries = 0;
bool probing = false;

bool qEmpty() { return qHead == qTail; }
void qClear() { qHead = qTail = 0; qTries = 0; probing = false; }
bool qPush(const OutCmd &c) {
  int nx = (qTail + 1) % QN;
  if (nx == qHead) return false;
  outq[qTail] = c;
  qTail = nx;
  return true;
}

void lineReset(LineBuf &lb) { lb.len = 0; lb.overflow = false; }

// ---- network (Wi-Fi link to the daemon) ----

static const char *FW_VERSION = "1.1.0";
static const char *OTA_NAME   = "chess-clock";    // -> chess-clock.local

static const int PIN_LED = 2;                     // onboard, active HIGH

static const uint32_t HOUSEKEEP_MS     = 100;     // OTA + HTTP + connect gate
static const uint32_t WIFI_DEAD_MS     = 60000;   // Wi-Fi down this long -> reboot
static const uint32_t BACKOFF_MIN_MS   = 1000;
static const uint32_t BACKOFF_MAX_MS   = 5000;
static const uint32_t RESOLVE_RETRY_MS = 3000;    // host not found -> try again
static const uint32_t MDNS_QUERY_MS    = 300;
static const uint32_t TCP_CONNECT_MS   = 400;
static const uint32_t TCP_IO_MS        = 200;
static const uint32_t RX_IDLE_MS       = 10000;   // daemon pings every 2 s

WiFiClient client;
WebServer server(80);
Preferences prefs;

static volatile bool otaActive = false;   // set in ArduinoOTA.onStart
static bool servicesUp = false;
static bool otaUp = false;
static bool wifiEverUp = false;           // gates the 60 s reboot

static uint32_t wifiDownSince = 0;        // 0 = Wi-Fi is up
static uint32_t nextAttempt = 0;
static uint32_t backoffMs = BACKOFF_MIN_MS;
static uint32_t lastRxAt = 0;             // last byte from the daemon

static IPAddress daemonIP;
static uint32_t linesSent = 0;
static uint32_t linesDropped = 0;
static uint32_t reconnects = 0;
static uint32_t wifiDrops = 0;
static char lastClkLine[48] = "(none)";

static void dropLink(const char *why);

static bool linkUp() { return !otaActive && client.fd() >= 0 && client.connected(); }

// Write one already-formatted line to the daemon. Never blocks: a full send
// buffer drops the line, a partial write kills the link (half a line would
// corrupt the framing of the next one).
static bool netWriteLine(const char *buf, int n) {
  if (otaActive) return false;
  int fd = client.fd();
  if (fd < 0) return false;
  int res = ::send(fd, buf, (size_t)n, MSG_DONTWAIT);
  if (res == n) { linesSent++; return true; }
  if (res < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
    linesDropped++;
    return false;
  }
  dropLink("write");
  return false;
}

// Every protocol line goes through here: Serial first (USB keeps working with
// a dead network), then the daemon socket. fmt must end in \n.
static bool emit(const char *fmt, ...) {
  char buf[160];
  va_list ap;
  va_start(ap, fmt);
  int n = vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  if (n <= 0) return false;
  if (n > (int)sizeof(buf) - 1) { n = (int)sizeof(buf) - 1; buf[n - 1] = '\n'; }
  Serial.write((const uint8_t *)buf, (size_t)n);
  return netWriteLine(buf, n);
}

// Local-only chatter, Serial only, '#'-prefixed so no parser takes it for a
// protocol line.
static void note(const char *fmt, ...) {
  char buf[160];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  Serial.printf("# %s\n", buf);
}

// ------------------------------------------------------------------

void printClk() {
  snprintf(lastClkLine, sizeof(lastClkLine), "clk L=%u:%02u:%02u R=%u:%02u:%02u run=%u,%u",
           tm[0], tm[1], tm[2], tm[3], tm[4], tm[5], runL, runR);
  emit("%s\n", lastClkLine);
  lastClkPrint = millis();
  clkDirty = false;
}

void setConnected(bool up) {
  if (up == connected) return;
  connected = up;
  emit(up ? "clock connected\n" : "clock disconnected\n");
  if (up) clkDirty = true;
}

void connFail() {
  if (dgt.debug) emit("dbg connect failed at step %d\n", (int)conn);
  qClear();
  setConnected(false);
  conn = C_IDLE;
  tries = 0;
  nextStepAt = millis() + RECONNECT_MS;
}

void gotoStep(ConnState s, uint32_t gap) {
  conn = s;
  tries = 0;
  nextStepAt = millis() + gap;
}

// One acked config command attempt; up to MAX_TRIES spread across loops.
void cfgAcked(uint8_t *pkt, uint8_t len, uint8_t ackCmd, ConnState next) {
  if (dgt.send(pkt, len, DGT_ADDR_CLOCK, DGT_ADDR_ACK, ackCmd) == 0) {
    gotoStep(next, CFG_GAP_MS);
  } else if (++tries >= MAX_TRIES) {
    connFail();
  } else {
    nextStepAt = millis() + RETRY_GAP_MS;
  }
}

// Mirrors Tortue95 DGT3000::configure(), one step per loop() pass.
void connStep() {
  if (conn == C_UP || (int32_t)(millis() - nextStepAt) < 0) return;
  uint8_t b[20], n;
  switch (conn) {
    case C_IDLE:  // step 1: change state, no ack; NACK => clock off, try wake
      n = Dgt3000::buildChangeState(b);
      if (dgt.send(b, n, DGT_ADDR_CLOCK, DGT_ADDR_LISTEN, 0) == 0) {
        gotoStep(C_SETCC, CFG_GAP_MS);
      } else {
        dgt.sendWakePing();
        pingDeadline = millis() + PING_WAIT_MS;
        conn = C_PING_WAIT;
      }
      break;
    case C_PING_WAIT:
      if (dgt.pingSeen()) {
        n = Dgt3000::buildChangeState(b);
        if (dgt.send(b, n, DGT_ADDR_CLOCK, DGT_ADDR_LISTEN, 0) == 0) gotoStep(C_SETCC, CFG_GAP_MS);
        else connFail();
      } else if ((int32_t)(millis() - pingDeadline) >= 0) {
        connFail();  // clock off / unplugged: quiet retry in 2 s
      }
      break;
    case C_SETCC:  // step 2: take central control (ack on 0x10)
      n = Dgt3000::buildSetCC(b);
      cfgAcked(b, n, DGT_CMD_SET_CC, C_CS);
      break;
    case C_CS:  // step 3: change state again, acked
      n = Dgt3000::buildChangeState(b);
      cfgAcked(b, n, DGT_CMD_CHANGE_STATE, C_SNR);
      break;
    case C_SNR:  // step 4: restore last known time (Tortue95 sends 0:00:00)
      n = Dgt3000::buildSetAndRun(b, tm[0], tm[1], tm[2], tm[3], tm[4], tm[5], runL, runR);
      if (dgt.send(b, n, DGT_ADDR_CLOCK, DGT_ADDR_LISTEN, 0) == 0) {
        conn = C_UP;
        connectedAt = millis();
        qClear();
        setConnected(true);
      } else if (++tries >= MAX_TRIES) {
        connFail();
      } else {
        nextStepAt = millis() + RETRY_GAP_MS;
      }
      break;
    default:
      break;
  }
}

// Drain one attempt of the head command. Tortue95 semantics: 3 tries, then
// the clock is considered gone.
void queueStep() {
  if (conn != C_UP || qEmpty() || (int32_t)(millis() - nextStepAt) < 0) return;
  OutCmd &c = outq[qHead];
  int rc = dgt.send(c.pkt, c.len, DGT_ADDR_CLOCK, c.ackAddr, c.ackCmd);
  if (rc == 0) {
    qHead = (qHead + 1) % QN;
    qTries = 0;
    if (qEmpty()) probing = false;
    return;
  }
  if (++qTries >= MAX_TRIES) {
    if (!probing) emit(rc == 1 ? "err clock not answering\n" : "err clock did not ack\n");
    connFail();
  } else {
    nextStepAt = millis() + RETRY_GAP_MS;
  }
}

// If the clock goes silent, confirm it is still there with an acked
// Set Central Control (harmless when we already hold control).
void silenceWatch() {
  if (conn != C_UP || probing || !qEmpty()) return;
  uint32_t last = dgt.lastRxMs();
  if ((int32_t)(connectedAt - last) > 0) last = connectedAt;
  if (millis() - last < SILENCE_MS) return;
  OutCmd c;
  c.len = Dgt3000::buildSetCC(c.pkt);
  c.ackAddr = DGT_ADDR_ACK;
  c.ackCmd = DGT_CMD_SET_CC;
  if (qPush(c)) probing = true;
}

// ---- clock messages ----

static uint8_t bcd2dec(uint8_t b) { return (uint8_t)((b >> 4) * 10 + (b & 0x0F)); }

// Byte 16 of the time broadcast is 0x19 while we hold central control and
// 0x00 after the clock was switched off/on (back in its own mode, showing
// dashes). Two in a row => rerun the connect sequence; the last known times
// are restored by step 4. Observed on the wire; not documented anywhere.
uint8_t nativeSeen = 0;
void forceReconnect() {
  setConnected(false);
  qClear();
  probing = false;
  conn = C_IDLE;
  tries = 0;
  nextStepAt = millis();
}

void handleTime(const DgtRxMsg &m) {
  if (conn == C_UP && m.len > 16 && m.data[1] == 0x18) {
    if (m.data[16] == 0x00) {
      if (++nativeSeen >= 2) { nativeSeen = 0; forceReconnect(); }
      return;  // its own times, not the game's
    }
    nativeSeen = 0;
  }
  // Offsets are dgtpi rm[] minus 1 (the ESP32 slave strips the address byte).
  if (m.len > 19 && m.data[19] == 1) return;  // "no update" echo (Tortue95)
  if (m.len < 14 || m.data[1] != 0x18) return;
  uint8_t t[6] = {
    (uint8_t)(m.data[4] & 0x0F), bcd2dec(m.data[5]), bcd2dec(m.data[6]),
    (uint8_t)(m.data[10] & 0x0F), bcd2dec(m.data[11]), bcd2dec(m.data[12])};
  if (t[0] > 9 || t[1] > 59 || t[2] > 59 || t[3] > 9 || t[4] > 59 || t[5] > 59) return;
  if (memcmp(t, tm, 6) != 0) {
    memcpy(tm, t, 6);
    clkDirty = true;
  }
}

void emitButtons(uint8_t ev) {
  if (ev == DGT_EV_ONOFF_PRESS) { emit("btn onoff\n"); return; }
  if (ev == DGT_EV_ONOFF_REL) return;
  if (ev == DGT_EV_LEVER_LEFT) { emit("btn lever_left\n"); return; }
  if (ev == DGT_EV_LEVER_RIGHT) { emit("btn lever_right\n"); return; }
  if (ev & DGT_EV_BACK) emit("btn back\n");
  if (ev & DGT_EV_MINUS) emit("btn minus\n");
  if (ev & DGT_EV_PLAY) emit("btn play\n");
  if (ev & DGT_EV_PLUS) emit("btn plus\n");
  if (ev & DGT_EV_FWD) emit("btn fwd\n");
}

// Tortue95 processButtonMessage(): [10 len 05 current previous ...]
void handleButton(const DgtRxMsg &m) {
  if (m.len < 5) return;
  uint8_t cur = m.data[3], prev = m.data[4];
  uint8_t chg = cur ^ prev;
  if (!chg) return;
  if (chg & 0x20) emitButtons((cur & 0x20) ? DGT_EV_ONOFF_PRESS : DGT_EV_ONOFF_REL);
  else if (chg & 0x40) emitButtons((cur & 0x40) ? DGT_EV_LEVER_LEFT : DGT_EV_LEVER_RIGHT);
  else if (chg & cur & 0x1F) emitButtons(chg & cur & 0x1F);
}

void drainClock() {
  DgtRxMsg m;
  for (int i = 0; i < 8 && dgt.popMessage(&m); i++) {
    if (m.data[2] == 4) handleTime(m);
    else if (m.data[2] == 5) handleButton(m);
  }
}

// ---- host commands ----

bool parseU8(const char *&p, uint8_t &out) {
  while (*p == ' ') p++;
  if (*p < '0' || *p > '9') return false;
  int v = 0;
  while (*p >= '0' && *p <= '9') { v = v * 10 + (*p - '0'); if (v > 255) return false; p++; }
  out = (uint8_t)v;
  return true;
}

bool needClock() {
  if (conn == C_UP) return true;
  emit("err clock not connected\n");
  return false;
}

void pushOrErr(const OutCmd &c) {
  if (!qPush(c)) emit("err busy\n");
}

void handleLine(char *s) {
  while (*s == ' ') s++;
  int n = strlen(s);
  while (n > 0 && (s[n - 1] == ' ' || s[n - 1] == '\r')) s[--n] = 0;
  if (n == 0) return;

  if (strcmp(s, "ping") == 0) { emit("pong\n"); return; }
  if (strcmp(s, "version") == 0) { emit("version dgt_clock_bridge %s\n", FW_VERSION); return; }
  if (strcmp(s, "debug") == 0) { dgt.debug = !dgt.debug; emit(dgt.debug ? "debug on\n" : "debug off\n"); return; }

  if (strcmp(s, "wake") == 0) {
    forceReconnect();
    return;
  }

  if (strcmp(s, "end") == 0) {
    if (!needClock()) return;
    OutCmd c;
    c.len = Dgt3000::buildEndDisplay(c.pkt);
    c.ackAddr = DGT_ADDR_LISTEN; c.ackCmd = 0;  // Tortue95: end display unacked
    pushOrErr(c);
    return;
  }

  if (strncmp(s, "disp", 4) == 0 && (s[4] == ' ' || s[4] == 0)) {
    if (!needClock()) return;
    char *text = s[4] ? s + 5 : s + 4;
    uint8_t beep = 0;
    char *bar = strrchr(text, '|');
    if (bar) {
      const char *p = bar + 1;
      if (!parseU8(p, beep) || *p != 0 || beep > 48) { emit("err beep must be 0-48\n"); return; }
      *bar = 0;
    }
    char t[12];
    strncpy(t, text, 11);
    t[11] = 0;
    OutCmd e, d;
    e.len = Dgt3000::buildEndDisplay(e.pkt);
    e.ackAddr = DGT_ADDR_LISTEN; e.ackCmd = 0;
    d.len = Dgt3000::buildDisplay(d.pkt, t, beep, 0, 0);
    d.ackAddr = DGT_ADDR_LISTEN; d.ackCmd = DGT_CMD_DISPLAY;  // Tortue95 listens on 0x00
    int freeSlots = (qHead - qTail - 1 + QN) % QN;
    if (freeSlots < 2) { emit("err busy\n"); return; }
    qPush(e);
    qPush(d);
    return;
  }

  if (strncmp(s, "set ", 4) == 0) {
    const char *p = s + 4;
    uint8_t v[8];
    for (int i = 0; i < 8; i++) {
      if (!parseU8(p, v[i])) { emit("err usage: set lh lm ls rh rm rs lr rr\n"); return; }
    }
    while (*p == ' ') p++;
    if (*p) { emit("err usage: set lh lm ls rh rm rs lr rr\n"); return; }
    if (v[0] > 9 || v[3] > 9 || v[1] > 59 || v[2] > 59 || v[4] > 59 || v[5] > 59 || v[6] > 2 || v[7] > 2) {
      emit("err set out of range (h 0-9, m/s 0-59, run 0-2)\n");
      return;
    }
    if (!needClock()) return;
    OutCmd c;
    c.len = Dgt3000::buildSetAndRun(c.pkt, v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7]);
    c.ackAddr = DGT_ADDR_LISTEN; c.ackCmd = 0;  // Tortue95: set-and-run unacked
    if (!qPush(c)) { emit("err busy\n"); return; }
    memcpy(tm, v, 6);
    runL = v[6];
    runR = v[7];
    clkDirty = true;
    return;
  }

  emit("err unknown command: %s\n", s);
}

// Feed one byte into a transport's line accumulator; a complete line goes to
// handleLine(), whichever transport it came from.
void feedByte(LineBuf &lb, char ch) {
  if (ch == '\n') {
    lb.buf[lb.len] = 0;
    if (lb.overflow) emit("err line too long\n");
    else handleLine(lb.buf);
    lineReset(lb);
  } else if (lb.len < (int)sizeof(lb.buf) - 1) {
    lb.buf[lb.len++] = ch;
  } else {
    lb.overflow = true;
  }
}

void readSerial() {
  int budget = 128;
  while (Serial.available() && budget-- > 0) feedByte(serialIn, (char)Serial.read());
}

// Bytes from the daemon. Raw non-blocking recv() on the fd (NetworkClient's
// connected() does not notice an orderly close; recv() == 0 does). Budget:
// 128 bytes per loop, same as readSerial().
void readSocket() {
  if (otaActive) return;
  int fd = client.fd();
  if (fd < 0) return;
  char buf[64];
  for (int round = 0; round < 2; round++) {
    int n = ::recv(fd, buf, sizeof(buf), MSG_DONTWAIT);
    if (n == 0) { dropLink("closed by daemon"); return; }
    if (n < 0) {
      if (errno == EAGAIN || errno == EWOULDBLOCK || errno == ENOENT) return;
      dropLink("read");
      return;
    }
    lastRxAt = millis();
    for (int i = 0; i < n; i++) {
      feedByte(sockIn, buf[i]);
      if (client.fd() != fd) return;  // a reply write dropped the link
    }
  }
}

// ---- Wi-Fi / daemon link ----

static void dropLink(const char *why) {
  if (client.fd() >= 0) {
    client.stop();
    note("daemon link dropped (%s)", why);
  }
  lineReset(sockIn);
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

// mDNS (both names, see secrets.example.h) -> last good IP in NVS ->
// SCB_FALLBACK_IP (first boot only, in practice).
static bool resolveDaemon(IPAddress &out) {
  IPAddress ip = MDNS.queryHost(stripLocal(SCB_HOST), MDNS_QUERY_MS);
  if ((uint32_t)ip != 0) { out = ip; return true; }
#ifdef SCB_HOST_ALT
  ip = MDNS.queryHost(stripLocal(SCB_HOST_ALT), MDNS_QUERY_MS);
  if ((uint32_t)ip != 0) { out = ip; return true; }
#endif
  uint32_t saved = prefs.getUInt("hostip", 0);
  if (saved) { out = IPAddress(saved); return true; }
#ifdef SCB_FALLBACK_IP
  {
    IPAddress fb;
    if (fb.fromString(SCB_FALLBACK_IP)) { out = fb; return true; }
  }
#endif
  return false;
}

static void connectDaemon() {
  IPAddress ip;
  uint32_t now = millis();
  if (!resolveDaemon(ip)) {
    note("cannot resolve %s (no mDNS answer, no saved IP)", SCB_HOST);
    nextAttempt = now + RESOLVE_RETRY_MS;
    return;
  }
  if (!client.connect(ip, SCB_CLOCK_PORT, TCP_CONNECT_MS)) {
    client.stop();
    backoffMs = (backoffMs * 2 > BACKOFF_MAX_MS) ? BACKOFF_MAX_MS : backoffMs * 2;
    nextAttempt = millis() + backoffMs;
    note("connect %s:%d failed, retry in %lu ms",
         ip.toString().c_str(), (int)SCB_CLOCK_PORT, (unsigned long)backoffMs);
    return;
  }
  client.setNoDelay(true);            // button events must not wait for Nagle
  client.setConnectionTimeout(TCP_IO_MS);
  daemonIP = ip;
  reconnects++;
  backoffMs = BACKOFF_MIN_MS;
  lastRxAt = millis();
  lineReset(sockIn);
  if (prefs.getUInt("hostip", 0) != (uint32_t)ip) prefs.putUInt("hostip", (uint32_t)ip);

  // Greeting, socket only (Serial already knows all this): who we are, then
  // the current clock state, then a clk line on the next loop if connected.
  char hello[128];
  int n = snprintf(hello, sizeof(hello), "hello dgt_clock_bridge %s %s %s\n",
                   FW_VERSION, WiFi.macAddress().c_str(),
                   WiFi.localIP().toString().c_str());
  netWriteLine(hello, n);
  const char *st = connected ? "clock connected\n" : "clock disconnected\n";
  netWriteLine(st, strlen(st));
  if (connected) {
    clkDirty = true;
    lastClkPrint = millis() - CLK_HEARTBEAT_MS;   // printClk fires next loop
  }
  note("daemon link up: %s:%d", ip.toString().c_str(), (int)SCB_CLOCK_PORT);
}

static void handleRoot() {
  uint32_t up = millis() / 1000;
  char body[900];
  snprintf(body, sizeof(body),
           "dgt_clock_bridge %s\n"
           "uptime      %lud %02lu:%02lu:%02lu\n"
           "wifi        %s  rssi %d dBm  ip %s\n"
           "mac         %s\n"
           "daemon      %s  %s:%d\n"
           "clock       %s\n"
           "last clk    %s\n"
           "lines       %lu sent, %lu dropped\n"
           "reconnects  %lu tcp, %lu wifi\n"
           "heap        %lu bytes free\n"
           "ota         %s\n",
           FW_VERSION,
           (unsigned long)(up / 86400), (unsigned long)((up / 3600) % 24),
           (unsigned long)((up / 60) % 60), (unsigned long)(up % 60),
           WIFI_SSID, (int)WiFi.RSSI(), WiFi.localIP().toString().c_str(),
           WiFi.macAddress().c_str(),
           linkUp() ? "connected" : "down",
           ((uint32_t)daemonIP != 0) ? daemonIP.toString().c_str() : "(unresolved)",
           (int)SCB_CLOCK_PORT,
           connected ? "connected" : "disconnected",
           lastClkLine,
           (unsigned long)linesSent, (unsigned long)linesDropped,
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
    ArduinoOTA.setHostname(OTA_NAME);   // no password, same as board_stream_wifi
    ArduinoOTA.onStart([]() {
      otaActive = true;                 // pauses the I2C loop and TCP writes
      client.stop();
      digitalWrite(PIN_LED, HIGH);
      Serial.println("# OTA start - clock loop paused");
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

// Fast blink = no Wi-Fi. Slow blink = Wi-Fi but no daemon. Solid = linked.
static void ledTick() {
  uint32_t period;
  if (WiFi.status() != WL_CONNECTED) period = 100;
  else if (!linkUp())                period = 500;
  else { digitalWrite(PIN_LED, HIGH); return; }
  digitalWrite(PIN_LED, ((millis() / period) & 1) ? HIGH : LOW);
}

// Everything network, on the 100 ms gate. Worst case: two mDNS queries plus
// one TCP connect, and only while the daemon link is already down.
static void serviceNet() {
  uint32_t now = millis();

  if (WiFi.status() != WL_CONNECTED) {
    if (wifiDownSince == 0) { wifiDownSince = now; wifiDrops++; note("wifi down"); }
    if (client.fd() >= 0) dropLink("wifi down");
    servicesUp = false;
    // A wedged Wi-Fi stack is not debuggable from outside. Only after it has
    // worked once, so USB-only use without Wi-Fi never reboot-loops.
    if (wifiEverUp && now - wifiDownSince > WIFI_DEAD_MS) {
      Serial.println("# wifi dead 60s - restarting");
      Serial.flush();
      ESP.restart();
    }
    return;
  }

  if (wifiDownSince != 0) {
    wifiDownSince = 0;
    wifiEverUp = true;
    WiFi.setSleep(false);        // re-assert after every (re)association
    note("wifi up: %s rssi %d", WiFi.localIP().toString().c_str(), (int)WiFi.RSSI());
  }
  if (!servicesUp) startServices();

  if (client.fd() >= 0) {
    if (!client.connected()) dropLink("lost");
    else if (now - lastRxAt > RX_IDLE_MS) dropLink("idle 10s");
    return;
  }

  if ((int32_t)(now - nextAttempt) < 0) return;
  connectDaemon();
}

// ------------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  delay(50);
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, LOW);
  // Line check before I2C init: with nothing driving, every pin must read 1.
  {
    const int pins[] = {M_SDA, M_SCL, S_SDA, S_SCL};
    for (int i = 0; i < 4; i++) pinMode(pins[i], INPUT_PULLUP);
    delay(5);
    emit("pins sda21=%d scl22=%d sda18=%d scl19=%d\n",
         digitalRead(M_SDA), digitalRead(M_SCL), digitalRead(S_SDA), digitalRead(S_SCL));
  }
  if (!dgt.begin(M_SDA, M_SCL, S_SDA, S_SCL)) emit("err i2c init failed\n");
  emit("ready\n");
  nextStepAt = millis() + 200;

  // Wi-Fi joins in the background: no boot-time wait, the clock connects
  // right away and serviceNet() picks the association up when it lands.
  prefs.begin("scbclk", false);
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);          // see board_stream_wifi trap 1. Not optional.
  WiFi.setAutoReconnect(true);
  WiFi.setHostname(OTA_NAME);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  wifiDownSince = millis();      // "down since boot", not counted as a drop
}

void loop() {
  static uint32_t lastHouse = 0;

  // OTA owns the CPU while it runs: I2C and TCP are paused (onStart).
  if (otaActive) { ArduinoOTA.handle(); return; }

  readSerial();
  readSocket();
  drainClock();
  connStep();
  queueStep();
  silenceWatch();

  if (connected) {
    uint32_t since = millis() - lastClkPrint;
    if ((clkDirty && since >= CLK_MIN_GAP_MS) || since >= CLK_HEARTBEAT_MS) printClk();
  }

  uint32_t now = millis();
  if (now - lastHouse >= HOUSEKEEP_MS) {
    lastHouse = now;
    ArduinoOTA.handle();
    server.handleClient();
    serviceNet();
    ledTick();
  }
  delay(1);
}
