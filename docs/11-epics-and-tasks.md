# Epics and Tasks (Draft)

This is a decomposition into small, independently executable tasks. Dependencies are noted explicitly.

## Epic A: Foundations
- A1: Define storage layout conventions (originals/derived/temp) in code constants.
  - Accept: single config struct maps to absolute paths.
- A2: Add environment/config loader with sane defaults.
  - Accept: app starts with local defaults and prints effective config.
- A3: Set up DB migrations and versioning.
  - Accept: `migrate up` creates all required tables.
- A4: Add Redis connection and job queue wrapper.
  - Accept: can enqueue/dequeue a test job.
- A5: Add typing + lint baseline (mypy/pyright + ruff).
  - Accept: type check and lint commands run in CI or locally.

## Epic B: Auth and Sessions (Passkeys)
- B1: Implement WebAuthn registration options endpoint.
  - Accept: returns challenge + RP info + user info.
- B2: Implement WebAuthn registration verify endpoint.
  - Depends: B1.
  - Accept: credential stored; duplicate registrations handled.
- B3: Implement WebAuthn login options endpoint.
  - Accept: returns challenge for registered user.
- B4: Implement WebAuthn login verify endpoint + session cookie.
  - Depends: B3.
  - Accept: valid passkey creates session; invalid rejected.
- B5: Add auth middleware for owner-only routes.
  - Accept: owner endpoints require session.

## Epic C: Indexing
- C1: File type registry (image/video/Live Photo pairs).
  - Accept: detect Live Photo pair by filename conventions.
- C2: Full scan job to index watched folders.
  - Accept: creates/updates assets in DB from disk.
- C3: Filesystem watcher for incremental changes.
  - Depends: C2.
  - Accept: add/move/delete reflected in DB.
- C4: Move/delete reconciliation logic.
  - Accept: moved files preserve asset identity; deletes remove assets.

## Epic D: Media Processing
- D1: Metadata extraction job (EXIF + ffprobe).
  - Depends: C2.
  - Accept: captured_at, dimensions, duration, lat/lon stored.
- D2: Thumbnail generation job for images.
  - Depends: D1.
  - Accept: multiple sizes written to derived storage.
- D3: Poster frame extraction for videos.
  - Depends: D1.
  - Accept: still image available for video assets.
- D4: Video transcode job (multi-quality).
  - Depends: D1.
  - Accept: produces HLS/DASH manifests + segments.
- D5: Live Photo pairing logic.
  - Depends: C1, D1.
  - Accept: still + short video linked in DB.

## Epic E: Library API
- E1: Timeline API with cursor pagination.
  - Depends: D1.
  - Accept: returns newest-first list with next cursor.
- E2: Asset detail API.
  - Accept: includes metadata and available variants.
- E3: Location + date range filters.
  - Accept: bbox and from/to applied.
- E4: Original file download with range support.
  - Accept: supports large videos and resumable downloads.

## Epic F: Albums and Sharing
- F1: Album CRUD endpoints.
  - Accept: create/update/delete albums.
- F2: Album item add/remove endpoints.
  - Accept: updates album contents and counts.
- F3: Share link creation endpoint.
  - Accept: returns unguessable token.
- F4: Share link revocation endpoint.
  - Accept: token invalidated immediately.
- F5: Public album endpoints (token-based).
  - Depends: F3.
  - Accept: only album content exposed.

## Epic G: Downloads
- G1: Album ZIP job creation.
  - Depends: F2.
  - Accept: creates ZIP from originals.
- G2: ZIP cache invalidation on album change.
  - Depends: G1.
  - Accept: add/remove invalidates cached ZIP.
- G3: ZIP download endpoint.
  - Accept: streams ZIP to viewer.

## Epic H: Frontend (Owner)
- H1: App shell + routing.
  - Accept: public vs owner routes separated.
- H2: Passkey sign-in UI.
  - Depends: B1-B4.
  - Accept: owner can log in.
- H3: Timeline view with infinite scroll.
  - Depends: E1.
  - Accept: thumbnails load progressively.
- H4: Album list + album grid view.
  - Depends: F1.
  - Accept: list albums and contents.
- H5: Multi-select + action menu.
  - Depends: F2.
  - Accept: add/remove from albums.
- H6: Viewer with hover arrows and prev/next navigation.
  - Accept: arrows appear on hover and navigate.
- H7: Live Photo hover playback (silent).
  - Depends: D5.
  - Accept: inline hover play; no viewer hover play.
- H8: Video viewer with adaptive streaming.
  - Depends: D4.
  - Accept: quality adapts to bandwidth.
- H9: Date range + location filter UI.
  - Depends: E3.
  - Accept: filter updates timeline.

## Epic I: Frontend (Public Album)
- I1: Public album view (token route).
  - Depends: F5.
  - Accept: album only; no owner features.
- I2: Public viewer navigation and playback.
  - Depends: H6-H8.
  - Accept: same viewer UX as owner.
- I3: Album ZIP download UI.
  - Depends: G3.
  - Accept: download starts from public view.

## Epic J: Observability and Ops
- J1: Health endpoints.
  - Accept: /health returns OK.
- J2: Structured logging for jobs and API.
  - Accept: log includes request/job IDs.
- J3: Metrics placeholders (future).
  - Accept: minimal counters for jobs and API.

## Epic L: Testing
- L1: Unit test harness for core modules (TDD workflow).
  - Accept: tests run in CI and locally with coverage report and 90%+ unit coverage.
- L2: API integration test suite (auth, timeline, albums, share links).
  - Depends: B1-B5, E1, F1-F5.
  - Accept: tests run against a temporary DB and pass reliably.
- L3: Media pipeline integration tests (indexing + thumbnails + transcodes).
  - Depends: C2, D2, D4.
  - Accept: tests run with small fixtures and verify derived outputs.
- L4: Enforce coverage thresholds in CI.
  - Accept: CI fails if unit coverage < 90%.

## Epic K: Stretch (Duplicates)
- K1: Compute perceptual hash for images.
  - Accept: hash stored per image asset.
- K2: Duplicate candidate query.
  - Depends: K1.
  - Accept: returns sets of near-duplicates.
