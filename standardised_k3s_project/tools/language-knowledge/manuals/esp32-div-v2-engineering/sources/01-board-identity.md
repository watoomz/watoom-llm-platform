# ESP32-DIV v2 engineering guide 1: board identity, silicon and firmware profile

Evidence labels used in this guide: MEASURED (observed on the lab's board with a named job), CONFIG (resolved from the application's own headers, not checked against the physical board), VENDOR (stated by the upstream project), INFERRED (reasoned from the above, not tested).

## Enrolled device

MEASURED: the lab board is enrolled as device `esp32-div-v2` with profile `esp32-div-v2-s3`, chip `esp32s3`, chip MAC `e8:f6:0a:dc:bc:10`, 16 MiB flash (16777216 bytes) and 8388608 bytes of PSRAM detected. It enumerates as a Silicon Labs CP2102 USB-UART bridge, USB vendor `10c4`, product `ea60`, serial `0001`, on `/dev/ttyUSB0`, with the stable path `/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0`. The bridge serial `0001` is not unique to this board, so the worker also checks the physical USB path and the chip MAC before any firmware write.

## Silicon

MEASURED (esptool): ESP32-S3, Wi-Fi, BT 5 (LE), dual core plus LP core, 240 MHz, `Embedded PSRAM 8MB (AP_3v3)`, and `Flash type set in eFuse: quad (4 data lines)`. INFERRED: the `AP_3v3` tag marks an AP Memory octal (OPI) PSRAM, so with quad flash this is an ESP32-S3R8 style part. The boot ROM banner is `ESP-ROM:esp32s3-20210327`, boot mode `SPI_FAST_FLASH_BOOT`, flash `mode:DIO, clock div:1` for the qualified image.

## Qualified firmware profile

MEASURED: the only profile that has passed a serial hardware test is Arduino-ESP32 core 2.0.10 with fully-qualified board name `esp32:esp32:esp32s3:FlashSize=4M,PartitionScheme=min_spiffs,UploadSpeed=460800,PSRAM=disabled`. It keeps the original compatible 4 MiB image layout on the physical 16 MiB chip, leaves PSRAM disabled, and preserves the SDK boot headers exactly. The merged image `firmware-merged.bin` is what gets written, and its sha256 is pinned in the flash request.

## PSRAM is disabled on purpose

MEASURED: the first OPI-enabled builds reached RTC watchdog resets before the application started. The PSRAM test application only ever proved the disabled case (`PSRAM: NOT AVAILABLE (disabled in SDK profile)`).
CONFIG: the display panel's SPI lines are GPIO 35 (MOSI), 36 (SCLK) and 37 (MISO), in `include/User_Setup.h`, which says it matches the stock ESP32-DIV V2 map.
INFERRED: octal PSRAM on the ESP32-S3 uses GPIO 35, 36 and 37 for its data and strobe lines, so enabling it would put the PSRAM controller and the display on the same pins. This is not tested. Treat PSRAM as unavailable; do not enable `psram` build overrides on this board without a dedicated qualification, and note that the `enabled` (quad) override does not match this octal part.

## Boot reading

MEASURED: opening the serial port resets the board, so every serial capture begins with the boot ROM lines (`rst:0x1 (POWERON)` for a power-on or port-open reset). A build PASS is not hardware verification, and a successful flash is not application success: only the application's own serial output (`[boot] ready`) proves the firmware started.
