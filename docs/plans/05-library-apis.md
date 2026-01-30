# Plan 05: Library APIs (Browse + Assets)

## Goals
- Provide fast timeline browsing and asset detail retrieval.
- Serve thumbnails, originals, and streaming variants efficiently.

## Scope
- Timeline endpoint with cursor pagination (newest first).
- Asset detail endpoint with metadata and variants.
- Date range + location (bbox) filters.
- Thumbnail, original, and stream endpoints with range support.

## Out of Scope
- Album management and sharing (handled separately).

## Dependencies
- Plan 04: Media Processing (metadata and variants available).

## Deliverables
- `/assets` timeline endpoint with cursor and filters.
- `/assets/{id}` detail endpoint.
- `/assets/{id}/thumb`, `/assets/{id}/original`, `/assets/{id}/stream`, `/assets/{id}/live` endpoints.
- Range request support for large originals and streams.

## Steps
1) Implement cursor-based pagination with stable ordering.
2) Add date range and bbox filters; index DB fields as needed.
3) Implement detail endpoint exposing variants and metadata.
4) Implement thumbnail and original serving with cache headers.
5) Implement streaming endpoint for transcodes and Live Photo video.

## Tests and Acceptance
- Integration tests for cursor pagination and filters.
- Range request tests for original downloads.
- Thumbnail and stream endpoints return correct content types.
- Public endpoints remain locked down to album-only data (no library exposure).
