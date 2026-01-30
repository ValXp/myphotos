# Architecture

## Proposed Stack (default)
- Backend: Python (FastAPI for API + background workers).
- Frontend: React + Vite (static build served by API).
- DB: Postgres.
- Queue/Cache: Redis (RQ or Celery).
- Media tools: ffmpeg/ffprobe, exiftool, libvips, libheif.
- Typing: Pydantic models + mypy/pyright.
- Testing: pytest + coverage + httpx/pytest-asyncio for integration tests.

## Components
- Reverse proxy (nginx): terminates HTTPS and forwards to API.
- API server:
  - Auth (passkey), albums, shares, browsing, downloads.
  - Serves web app.
- Indexer service:
  - Watches folders and triggers scans.
  - Periodic full scan to recover from missed events.
- Media worker:
  - Extracts metadata.
  - Generates thumbnails.
  - Generates video transcodes + manifests.
- Storage:
  - Originals: read-only source folders.
  - Derived: thumbnails, transcodes, manifests.
  - Temp: album ZIP cache.
- Postgres:
  - Assets, albums, shares, metadata, job state.
- Redis:
  - Job queue, short-lived caches (ZIP status, browse cursors).

## Data Flow
1) **Ingest**
   - Indexer watches folders and detects add/move/delete.
   - Assets are registered in Postgres.
   - Jobs are queued for metadata + thumbnails + transcodes.

2) **Processing**
   - Worker reads originals, writes derived assets to derived storage.
   - Metadata is persisted to Postgres.

3) **Browse**
   - Timeline queries Postgres with cursor-based pagination.
   - Thumbnails served from derived storage.

4) **Share**
   - Album share tokens map to album IDs.
   - Public link uses share token and returns album-only view.

5) **Download**
   - ZIP is generated on demand, stored in temp storage.
   - ZIP invalidated on album changes or delete.

## Notes
- Lat/long stored as numeric fields; reverse geocode deferred.
- Live Photos handled as paired assets (still + short video).
- Adaptive video streaming via HLS/DASH (exact format TBD).
