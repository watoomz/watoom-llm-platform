## 🛠️ Troubleshooting & FAQ

A quick reference for the most common issues reported by the community. If your problem isn't listed here, please [open an issue](https://github.com/cifertech/ESP32-DIV/issues).

---
### 📡 Wi-Fi

**Q: Wi-Fi Scanner shows no networks or crashes on v1.53+**
> This is a known issue related to the NVS partition becoming full after repeated scans. Flash the latest pre-compiled binary from the `Pre-compiled Bin/` folder, or perform a full chip erase before re-flashing: `esptool.py erase_flash`. Then re-flash the firmware.

**Q: Deauth attack has no effect on the target network**
> Make sure you are within close range of the target AP and client. Some modern routers (802.11w / PMF enabled) are immune to deauthentication frames by design. The attack will not work on those.

**Q: Beacon Spammer SSIDs are not visible on nearby devices**
> Reduce the number of SSIDs in your spam list. Broadcasting too many simultaneously can cause the ESP32-S3 watchdog to trigger a reset.

---

### ⌨️ Keyboard / Input

**Q: The on-screen keyboard is unresponsive or registers wrong characters**
> This is usually a touchscreen calibration issue. Go to **Device & System → Touch Calibrate** and run the four-corner calibration routine. Save the result and restart the device.

**Q: Navigation buttons do not respond**
> Check that the PCF8574 I/O expander is seated correctly on the board. Inspect solder joints on the button headers. If using a custom build, verify the I2C address (default `0x20`) matches the address jumper configuration on the PCF8574.

---

### 🔋 Power & Battery

**Q: What battery type and capacity should I use?**
> The IP5306 charging IC supports a single-cell **3.7V Li-Ion / LiPo** battery. A capacity of **1000–2000 mAh** is recommended for several hours of operation. Do **not** use Li-Ion cells rated above 4.2V or flat-top cells without a protection circuit.

**Q: The device powers off immediately after unplugging USB**
> The IP5306 requires a minimum load current to stay on. If the system draw is too low it will auto-shutdown. Enabling the display backlight or an active scan will keep the load sufficient. Alternatively, a short press of the power button after unplug will re-enable the output.

**Q: Charging LED never turns green / battery never fully charges**
> Confirm your USB power supply can deliver at least **5V 1A**. Underpowered chargers cause the IP5306 to cycle in and out of charge mode.

---

### 🖥️ Firmware & Flashing

**Q: Cannot flash — `esptool` reports "Failed to connect"**
> 1. Hold the **BOOT** button on the ESP32-S3 before connecting USB, then release after the flashing command starts.
> 2. Try a different USB cable (data-capable, not charge-only).
> 3. Check that the CP2102 driver is installed on your OS.

**Q: How do I load the project in Arduino IDE / Android Studio?**
> The firmware is built with the **Arduino IDE** (not Android Studio). Install the **ESP32 board package** by Espressif via Board Manager, then install all libraries listed in the `Libraries/` folder. Set the board to **ESP32S3 Dev Module**, partition scheme to **16MB Flash (3MB APP/9.9MB FATFS)**.

**Q: Firmware update from SD card fails or gets stuck**
> Ensure the `.bin` file is placed in the **root** of the SD card and is named exactly as expected by the OTA routine. Use a FAT32-formatted card with a capacity of 32 GB or less.



### 📻 Sub-GHz / NRF24 / CC1101

**Q: Sub-GHz Jammer / Replay shows no received signals**
> Verify the CC1101 module is firmly seated on the shield header. Check SPI connections and confirm the correct frequency band is selected in settings (433 MHz, 868 MHz, or 915 MHz depending on your region).

**Q: 2.4GHz Scanner or Protokill has no effect**
> Confirm all three NRF24 modules are inserted and powered. A missing or poorly seated module will silently reduce jamming coverage.

---

### 🧲 RFID / NFC

**Q: Card Reader shows "No card detected" even when a card is present**
> Ensure the card is held **flat and still** within 2–3 cm of the antenna. High-frequency interference from nearby Wi-Fi or BLE activity can reduce read range — try disabling other active scans temporarily.

---

Troubleshooting content contributed by [@pangerlkr](https://github.com/pangerlkr)