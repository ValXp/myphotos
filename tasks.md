# Tasks: myphotos plan decomposition
### Global requirements (apply to all tasks)
- Use implementation_plan.md for ordering and scope; do not reorder plan dependencies.
- Apply cross-cutting standards from implementation_plan.md (TDD first, >=90% unit coverage for core modules, integration tests per major feature, originals read-only with derived storage, timeline cursor pagination newest-first, public routes limited to album-only data).
- Keep tasks bite-sized (1-2 focused changes) and preserve current behavior unless the plan explicitly changes it.
- Acceptance criteria must be objective and verifiable; include exact test/build commands when specified by a plan.
- Use ASCII only.
- It is ok for the "Expand plan" tasks to not have anything to build or test, these are meta tasks and don't require build to be considered successful.
### Task 1: Expand plan 01 foundations and tooling
- Scope: tasks.md, docs/plans/01-foundations-and-tooling.md
- Acceptance criteria:
  - Read docs/plans/01-foundations-and-tooling.md fully.
  - Append new tasks derived from that plan to tasks.md after the last existing task; continue task numbering without gaps.
  - Each appended task follows the tasks.md format (Task N, Scope, Acceptance criteria) and keeps 1-2 focused changes.
  - Include any test or build commands explicitly specified in the plan verbatim in appended task acceptance criteria.
### Task 2: Expand plan 02 auth and sessions
- Scope: tasks.md, docs/plans/02-auth-and-sessions.md
- Acceptance criteria:
  - Read docs/plans/02-auth-and-sessions.md fully.
  - Append new tasks derived from that plan to tasks.md after the last existing task; continue task numbering without gaps.
  - Each appended task follows the tasks.md format (Task N, Scope, Acceptance criteria) and keeps 1-2 focused changes.
  - Include any test or build commands explicitly specified in the plan verbatim in appended task acceptance criteria.
### Task 3: Expand plan 03 indexing and ingest
- Scope: tasks.md, docs/plans/03-indexing-and-ingest.md
- Acceptance criteria:
  - Read docs/plans/03-indexing-and-ingest.md fully.
  - Append new tasks derived from that plan to tasks.md after the last existing task; continue task numbering without gaps.
  - Each appended task follows the tasks.md format (Task N, Scope, Acceptance criteria) and keeps 1-2 focused changes.
  - Include any test or build commands explicitly specified in the plan verbatim in appended task acceptance criteria.
### Task 4: Expand plan 04 media processing
- Scope: tasks.md, docs/plans/04-media-processing.md
- Acceptance criteria:
  - Read docs/plans/04-media-processing.md fully.
  - Append new tasks derived from that plan to tasks.md after the last existing task; continue task numbering without gaps.
  - Each appended task follows the tasks.md format (Task N, Scope, Acceptance criteria) and keeps 1-2 focused changes.
  - Include any test or build commands explicitly specified in the plan verbatim in appended task acceptance criteria.
### Task 5: Expand plan 05 library APIs
- Scope: tasks.md, docs/plans/05-library-apis.md
- Acceptance criteria:
  - Read docs/plans/05-library-apis.md fully.
  - Append new tasks derived from that plan to tasks.md after the last existing task; continue task numbering without gaps.
  - Each appended task follows the tasks.md format (Task N, Scope, Acceptance criteria) and keeps 1-2 focused changes.
  - Include any test or build commands explicitly specified in the plan verbatim in appended task acceptance criteria.
### Task 6: Expand plan 06 albums sharing and downloads
- Scope: tasks.md, docs/plans/06-albums-sharing-downloads.md
- Acceptance criteria:
  - Read docs/plans/06-albums-sharing-downloads.md fully.
  - Append new tasks derived from that plan to tasks.md after the last existing task; continue task numbering without gaps.
  - Each appended task follows the tasks.md format (Task N, Scope, Acceptance criteria) and keeps 1-2 focused changes.
  - Include any test or build commands explicitly specified in the plan verbatim in appended task acceptance criteria.
