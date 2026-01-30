# Requirements

## Core
- Single shared library for me + wife (no multi-tenant).
- Private by default; share albums via unguessable public links.
- Public HTTPS handled by nginx reverse proxy; app must respect reverse-proxy headers.
- Web-only UI (desktop + mobile web).
- Infinite scroll timeline, newest to oldest.
- Album list view (owner); public viewers only see the album the link points to.
- No in-app edits.

## Media Support
- Support all modern image and video formats.
- Live Photos (iOS + Android style) supported as paired assets.
- Preserve and display EXIF/metadata including location.
- Metadata filtering (MVP): date range + location.

## Performance
- Precomputed thumbnails for fast grids.
- Pre-transcoded multi-quality videos with adaptive streaming.
- Originals are read-only and untouched; derived assets stored separately.

## Ingest
- Background indexing via folder monitoring.
- Detect add, move, and delete.

## Downloads
- Album viewers can download originals.
- Whole-album ZIP generated on demand and cached; invalidated on album add/remove or delete.

## Out of Scope
- App-level backups.
- Face recognition.
- Mobile auto-backup (existing external sync pipeline handles ingest).
