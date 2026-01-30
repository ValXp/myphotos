# Implementation Plan (Index)

## Intent
This plan is split into focused implementation plans for each major subsystem. Use the individual plans for day-to-day execution and sequencing; this file provides the ordering and shared standards.

## Plan Index (major parts)
1) Foundations and tooling: `docs/plans/01-foundations-and-tooling.md`
2) Auth and sessions (passkeys): `docs/plans/02-auth-and-sessions.md`
3) Indexing and ingest: `docs/plans/03-indexing-and-ingest.md`
4) Media processing pipeline: `docs/plans/04-media-processing.md`
5) Library APIs (browse + assets): `docs/plans/05-library-apis.md`
6) Albums, sharing, and downloads: `docs/plans/06-albums-sharing-downloads.md`
7) Frontend (owner app): `docs/plans/07-frontend-owner.md`
8) Frontend (public album): `docs/plans/08-frontend-public.md`
9) Observability and quality gates: `docs/plans/09-observability-and-quality.md`

## Dependency Order (MVP)
- Foundations and tooling
- Auth and sessions (unblocks owner app and protected APIs)
- Indexing and ingest
- Media processing pipeline
- Library APIs
- Albums, sharing, and downloads
- Frontend owner app
- Frontend public album
- Observability and quality gates (begins early; enforced by MVP exit)

## Cross-Cutting Standards
- TDD workflow: unit tests written before implementation.
- Unit coverage >= 90% for core modules.
- Integration tests for each major feature (auth, indexing, media processing, albums/shares, downloads, timeline).
- Originals are read-only; derived assets live in separate storage.
- Timeline is cursor-paginated, newest-first.
- Public routes must be limited to album-only data.

## MVP Exit Criteria (system-wide)
- Passkey login works for the owner and protects private routes.
- Indexer reflects add/move/delete and creates assets in the DB.
- Thumbnails and video transcodes are generated ahead of time.
- Timeline loads quickly using thumbnails only.
- Albums can be created, shared via unguessable link, and revoked.
- Public album view exposes only the shared album and can download originals.
- Album ZIPs are generated on demand and invalidated on changes.
- All tests pass; coverage threshold enforced in CI.