### Task 7: Expand plan 07 frontend owner
- Scope: tasks.md, docs/plans/07-frontend-owner.md
- Acceptance criteria:
  - Read docs/plans/07-frontend-owner.md fully.
  - Append new tasks derived from that plan to tasks.md after the last existing task; continue task numbering without gaps.
  - Each appended task follows the tasks.md format (Task N, Scope, Acceptance criteria) and keeps 1-2 focused changes.
  - Include any test or build commands explicitly specified in the plan verbatim in appended task acceptance criteria.
### Task 8: Expand plan 08 frontend public
- Scope: tasks.md, docs/plans/08-frontend-public.md
- Acceptance criteria:
  - Read docs/plans/08-frontend-public.md fully.
  - Append new tasks derived from that plan to tasks.md after the last existing task; continue task numbering without gaps.
  - Each appended task follows the tasks.md format (Task N, Scope, Acceptance criteria) and keeps 1-2 focused changes.
  - Include any test or build commands explicitly specified in the plan verbatim in appended task acceptance criteria.
### Task 9: Expand plan 09 observability and quality
- Scope: tasks.md, docs/plans/09-observability-and-quality.md
- Acceptance criteria:
  - Read docs/plans/09-observability-and-quality.md fully.
  - Append new tasks derived from that plan to tasks.md after the last existing task; continue task numbering without gaps.
  - Each appended task follows the tasks.md format (Task N, Scope, Acceptance criteria) and keeps 1-2 focused changes.
  - Include any test or build commands explicitly specified in the plan verbatim in appended task acceptance criteria.
### Task 10: Backend project skeleton and tooling
- Scope: backend project layout (app, tests, migrations, workers), typed tooling config (mypy/pyright + ruff)
- Acceptance criteria:
  - Create the backend directory structure for app, tests, migrations, and workers per plan 01.
  - Add typed Python tooling configuration for mypy/pyright and ruff.
### Task 11: Config loader and storage layout
- Scope: config loader with defaults for paths, DB, Redis, app settings; storage layout resolution (originals, derived, temp)
- Acceptance criteria:
  - Implement config parsing and validation with default values for paths, DB, Redis, and app settings.
  - Resolve storage layout paths for originals, derived, and temp using the config loader.
  - Print the effective config at startup in the backend entrypoint.
  - Unit tests cover config parsing and validation (TDD, >= 90% unit coverage for config module).
### Task 12: ORM models and migrations for core entities
- Scope: ORM models and Alembic migrations for users, passkeys, assets, variants, albums, shares, jobs, zips
- Acceptance criteria:
  - Define ORM models for core entities listed in plan 01.
  - Add Alembic migrations that create all required tables for those entities.
  - Migration test: `migrate up` creates all required tables.
### Task 13: Redis connection and queue wrapper
- Scope: Redis connection, queue abstraction, test job
- Acceptance criteria:
  - Add Redis connection wiring and a queue wrapper that can enqueue/dequeue jobs.
  - Implement a no-op test job handled by the queue wrapper.
  - Queue smoke test enqueues and processes a no-op job.
  - Unit tests cover queue wrapper behavior (TDD, >= 90% unit coverage for queue module).
### Task 14: Health endpoint and DI wiring
- Scope: `/health` endpoint and basic dependency injection wiring
- Acceptance criteria:
  - Add `/health` endpoint to the API shell and return the expected payload.
  - Implement basic dependency injection wiring needed for the health route.
  - `/health` returns 200 with expected payload.
### Task 15: WebAuthn RP settings and session storage
- Scope: auth configuration for RP settings, session storage backend (DB or Redis)
- Acceptance criteria:
  - Define WebAuthn RP settings (RP ID, RP name, allowed origins) in configuration.
  - Implement session storage abstraction with create/validate/revoke operations and TTL handling.
  - Session storage backend (DB or Redis) is wired for the auth module.
### Task 16: Registration options endpoint
- Scope: WebAuthn registration options endpoint
- Acceptance criteria:
  - Add registration options endpoint that returns WebAuthn creation options using RP settings.
  - Persist registration challenge for replay protection and bind it to the session context.
### Task 17: Registration verify endpoint and bootstrap rule
- Scope: WebAuthn registration verification, credential persistence, bootstrap rule
- Acceptance criteria:
  - Implement registration verification endpoint that validates attestation and stored challenge.
  - Persist passkey credential data and sign count for the owner user.
  - Enforce bootstrap rule: if no user exists, allow first registration; otherwise require owner session.
  - Integration tests cover registration happy path and invalid challenge.
  - Registration is blocked when already registered unless an owner session is present.
