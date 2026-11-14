// dgt3000.h - non-blocking DGT 3000 clock driver for a plain ESP32.
//
// Packet formats and command set ported from Tortue95/DGT3000-BLE-Gateway
// lib/DGT3000 (GPL-3.0), itself derived from jromang/dgtpi dgt3000.c.
//
// Bus setup (measured on the wire with a logic capture):
//   - The clock stretches SCL for ~240 us after it ACKs the last byte of a
//     packet. The ESP32 hardware master reports a bus error there, so the
//     master side is bit-banged on GPIO21/22 and ends every packet with a
//     real STOP once the stretch is over.
//   - With that STOP in place the clock replies with legal START/STOP at
//     400 kHz, so the slave side is the ESP32 hardware I2C slave (Wire1) on
//     GPIO18/19.
//   - Both pairs are tied to the same two wires. External pull-ups
//     (2 x 10k in parallel per line) are REQUIRED: without them the wires
//     crosstalk and every edge grows a ~200 ns glitch on the other line.
//
// Envelope sent:     [0x20 src, len, cmd, payload..., crc8]; len counts the
//                    whole packet incl. crc plus the address byte.
//                    CRC-8 poly 0x07, seeded with 0x10 (write addr of 0x08).
// Envelope received: [0x10, len, type, payload...]  (address byte stripped)
//                    type 1=ack 2=hello/ping-resp 4=time 5=button

#pragma once
#include <Arduino.h>
#include <Wire.h>

#define DGT_ADDR_CLOCK   0x08
#define DGT_ADDR_WAKE    0x28
#define DGT_ADDR_LISTEN  0x00   // broadcasts: time, buttons, some acks
#define DGT_ADDR_ACK     0x10   // acks for changeState / setCC

#define DGT_CMD_DISPLAY      0x06
#define DGT_CMD_END_DISPLAY  0x07
#define DGT_CMD_SET_AND_RUN  0x0a
#define DGT_CMD_CHANGE_STATE 0x0b
#define DGT_CMD_PING         0x0d
#define DGT_CMD_SET_CC       0x0f

// Button event codes (same as Tortue95 getButtonEvent()).
#define DGT_EV_BACK        0x01
#define DGT_EV_MINUS       0x02
#define DGT_EV_PLAY        0x04
#define DGT_EV_PLUS        0x08
#define DGT_EV_FWD         0x10
#define DGT_EV_ONOFF_PRESS 0x20
#define DGT_EV_ONOFF_REL   0xA0
#define DGT_EV_LEVER_RIGHT 0x40
#define DGT_EV_LEVER_LEFT  0xC0

// One raw packet from the slave, parsed later in loop().
struct DgtRxMsg {
  uint8_t len;
  uint8_t data[32];
};

class Dgt3000 {
public:
  bool begin(int mSda, int mScl, int sSda, int sScl);

  // Low-level send. ackCmd = 0 means fire-and-forget. ackAddr is kept for
  // API compatibility: the hardware slave sits on 0x00 and switches to 0x10
  // only while waiting for an ack.
  // Returns 0 ok, 1 bus busy, 2 NACK, 3 no ack message in time.
  // Worst case ~55 ms (5 ms bus wait + 50 ms ack wait).
  int send(const uint8_t *pkt, uint8_t len, uint8_t target,
           uint8_t ackAddr, uint8_t ackCmd);

  // Wake ping to 0x28. Non-blocking: poll pingSeen() afterwards.
  void sendWakePing();
  bool pingSeen();
  /** When true, every packet in and out logs `dbg ...` on Serial. */
  bool debug = false;

  // Packet builders (fill buf, return length).
  static uint8_t buildChangeState(uint8_t *buf);
  static uint8_t buildSetCC(uint8_t *buf);
  static uint8_t buildEndDisplay(uint8_t *buf);
  static uint8_t buildDisplay(uint8_t *buf, const char *text, uint8_t beep,
                              uint8_t leftDots, uint8_t rightDots);
  static uint8_t buildSetAndRun(uint8_t *buf, uint8_t lh, uint8_t lm, uint8_t ls,
                                uint8_t rh, uint8_t rm, uint8_t rs,
                                uint8_t lr, uint8_t rr);

  // Pops one non-ack message from the rx queue. Returns false if empty.
  bool popMessage(DgtRxMsg *out);
  uint32_t lastRxMs() const { return _lastRxMs; }

  // No-op kept for callers: the hardware slave sits on 0x00 and switches to
  // 0x10 only while waiting for an ack (handled inside send()).
  void listenOn(uint8_t) {}

private:
  static void crcFill(uint8_t *buf, uint8_t len);

  // ---- bit-banged master ----
  uint8_t swWrite(uint8_t addr, const uint8_t *data, uint8_t len);
  bool swWriteByte(uint8_t b);
  bool swWaitSclHigh();
  int _mSda = -1, _mScl = -1;

  // ---- hardware slave (Wire1) ----
  static Dgt3000 *sInst;
  static void onHwReceive(int n);
  void handleRx(const DgtRxMsg &m);
  int _sSda = -1, _sScl = -1;

  QueueHandle_t _q = nullptr;
  volatile bool _ackSeen = false;
  volatile uint8_t _ackCmd = 0;
  volatile bool _pingSeen = false;
  volatile uint32_t _lastRxMs = 0;
};
