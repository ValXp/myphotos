# Plan 06: Albums, Sharing, and Downloads

## Goals
- Let the owner organize assets into albums.
- Share albums via unguessable public links.
- Provide per-album downloads, including ZIPs of originals.

## Scope
- Album CRUD endpoints.
- Album item add/remove endpoints.
- Share link creation, revocation, and public album APIs.
- Album ZIP job creation, status, invalidation, and download.

## Out of Scope
- Multi-tenant permissions or collaboration beyond link sharing.

## Dependencies
- Plan 05: Library APIs (assets exist and can be served).
- Plan 01: Job queue and storage layout.

## Deliverables
- Owner album management endpoints.
- Public album routes bound strictly to the share token.
- ZIP generation job and download endpoints with cache invalidation.

## Steps
1) Implement album CRUD and album-item add/remove endpoints.
2) Implement share link creation and revocation; enforce token-only access for public routes.
3) Implement public album endpoints with album-only asset listing.
4) Implement ZIP job creation and status endpoints.
5) Implement ZIP download streaming and cache invalidation on album changes.

## Tests and Acceptance
- Integration tests for album CRUD and item management.
- Share token reveals only its album; revocation immediately blocks access.
- ZIPs are generated from originals only and invalidated on album changes.
- Public album downloads work without exposing the private library.