### Task 18: Login options endpoint
- Scope: WebAuthn login options endpoint
- Acceptance criteria:
  - Add login options endpoint that returns WebAuthn assertion options for the owner.
  - Persist login challenge for replay protection and bind it to the session context.
### Task 19: Login verify endpoint and session cookie
- Scope: WebAuthn login verification, session creation, cookie issuance
- Acceptance criteria:
  - Implement login verification endpoint that validates assertion and stored challenge.
  - Update credential sign count on successful login.
  - Create an owner session and issue a session cookie on successful login.
  - Session cookie is HttpOnly and SameSite with secure flag behind HTTPS.
  - Integration tests cover login happy path and invalid challenge.
### Task 20: Logout endpoint and auth middleware
- Scope: logout endpoint, auth middleware, owner-only guard
- Acceptance criteria:
  - Implement logout endpoint that revokes the active session.
  - Add auth middleware that validates the owner session for protected routes.
  - Owner-only routes reject unauthenticated requests.
  - Public share routes remain unauthenticated.
### Task 21: File type registry and Live Photo pairing
- Scope: file type detection registry, Live Photo pairing rules
- Acceptance criteria:
  - Define supported file extensions for images and videos in a file type registry.
  - Implement Live Photo pairing rules for still/video counterparts.
  - Unit tests cover file type detection and pairing rules (TDD, >= 90% unit coverage for file type registry module).
### Task 22: Full scan job for watched folders
- Scope: full scan job that walks watched folders and upserts assets
- Acceptance criteria:
  - Implement a full scan job that walks watched folders and upserts assets into the database.
  - Full scan detects new and changed assets using the file type registry.
  - Unit tests cover full scan job behavior (TDD, >= 90% unit coverage for scan module).
### Task 23: Filesystem watcher for add/move/delete
- Scope: filesystem watcher that emits add/move/delete events
- Acceptance criteria:
  - Implement a watcher that emits add, move, and delete events for watched folders.
  - Watcher filters events to supported file types and Live Photo pairs.
  - Unit tests cover watcher event emission and filtering (TDD, >= 90% unit coverage for watcher module).
### Task 24: Move/delete reconciliation logic
- Scope: move/delete reconciliation that preserves asset identity
- Acceptance criteria:
  - Implement reconciliation logic that preserves asset identity for moves using inode + size + timestamp, with hash fallback.
  - Move events update asset paths without changing asset IDs.
  - Delete events remove assets and derived variants for removed files.
  - Unit tests cover reconciliation behavior for move and delete cases (TDD, >= 90% unit coverage for reconciliation module).
### Task 25: Enqueue downstream processing jobs
- Scope: enqueue metadata, thumbnail, and transcode jobs for new/changed assets
- Acceptance criteria:
  - Enqueue metadata, thumbnail, and transcode jobs for new or changed assets after scans or watcher events.
  - Jobs are not enqueued for unchanged assets.
  - Unit tests cover job enqueue decisions (TDD, >= 90% unit coverage for ingest job module).
### Task 26: Admin scan endpoints with backoff
- Scope: admin endpoints to start scans and check status, backoff handling
- Acceptance criteria:
  - Add admin endpoints to start a scan and return scan status.
  - Implement backoff handling for large scans.
  - Integration tests cover scan start and status endpoints.
### Task 27: Integration tests for ingest flows
- Scope: integration tests for add/move/delete and full scan recovery
- Acceptance criteria:
  - Integration test with a fixture folder covers add, move, and delete flows.
  - Move events preserve asset IDs and update paths.
  - Delete events remove assets and derived variants.
  - Full scan recovers from missed events.
### Task 28: Media variant profiles and derived mapping
- Scope: variant profile definitions (thumbnail sizes, poster size, video renditions) and AssetVariant mapping
- Acceptance criteria:
  - Define variant profile configurations for thumbnail sizes, video poster size, and video renditions.
  - Derived outputs are written to derived storage and recorded as AssetVariant entries with profile metadata.
  - Unit tests cover profile selection and derived path resolution (TDD, >= 90% unit coverage for variant profile module).
