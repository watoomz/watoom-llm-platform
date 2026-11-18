---
title: Voice companion (ESP32-S3)
nav: Voice companion
summary: The ESP32-S3 desk companion: a hand-drawn capybara on a 2.8" touch screen that wakes on "Hey Buddy" and talks through the Gemini Live API. Hardware, behaviour, build and flash, and fixes for known faults.
---

## Overview

A small voice assistant on an ES3C28P board (ESP32-S3, 16 MB flash, 8 MB PSRAM, 2.8" 240x320 ILI9341 touch display, ES8311 audio codec). It listens locally for the wake word, then streams the conversation straight from the board to the Gemini Live API over Wi-Fi. No server on this platform sits in the audio path.

| Part | Detail |
|---|---|
| Wake word | "Hey Buddy" (`wn10_en_heybuddy`, ESP-SR WakeNet), recognised on the board. Nothing leaves the board while idle. |
| Conversation | Gemini Live API websocket, model `models/gemini-3.8-live`, voice Kore, English only. |
| Audio | 16 kHz 16-bit mono up. The reply arrives at 24 kHz and is resampled to 16 kHz on the board. Half duplex: the microphone is muted while it speaks. |
| Time | SNTP, time zone `AEST-10` (`TZ_STR` in `main.c`). |
| Source | `/data/ai/projects/devices/grok-voice-esp32s3` (not part of this repository; `main/*.bak` files are the previous versions). The folder name is historical. |

> [!WARNING]
> The Gemini free tier may use submitted audio to improve Google's products, and the Live API is a preview with session limits of about 10 to 15 minutes. The board returns to wake-word mode long before that.

## Behaviour

Everything below is drawn on the screen from the owner's hand-drawn capybara (`art/capybara-handrawn.avif`), with the glow ring around it showing the state.

| State | Capybara | Ring |
|---|---|---|
| Idle | Breathes, blinks, tilts its head curiously, yawns now and then | Slow blue-grey breathing |
| Asleep (after 1 minute idle) | Separate pose: head dropped between the shoulders, paws in front, floating z's, dimmed screen | Faint |
| Connecting | Looks around | Orange spinner |
| Listening | Leans in, cocks its head, nods | Green pulse with an expanding ripple |
| Thinking | Tilts its head, heavy-lidded, thought bubbles | Purple spinner |
| Speaking | Mouth follows the audio level, small bounce | Blue, widening with the voice level |
| Patted (touch on the head) | Eyes shut, nuzzles, blushes, "<3"s, "purr..." | Pink |
| No connection | Shakes its head | Flashing red |

Other on-screen items: a clock (top left), Wi-Fi bars (top right), a volume bar while the volume changes, and a "tap to stop" button during a conversation. The backlight dims from 21:00 to 07:00 and dims further while asleep.

### Controls

| Control | Action |
|---|---|
| "Hey Buddy" | Start a conversation |
| BOOT short press | Start or stop a conversation |
| BOOT long press (0.6 s) | Step the volume 30, 50, 70, 90, 100, then back to 30 |
| Tap the body while idle | Start a conversation |
| Tap the head | Pat him (does not start a conversation) |
| Tap the "tap to stop" button | Stop the conversation |
| Say "volume 30", "louder" and so on | The model calls a `set_volume` tool (0 to 100) |

A conversation ends by itself after 20 seconds with no reply from the model. A sleeping capybara wakes on the wake word, a tap, or a pat.

## Build and flash

The build runs in the Espressif IDF container (`espressif/idf:v5.4.2`) on this server. The board is plugged into the rig, so flashing goes through the rig's `migrate` account.

```bash
cd /data/ai/projects/devices/grok-voice-esp32s3
./build.sh     # writes build/, reads the two secret files below, removes main/secrets.h afterwards
./flash.sh     # copies the images to the rig, flashes COM8, deletes the copies
```

| Secret file | Content |
|---|---|
| `/data/ai/secrets/gemini_api_key` | The Gemini API key (a Google AI Studio key) |
| `/data/ai/secrets/esp32_wifi.env` | `SSID=...` and `PASS=...` |

> [!RULE]
> The key and Wi-Fi password are compiled into the firmware by `build.sh` through a generated `main/secrets.h` that is deleted after the build. Never commit the key, never paste it into chat, and rebuild and reflash after rotating it. The `KEY_FILE` environment variable points `build.sh` at a different key file.

### Rebuilding the artwork

The pictures are generated from the drawing, not hand-edited.

| Step | Command |
|---|---|
| Awake sprite and feature coordinates | `ffmpeg -i art/capybara-handrawn.avif x.png` then `python3 -I tools/make_sprite.py x.png main/capy_sprite.c main/capy_sprite.h` |
| Sleeping pose | `python3 -I tools/make_sleep.py art/capybara-sleep-composite.png main/capy_sleep.c` |

The wake word is chosen in `sdkconfig.defaults` (`CONFIG_SR_WN_WN10_EN_HEYBUDDY`). Custom wake words such as "Hey Cappy" are not available without Espressif's paid training service.

### Reading the board's log

Opening COM8 on the rig resets the board and prints the boot log. Read it over SSH to the rig with a short PowerShell `System.IO.Ports.SerialPort` loop at 115200 baud. A colour test card (five labelled bars) is shown for the first 25 seconds after every reset.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Stuck on "connecting", log shows `esp_ws_handshake_status_code=400` | The API key is invalid. Query `https://generativelanguage.googleapis.com/` with the key from the server to read the exact message, replace the key file, then rebuild and reflash. |
| Log shows `403` or "no credits or licenses" | The key belongs to an account with no usable quota. Use a key from a project that has access to the Live API. |
| Connects, then drops about 2 s later | Wi-Fi power save or a short write timeout aborting the socket. The firmware disables power save and allows 3 s per send; keep both. |
| Replies in another language | The setup message pins `languageCode: en-US` and an English-only instruction. Check both are still in `main.c`. |
| Colours wrong (red shows cyan, white shows black) | The panel is inverted: `esp_lcd_panel_invert_color(p, true)` must stay set. Read the boot test card to tell inversion from a red/blue channel swap. |
| `task_wdt` warning about `taskLVGL` | Too much software rotation or zoom of the sprite. Rotation and zoom are quantised and limited to a few states; keep the idle pose to plain blits and small vertical offsets. |
| Touch does nothing | The log should show `touch controller found (chip id 0x64)` after boot. The controller sits at address 0x38 on the codec's I2C bus. |

## Known limits

- The touch coordinate orientation (head and bottom-button regions) follows the display's vertical axis; if patting the head or tapping "tap to stop" lands in the wrong place, the regions in `touch_task` and `face_tick` need adjusting.
- The clock needs Wi-Fi for its first sync and shows `--:--` until then.
- Weather and other online extras are not implemented.
