# Plan 07: Frontend (Owner App)

## Goals
- Provide a fast, responsive owner experience for browsing and managing the library.

## Scope
- App shell, routing, and auth gate.
- Passkey sign-in flow.
- Timeline with infinite scroll and filters.
- Album list and album grid views.
- Multi-select and add/remove actions.
- Viewer with prev/next navigation, zoom, Live Photo hover, and video playback.

## Out of Scope
- Public album UI (handled separately).

## Dependencies
- Plan 02: Auth and Sessions.
- Plan 05: Library APIs.
- Plan 06: Albums and Sharing.
- Plan 04: Media Processing (Live Photos and video variants).

## Deliverables
- Owner app routes and authenticated layout.
- Timeline and album UIs with selection and actions.
- Viewer experience for photos, videos, and Live Photos.
- Date range and location filter UI.

## Steps
1) Build app shell and routing; add auth gate.
2) Implement passkey sign-in UI and session bootstrap.
3) Build timeline view with infinite scroll and thumbnail loading.
4) Implement album list and album grid views.
5) Add multi-select and add/remove album actions.
6) Implement viewer with hover arrows, prev/next, zoom, and video playback.
7) Add Live Photo hover playback (silent) in grid; disable hover in viewer.
8) Add date range and location filter UI.

## Tests and Acceptance
- E2E or integration tests for sign-in and basic browsing flows.
- Timeline loads thumbnails without fetching originals.
- Viewer navigation works for photos, Live Photos, and videos.
- Filters update timeline results correctly.
