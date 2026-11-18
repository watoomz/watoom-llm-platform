
## You can see images; large ones are dropped before you do
Your model (`swift-qwen38-coder`, `qwen38-uncensored-mtp`, `tiel-coder-35b-a3b-mtp`) is a verified vision model: an image returned by `read` reaches you as real pixels. But the host silently drops an image it cannot shrink below its size limit and says so in the tool result: `[1 image omitted: could not be resized below the image size limit.]`. When you see that note, you did NOT see the image, and the guard will not count it as presented. That is a size problem, not a missing vision model: never report `VISION_MODEL_REQUIRED` or BLOCKED because of it, and never describe pixels you did not receive.

Avoid it up front. Before reading any image that is larger than about 2000 px on a side or 1.5 MB (textures, atlases, full-resolution renders, heightmaps), check it with `identify -format '%wx%h %b\n' "<image>"` and read a reduced copy instead:
`mkdir -p "<project>/.opencode/work/review" && convert "<image>" -alpha off -resize '1536x1536>' "<project>/.opencode/work/review/<name>-1536.png"`
(ImageMagick `convert` and Python PIL are installed). For detail, crop a region at full resolution with `convert "<image>" -crop 1024x1024+X+Y +repage ...`. In your review say that you looked at a downscaled copy and give its path. Read the large original only after a smaller copy has shown it is worth it.
