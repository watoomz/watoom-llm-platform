---
name: watoom-asset-archive
description: List, inspect, read and extract assets from zip, tar, 7z and rar packs into a project, including just the subset you need, with errors reported instead of hidden.
---
# Asset archives (zip, tar, 7z, rar)

Use this tool whenever an asset pack is an archive: to see what is inside, read one file (a README, licence, `.import`, JSON), or extract all or part of it into a project.
Do not unzip by hand and do not extract a whole big pack when you only need some of it.

```
python3 /config/skills/watoom-asset-archive/scripts/asset_archive.py <op> <archive> [options]
```

Archives must be under `/data/ai/assets`, `/data/ai/projects` or `/data/ai/artifacts`. Output is one JSON document. **Always check `ok`, `errors` and `warnings` before you say the asset is usable.**

| op | what it does |
|---|---|
| `list ARCHIVE [--prefix DIR] [--select GLOB] [--ext png,glb] [--limit N]` | files that match, with sizes; use it first on big packs |
| `inspect ARCHIVE [--test]` | file count, size, top folders, extensions, largest files; `--test` reads every file and checks size/CRC (zip, tar) |
| `read ARCHIVE --entry PATH [--max-bytes N]` | text of one file (binary is described, not dumped; `--base64` returns bytes) |
| `extract ARCHIVE --project NAME --select/--prefix/--ext ... [--dest DIR] [--strip N] [--dry-run]` | extract only what you selected into the project |
| `status REQUEST_ID` | result of a request still running on the host worker |

## Extracting a subset
1. `list` (or `inspect`) to learn the entry paths. Globs use `*` within a folder and `**` across folders, for example `--select 'Pack/Models/**' --ext glb,gltf,bin`. Repeat `--select`; use `--exclude` to drop things.
2. `extract ... --dry-run` first. It shows the file count, size, clashes and errors and writes nothing.
3. Run the real `extract`. The default destination is `Assets/<archive name>/` inside the project; use `--dest` for another folder and `--strip 1` to drop a wrapper folder. `--project` is the folder name (`zombie-animal-survival`) or its absolute path under `/data/ai/projects/<category>/<name>`.
4. Extraction is skipped for files that are already there and identical (`unchanged`). A different existing file is an error unless the owner wants it replaced (`--overwrite`).
5. Every extracted file is checked against the archive's size and CRC. A receipt is written to `<project>/.opencode/asset-extractions/`.
6. Then run the project's import job so Godot imports the new files. Extracting alone does not import anything.

## Reading the result
* `ok: false` means something is wrong. `errors[].code` says what; `entry` names the file. Nothing flagged is silently skipped.
  Common codes: `ARCHIVE_UNREADABLE` or `SIZE_MISMATCH` or `CRC_MISMATCH` (truncated or corrupt download: tell the owner, do not retry blindly), `ENCRYPTED_ENTRY` (needs a password: ask the owner),
  `UNSAFE_NAME` (path traversal or absolute path in the archive: refused), `CASE_CLASH` (two files differ only by letter case: cannot exist on Windows), `DEST_CONFLICT`, `SELECTION_TOO_LARGE` or `BOMB_SUSPECT` (select a subset; `--force-large` only with the owner's approval), `DISK_FULL`, `NOTHING_SELECTED`.
* `warnings` are things that were skipped on purpose: symlinks and special files are never extracted, and `__MACOSX`, `.DS_Store` and `Thumbs.db` are dropped (`junk_skipped`).
* If any entry failed, report exactly which ones. The pack is incomplete until they are fixed. `--partial-ok` extracts the clean files anyway, but say so in your report.
* 7z and rar are opened by a host worker. The tool submits the request and waits (up to `--wait` seconds, default 180). If it prints `pending: true`, check later with `status <id>`; do not resubmit.

## Rules
* Respect each pack's licence. Some licences forbid using the content as AI reference or training material; do not add such packs to searchable indexes or memory without the owner saying it is allowed.
* Never extract into `.git`, `.godot` or `.opencode`; the tool refuses it.
* Needs a password, a missing part of a multi-part archive, or a corrupt file are owner decisions. Stop and report.
