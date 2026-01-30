# Plan 08: Frontend (Public Album)

## Goals
- Provide a clean, limited public album experience with download support.

## Scope
- Public album route driven by share token.
- Album grid and viewer for public users.
- Album ZIP download UI and status handling.

## Out of Scope
- Owner-only features (auth, album management, filters beyond album).

## Dependencies
- Plan 06: Albums, Sharing, and Downloads.
- Plan 07: Owner frontend components (viewer and grid reused).

## Deliverables
- Public album UI that exposes only the shared album.
- Viewer UX consistent with owner app for media playback.
- ZIP download initiation and progress/status UI.

## Steps
1) Add public routing and layout separate from owner app.
2) Implement public album grid using share token APIs.
3) Reuse viewer for media playback in public context.
4) Add ZIP download flow with status checks and error handling.

## Tests and Acceptance
- Public routes load without authentication.
- Public viewer supports video playback and Live Photos.
- ZIP download starts and completes from public view.
