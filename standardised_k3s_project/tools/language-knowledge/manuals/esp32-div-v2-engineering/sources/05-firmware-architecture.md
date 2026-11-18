# ESP32-DIV v2 engineering guide 5: the application firmware (`apps/div-offensive`)

CONFIG for everything in this guide: read from the lab port's sources, `include/main.cpp`, `include/shared.h`, `src/utils.cpp`, with about 130,000 lines of C and C++ across `src/` and `include/`.

## What the firmware is

A port of CiferTech's ESP32-DIV firmware (the boot banner says `ESP32-DIV v1.7.2`). It builds as an Arduino sketch on core 2.0.10 for the `esp32-div-v2-s3` profile, with the sources placed under `src/` and headers under `include/` so the worker can snapshot them. Third-party code is vendored in the tree (`VENDOR.md` records version, source URL, archive hash and licence): rc-switch 2.6.4 and the HaleHound SD data pack (IEEE OUI registry of 40,478 entries and drone databases, read from the SD card at runtime, not compiled in).

## Libraries and subsystems

Display and UI: `TFT_eSPI`, `Touchscreen.cpp` with `XPT2046_Touchscreen`, `KeyboardUI.cpp`, `Theme.cpp`, `PCF8574.cpp` for the buttons, `qrcodegen.c` and `qr_payload.cpp` for QR codes. Radios: `ELECHOUSE_CC1101_SRC_DRV.cpp` and `RCSwitch.cpp` for sub-GHz, `RF24.cpp` for the NRF24 modules, `Adafruit_PN532.cpp` with `rfid.cpp` for NFC, `gps.cpp` for GPS. Infrared: IRremoteESP8266 (`IRrecv`, `IRsend`, `IRac` and about 100 protocol files) with `ir_bruteforce.cpp`. Wi-Fi: `wifi.cpp`, `wifi_sd.cpp` (PCAP and logs to SD), and `wsl_bypass.cpp`, which clears the closed-blob raw-frame check so management frames can be sent. Bluetooth: NimBLE-Arduino (`NimBLE*.cpp`), `bluetooth.cpp` (about 9,000 lines), `ducky.cpp` for BLE HID scripts, `gatt_enum.cpp`, and a BLE Mesh stack (`prov*.c`, `cfg*.c`, `model*.c`, `proxy*.c`). Storage and settings: `SettingsStore.cpp` writing `/config/settings.json`, `oui_lookup.cpp` for the vendor databases, `utils.cpp` for the SD mount, remount and shared-SPI handling.

## Boot sequence (order matters for memory and for the bus)

1. `Serial.begin(115200)` then `[boot] start`.
2. `tft.init()`, backlight PWM, theme, logo.
3. `initSDCard()`, which mounts the card and prints `SD Card detected`, then `oui::init()` loads the OUI databases if present.
4. `settingsLoad()` and the PCF8574 button expander (`[PCF8574] auto-detected at 0x20`).
5. `ensureBleStackReady()` starts NimBLE (`[ble] init begin` and `init done`).
6. `WifiScan::startBackgroundScanner()` and `BleScan::startBackgroundScanner()` start background tasks.
7. `restoreTftSpi()` rebinds the global SPI to the display pins because the SD mount moved it, then the first menu draw.
8. `startStatusBarTask()`, `setupTouchscreen()`.
9. A passive Wi-Fi scan (`[wifi-test]`), then a Wi-Fi TX self-test that starts a hidden SoftAP and injects five deauth-style frames at 50 ms spacing (`[wifi-tx-test]`), and then `esp_wifi_set_mode(WIFI_MODE_STA)` and `[boot] ready`.

MEASURED: a full boot reaches `[boot] ready` with 2 access points found and `burst complete: 5/5 ok`.

## Serial test commands

Typed at the serial console, one per line, only while no feature is active: `TEST_RFID` (starts the PN532, then restores SD and TFT SPI), `TEST_SUBGHZ` (initialises the CC1101), `TEST_QR` (restores SD, checks it mounts, lists `/qr/`) and `TEST_ALL` (all three in order, ending `=== TEST_ALL: N passed, M failed ===`). MEASURED on the lab board: RFID fails because no PN532 is fitted; CC1101 and QR/SD pass. The worker's `serial` operation sends the text and records the reply for a bounded time.

## Persistent files on the SD card

`/config/settings.json` (theme, brightness, NeoPixel flag, auto-scan), `/logs`, `/captures` (PCAP and capture files), `/qr/` (QR output), `/ducky` (BLE ducky scripts), and `/oui.db`, `/drone_oui.db`, `/drone_rid.db` at the root. The firmware does not look for the databases in subfolders.

## Where the bus is switched

Features that use the shared SPI bus (CC1101, NRF24, PN532) re-route it, then call `restoreSdAfterSharedSpi()` and `restoreTftSpi()` when they finish. Any new feature that touches the shared bus must do the same and must keep the SD chip select high while it runs; see the SD guide.
