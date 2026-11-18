# Native ESP32 operations

Project: `/data/ai/projects/llm/esp32`. Stable board ID: `esp32-div-v2`. Profile: `esp32-div-v2-s3`. Fixed operations only:

```json
{"schema":1,"operation":"inventory"}
{"schema":1,"operation":"probe","device":"esp32-div-v2"}
{"schema":1,"operation":"build","source":"/data/ai/projects/llm/esp32/apps/APP","source_sha256":"SOURCE_FINGERPRINT","profile":"esp32-div-v2-s3"}
{"schema":1,"operation":"build","source":"/data/ai/projects/llm/esp32/apps/APP","source_sha256":"SOURCE_FINGERPRINT","profile":"esp32-div-v2-s3","psram":"opi"}
{"schema":1,"operation":"flash","device":"esp32-div-v2","build":"/data/ai/artifacts/esp32/BUILD_JOB","firmware_sha256":"TRUSTED_BUILD_HASH","confirm_flash":true}
{"schema":1,"operation":"monitor","device":"esp32-div-v2","seconds":10,"baud":115200}
{"schema":1,"operation":"serial","device":"esp32-div-v2","seconds":3,"baud":115200,"text":"ping\n"}
{"schema":1,"operation":"restore","device":"esp32-div-v2","backup":"ORIGINAL_FLASH_JOB","backup_sha256":"BACKUP_HASH","confirm_restore":true}
```

Each JSON object is a separate `request.json`, not one JSON file containing all examples. Fresh job ID per distinct operation. Pin the source fingerprint from the installed helper. Before requesting, ensure inputs are complete and the app is in the selected ESP32 project. No direct device/node paths are accepted in a request. `inventory` reports detected USB identities and enrollment; `probe` resets the board to read chip and flash information without writing firmware.

Source budget:128 files/4MiB by default; a full firmware port that exceeds it adds `"source_profile":"large"` to the build manifest (up to 2048 files/16MiB, the operator ceiling; numbers cannot be set per job) and computes `source_sha256` with `request.py <source> --profile large`, only `.ino/.cpp/.c/.h/.hpp` under src/include, no symlinks/build scripts. Fixed SDK: ArduinoCLI1.5.1, Espressif core2.0.10, esptool5.6.0. Qualified FQBN: `esp32:esp32:esp32s3:FlashSize=4M,PartitionScheme=min_spiffs,UploadSpeed=460800,PSRAM=disabled`. Stock DIV patches/libraries are not installed. The initial firmware layout addresses4MiB, matching the original working DIV bootloader on this physical16MiB chip. Remaining flash is not allocated by this layout. SDK-derived bootloader/partition/app offsets are used; never invent offsets for another chip.

Artifact parent `/data/ai/artifacts/esp32` is root-owned. Each operation writes a fresh worker-owned directory. Build receipts pin the merged firmware. Compiler stdout is `compile.log`; flash/backup/verify logs are separate; serial data is `serial.json`. Root-owned authoritative receipts are under `/data/ai/helper-scripts/reports/esp32/<request-id>/result.json`, with matching root-owned `.opencode/esp32-requests/<request-id>.status.json`. Backups are private under `/data/ai/private/esp32`; the model receives only IDs/hashes and cannot replace their bytes. Compilation/serial workers have2GiB,2CPU,zero swap,900s limits. Serial reads1..30seconds/256KiB; serial writes<=256bytes; supported baud9600/57600/115200.

A failed/uncertain write is not replayable. Preserve receipts/backup and use the native status of the same job before a new authorized recovery. Hardware disconnect may require reconnecting or BOOT+RESET; report the actual error once. Enrollment is maintained in authoritative `config/esp32/devices.json` through `ansible/playbooks/watoom-esp32.yml`; agents cannot auto-enroll another device or change allow_flash. A CP2102 serial such as0001 is not unique, so physical USB path and probed chip MAC are also pinned. Moving USB ports needs enrollment review.

Manufacturer reference: https://github.com/cifertech/ESP32-DIV/wiki/Firmware-Upload ; hardware commit90f7967c4dc7bcd8c09ebdcf421886737516ddc2. For desktop Codex operator diagnostics only, host `tools/esp32/runner.py --project /data/ai/projects/llm/esp32 --job JOB --evidence FRESH_EVIDENCE --i-approve` invokes the same fixed worker. It is not an app-shell fallback. Never forge native request messages or receipts.

A flash may optionally include `reuse_backup` (prior flash job ID) and `reuse_backup_sha256`. The broker accepts only a trusted same-board backup and verifies the ENTIRE current flash against it before writing; a mismatch stops the job. This avoids rereading an unchanged full chip during a diagnosed test retry. It is not a bypass of backup preservation. SDK-generated boot headers are preserved during merge/write; never force a conflicting flash frequency/mode after compiling.

The physical chip reports8MiB PSRAM, but OPI-enabled SDK startup did not pass the serial hardware test. The initial application profile disables PSRAM; do not advertise usable PSRAM or enable it without a dedicated memory/startup qualification. Physical capacity and qualified application memory are distinct.

**PSRAM build override (added 2026-11-09):** a `build` request may include an optional `psram` field set to `disabled`, `enabled` or `opi` -- the real esp32s3 Arduino-core menu values (checked against the pinned toolchain's `boards.txt`; `enabled` is QSPI PSRAM, `opi` is OPI PSRAM). It substitutes only the `PSRAM=` segment of the qualified FQBN above; nothing else about the pinned toolchain/layout changes. This is compile-only and never touches the physical board. Re-attempting `opi` is not itself unsafe to *build*, but the prior finding in the paragraph above still stands: do not claim PSRAM works, and do not skip the probe/monitor verification after a flash, until a real hardware cycle (flash with the existing `confirm_flash`/MAC-match/full-backup safety net, then monitor serial boot output) actually re-confirms the board boots and runs correctly with it enabled.
