---
name: safe-edit
description: Explicit fallback for stale exact-string edits: hash-anchor a file range and fail closed if the current file no longer matches the lines that were read.
metadata:
  opencode/autoinvoke: false
---

# Safe edit fallback

Use normal OpenCode editing first.

If an exact edit fails because text is stale:

1. reread the exact region;
2. retry once with current text;
3. only then use the WatooM hashline helper.

Read anchors:

```bash
node ~/.config/opencode/watoom-tools/watoom-hashline.mjs read src/main.ts 180 240
```

Replace an anchored range:

```bash
node ~/.config/opencode/watoom-tools/watoom-hashline.mjs replace \
  src/main.ts \
  START_LINE START_HASH \
  END_LINE END_HASH \
  .watoom/replacement.txt
```

If either boundary hash changed, the helper refuses the edit.
