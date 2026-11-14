// dgt3000.cpp - see dgt3000.h.

#include "dgt3000.h"
#include <soc/gpio_reg.h>
#include <soc/i2c_struct.h>

// The hardware slave has one address. The clock sends acks to 0x10 and
// time/button broadcasts to 0x00, so we sit on 0x00 and switch to 0x10
// only while waiting for an ack.
static inline void hwSlaveAddr(uint8_t a) {
  I2C1.slave_addr.addr = a;
}

static const uint32_t ACK_TIMEOUT_MS = 50;      // Tortue95 DGT3000_ACK_TIMEOUT_MS
static const uint32_t STRETCH_TIMEOUT_US = 5000;
static const uint32_t HALF_US = 5;
static const uint32_t HOLD_US = 1;

// Direct register access: digitalRead/Write add ~1 us each.
static inline bool rd(int pin) { return (REG_READ(GPIO_IN_REG) >> pin) & 1; }
static inline void drvLow(int pin)  { REG_WRITE(GPIO_OUT_W1TC_REG, 1u << pin); }
static inline void drvHigh(int pin) { REG_WRITE(GPIO_OUT_W1TS_REG, 1u << pin); }

bool Dgt3000::begin(int mSda, int mScl, int sSda, int sScl) {
  _mSda = mSda; _mScl = mScl; _sSda = sSda; _sScl = sScl;
  if (!_q) _q = xQueueCreate(16, sizeof(DgtRxMsg));

  // Master pins: open-drain, released.
  pinMode(_mSda, OUTPUT_OPEN_DRAIN | PULLUP);
  pinMode(_mScl, OUTPUT_OPEN_DRAIN | PULLUP);
  drvHigh(_mSda); drvHigh(_mScl);
  // Hardware slave: the clock talks 400 kHz with legal START/STOP once we
  // end our packets with a real STOP.
  sInst = this;
  Wire1.onReceive(onHwReceive);
  if (!Wire1.begin((uint8_t)DGT_ADDR_LISTEN, _sSda, _sScl, 400000)) return false;
  return true;
}

Dgt3000 *Dgt3000::sInst = nullptr;
void Dgt3000::onHwReceive(int n) {
  DgtRxMsg m;
  m.len = 0;
  while (Wire1.available() && m.len < sizeof(m.data)) m.data[m.len++] = (uint8_t)Wire1.read();
  while (Wire1.available()) Wire1.read();
  if (sInst && m.len >= 3) sInst->handleRx(m);
}

// ---------------------------------------------------------------- master --

bool Dgt3000::swWaitSclHigh() {
  drvHigh(_mScl);
  uint32_t t0 = micros();
  while (!rd(_mScl)) {
    if (micros() - t0 > STRETCH_TIMEOUT_US) return false;
  }
  return true;
}

bool Dgt3000::swWriteByte(uint8_t b) {
  for (int i = 7; i >= 0; i--) {
    if (b & (1 << i)) drvHigh(_mSda); else drvLow(_mSda);
    delayMicroseconds(HALF_US);
    if (!swWaitSclHigh()) return false;
    delayMicroseconds(HALF_US);
    drvLow(_mScl);
    delayMicroseconds(HOLD_US);
  }
  drvHigh(_mSda);  // release for ACK
  delayMicroseconds(HALF_US);
  if (!swWaitSclHigh()) return false;
  delayMicroseconds(HALF_US);
  bool ack = !rd(_mSda);
  drvLow(_mScl);
  return ack;
}

// 0 ok, 1 bus busy, 2 NACK on address, 3 NACK on data, 5 stretch timeout
uint8_t Dgt3000::swWrite(uint8_t addr, const uint8_t *data, uint8_t len) {
  uint32_t t0 = micros();
  while (!rd(_mSda) || !rd(_mScl)) {
    if (micros() - t0 > STRETCH_TIMEOUT_US) return 1;
  }
  // START
  drvLow(_mSda);
  delayMicroseconds(HALF_US);
  drvLow(_mScl);
  delayMicroseconds(HALF_US);
  uint8_t rc = 0;
  if (!swWriteByte((uint8_t)(addr << 1))) {
    rc = 2;
  } else {
    for (uint8_t i = 0; i < len; i++) {
      if (!swWriteByte(data[i])) { rc = 3; break; }
    }
  }
  // STOP. The clock stretches SCL after the last ACK while it processes the
  // packet; it only replies after a real STOP (SDA rising while SCL high),
  // so hold SDA low until the stretch ends.
  drvLow(_mSda);
  delayMicroseconds(HALF_US);
  swWaitSclHigh();
  delayMicroseconds(HALF_US);
  drvHigh(_mSda);
  return rc;
}

int Dgt3000::send(const uint8_t *pkt, uint8_t len, uint8_t target,
                  uint8_t ackAddr, uint8_t ackCmd) {
  _ackSeen = false;
  _ackCmd = 0;
  // Config acks (setCC, changeState) come to 0x10; the display ack comes to
  // 0x00 like the broadcasts (seen on the wire 2026-09-27: waiting on 0x10
  // for it never succeeded, and it turned up on 0x00 after the reconnect).
  // So only leave 0x00 when the caller says the ack lives elsewhere.
  const bool switchAddr = ackCmd && ackAddr != DGT_ADDR_LISTEN;
  if (switchAddr) hwSlaveAddr(ackAddr);
  uint8_t r = swWrite(target, pkt, len);
  if (debug) {
    Serial.print("dbg tx 0x"); Serial.print(target, HEX); Serial.print(':');
    for (uint8_t i = 0; i < len; i++) { Serial.print(' '); Serial.print(pkt[i], HEX); }
    Serial.print(" rc="); Serial.println(r);
  }
  if (!ackCmd) return r == 0 ? 0 : (r == 1 ? 1 : 2);
  int rc = 3;
  if (r != 0) {
    rc = r == 1 ? 1 : 2;
  } else {
    uint32_t t0 = millis();
    while (millis() - t0 < ACK_TIMEOUT_MS) {
      if (_ackSeen && _ackCmd == ackCmd) { rc = 0; break; }
      delay(1);
    }
  }
  if (switchAddr) hwSlaveAddr(DGT_ADDR_LISTEN);
  return rc;
}

