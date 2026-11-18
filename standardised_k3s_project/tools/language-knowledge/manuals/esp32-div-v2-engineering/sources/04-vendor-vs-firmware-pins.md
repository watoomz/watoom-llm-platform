# ESP32-DIV v2 engineering guide 4: vendor wiring against firmware config, peripheral by peripheral

VENDOR is the upstream wiki's Schematics page (GitHub wiki commit 5f097aa19b480ff9593b9a0a4bdc6c6dc9c387d4). CONFIG is the lab application's resolved V2 header. None of these are measured on the physical board. Where they disagree, trust neither until a multimeter or a bring-up test confirms.

## Agreements (safe to rely on as the intended design)

TFT: SCK 36, MOSI 35, MISO 37, CS 17, DC 16 in both. Touch: CLK 36, MOSI 35, MISO 37, CS 18 in both; the touch interrupt is not connected (`XPT2046_IRQ` 255). NRF24 modules: shared SCK 12, MOSI 11, MISO 13, with CE/CSN 15/4, 47/48 and 14/21 in both. CC1101: SCK 12, MOSI 11, MISO 13, CS 5, GDO0 6, GDO2 3 in both. SD: SCK 12, MOSI 11, MISO 13, CS 10, card detect 38 in both. Infrared: receiver 21 and transmitter base 14 in both. PN532 data lines: both say MISO 11 and MOSI 13 (crossed relative to the shared bus names).

## Disagreements

Display reset: VENDOR says EN/RESET; `User_Setup.h` says `TFT_RST` 0 and calls it the stock V2 tie, so GPIO 0 (a strapping pin) may carry the panel reset. The T-0045 ticket text separately says the panel reset is tied to the SD card; those three statements cannot all be true.
Display backlight: VENDOR says GPIO 7 through an SI2302 MOSFET and `shared.h` `BACKLIGHT_PIN` is 7, but `User_Setup.h` says `TFT_BL` 21. GPIO 21 is also NRF24 module 3's chip select and the IR receiver pin, so 21 is very likely stale; use 7.
PN532 chip select: VENDOR says GPIO 4, which is NRF24 module 1's CSN; firmware `PN532_SS` is 5, which is the CC1101 chip select. Either choice shares a select line with another device on the shared bus.
GPS: VENDOR says RX on GPIO 47 and TX on GPIO 48, which are NRF24 module 2's CE and CSN; firmware uses 5 and 6, which are the CC1101 chip select and GDO0 line.
Buzzer and battery sense: VENDOR puts both on GPIO 2; firmware sets `BUZZER_PIN` and `BATTERY_ADC_PIN` to -1 on V2, so neither is active.
NeoPixels: VENDOR says data on GPIO 1. The lab port has no NeoPixel driver; `applyNeoPixel()` only toggles a stored setting, so the LEDs are never driven by this firmware.
SD legacy select: the firmware also defines `SD_CS_PIN` as 5 (the V1 value) next to `SD_CS` 10; the SD mount code skips it when it equals the CC1101 select.

## Pin reuse that limits what can run together

GPIO 21 is NRF24 module 3 CSN and the IR receiver. GPIO 14 is NRF24 module 3 CE and the IR transmitter. GPIO 4 and 5 are claimed by NRF24 module 1, CC1101, PN532 and the legacy SD select in different places. GPIO 35, 36 and 37 are the display and touch bus and also the octal PSRAM lines. The firmware's own comment says the IR defaults overlap NRF24 module 3, so features that use both must be exclusive.

## Rule for adding hardware

Before wiring or coding a new peripheral, list every pin it needs, check it against this table and the shared-bus rules, and prefer a pin that no entry above claims. Verify the board with a continuity test, since the vendor wiki and the firmware were written separately.
