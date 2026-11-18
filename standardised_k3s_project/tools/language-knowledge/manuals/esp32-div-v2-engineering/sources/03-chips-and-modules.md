# ESP32-DIV v2 engineering guide 3: every chip and module, one section each

Evidence labels: MEASURED (lab board, named job), CONFIG (application headers, unverified on hardware), VENDOR (upstream wiki), DATASHEET (general chip knowledge from the part's published data, not re-measured here). Firmware version reported at boot: `ESP32-DIV v1.7.2` by CiferTech; the lab application is a port of it (`apps/div-offensive`).

## ESP32-S3 (main controller)

DATASHEET: dual-core Xtensa LX7 up to 240 MHz, 512 KB internal SRAM, 2.4 GHz Wi-Fi (802.11 b/g/n) and Bluetooth LE 5, up to 45 GPIO, built-in USB serial/JTAG on GPIO 19 and 20. Strapping pins are GPIO 0, 3, 45 and 46. GPIO 26 to 32 serve the SPI flash (and PSRAM on parts with it); on octal-PSRAM parts GPIO 33 to 37 are also taken by the PSRAM. ADC1 is GPIO 1 to 10 and ADC2 is GPIO 11 to 20. This board talks to the host through a CP2102 bridge, not the native USB port.
MEASURED: 16 MiB flash, 8 MiB embedded PSRAM (disabled in the qualified profile), 240 MHz; see guide 1. Free internal heap at start of the application is roughly 196 KB at the SD mount and falls as stacks start (see the memory guide).

## CP2102 USB-to-UART bridge

VENDOR: handles firmware flashing and serial communication. MEASURED: enumerates as USB `10c4:ea60`; opening the serial port resets the board, so a capture always starts with the boot ROM lines. The UART runs at 115200 baud in every lab job; 9600, 57600 and 115200 are the permitted worker baud rates.

## IP5306 power management

VENDOR: battery charging and boost conversion, stable operation under load. DATASHEET/known behaviour: IP5306-class chips shut the 5 V boost output off after a period of very low load current, which can make a lightly loaded board power down on battery; this has not been observed or tested on the lab board. CONFIG: the firmware has `BATTERY_ADC_PIN` -1 on V2 (no battery reading) while the vendor's schematic shows the divider on GPIO 2.

## ILI9341 2.8 inch TFT display

VENDOR: 240 x 320 panel on SPI, backlight switched by an SI2302 N-channel MOSFET on GPIO 7; reset on EN/RESET. CONFIG: driven by the vendored `TFT_eSPI` with `TFT_MOSI` 35, `TFT_SCLK` 36, `TFT_MISO` 37, `TFT_CS` 17, `TFT_DC` 16, `TFT_RST` 0, rotation 2. DATASHEET: ILI9341 uses 16-bit RGB565 pixels over 4-wire SPI. INFERRED: the display lines (GPIO 35 to 37) are the same pins octal PSRAM uses; whether the panel renders correctly was not checked by the serial-only lab jobs.

## XPT2046 resistive touch controller

VENDOR: on the display's SPI lines (35, 36, 37) with `T_CS` GPIO 18 and the interrupt pin not connected. CONFIG: driven by `XPT2046_Touchscreen` through `Touchscreen.cpp` with a separate `SPIClass`; calibration limits are `TOUCH_X_MIN` 280, `TOUCH_X_MAX` 3850, `TOUCH_Y_MIN` 320, `TOUCH_Y_MAX` 3750 and profile id `ESP32_DIV_V2`. DATASHEET: a 12-bit SPI touch ADC.

## PCF8574 button expander

CONFIG: `HAS_PCF8574_BUTTONS` is 1; the firmware auto-detects an address in 0x20 to 0x27. MEASURED: `[PCF8574] auto-detected at 0x20` and `direction mask 0xF8 (all 5 buttons input)`, `pcf dataIn=0xF8` at boot. DATASHEET: an 8-bit I2C quasi-bidirectional port expander; the A version uses 0x38 to 0x3F. The firmware calls `Wire.begin()` with default pins.

## microSD slot

VENDOR/CONFIG: SPI mode on the shared bus, `SD_CS` GPIO 10, card detect GPIO 38. MEASURED: `SD Card detected` at boot; raw SPI init returns `CMD8` echo `000001AA`, `ACMD41` ready after 2 tries and OCR `C0FF8000`, meaning a high-capacity (SDHC/SDXC) card with the 2.7 to 3.6 V window supported. The Arduino SD library mounts it at `/sd` with up to 16 open files (fewer after heap pressure; see the SD guide). Settings live in `/config/settings.json`, logs in `/logs`, captures in `/captures`, QR output in `/qr/`, BLE ducky scripts in `/ducky`, and the OUI databases `/oui.db`, `/drone_oui.db`, `/drone_rid.db` at the card root; on the lab card the OUI database is absent and the boot log says `no OUI database on SD (MAC vendor names disabled)`.

## CC1101 sub-GHz transceiver

VENDOR/CONFIG: SPI on the shared bus with `CC1101_CS` GPIO 5, GDO0 on GPIO 6 and GDO2 on GPIO 3; driven by the vendored ELECHOUSE CC1101 library and `RCSwitch` 2.6.4, default frequency 433.92 MHz. DATASHEET: bands 300 to 348, 387 to 464 and 779 to 928 MHz; 2-FSK, GFSK, MSK, OOK and ASK modulation; 64-byte FIFOs; 3.3 V only. The driver's `SpiStart()` calls `SPI.begin(SCK, MISO, MOSI, SS)` and pins the clock to 1 MHz, and `SpiEnd()` calls `SPI.end()`, so each CC1101 access re-routes the shared bus away from the SD card. MEASURED: `SubGHz: CC1101 OK` in the TEST_ALL job.

## NRF24L01+ 2.4 GHz radios (three on the shield)

VENDOR: three modules sharing SCK/MOSI/MISO (GPIO 12, 11, 13) with chip enable and chip select pairs CE/CSN = 15/4, 47/48 and 14/21. CONFIG: driven by the vendored RF24 library; `NRF24_DATA_RATE` is 2 and `NRF24_PA_LEVEL` is 3 (their meaning is the RF24 library's enum values). DATASHEET: 2.4 GHz ISM, 125 channels from 2400 MHz, 250 kbps, 1 Mbps or 2 Mbps, 3.3 V supply, SPI. Power-amplifier variants draw high peak current, which stresses a battery supply. MEASURED: not exercised in the lab jobs.

## PN532 RFID/NFC reader (optional)

VENDOR: SPI on the shared bus, SS GPIO 4. CONFIG: firmware `PN532_SS` is 5 and the MISO/MOSI definitions are swapped relative to the shared bus (11 and 13); driven by the vendored Adafruit PN532 library through `rfid.cpp`. DATASHEET: 13.56 MHz NFC front end for ISO14443 A/B, MIFARE and FeliCa; its SPI mode is LSB first, and the Adafruit library handles that. CONFIG: the firmware's test path calls the SD restore and the display SPI restore after `RfidNfc::begin()`, so RFID use moves the shared bus. MEASURED: `RFID: PN532 NOT FOUND` in every TEST_ALL job; no PN532 module is fitted on the lab board, so this failure is expected and not a fault.

## Neo-6M GPS (optional)

VENDOR: UART with module TX to GPIO 47 and module RX from GPIO 48. CONFIG: firmware `GPS_UART_RX` 5 and `GPS_UART_TX` 6 on V2, handled in `gps.cpp`. DATASHEET: u-blox NEO-6M, NMEA over UART at 9600 baud by default, up to 5 Hz position updates. MEASURED: not fitted or exercised.

## Infrared receiver and transmitter

VENDOR: the receiver output is on GPIO 21; the transmitter LED is switched low-side by a BC847 NPN transistor whose base (220 ohm) is on GPIO 14, with the LED anode on 5 V through a 220 ohm resistor. CONFIG: `IR_RX_PIN` 21, `IR_TX_PIN` 14, default carrier `IR_DEFAULT_KHZ` 38, using the vendored IRremoteESP8266 protocol set (about 100 protocol files) plus `ir_bruteforce.cpp`. DATASHEET: a demodulating receiver outputs the envelope of a 38 kHz carrier. Note both pins are shared with NRF24 module 3 (CE 14, CSN 21).

## WS2812 NeoPixels (four)

VENDOR: data on GPIO 1. CONFIG: brightness cap `NEOPIXEL_BRIGHT_MAX` 64. DATASHEET: one-wire 800 kHz serial LEDs, normally 5 V powered, so a 3.3 V data line is marginal.

## Buzzer

VENDOR: signal on GPIO 2 as a PWM/tone output. CONFIG: `BUZZER_PIN` resolves to -1 on V2, so the firmware does not drive it. VENDOR also puts the battery divider ADC on GPIO 2; both cannot be wired to one pin.

## Battery divider

VENDOR: ADC on GPIO 2. CONFIG: divider `BATTERY_VDIV_R1` 200000 and `BATTERY_VDIV_R2` 100000 ohms, low-battery threshold 3.40 V, but `BATTERY_ADC_PIN` is -1 on V2.

## Antennas and shield

VENDOR: an external antenna connector on the core board; the shield carries three NRF24 modules, the CC1101, separate antennas per band and the infrared circuitry, connected through pogo-pin headers so the shield can be replaced. The core board is described as stable by design and the shield as modular.
