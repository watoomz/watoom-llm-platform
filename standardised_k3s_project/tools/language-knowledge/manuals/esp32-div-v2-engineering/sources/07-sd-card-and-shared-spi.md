# ESP32-DIV v2 engineering guide 7: the SD card, the shared SPI bus and the T-0045 case

Evidence: MEASURED for serial results (jobs `t45-r29` to `t45-r33`, 2026-11-17), CONFIG for code read from the lab port and from the pinned Arduino core 2.0.10 `SD` library.

## One bus, four devices

The SD card, CC1101, NRF24 modules and (optionally) the PN532 share SCK 12, MISO 13 and MOSI 11 on the ESP32-S3's general SPI peripheral, which the Arduino global `SPI` object owns. Only one chip select may be low at a time. The CC1101 driver's `SpiStart()` runs `SPI.begin(SCK, MISO, MOSI, CC1101_CS)` and `SPI.setFrequency(1000000)`, and `SpiEnd()` runs `SPI.endTransaction()` and `SPI.end()`, so after any CC1101 access the global `SPI` is detached and the SD card must be brought back by code.

## How the Arduino SD library mounts a card (core 2.0.10)

`SD.begin(ssPin, spi, frequency, mountpoint, max_files)` does: if already mounted (`_pdrv != 0xFF`) return true; call `spi.begin()` (a no-op if the bus is already started); `sdcard_init()`, which allocates a drive slot and registers a disk interface but does not talk to the card; then `sdcard_mount()`, which calls FatFs `f_mount` and so triggers `ff_sd_initialize`. That routine takes the SPI bus at 400 kHz, sends 20 idle bytes with CS high, waits for the card to release the line, sends CMD0, then CMD8, then the ACMD41 loop, reads the OCR (CMD58) and finally raises the clock to the requested frequency. `SD.end()` unmounts and frees the slot. The library's `log_e` and `log_w` messages are compiled out in this build, so a failed `SD.begin()` returns false with no explanation.

## The lab's restore path

`isSDCardAvailable()` and `restoreSdAfterSharedSpi()` in `src/utils.cpp` decide whether the card needs remounting; `sdRemountSoft()` releases the other chip selects, calls `SD.end()`, `SPI.end()`, resets the data pins, clocks the card with CS low to reset its state machine, runs a CMD0 probe through bit-banging and through the SPI peripheral, then calls `sdTryBeginOrder()`, which tries the chip selects in order. `sdMountChipSelect(cs)` is the call that finally does `SD.begin(...)`.

## T-0045: SD available NO after the CC1101 test

Symptom (MEASURED): boot mounts the card, but after `TEST_SUBGHZ` the QR test printed `SD available: NO`. Thirteen builds (r15 to r28) changed pins, clocks, CMD0 resets and delays on the SPI side and the serial output stayed byte-identical.

What the diagnostic builds proved (MEASURED): over the global SPI after the CC1101 ran, a raw command sequence worked completely: CMD0 gave 0x01, CMD8 gave 0x01 with echo `000001AA`, ACMD41 became ready after 2 tries, CMD58 gave OCR `C0FF8000`. Calling the library's two stages by hand (`sdcard_init`, `sdcard_mount` from `sd_diskio.h`) worked on a different mount point with 4 files. Unregistering the `/sd` VFS path returned `0x103` (not registered), so it was not a stale mount. `SD.begin(...,"/sd",16)` failed while `max_files` 8 succeeded.

Root cause (MEASURED): heap. The FatFs mount allocates its file table for `max_files` entries as one contiguous block. At the early boot mount the largest free block was 163,828 bytes. After boot finished and the CC1101 test ran it was 69,620 bytes, too small for the 16-file table, so the mount failed even though the card, wiring and bus were healthy.

Fix, first version: `sdMountChipSelect()` tried `max_files` 16, then 8, then 4, calling `SD.end()` between attempts, and printed `[sd] mounted with max_files=N (heap largest block X too small for 16)`. Verified in job `t45-r33`: `CC1101 OK`, `QR: SD available: YES`, `/qr/ files: 0`. Current version (job `t45-m8`): the first choice is 8, then 4, because 16 slots reserve about 72 KB of internal heap; see the memory guide. Do not raise `max_files` without checking heap. The one remaining `TEST_ALL` failure, `PN532 NOT FOUND`, is an unfitted module.

## Techniques worth reusing

Raw SD probe: with CS low send 0xFF, then the six-byte command (0x40 | cmd, four argument bytes, CRC: 0x95 for CMD0 and 0x87 for CMD8 with argument `0x1AA`), then read up to ten bytes until the top bit clears; for ACMD41 send CMD55 first, argument `0x40000000`, and loop until the response is 0x00. If the card answers this but `SD.begin()` fails, the fault is above the card and bus, in the library, memory or mount layer. Stage splitting: call `sdcard_init()` and `sdcard_mount()` yourself and print each result. Heap check: print `ESP.getFreeHeap()` and `ESP.getMaxAllocHeap()` at success and at failure; the largest free block, not the free total, decides whether a large allocation works.

## Rules for new code on the shared bus

Keep `SD_CS` high while any other device uses the bus (`TEST_ALL` does this explicitly). After using the bus call `restoreSdAfterSharedSpi()` and, on the S3 board, `restoreTftSpi()`. Never assume a mount survives a radio operation. Do not hold more than a few KB of heap you can avoid, because the SD mount needs a large contiguous block.
