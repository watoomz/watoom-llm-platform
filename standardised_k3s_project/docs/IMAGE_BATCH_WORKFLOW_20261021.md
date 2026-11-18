# Explicit image batches — 2026-10-21

The image skill distinguishes a distinct requested output from a retry. Discover once, queue one stable request per requested image in the same native turn, report exact returned IDs and accepted/requested counts, then end the turn. Default to one only when no count is specified. The worker processes jobs serially; verified receipts are delivered automatically. Do not invent a review gate between stills; preserve user-requested staged review and actual native guards.

The image-size form default preserves explicit counts. The maintained and installed skill match and the native skill catalog exposes WATOOM_IMAGE_EXPLICIT_BATCH_V1 after cache warmup. No image rebuild is needed.

Three neutral regression tests pass: three distinct FIFO jobs with scoped receipts, idempotent/conflicting retries, and negative-prompt forwarding. No production images or sessions were started. The first image finished and restored the chat model before cancellation could be applied; no other jobs remained queued. Active GPU generation currently has no supported mid-inference cancellation parameter; cancellation must not be falsely claimed.

Evidence: /data/ai/helper-scripts/reports/image-batch-workflow-20261021.
