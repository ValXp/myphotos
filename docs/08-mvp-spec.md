# MVP Specification

## Goals
- Fast browsing of a large personal library (100k photos, 13k videos).
- Easy album sharing via unguessable public links.
- Reliable background indexing from watched folders.
- High-quality, adaptive video streaming.

## Non-Goals (MVP)
- Face recognition.
- In-app photo/video editing.
- Mobile auto-backup.
- App-level backups.
- Multi-tenant user management.

## User Stories
- As an owner, I can sign in with a passkey to manage my library.
- As an owner, I can browse my entire library in an infinite timeline.
- As an owner, I can filter by date range and location (lat/long).
- As an owner, I can create albums and add/remove items via multi-select.
- As an owner, I can share an album via an unguessable link and invalidate it.
- As a viewer, I can open an album link and browse only that album.
- As a viewer, I can download originals, including a full-album ZIP.
- As a viewer, I can watch videos with adaptive quality.
- As a viewer, I can view Live Photos as stills with hover playback.

## Functional Requirements
- Web app supports desktop + mobile web.
- Timeline infinite scroll, newest first.
- Album list for owner; public viewers see only linked album.
- Viewer supports prev/next with hover-revealed arrows.
- Live Photos: hover to play inline, no sound; no hover playback inside viewer.
- Video viewer: video player present; still image available full-size with zoom.
- Original files are read-only and never modified.
- Derived assets stored separately (thumbs, transcodes, metadata DB).
- Precomputed thumbnails for fast grid loading.
- Pre-transcoded multi-quality videos with adaptive streaming.
- Background indexing monitors folders and detects add/move/delete.
- Whole-album ZIP generated on demand, cached, invalidated on album changes.

## Acceptance Criteria (MVP)
- Owner can sign in via passkey and reach a private library view.
- Timeline loads thumbnails without fetching originals.
- Video playback adapts quality on constrained bandwidth.
- Live Photos play on hover in grid and stay silent.
- Album sharing link exposes only that album and can be invalidated.
- Album ZIP download completes and uses originals only.
- Indexer reflects filesystem changes (add/move/delete) into the UI.
- Each major feature includes integration tests as acceptance criteria.
- Unit test coverage is 90%+ for core modules.

## Open for Later
- Duplicate detection.
- Advanced metadata filters (camera model, lens, etc.).
- Geocoded place names (reverse geocode).
- Native mobile apps.
