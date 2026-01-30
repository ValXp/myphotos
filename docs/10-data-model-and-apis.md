# Data Model and APIs (Draft)

## Entities

### User
- id
- display_name
- created_at

### PasskeyCredential
- id
- user_id
- credential_id
- public_key
- sign_count
- transports
- created_at

### Asset
- id
- type (photo | video | live_photo)
- created_at (ingest time)
- captured_at (from metadata)
- duration_ms (video/live)
- width, height
- lat, lon (nullable)
- hash (for duplicate detection later)
- original_path
- original_bytes
- original_mime

### AssetVariant
- id
- asset_id
- kind (thumb | video_transcode | live_video)
- profile (e.g., thumb_256, hls_480p)
- path
- bytes
- created_at

### Album
- id
- title
- created_at
- updated_at

### AlbumItem
- album_id
- asset_id
- order_index
- added_at

### ShareLink
- id
- album_id
- token
- created_at
- revoked_at (nullable)

### AlbumZip
- album_id
- path
- created_at
- invalidated_at (nullable)

### Job
- id
- type (scan | metadata | thumb | transcode | zip)
- status (queued | running | done | failed)
- payload
- created_at
- updated_at

## API (Draft)

### Auth (Owner)
- POST /auth/webauthn/register/options
- POST /auth/webauthn/register/verify
- POST /auth/webauthn/login/options
- POST /auth/webauthn/login/verify
- POST /auth/logout

### Library
- GET /assets?cursor=&limit=&from=&to=&bbox=
- GET /assets/{id}
- GET /assets/{id}/thumb?size=
- GET /assets/{id}/original
- GET /assets/{id}/stream?profile=
- GET /assets/{id}/live (for Live Photo video)

### Albums
- GET /albums
- POST /albums
- PATCH /albums/{id}
- DELETE /albums/{id}
- POST /albums/{id}/items
- DELETE /albums/{id}/items

### Sharing
- POST /albums/{id}/share
- DELETE /shares/{id}
- GET /share/{token} (public album)
- GET /share/{token}/items

### Downloads
- POST /albums/{id}/zip (start or refresh)
- GET /albums/{id}/zip (status + download URL)
- GET /albums/{id}/zip/download

### Admin
- POST /admin/index/scan?path=
- GET /admin/index/status

## Notes
- Use cursor-based pagination for timeline.
- Location filter uses bounding box (bbox) and date range (from/to).
- Public routes must be limited to album-only data.
