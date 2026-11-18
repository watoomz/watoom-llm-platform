<!-- Source: wiki/Features.md — https://github.com/cifertech/ESP32-DIV/wiki/Features -->

# Features

**ESP32-DIV** is an **ESP32-S3** board with a small **TFT UI** (touch + keypad). Firmware packs Wi-Fi, BLE, 2.4 GHz (NRF24), Sub-GHz (CC1101), IR, optional RFID/NFC and GPS, plus tools and settings. **This page is a map**, not a manual: use the tables to jump to each wiki article.

> **Legal & ethics** — Use only on **your** hardware, networks, and spectrum, or with **written permission**. Many tools are **regulated** or **illegal** if pointed at strangers’ systems or public bands.

---

## Contents

Use these links (they include this page URL so anchors work from anywhere):

- [Main menu layout](https://github.com/cifertech/ESP32-DIV/wiki/Features#main-menu-layout)
- [Wi-Fi tools](https://github.com/cifertech/ESP32-DIV/wiki/Features#wi-fi-tools)
- [Bluetooth tools](https://github.com/cifertech/ESP32-DIV/wiki/Features#bluetooth-tools)
- [2.4 GHz tools NRF24](https://github.com/cifertech/ESP32-DIV/wiki/Features#24-ghz-tools-nrf24)
- [SubGHz tools CC1101](https://github.com/cifertech/ESP32-DIV/wiki/Features#subghz-tools-cc1101)
- [More IR RFID GPS](https://github.com/cifertech/ESP32-DIV/wiki/Features#more-ir-rfid-gps)
- [Tools settings about](https://github.com/cifertech/ESP32-DIV/wiki/Features#tools-settings-about)
- [Reference](https://github.com/cifertech/ESP32-DIV/wiki/Features#reference)

**Index of every article:** [Home](https://github.com/cifertech/ESP32-DIV/wiki/Home)

---

## Main menu layout

On the device the home screen is **two columns of four rows**:

```text
+----------------+----------------+
| WiFi           | Bluetooth      |
| 2.4GHz         | SubGHz         |
| More           | Tools          |
| Settings       | About          |
+----------------+----------------+
```

Each **hub** page lists submenu rows and links to every feature article:

| Tile | Role | Hub |
|------|------|-----|
| **WiFi** | 802.11 lab tools | [Menu: WiFi](https://github.com/cifertech/ESP32-DIV/wiki/Menu-WiFi) |
| **Bluetooth** | BLE tools + HID ducky | [Menu: Bluetooth](https://github.com/cifertech/ESP32-DIV/wiki/Menu-Bluetooth) |
| **2.4GHz** | NRF24 scan / disrupt | [Menu: 2.4GHz](https://github.com/cifertech/ESP32-DIV/wiki/Menu-2-4GHz) |
| **SubGHz** | CC1101 replay / jam / files | [Menu: SubGHz](https://github.com/cifertech/ESP32-DIV/wiki/Menu-SubGHz) |
| **More** | IR, RFID/NFC, GPS | [Menu: More](https://github.com/cifertech/ESP32-DIV/wiki/Menu-More) |
| **Tools** | Serial, flash, touch, SD | [Menu: Tools](https://github.com/cifertech/ESP32-DIV/wiki/Menu-Tools) |
| **Settings** | Full-screen preferences | [Menu: Settings](https://github.com/cifertech/ESP32-DIV/wiki/Menu-Settings) |
| **About** | Version + credits | [Menu: About](https://github.com/cifertech/ESP32-DIV/wiki/Menu-About) |

---

## Wi-Fi tools

**Path:** Main → **WiFi** → list.

| Feature | Notes | Doc |
|---------|-------|-----|
| Packet Monitor | Waterfall-style channel view; **PCAP** to SD when enabled | [Wi-Fi Packet Monitor](https://github.com/cifertech/ESP32-DIV/wiki/Wi-Fi-Packet-Monitor) |
| Beacon Spammer | Beacon / SSID flood for demos | [Wi-Fi Beacon Spammer](https://github.com/cifertech/ESP32-DIV/wiki/Wi-Fi-Beacon-Spammer) |
| WiFi Deauther | Deauth-style traffic — **authorized targets only** | [Wi-Fi Deauther](https://github.com/cifertech/ESP32-DIV/wiki/Wi-Fi-Deauther) |
| Probe Request Flood | High-rate probes for stress tests | [Wi-Fi Probe Request Flood](https://github.com/cifertech/ESP32-DIV/wiki/Wi-Fi-Probe-Request-Flood) |
| Deauth Detector | Passive watch for deauth-like events | [Wi-Fi Deauth Detector](https://github.com/cifertech/ESP32-DIV/wiki/Wi-Fi-Deauth-Detector) |
| WiFi Scanner | AP list, channel, RSSI, security when known | [Wi-Fi Scanner](https://github.com/cifertech/ESP32-DIV/wiki/Wi-Fi-Scanner) |
| Captive Portal | AP + DNS + portal — **training / lab only** | [Wi-Fi Captive Portal](https://github.com/cifertech/ESP32-DIV/wiki/Wi-Fi-Captive-Portal) |

---

## Bluetooth tools

**Path:** Main → **Bluetooth** → list.

| Feature | Notes | Doc |
|---------|-------|-----|
| BLE Jammer | Floods BLE spectrum — **lab / license** | [Bluetooth BLE Jammer](https://github.com/cifertech/ESP32-DIV/wiki/Bluetooth-BLE-Jammer) |
| BLE Spoofer | Fake or custom advertisements | [Bluetooth BLE Spoofer](https://github.com/cifertech/ESP32-DIV/wiki/Bluetooth-BLE-Spoofer) |
| Sour Apple | Apple-style BLE bursts | [Bluetooth Sour Apple](https://github.com/cifertech/ESP32-DIV/wiki/Bluetooth-Sour-Apple) |
| Sniffer | Ads + RSSI + heuristics | [Bluetooth BLE Sniffer](https://github.com/cifertech/ESP32-DIV/wiki/Bluetooth-BLE-Sniffer) |
| BLE Scanner | Passive discovery list | [Bluetooth BLE Scanner](https://github.com/cifertech/ESP32-DIV/wiki/Bluetooth-BLE-Scanner) |
| BLE Rubber Ducky | BLE HID; payloads in **`/ducky`** | [Bluetooth BLE Rubber Ducky](https://github.com/cifertech/ESP32-DIV/wiki/Bluetooth-BLE-Rubber-Ducky) |

---

## 2.4 GHz tools NRF24

**Path:** Main → **2.4GHz** → list. **NRF24** on the shield.

| Feature | Notes | Doc |
|---------|-------|-----|
| Scanner | Channel energy / spectrum-style view | [2.4GHz Scanner](https://github.com/cifertech/ESP32-DIV/wiki/2-4GHz-Scanner) |
| Proto Kill | Aggressive 2.4 GHz patterns — **lab only** | [2.4GHz Proto Kill](https://github.com/cifertech/ESP32-DIV/wiki/2-4GHz-Protokill) |

---

## SubGHz tools CC1101

**Path:** Main → **SubGHz** → list. **CC1101** (see `shared.h`).

| Feature | Notes | Doc |
|---------|-------|-----|
| Replay Attack | Learn / replay simple remotes | [SubGHz Replay Attack](https://github.com/cifertech/ESP32-DIV/wiki/SubGHz-Replay-Attack) |
| SubGHz Jammer | Carrier / sweep — **lab / license** | [SubGHz Jammer](https://github.com/cifertech/ESP32-DIV/wiki/SubGHz-Jammer) |
| Saved Profile | Replay from SD | [SubGHz Saved Profiles](https://github.com/cifertech/ESP32-DIV/wiki/SubGHz-Saved-Profiles) |

---

## More IR RFID GPS

**Path:** Main → **More** → grid, then nested list. Hub: [Menu: More](https://github.com/cifertech/ESP32-DIV/wiki/Menu-More).

### IR Remote

| Screen | Doc |
|--------|-----|
| Record | [IR Remote Record](https://github.com/cifertech/ESP32-DIV/wiki/IR-Remote-Record) |
| Saved Profile | [IR Remote Saved Profiles](https://github.com/cifertech/ESP32-DIV/wiki/IR-Remote-Saved-Profiles) |
| Universal Controller | [IR Remote Universal Controller](https://github.com/cifertech/ESP32-DIV/wiki/IR-Remote-Universal-Controller) |

### RFID NFC

1. **[RFID NFC Overview](https://github.com/cifertech/ESP32-DIV/wiki/RFID-NFC-Overview)** — PN532 SPI, SD session rules.  
2. **[Home](https://github.com/cifertech/ESP32-DIV/wiki/Home)** — full table for Card Reader, Clone, Erase, Dump, Decode Access, Jam Reader, Tag Disrupt, Disrupt Emulate.

### GPS

| Screen | Doc |
|--------|-----|
| Wardriver | [GPS Wardriver](https://github.com/cifertech/ESP32-DIV/wiki/GPS-Wardriver) |
| Satellite Scanner | [GPS Satellite Scanner](https://github.com/cifertech/ESP32-DIV/wiki/GPS-Satellite-Scanner) |

---

## Tools settings about

| Area | Path | Doc |
|------|------|-----|
| **Tools** | Main → **Tools** → list (serial, OTA, touch, SD) | [Menu: Tools](https://github.com/cifertech/ESP32-DIV/wiki/Menu-Tools) |
| **Settings** | Main → **Settings** (full screen: theme, brightness, NeoPixel, auto-scan, save JSON) | [Settings](https://github.com/cifertech/ESP32-DIV/wiki/Settings) |
| **About** | Main → **About** (full screen: version + credits) | [About](https://github.com/cifertech/ESP32-DIV/wiki/About) |

Per-tool pages: [Serial Monitor](https://github.com/cifertech/ESP32-DIV/wiki/Tools-Serial-Monitor) · [Update Firmware](https://github.com/cifertech/ESP32-DIV/wiki/Tools-Update-Firmware) · [Touch Calibrate](https://github.com/cifertech/ESP32-DIV/wiki/Tools-Touch-Calibrate) · [SD File Manager](https://github.com/cifertech/ESP32-DIV/wiki/Tools-SD-File-Manager)

