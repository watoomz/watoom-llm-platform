# Navigation and controls

How to move around the ESP32-DIV firmware UI (TFT + PCF8574 keypad + touch).

---

## Main menu

The home screen is an **8-tile grid** (two columns of four rows):

| Left column | Right column |
|-------------|--------------|
| WiFi | Bluetooth |
| 2.4GHz | SubGHz |
| More | Tools |
| Settings | About |

### Hardware buttons (PCF8574 expander)

Typical mapping (see `shared.h` in firmware):

| Control | Use on main menu |
|---------|------------------|
| **Up** | Move selection up within the current column |
| **Down** | Move selection down within the current column |
| **Left** | Jump to the **left** column (same row band) |
| **Right** | Jump to the **right** column |
| **Select** | Open the highlighted tile |

**Settings** and **About** open **full-screen** flows directly (no list submenu).

---

## Submenus

Wi-Fi, Bluetooth, 2.4 GHz, SubGHz, and **Tools** show a **vertical list** of features plus **Back to Main Menu**.

**More** opens a small grid (**IR Remote**, **RFID/NFC**, **GPS**, **Main Menu**). Choosing IR / RFID / GPS opens a **nested** submenu for that category.

### Touch

Tap a list row or button to activate the same entry you would select with keys.

---

## Inside a feature

Many tools draw a **status bar** at the top with **icons** (scan, back, exit, etc.). Tapping the **exit** icon sets internal exit flags and returns you toward the submenu or main menu, depending on the module.

Some Wi-Fi loops also exit when you press **Select** again after the feature runs—behavior can differ per tool; always prefer the on-screen **exit / back** control if shown.

---

## SD card layout (typical)

| Path | Purpose |
|------|---------|
| `/config/settings.json` | Brightness, theme, NeoPixel, auto-scan, touch bounds |
| `/captures` | SubGHz / IR captures (when implemented) |
| `/logs` | Logs (when implemented) |
| `/ducky` | BLE Rubber Ducky scripts (`.txt` payloads) |

Use a **FAT-formatted** SD card. Avoid removing the card while RFID or file tools are active.

---

## Related

- [Home](Home.md)
- [Settings](Settings.md)
