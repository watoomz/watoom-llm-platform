# The verify loop (stage a): how you see

You cannot look at an image. You measure it, and you read the engine log. Never judge a look before both are clean.

## Commands

```bash
S=<skill>/scripts
python3 $S/gg_verify.py selftest                                   # once per host; both renderers; ~1 minute
python3 $S/gg_verify.py shot --project P --scene res://levels/x/x.tscn --out OUT --view '{"name":"hero","kind":"3d","position":[0,3,8],"look_at":[0,1,0],"fov":60}'
python3 $S/gg_verify.py measure OUT/hero.png --targets targets.json
python3 $S/gg_verify.py compare before.png after.png --expect brighter
python3 $S/gg_verify.py log godot.log
```

`shot` writes `OUT/<view>.png` and `OUT/verify_report.json`, and prints p5/p50/p95 luma, saturation, clipped fractions, colour count and each failed target with a hint.

## Exit codes (every gg_*.py)

| Code | Meaning | What you do |
|---|---|---|
| 0 | pass | go on |
| 1 | a check failed (metric out of target, blank frame, wrong size) | read the FAIL line and its hint; change ONE thing; shoot again |
| 2 | refused: bad input (names both values) | fix the command or the file it names |
| 3 | fatal line in the engine log (script, shader, load or plain ERROR:) | read the printed log line; fix that; the image is NOT valid |
| 4 | no verdict: timeout, crash, GPU error, no result, no `@@GG_DONE@@` | read `godot.log` in the job directory (path printed as job_dir); the cause of a hang is not known in advance, the log says; on a GPU error the wrapper already waited 20 s and retried once (that path is not exercised by the selftest) |
| 5 | the runner reported failure (message printed) | fix what the message says |

Precedence when several apply: 4, 3, 5, 1. **Godot exits 0 even when it printed ERROR:** (measured: `look_at()` on a node outside the tree). The wrapper reads the log, not the exit code.

## After EVERY deliberate change, prove the loop saw it

Take a shot before and after, then `compare --expect <what you intended>` (brighter, darker, more-saturated, less-saturated, tint-r/g/b, different, same). `different` needs at least 1% of pixels changed by more than 2/255, `same` at most 0.1%; the output also prints the changed-pixel percentage, so a small change is visible. Two images of different sizes are refused (exit 2) naming both sizes. If you changed something and `compare --expect different` fails, your change did not reach the pixels: a failed shader or script is the usual cause, so read the log first.

## Rules the wrapper enforces

- `shot` refuses (exit 2) until `gg_verify.py selftest` has passed for the same renderer and the same godot binary. Pass `--renderer` equal to the project's preset renderer; a result from another renderer is refused.
- Bad views (unknown kind or key, duplicate or missing name) and malformed targets are refused before Godot starts. For several views use `--views-file views.json` instead of shell-quoted JSON.
- Before a run the old `<view>.png` and `verify_report.json` are deleted; images from a run with exit 3, 4 or 5 are renamed `<view>.INVALID.png`, so a stale or invalid picture can never be measured.
- `measure` and `shot` use the same default tolerance (0.01).

## Metrics (all on the encoded 8-bit sRGB values, 0..1, after tonemapping)

luma Y = 0.2126R + 0.7152G + 0.0722B; `luma_p1/5/50/95/99/mean/std`; `sat_mean`/`sat_p95` = HSV saturation over pixels with max >= 0.08; `clip_black` = fraction with Y <= 2/255; `clip_white` = fraction with min(R,G,B) >= 250/255; `unique_colors` (cap 65536); `flat_fraction` = pixels equal to both right and down neighbours; `local_contrast`; `grid_integrity` (with `--block K`) = fraction of KxK blocks that are one colour (pixel art). Targets are `{"metric": [lo, hi]}`, null = open end. Hard failures regardless of targets: `luma_std < 0.01` (blank), `clip_black > 0.5` (black), size differs from the request.

## What the selftest proves (measured 2026-11-16, Godot 4.7.2 Fedora build under xvfb; forward_plus ran on the NVIDIA GPU, gl_compatibility ran on `llvmpipe` software GL: the adapter is recorded in the report; about 60 s per renderer)

1. A shot has real pixels. 2. Repeating a shot gives an identical image (noise floor 0). 3. Doubling light reads brighter (p50 +0.145..+0.149). 4. A red albedo reads tint-r (+0.076). 5. An unshaded colour round-trips exactly (max delta 0 on both renderers, linear tonemap). 6-8. A broken shader, a script syntax error and a `look_at` on an off-tree node are all caught from the log (the engine exits 0 for the last). 9. An op that never finishes ends with exit 4 and a `why` starting `timeout` or `no verdict` (headless runs are not throttled, so the engine's own `--quit-after` limit can end the run before the wall-clock timeout; either way there is no `@@GG_DONE@@`). 10. A missing scene is exit 3 naming the path. If any of 6-8 returned 0 the selftest would say "verify loop is BLIND": do not trust the loop on that host.

## Measured engine facts used here

- `--headless` has no pixels: render ops run under `xvfb-run`. `--audio-driver Dummy` removes the PulseAudio errors.
- Real log wording (Godot 4.7.2): `SCRIPT ERROR: Parse Error: ...`, `SHADER ERROR: Unknown identifier in expression: 'x'.` plus `ERROR: Shader compilation failed.`, `ERROR: Cannot open file 'res://missing.tscn'.`, `ERROR: Node not inside tree. Use look_at_from_position() instead.`
- `godot --headless --import --quit` prints a spurious `ERROR: Parameter "singleton" is null` (fixture `scripts/fixtures/import_quit.log`); `--import` without `--quit` did not. The wrapper imports before every run.
- A parse error in a builder script prints `SCRIPT ERROR: Parse Error` and later `Invalid call. Nonexistent function 'new'`; the run still reaches `@@GG_DONE@@` and the wrapper returns exit 3 (measured). A run that never prints `@@GG_DONE@@` (hang, crash) is exit 4.
- The first run in a fresh project creates `.godot/` by importing; the wrapper does that first.
