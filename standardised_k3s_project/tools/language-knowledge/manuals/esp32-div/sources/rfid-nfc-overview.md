# RFID / NFC overview

**Menu path:** More → **RFID/NFC**

## Hardware

- **PN532** module on **SPI** (not I2C in default firmware).
- Arduino library: **Adafruit PN532**.
- Default SPI pins: `PN532_SCK`, `PN532_MISO`, `PN532_MOSI`, `PN532_SS` in `shared.h` — must not conflict with **CC1101**, **SD**, or **touch** on your wiring.

## Session note

Firmware may **remount SD** if the reader fails to start, and can **share the SPI bus** between PN532 and SD for the session. Avoid **hot-removing SD** during an RFID session.

## Sub-features

| Page | Menu item |
|------|-----------|
| [Card Reader](RFID-Card-Reader) | Card Reader |
| [Card Clone](RFID-Card-Clone) | Card Clone |
| [Erase](RFID-Erase) | Erase |
| [Dump](RFID-Dump) | Dump |
| [Decode Access](RFID-Decode-Access) | Decode Access |
| [Jam Reader](RFID-Jam-Reader) | Jam Reader |
| [Tag Disrupt](RFID-Tag-Disrupt) | Tag Disrupt |
| [Disrupt Emulate](RFID-Disrupt-Emulate) | Disrupt Emulate |

Use **Back to Main Menu** to leave the RFID submenu.

---

[← Home](Home)
