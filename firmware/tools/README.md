# Serial tools

These use raw `termios` instead of `pyserial`, so they need no dependencies.

```bash
python3 firmware/tools/read_serial.py 8          # read 8s, no reset
python3 firmware/tools/read_serial_reset.py 8    # pulse RTS to reset first, then read
python3 firmware/tools/magnet_sweep.py 60        # record 60s, print which squares responded
python3 firmware/tools/clock_talk.py 5 debug "disp HI"  # send lines to dgt_clock_bridge (no reset), print 5s of output
```

`clock_talk.py` prints only when it exits, so long runs show nothing until the end.

Port is hardcoded to `/dev/cu.usbserial-0001` (macOS). Edit the port near the
top of each script for your machine.

Flash with:
```bash
export PATH=/opt/homebrew/bin:$PATH
cd firmware
arduino-cli compile --fqbn esp32:esp32:esp32 quadrant_test
arduino-cli upload -p /dev/cu.usbserial-0001 --fqbn esp32:esp32:esp32 quadrant_test
```
