# ESP32-DIV v2 engineering guide 8: memory and heap budget

Evidence: MEASURED from job `t45-h1-serial` (2026-11-17, firmware with `[heap]` markers, `TEST_ALL` run), CONFIG for the pinned Arduino core 2.0.10 build settings.

## The budget in one line

The qualified profile has no PSRAM, so everything runs from internal heap. It starts at about 197 KB free (largest block 163,828 bytes) and is down to **13,584 bytes free, largest block 7,668 bytes, at `[boot] ready`**. There is almost no headroom: any feature that needs a block over about 7 KB right after boot can fail.

## Boot heap ledger (bytes)

| Step | Free | Largest block | Change |
| --- | --- | --- | --- |
| setup start | 196,852 | 163,828 | |
| after tft.init | 196,620 | 163,828 | -232 |
| after logo | 196,596 | 163,828 | -24 |
| after initSDCard | 123,480 | 90,100 | **-73,116** |
| after oui::init | 123,480 | 90,100 | 0 (no OUI database on the card) |
| after settingsLoad | 123,480 | 90,100 | 0 |
| after BLE stack | 75,392 | 65,524 | **-48,088** |
| after background scanners | 66,448 | 57,332 | -8,944 |
| after status bar and touch | 63,936 | 55,284 | -2,512 |
| after Wi-Fi scan and TX self-test | 15,228 | 7,668 | **-48,708** |
| boot ready | 13,584 | 7,668 | -1,644 |

The four large consumers are the SD mount (73 KB), the Wi-Fi radio start with the boot scan and TX self-test (49 KB), the NimBLE stack (48 KB, `[ble] init begin, free heap=122520` then `init done, free heap=75392`) and the two background scanner tasks (9 KB). Display initialisation and the touch controller are negligible. The Wi-Fi and BLE figures are for starting the stacks, so they are paid at boot whether or not a feature needs them yet.

## Why the SD mount costs 73 KB

CONFIG: the pinned core's `sdkconfig` has `CONFIG_WL_SECTOR_SIZE 4096`, so the FatFs configuration sets `FF_MAX_SS` to 4096. Every FatFs file object and the filesystem window then carry a 4096-byte sector buffer, so each open-file slot reserves about 4.2 KB. The firmware originally mounted with `max_files` 16, which is 16 slots plus the window, about 72 KB; the measured drop is 73,116 bytes. The ledger also fits a remount with 8 files: after `TEST_SUBGHZ` the free heap rose by 33,068 bytes, which is the 16-file mount released (about 73 KB) minus an 8-file mount (about 38 KB) minus about 2 KB for the CC1101 initialisation. INFERRED: 4 files would cost about 21 KB, so `max_files` is a direct memory dial, about 4.2 KB per slot.

The original code comment says the default of 5 was too small because the app holds the OUI file plus up to four feature logs; 8 slots therefore probably covers the real maximum, but no test of every feature with 8 slots has been run.

## What this means for the T-0045 fix

The 16-file mount needs one large contiguous block. After boot and the first remount the largest block is 32,756 bytes, so it cannot be allocated again, which is why the SD restore failed after the CC1101 test. The fallback in `sdMountChipSelect()` keeps the card usable and prints which size it got, for example `[sd] mounted with max_files=8 (heap largest block 32756 too small for 16)`; since 2026-11-17 the list is 8 then 4 (see below).

## Applied: default max_files 8 (job `t45-m8`, 2026-11-17)

`sdMountChipSelect()` now asks for 8 slots and falls back to 4. MEASURED result: the SD mount cost fell from 73,116 to 40,020 bytes, free heap at `[boot] ready` rose from 13,584 to 46,688 bytes and the largest block from 7,668 to 34,804 bytes (setup start is unchanged at 196,852). `TEST_ALL` still reports `CC1101 OK` and `QR: SD available: YES`.
Trade-off (MEASURED): after the CC1101 test the largest free block is 38,900 bytes, just under what 8 slots need, so the remount logs `[sd] mounted with max_files=4 (heap largest block 38900 too small for 8)`. After a radio operation the card therefore has 4 file slots until the next reboot, and a feature that holds more than 4 files open at once would fail with ENFILE then. The original code comment says the app keeps the OUI file plus up to four feature logs open; no test of every feature at 8 or 4 slots has been run.

## Options still open

Defer the BLE stack and the two scanners until a BLE feature is opened (the classic-ESP32 path of this firmware already does this): would return about 57 KB at boot and leave a larger contiguous block for the SD remount, which would restore 8 slots after radio tests. Move the boot-time Wi-Fi scan and TX self-test to an on-demand command: the radio start costs 49 KB, but Wi-Fi tools would then pay it when first used. Reduce fragmentation so the remount can get 8 slots again. PSRAM is not an option on this board: its pins are the display's (see guide 1).

## How to measure heap in this firmware

A `heapMark("tag")` helper in `include/main.cpp` prints `[heap] <tag> free=<n> largest=<n> min=<n>` at each boot step and around the test commands; use it, or print `ESP.getFreeHeap()`, `ESP.getMaxAllocHeap()` and `ESP.getMinFreeHeap()` directly. The largest block decides whether a big allocation works; the minimum is the low-water mark since boot (11,676 bytes after boot here).