### Task 29: Metadata extraction job
- Scope: metadata extraction job using exiftool and ffprobe
- Acceptance criteria:
  - Implement metadata extraction job that runs exiftool and ffprobe for assets.
  - Persist captured_at, dimensions, duration, and location metadata for assets.
  - Integration tests on small fixtures cover EXIF parsing, video duration, and dimensions.
  - Unit tests cover metadata parsing (TDD, >= 90% unit coverage for metadata module).
### Task 30: Thumbnail and poster generation
- Scope: image thumbnails and video poster extraction
- Acceptance criteria:
  - Implement thumbnail job using libvips for images with multiple sizes.
  - Extract video poster frames and store as derived variants.
  - Generated thumbnails exist for multiple sizes and are readable.
  - Unit tests cover thumbnail sizing and variant creation (TDD, >= 90% unit coverage for thumbnail module).
### Task 31: Video transcode job and manifests
- Scope: multi-quality video transcodes with streaming manifests
- Acceptance criteria:
  - Implement video transcode job that produces multi-quality renditions and streaming manifests (HLS or DASH).
  - Transcode job outputs manifests and segments with expected profiles.
  - Unit tests cover profile selection and output paths (TDD, >= 90% unit coverage for transcode module).
  - Integration tests verify manifest and segment outputs for a small fixture.
### Task 32: Live Photo linking and live-video variants
- Scope: Live Photo pairing metadata and live-video variant generation
- Acceptance criteria:
  - Implement Live Photo linking logic to associate still and video counterparts.
  - Generate live-video variants for paired assets and store as derived variants.
  - Live Photo pairs link correctly and are marked for silent playback in grid.
  - Integration tests cover Live Photo pairing and variant creation.
### Task 33: Media job retries and failure reporting
- Scope: retries and failure reporting for media processing jobs
- Acceptance criteria:
  - Add retry policies with backoff for metadata, thumbnail, and transcode jobs.
  - Record and report failures for media jobs with actionable error context.
  - Unit tests cover retry and failure reporting behavior (TDD, >= 90% unit coverage for media jobs module).
### Task 34: Timeline endpoint with cursor pagination
- Scope: `/assets` timeline endpoint with cursor pagination (newest-first)
- Acceptance criteria:
  - Implement `/assets` timeline endpoint with stable ordering and cursor pagination (newest-first).
  - Integration tests cover cursor pagination behavior.
### Task 35: Timeline filters and indexes
- Scope: `/assets` date range and bbox filters, DB indexing for query fields
- Acceptance criteria:
  - Add date range and bbox filters to the `/assets` timeline endpoint.
  - Add DB indexes needed for filter fields.
  - Integration tests cover date range and bbox filters.
### Task 36: Asset detail endpoint
- Scope: `/assets/{id}` detail endpoint
- Acceptance criteria:
  - Implement `/assets/{id}` detail endpoint exposing metadata and variants.
  - Integration tests cover asset detail responses.
### Task 37: Thumbnail and original endpoints
- Scope: `/assets/{id}/thumb` and `/assets/{id}/original` endpoints
- Acceptance criteria:
  - Implement thumbnail and original endpoints with cache headers.
  - Endpoints return correct content types.
  - Add range request support for original downloads.
  - Range request tests cover original downloads.
### Task 38: Streaming and Live endpoints
- Scope: `/assets/{id}/stream` and `/assets/{id}/live` endpoints
- Acceptance criteria:
  - Implement stream and Live Photo video endpoints for transcodes and live assets.
  - Add range request support for streams.
  - Endpoints return correct content types.
### Task 39: Library endpoint access control
- Scope: library API authorization and public route lockdown
- Acceptance criteria:
  - Library endpoints require an owner session.
  - Public endpoints remain limited to album-only data (no library exposure).
  - Integration tests cover unauthorized access to `/assets` endpoints.
### Task 40: Album CRUD and item management
- Scope: album CRUD endpoints and album item add/remove endpoints
- Acceptance criteria:
  - Implement owner album CRUD endpoints.
  - Implement album item add/remove endpoints.
  - Integration tests cover album CRUD and item management.
