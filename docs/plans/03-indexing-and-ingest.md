# Plan 03: Indexing and Ingest

## Goals
- Keep the library in sync with watched folders (add/move/delete).
- Register assets in the DB and enqueue downstream processing jobs.

## Scope
- File type registry (image/video/Live Photo pairs).
- Full scan job for watched folders.
- Filesystem watcher for incremental changes.
- Move/delete reconciliation logic.
- Admin endpoint to trigger scans and check status.

## Out of Scope
- Duplicate detection (stretch goal).
- In-app uploads or mobile auto-backup.

## Dependencies
- Plan 01: Foundations and Tooling.

## Deliverables
- File type detection and Live Photo pairing rules.
- Full scan job that creates/updates assets in Postgres.
- Watcher that handles add/move/delete and queues jobs.
- Reconciliation logic that preserves asset identity on moves.

## Steps
1) Define supported file extensions and Live Photo pairing rules.
2) Implement a full scan job that walks watched folders and upserts assets.
3) Implement a watcher that emits add/move/delete events.
4) Add move/delete reconciliation (prefer stable identity based on inode + size + timestamp; fall back to hash if needed).
5) Enqueue metadata/thumb/transcode jobs for new or changed assets.
6) Add admin scan endpoints (start/status) and backoff for large scans.

## Tests and Acceptance
- Integration test with a fixture folder for add/move/delete.
- Move events preserve asset IDs and update paths.
- Delete events remove assets and derived variants.
- Full scan recovers from missed events.
