// secrets.example.h - template. Copy to secrets.h and fill it in:
//
//     cp secrets.example.h secrets.h
//
// secrets.h is gitignored. This file is NOT: never put a real password here.
// If secrets.h is missing the sketch still compiles (against this file) and
// warns, so a fresh clone builds before it can connect to anything.

#pragma once

#define WIFI_SSID "YOUR_WIFI_NAME"       // 2.4 GHz only - the ESP32 has no 5 GHz radio
#define WIFI_PASS "YOUR_WIFI_PASSWORD"

#define SCB_HOST "YOUR_HOST_NAME.local"  // mDNS name of the computer that receives the board stream
#define SCB_PORT 8789                    // that computer's raw-line TCP listener

// Optional second mDNS name to try if SCB_HOST does not answer, for example
// the name the host had before you renamed it. Leave commented out if unused.
// #define SCB_HOST_ALT "YOUR_OTHER_HOST_NAME.local"

// Bootstrap only. Used if mDNS gives no answer AND the chip has no saved
// address yet - i.e. the first boot after flashing. One successful connect
// caches the real address in NVS and this is never consulted again.
// Set it to the host's IPv4 address on your network.
#define SCB_FALLBACK_IP "YOUR_HOST_IP"