### Task 41: Share link lifecycle and public token enforcement
- Scope: share link creation/revocation and token-only access enforcement for public routes
- Acceptance criteria:
  - Implement share link creation and revocation endpoints.
  - Public routes require a valid share token and revocation immediately blocks access.
  - Share token access is limited to its album only.
### Task 42: Public album endpoints and listing scope
- Scope: public album endpoints with album-only asset listing
- Acceptance criteria:
  - Implement public album endpoints that return album metadata and asset listings.
  - Public album listings include only assets in the shared album.
  - Public endpoints do not expose private library data.
  - Integration tests cover public album listing behavior.
### Task 43: Album ZIP job creation and status
- Scope: ZIP job creation and status endpoints
- Acceptance criteria:
  - Implement ZIP job creation endpoint for albums.
  - Implement ZIP job status endpoint for albums.
  - ZIP jobs generate archives from originals only.
### Task 44: ZIP download streaming and cache invalidation
- Scope: ZIP download streaming and album change invalidation
- Acceptance criteria:
  - Implement ZIP download streaming endpoint for albums.
  - ZIP caches are invalidated when album contents change.
  - Public album downloads work without exposing the private library.
### Task 45: Owner app shell and auth gate
- Scope: owner app shell, routing, and authenticated layout
- Acceptance criteria:
  - Implement the owner app shell with routes for timeline, albums, and viewer.
  - Add an auth gate that protects owner routes and renders the authenticated layout.
### Task 46: Passkey sign-in UI and session bootstrap
- Scope: passkey sign-in flow and session bootstrap
- Acceptance criteria:
  - Implement passkey sign-in UI that calls the auth endpoints for registration/login.
  - Successful sign-in boots the authenticated layout with the owner session.
### Task 47: Timeline view with infinite scroll and thumbnails
- Scope: timeline UI with infinite scroll and thumbnail loading
- Acceptance criteria:
  - Build a timeline view that loads assets with cursor pagination and infinite scroll.
  - Timeline loads thumbnails without fetching originals.
  - E2E or integration tests cover sign-in and basic browsing flows.
### Task 48: Album list and album grid views
- Scope: album list UI and album grid view
- Acceptance criteria:
  - Implement the album list view for owner albums.
  - Implement the album grid view for a selected album.
### Task 49: Multi-select and album add/remove actions
- Scope: multi-select UI and album item actions
- Acceptance criteria:
  - Add multi-select support in timeline and album grids.
  - Implement add/remove actions for album items.
### Task 50: Viewer navigation and hover arrows
- Scope: viewer navigation with prev/next and hover arrows
- Acceptance criteria:
  - Implement viewer navigation with prev/next and hover arrows.
  - Viewer navigation works for photos, Live Photos, and videos.
### Task 51: Viewer zoom and video playback
- Scope: viewer zoom controls and video playback
- Acceptance criteria:
  - Implement zoom controls for images in the viewer.
  - Implement video playback for video assets.
### Task 52: Live Photo hover playback in grid
- Scope: Live Photo hover playback and viewer hover disablement
- Acceptance criteria:
  - Add Live Photo hover playback (silent) in grid cards.
  - Disable hover playback in the viewer.
### Task 53: Date range and location filters
- Scope: timeline filter UI for date range and location
- Acceptance criteria:
  - Add date range and location filters to the timeline UI.
  - Filters update timeline results correctly.
### Task 54: Public routing and layout
- Scope: public album routing and layout separate from owner app
- Acceptance criteria:
  - Add public routes and layout that are distinct from the owner app shell.
  - Public album routes load without authentication.
### Task 55: Public album grid
- Scope: public album grid using share token APIs
- Acceptance criteria:
  - Implement public album grid view wired to share token APIs.
  - Public album grid exposes only assets from the shared album.
### Task 56: Public viewer playback
- Scope: reuse viewer for public playback context
- Acceptance criteria:
  - Reuse the viewer for the public album context.
  - Public viewer supports video playback and Live Photos.
### Task 57: Public ZIP download flow
- Scope: ZIP download initiation, status, and error handling
- Acceptance criteria:
  - Add ZIP download initiation and status UI for public albums.
  - ZIP download starts and completes from the public view, with error handling.
