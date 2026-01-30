# Media Processing

## Originals
- Originals are read-only and never modified.
- Derived assets (thumbnails, transcodes, metadata DB) live in separate storage.

## Thumbnails
- Precompute thumbnails for fast grid rendering.
- Multiple sizes for responsive layouts (exact sizes TBD).

## Video
- Pre-transcode to multiple qualities.
- Adaptive streaming (auto quality adjustment based on connection).
- No requirement for live transcoding; pre-transcode is acceptable.

## Live Photos
- Treat as paired assets (still + short video).
- Hover in grid plays video inline with no sound.
