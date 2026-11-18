# Firmware Upload Guide for ESP32-DIV

The **ESP32-DIV** requires firmware or code to unlock its wireless capabilities. This guide covers three methods to upload firmware: **OTA/SD Card**, **Flash Download Tool**, and **Arduino IDE**. These methods suit both beginners and advanced users.

⚠️ **Note**: Always download firmware and sketches from the [ESP32-DIV GitHub repository](https://github.com/cifertech/ESP32-DIV).

---

## Method 1: Update Firmware via OTA or SD Card (Recommended)

If your ESP32-DIV is running its main firmware, use the built-in update feature via **Over-The-Air (OTA)** or **SD card**. This method is ideal for quick, computer-free updates using the TFT display.

> ✅ **ESP32-DIV**: OTA and SD updates are fully supported.

---

### What You’ll Need
- Working ESP32-DIV with main firmware and functional TFT display
- MicroSD card (FAT32 formatted) for SD card updates
- `.bin` firmware file from the repository
- Wi-Fi credentials for OTA updates
- Computer or phone to host the firmware file for OTA

---

### Steps for OTA Update

1. **Get the Firmware File**
   - Download the latest `.bin` file from the  
     [ESP32-DIV GitHub repository](https://github.com/cifertech/ESP32-DIV)
   - Host it on a server or computer and note the URL  
     (e.g. `http://192.168.1.100/firmware.bin`)

2. **Connect to Wi-Fi**
   - Power on the ESP32-DIV
   - Go to **Wi-Fi Settings** on the TFT display
   - Select your network, enter the password using the on-screen keyboard, and connect

3. **Run the OTA Update**
   - Navigate to **Firmware Update**
   - Select **OTA Update**
   - Enter the firmware URL
   - Press **Update**
   - The device reboots automatically when done

4. **Check the Update**
   - Verify the new firmware version on the TFT display or Serial Monitor (115200 baud)
   - If it fails, check the URL and Wi-Fi stability, then retry

---

### Steps for SD Card Update

1. **Prepare the SD Card**
   - Format a microSD card to **FAT32**
   - Download the latest `.bin` file from the repository
   - Rename it to `firmware.bin`
   - Place it in the SD card **root directory**
   - Eject the card safely

2. **Insert the SD Card**
   - Power off the ESP32-DIV
   - Insert the SD card

3. **Run the SD Card Update**
   - Power on the device
   - Go to **Firmware Update**
   - Select **SD Card Update**
   - Select `firmware.bin`
   - Press **Update**
   - Device reboots after flashing

4. **Check the Update**
   - Confirm the firmware version on the TFT display or Serial Monitor
   - The file may be renamed (e.g. `firmware.bak`)
   - Remove or reformat the SD card for future use

---

### Tips
- **OTA**: Ensure a strong Wi-Fi signal and keep the host online
- **SD Card**: Use a reliable microSD card and power off before inserting/removing
- **Troubleshooting**: Verify the `.bin` file, FAT32 format, or check Serial Monitor for errors

---

## Method 2: Flash a `.bin` File with Flash Download Tool

Use the **Espressif Flash Download Tool** to upload firmware via USB. This is ideal for **initial setup**, **recovery**, or **bricked devices**.

> ⚠️ **ESP32-DIV**: Make sure you select the correct chip and flash size.

---

### What You’ll Need
- ESP32-DIV with USB-C / micro-USB port
- Computer (Windows, macOS, Linux)
- USB cable
- `.bin` firmware file from  
  https://github.com/cifertech/ESP32-DIV/tree/main/Pre-compiled%20Bin
- `.partitions` file from  
  https://github.com/cifertech/ESP32-DIV/tree/main/Flash%20File
- Espressif Flash Download Tool  
  https://www.espressif.com/en/support/download/other-tools

---

### Steps

1. **Prepare the Firmware Files**
   - Download the `.bin` file
   - Download the `.partitions` file

2. **Install Flash Download Tool**
   - Install and run the tool
   - On Windows, run as **Administrator**

3. **Connect the ESP32-DIV**
   - Connect via USB
   - Enter **Download Mode**:
     - Hold **BOOT**
     - Press **RESET**
     - Release both
   - Select the correct **COM port**

4. **Configure Flash Settings**
   - Chip: **ESP32**
   - Mode: **Download Mode**
   - `.bin` file → Offset `0x10000`
   - `.partitions` file → Offset `0x8000`
   - SPI Speed: **40 MHz**
   - SPI Mode: **DIO**
   - Check both file boxes

5. **Flash the Firmware**
   - Click **START**
   - Wait for “FINISH” / “Download Complete”

6. **Reset and Verify**
   - Power cycle the ESP32-DIV
   - Verify on TFT display or Serial Monitor
   - If it fails, recheck COM port, offsets, or Download Mode

---

### Tips
- Install USB-to-serial drivers (CP2102 / CH340) if needed
- Verify firmware matches your hardware
- Try another USB cable or reduce SPI speed to **20 MHz** if flashing fails

---

## Method 3: Upload Sketch via Arduino IDE

Compile and upload the ESP32-DIV sketch for customization.

> ⚠️ **ESP32-DIV**: Uses updated libraries and platform configuration.

---

### What You’ll Need
- ESP32-DIV with USB-C / micro-USB
- Computer with Arduino IDE (2.x or 1.8.x)
- USB cable
- ESP32-DIV sketch
- Libraries:  
  https://github.com/cifertech/ESP32-DIV/tree/main/Libraries
- `platform.txt`:  
  https://github.com/cifertech/ESP32-DIV/tree/main/Flash%20File

---

### Steps

1. **Install Arduino IDE and ESP32 Board Package**
   - Install Arduino IDE
   - Open **Boards Manager**
   - Install **esp32 by Espressif Systems (v2.0.10)**

2. **Replace `platform.txt`**
   - Download from the repository
   - Replace the file in:
     - Windows:  
       `C:\Users\<YOUR_USERNAME>\AppData\Local\Arduino15\packages\esp32\hardware\esp32\2.0.10`
     - macOS:  
       `~/Library/Arduino15/packages/esp32/hardware/esp32/2.0.10`
     - Linux:  
       `~/.arduino15/packages/esp32/hardware/esp32/2.0.10`
   - Back up the original file

3. **Replace Library Files**
   - Unzip the library ZIP
   - Replace existing libraries in:
     - Windows: `Documents/Arduino/libraries`
     - macOS: `~/Documents/Arduino/libraries`
     - Linux: `~/Arduino/libraries`
   - Restart Arduino IDE

4. **Download and Open Sketch**
   - Open the `.ino` file from the repository

5. **Configure Arduino IDE**
   - Board: **ESP32 S3 Dev Module**
   - Select correct **Port**
   - **Partition Scheme: Minimal SPIFFS**
   - Flash Size according to your hardware
   - Optional:
     - Upload Speed: 921600
     - CPU Frequency: 240 MHz

6. **Compile and Upload**
   - Click **Verify**
   - Click **Upload**
   - Enter **Download Mode** if prompted
   - Wait for “Done uploading”

7. **Verify Upload**
   - Check TFT display or Serial Monitor (115200 baud)
   - If it fails, recheck settings or cable

---

### Tips
- Ensure libraries match the provided ZIP
- Install USB drivers if the port is missing
- Lower upload speed to **115200** if needed

---

*Your ESP32-DIV is ready! Explore its tools on the [Features](Features) page.*
