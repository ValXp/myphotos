# Plan 04: Media Processing

## Goals
- Extract metadata and generate derived media for fast browsing and playback.
- Produce multi-quality video transcodes for adaptive streaming.

## Scope
- Metadata extraction using exiftool and ffprobe.
- Thumbnail generation for images and video posters.
- Video transcodes and streaming manifests (HLS or DASH).
- Live Photo pairing and short video variants.

## Out of Scope
- On-the-fly transcoding.
- Face recognition or advanced AI tagging.

## Dependencies
- Plan 03: Indexing and Ingest (assets exist in DB).

## Deliverables
- Metadata extraction job that persists captured_at, dimensions, duration, and location.
- Thumbnail generation job with multiple sizes.
- Video poster extraction and multi-quality transcode job.
- Derived assets stored in dedicated storage with AssetVariant records.

## Steps
1) Define variant profiles (thumb sizes, video renditions, poster size).
2) Implement metadata extraction job (EXIF + ffprobe) and persist results.
3) Implement thumbnail job using libvips for images and poster frame extraction for videos.
4) Implement video transcode job producing manifests and segments.
5) Implement Live Photo linking logic and live-video variant generation.
6) Add retries and failure reporting for media jobs.

## Tests and Acceptance
- Integration tests on small fixtures for EXIF, video duration, and dimensions.
- Generated thumbnails exist for multiple sizes and are readable.
- Transcode job outputs manifests and segments with expected profiles.
- Live Photo pairs link correctly and play silently in grid.
