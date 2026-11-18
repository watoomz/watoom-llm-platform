#!/bin/sh
# Copy Dispatcharr's live Web_stream playlist next to VLC's service-discovery script (atomic replace).
set -eu
URL="${DISPATCHARR_PLAYLIST_URL:-http://10.99.20.225:9191/output/m3u/Web_stream}"
OUT="${VLC_PLAYLIST_FILE:-/home/watoom/.local/share/vlc/dispatcharr-web_stream.m3u}"
TMP="$OUT.tmp"
curl -fsS --max-time 20 "$URL" -o "$TMP"
grep -q '^#EXTM3U' "$TMP"
mv -f "$TMP" "$OUT"
