# MyPhotos

A self-hosted, Google Photos-like service for a single shared library (me + wife). It focuses on fast browsing, album sharing, robust video playback, and simple ingest via watched folders. Scope is intentionally smaller than Google Photos: no multi-tenant accounts, no AI/face recognition, and no in-app edits.

## Highlights

- Owner passkey (WebAuthn) authentication with session cookies.
- Infinite-scroll timeline (newest first) with date + lat/long filters.
- Album management with multi-select add/remove from the timeline.
- Public album sharing via unguessable tokens and a dedicated share UI.
- Adaptive video streaming (HLS) and Live Photo hover playback.
- Precomputed thumbnails, metadata extraction, and derived media storage.
- Structured JSON logging, request/job correlation IDs, and basic metrics.

## Architecture at a glance

- **Frontend:** React + Vite, owner and public share experiences.
- **Backend:** FastAPI + SQLAlchemy, WebAuthn auth, assets/albums APIs.
- **Database:** Postgres for assets, albums, shares, jobs.
- **Queue/Cache:** Redis for sessions, WebAuthn challenges, job queue.
- **Media tools:** ffmpeg/ffprobe, exiftool, libvips (plus libheif for HEIC/HEIF).
- **Storage:**
  - Originals (read-only): source folders
  - Derived: thumbnails, transcodes, manifests
  - Temp: album ZIP staging

See `docs/` for detailed requirements, UX, processing, and data model notes.

## Repository layout

- `backend/` FastAPI app, SQLAlchemy models, ingest, media pipeline, tests.
- `frontend/` React app (Vite), shared/public views, tests.
- `docs/` product requirements, UX, architecture, and API drafts.
- `migrate` Alembic migration helper (`up` / `down`).
- `.github/workflows/ci.yml` CI for backend + frontend tests.

## Getting started

### Prerequisites

- **Python:** 3.13 (CI runs on 3.13)
- **Node:** 20 (CI runs on 20)
- **Services:** Postgres 16+, Redis 7+
- **Media tools:**
  - `ffmpeg` + `ffprobe`
  - `exiftool`
  - `libvips` + `pyvips` (plus `libheif` for HEIC/HEIF)

### Backend setup

1) Create a virtualenv and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
# Web server (not included in requirements.txt)
python -m pip install uvicorn
```

2) Configure environment variables (see **Configuration** below).

3) Run migrations:

```bash
./migrate up
```

4) Start the API:

```bash
cd backend
uvicorn app.api.app:app --reload --host 0.0.0.0 --port 8000
```

### Frontend setup

```bash
cd frontend
npm ci
npm run dev
```

If the API is not on the same origin, set `VITE_API_BASE_URL`:

```bash
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

### WebAuthn / passkey notes

Passkeys require HTTPS (or `localhost`). In production, terminate TLS in a reverse proxy (e.g., nginx) and set `WEBAUTHN_RP_ID` + `WEBAUTHN_ORIGINS` to match the public domain. `APP_ENV=production` enables secure session cookies.

## Configuration

Backend config is environment-driven (see `backend/app/config.py`). Defaults shown in parentheses.

- `DATA_ROOT` (`./data`) Root for derived data.
- `ORIGINALS_DIR` (`DATA_ROOT/originals`) Source media (read-only).
- `DERIVED_DIR` (`DATA_ROOT/derived`) Thumbnails, transcodes, manifests.
- `TEMP_DIR` (`DATA_ROOT/temp`) Temporary ZIP staging.
- `DB_URL` (`postgresql+psycopg://myphotos:myphotos@localhost:5432/myphotos`)
- `REDIS_URL` (`redis://localhost:6379/0`)
- `APP_ENV` (`development`)
- `APP_HOST` (`127.0.0.1`)
- `APP_PORT` (`8000`)
- `APP_LOG_LEVEL` (`INFO`)
- `WEBAUTHN_RP_ID` (`APP_HOST`)
- `WEBAUTHN_RP_NAME` (`myphotos`)
- `WEBAUTHN_ORIGINS` (`http://{APP_HOST}:{APP_PORT}`)
- `SESSION_TTL_SECONDS` (86400)
- `SESSION_COOKIE_NAME` (`myphotos_session`)

Frontend config:

