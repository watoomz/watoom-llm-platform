# ESP32-DIV v2 engineering guide 2: pin map and shared buses

All pin numbers below are CONFIG: resolved by running the C preprocessor over the application's `include/shared.h` with `BOARD_ESP32_DIV_V2` defined, plus `include/User_Setup.h`. They show what the firmware assumes, not what was measured on the board. Where the vendor wiki and the firmware disagree, verify with a multimeter before wiring a module.

## Shared SPI bus (GPIO 11, 12, 13)

CONFIG: the SD card, the CC1101 sub-GHz radio and the NRF24 radios share one SPI bus: `SD_SCLK`/`CC1101_SCK`/`NRF24_SPI_SCK` are GPIO 12, `SD_MISO`/`CC1101_MISO`/`NRF24_SPI_MISO` are GPIO 13, `SD_MOSI`/`CC1101_MOSI`/`NRF24_SPI_MOSI` are GPIO 11. Only the chip-select lines differ, so exactly one device may be selected at a time and every other chip-select must be held high.

## Chip selects and control pins

CONFIG: `SD_CS` is GPIO 10 and `SD_CD` (card detect) is GPIO 38. `CC1101_CS` is GPIO 5 with `CC1101_GDO0` on `SUBGHZ_TX_PIN` (GPIO 6) and `CC1101_GDO2` on `SUBGHZ_RX_PIN` (GPIO 3). The NRF24 modules use `CE_PIN_1`/`CSN_PIN_1` = 15/4, `CE_PIN_2`/`CSN_PIN_2` = 47/48 and `CE_PIN_3`/`CSN_PIN_3` = 14/21. `PN532_SS` is GPIO 5, the same pin as `CC1101_CS`, and `SD_CS_PIN` is also 5; the SD mount code skips `SD_CS_PIN` when it equals `CC1101_CS`.

## Display and touch (separate bus on GPIO 35, 36, 37)

CONFIG: the ILI9341 panel (240 x 320, `TFT_ROTATION` 2) uses `TFT_MOSI` 35, `TFT_SCLK` 36, `TFT_MISO` 37, `TFT_CS` 17, `TFT_DC` 16, `TFT_RST` 0 and `TFT_BL` 21. The XPT2046 touch controller uses `XPT2046_MOSI` 35, `XPT2046_CLK` 36, `XPT2046_MISO` 37 and `XPT2046_CS` 18, and `XPT2046_IRQ` is 255 (not used). `TOUCH_SHARES_TFT_SPI` is 0 on this board. INFERRED: GPIO 0 is the ESP32-S3 boot-strapping pin, so a panel reset line on it can interact with boot mode; this has not been tested on the board.
CONFIG warning: `BACKLIGHT_PIN` in `shared.h` resolves to 7 while `User_Setup.h` says `TFT_BL` 21; check which one the board actually uses before changing backlight code.

## Buttons, battery and indicators

CONFIG: buttons are read through a PCF8574 I2C expander (`HAS_PCF8574_BUTTONS` 1, default address 0x20, auto-detect range 0x20 to 0x27) with `BTN_LEFT` 3, `BTN_RIGHT` 4, `BTN_DOWN` 5, `BTN_SELECT` 6 and `BTN_UP` 7 as expander pin indexes. `BATTERY_ADC_PIN` and `BUZZER_PIN` resolve to -1 (not wired in firmware), the battery divider is 200k over 100k, and `BATTERY_LOW_VOLT` is 3.40 V. The vendor lists an IP5306 charger, four WS2812 NeoPixels (`NEOPIXEL_BRIGHT_MAX` 64) and an external antenna connector.

## Known disagreements to verify on the board

CONFIG: `PN532_MISO` is 11 and `PN532_MOSI` is 13, the reverse of the shared bus naming above, so RFID uses its own pin assignment rather than the shared peripheral mapping. `GPS_UART_RX` is 5 and `GPS_UART_TX` is 6, which collide with `CC1101_CS` and `SUBGHZ_TX_PIN`. `IR_RX_PIN` 21 and `IR_TX_PIN` 14 reuse NRF24 module 3 pins. The vendor wiki and the firmware also differ on PN532 SS, GPS pins and buzzer/ADC.

## Pin sharing rules that matter in code

MEASURED (T-0045): after a feature re-routes the shared SPI bus, any code that wants the SD card must release the other chip selects and remount the SD library; see the SD guide. INFERRED: because GPIO 35 to 37 are also the octal PSRAM pins, any use of PSRAM conflicts with the display.
