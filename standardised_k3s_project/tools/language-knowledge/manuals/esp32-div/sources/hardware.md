# Hardware of ESP32-DIV

ESP32-DIV v2 is designed around a **stable core board** and an **expandable shield**, keeping the system modular, thin, and reliable.  
The main board handles essential power, storage, UI, and processing, while the shield provides expansion points for external modules.

---

## 🛠️ Main Board

The main board focuses on stability and core functionality:

- **ESP32-S3**  
  The main microcontroller. Fixes previous pin conflicts, improves USB support, and allows future expansions.

- **IP5306 Power Management IC**  
  Manages battery charging and boost conversion, providing stable operation under load.

- **Battery Voltage Divider**  
  Monitors battery voltage.

- **CP2102 USB-to-Serial Converter**  
  Handles firmware flashing and serial communication.

- **SD Card Slot**  
  Stores logs, scripts, and configurations.

- **ILI9341 TFT Display (2.8")**  
  Main interface display.

- **Soft Tactile Buttons**  
  Reliable low-profile switches for user interaction.

- **Buzzer**  
  Optional audio feedback.

- **4× WS2812 NeoPixels**  
  Visual status indicators.

- **External Antenna Connector**  
  Supports flexible antenna setups for improved range.

<div align="center"> 
  <img src="https://github.com/user-attachments/assets/0aeca1bb-9023-43a0-9f62-f89ced53098f" alt="screenshot" width="Auto" height="Auto" />
</div>


---

## 🛡️ Shield (Expansion Board)

The shield is modular and designed for external modules.  

- **3 × NRF24 Modules** – Dedicated for 2.4GHz operations.  
- **CC1101 Sub-GHz Transceiver** – For Sub-GHz connectivity.  
- **Multiple Antennas** – Separate antennas for different bands.  
- **Infrared Circuitry** – For IR input/output operations.

### 🧩 Shield Interface

ESP32-DIV v2 uses **pogo-pin headers** for shield connection:

- Thin stacking without bulky connectors  
- Clean electrical contact  
- Easy shield replacement and expansion

<div align="center"> 
  <img src="https://github.com/user-attachments/assets/bbfa2c55-02e0-4795-b003-fde06f2d64d9" alt="screenshot" width="Auto" height="Auto" />
</div>

---

## 📐 Design Notes

- Core board is **stable by design** (for now) 
- Shield is **modular and replaceable**  
- Thin, stackable form factor using pogo pins  
- All components are exposed and hackable  

---

*For wiring and pin assignments, see the [Schematics](Schematics) page.  
To flash firmware, follow the [Firmware Upload Guide](Firmware-Upload-Guide).*