void Dgt3000::sendWakePing() {
  static const uint8_t ping[] = {0x20, 0x05, DGT_CMD_PING, 0x46};
  _pingSeen = false;
  hwSlaveAddr(DGT_ADDR_ACK);  // reply comes to 0x10; next acked send() restores 0x00
  uint8_t r = swWrite(DGT_ADDR_WAKE, ping, sizeof(ping));  // NACK is normal when asleep
  if (debug) { Serial.print("dbg wake ping rc="); Serial.println(r); }
}

bool Dgt3000::pingSeen() {
  if (!_pingSeen) return false;
  _pingSeen = false;
  return true;
}

// ----------------------------------------------------------------- slave --

// Runs in the Wire1 receive callback. Acks and ping replies are flagged
// here so a waiting send() sees them; everything else is queued for loop().
void Dgt3000::handleRx(const DgtRxMsg &m) {
  if (m.data[0] != 0x10) return;
  _lastRxMs = millis();
  if (debug) {
    Serial.print("dbg rx:");
    for (uint8_t i = 0; i < m.len; i++) { Serial.print(' '); Serial.print(m.data[i], HEX); }
    Serial.println();
  }
  switch (m.data[2]) {
    case 1:  // ack: 10 08 01 <cmd> <status> ...
      if (m.len >= 5) {
        _ackCmd = m.data[3];
        _ackSeen = true;
      }
      break;
    case 2: {  // wake/ping response: 10 07 02 22 01 05
      static const uint8_t exp[] = {0x10, 0x07, 0x02, 0x22, 0x01, 0x05};
      if (m.len >= sizeof(exp) && memcmp(m.data, exp, sizeof(exp)) == 0) _pingSeen = true;
      break;
    }
    default:
      if (_q) xQueueSend(_q, &m, 0);
      break;
  }
}

bool Dgt3000::popMessage(DgtRxMsg *out) {
  return _q && xQueueReceive(_q, out, 0) == pdTRUE;
}

// ------------------------------------------------------------- builders --

// CRC-8 poly 0x07, seeded with the 0x10 address byte. buf[len-1] gets the crc.
void Dgt3000::crcFill(uint8_t *buf, uint8_t len) {
  uint8_t c = 0;
  auto step = [&](uint8_t x) {
    c ^= x;
    for (int i = 0; i < 8; i++) c = (c & 0x80) ? (uint8_t)((c << 1) ^ 0x07) : (uint8_t)(c << 1);
  };
  step(0x10);
  for (uint8_t i = 0; i + 1 < len; i++) step(buf[i]);
  buf[len - 1] = c;
}

uint8_t Dgt3000::buildChangeState(uint8_t *b) {  // == {20 06 0b 39 b9}
  b[0] = 0x20; b[1] = 0x06; b[2] = DGT_CMD_CHANGE_STATE; b[3] = 0x39;
  crcFill(b, 5);
  return 5;
}

uint8_t Dgt3000::buildSetCC(uint8_t *b) {  // == {20 05 0f 48}
  b[0] = 0x20; b[1] = 0x05; b[2] = DGT_CMD_SET_CC;
  crcFill(b, 4);
  return 4;
}

uint8_t Dgt3000::buildEndDisplay(uint8_t *b) {  // == {20 05 07 70}
  b[0] = 0x20; b[1] = 0x05; b[2] = DGT_CMD_END_DISPLAY;
  crcFill(b, 4);
  return 4;
}

uint8_t Dgt3000::buildDisplay(uint8_t *b, const char *text, uint8_t beep,
                              uint8_t ld, uint8_t rd) {
  b[0] = 0x20; b[1] = 0x15; b[2] = DGT_CMD_DISPLAY;
  size_t n = strlen(text);
  for (int i = 0; i < 11; i++) b[3 + i] = (i < (int)n) ? (uint8_t)text[i] : 0x20;
  b[14] = 0xFF;
  b[15] = beep > 48 ? 48 : beep;
  b[16] = 0x03;
  b[17] = ld & 0x3F;  // flag, wking, bking, colon, dot, extra
  b[18] = rd & 0x1F;  // no "extra" on the right
  crcFill(b, 20);
  return 20;
}

static inline uint8_t toBcd(uint8_t v) { return (uint8_t)(((v / 10) << 4) | (v % 10)); }

uint8_t Dgt3000::buildSetAndRun(uint8_t *b, uint8_t lh, uint8_t lm, uint8_t ls,
                                uint8_t rh, uint8_t rm, uint8_t rs,
                                uint8_t lr, uint8_t rr) {
  b[0] = 0x20; b[1] = 0x0c; b[2] = DGT_CMD_SET_AND_RUN;
  b[3] = lh; b[4] = toBcd(lm); b[5] = toBcd(ls);
  b[6] = rh; b[7] = toBcd(rm); b[8] = toBcd(rs);
  b[9] = (uint8_t)(lr | (rr << 2));
  crcFill(b, 11);
  return 11;
}