- `VITE_API_BASE_URL` (empty = same origin)

Integration tests:

- `INTEGRATION_TESTS=1` to enable integration tests
- `INTEGRATION_DB_URL` / `INTEGRATION_REDIS_URL` (or `DB_URL` / `REDIS_URL`)

## Storage layout

By default (with `DATA_ROOT=./data`):

- `data/originals/` original media (read-only)
- `data/derived/` thumbnails, HLS playlists/segments, live photo videos
- `data/derived/album_zips/` cached album ZIPs
- `data/temp/` temporary ZIP files

Derived assets are stored under `data/derived/{asset_id}/{variant_kind}/...`.

## API overview

Core endpoints (owner-authenticated unless noted):

- **Auth**
  - `POST /auth/webauthn/register/options`
  - `POST /auth/webauthn/register/verify`
  - `POST /auth/webauthn/login/options`
  - `POST /auth/webauthn/login/verify`
  - `GET /auth/session`
  - `POST /auth/logout`

- **Assets**
  - `GET /assets` (cursor pagination, date + bbox filters)
  - `GET /assets/{id}`
  - `GET /assets/{id}/thumb?profile=`
  - `GET /assets/{id}/original`
  - `GET /assets/{id}/stream?file=` (HLS manifest/segments)
  - `GET /assets/{id}/live` (Live Photo video)

- **Albums**
  - `GET /albums`
  - `POST /albums`
  - `PATCH /albums/{id}`
  - `DELETE /albums/{id}`
  - `GET /albums/{id}/assets`
  - `POST /albums/{id}/items`
  - `DELETE /albums/{id}/items`
  - `POST /albums/{id}/shares`
  - `DELETE /albums/{id}/shares/{share_id}`

- **Public share**
  - `GET /public/shares/{token}/album`
  - `GET /public/shares/{token}/assets`
  - `GET /public/shares/{token}/assets/{id}/thumb`
  - `GET /public/shares/{token}/assets/{id}/stream`
  - `POST /public/shares/{token}/zip`
  - `GET /public/shares/{token}/zip`
  - `GET /public/shares/{token}/zip/download`

- **Downloads (owner)**
  - `POST /albums/{id}/zip`
  - `GET /albums/{id}/zip`
  - `GET /albums/{id}/zip/download`

- **Admin**
  - `POST /admin/index/scan?path=` (enqueue full scan)
  - `GET /admin/index/status`

- **Health**
  - `GET /health` (process-only)
  - `GET /ready` (checks Postgres + Redis)

## Media pipeline

1) **Ingest:**
   - Folder scanning and polling watcher detect adds/moves/deletes.
   - Assets are upserted into Postgres.
   - Metadata, thumbnails, and transcode jobs are queued.

2) **Processing:**
   - `metadata`: exiftool + ffprobe extract EXIF, size, duration, and GPS.
   - `thumb`: pyvips for images; ffmpeg for video posters.
   - `transcode`: ffmpeg HLS renditions + master manifest.
   - `live`: ffmpeg-derived silent Live Photo preview.

There is no standalone worker binary yet. The queue primitives are in
`backend/app/queue.py` and job handlers live in `backend/app/media/*`.

## Testing

Backend unit tests:

```bash
cd backend
python -m pytest
```

Backend tests with coverage (CI enforces 90% for core modules):

```bash
cd backend
python -m pytest --cov --cov-config=.coveragerc --cov-report=term-missing --cov-fail-under=90
```

Backend integration tests (requires Postgres + Redis):

```bash
cd backend
INTEGRATION_TESTS=1 \
INTEGRATION_DB_URL=postgresql://myphotos:myphotos@localhost:5432/myphotos_test \
INTEGRATION_REDIS_URL=redis://localhost:6379/0 \
python -m pytest tests/test_integration_*.py
```

Frontend tests:

```bash
cd frontend
npm test
```

## Docs

Start with:

- `docs/01-overview.md`
- `docs/02-requirements.md`
- `docs/08-mvp-spec.md`
- `docs/09-architecture.md`
- `docs/10-data-model-and-apis.md`

## Project status

Core backend APIs, media pipeline primitives, and the owner/public UI are in place. Remaining work is primarily around operational glue (worker runner, deploy wiring, and serving the frontend bundle from the API or proxy).
