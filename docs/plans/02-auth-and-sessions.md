# Plan 02: Auth and Sessions (Passkeys)

## Goals
- Enable owner authentication via WebAuthn passkeys.
- Provide session-based access control for owner-only routes.

## Scope
- WebAuthn registration and login flows.
- Session creation, validation, and logout.
- Auth middleware for owner-only endpoints.
- Passkey credential storage and replay protection.

## Out of Scope
- Multi-tenant user management or roles.
- OAuth or third-party identity providers.

## Dependencies
- Plan 01: Foundations and Tooling.

## Deliverables
- Registration options and verification endpoints.
- Login options and verification endpoints.
- Session cookie issuance and validation.
- Auth middleware and logout endpoint.

## Steps
1) Define WebAuthn RP settings and session storage (DB or Redis-backed).
2) Implement registration options endpoint.
3) Implement registration verify endpoint; store credential and sign count.
4) Implement login options endpoint.
5) Implement login verify endpoint; create session cookie.
6) Implement logout endpoint and auth middleware.
7) Add owner-only guard for private routes; keep public share routes unauthenticated.
8) Bootstrap rule: if no user exists, allow first registration; afterward require owner session to add passkeys.

## Tests and Acceptance
- Integration tests for registration and login (happy path + invalid challenge).
- Session cookie is HttpOnly and SameSite with secure flag behind HTTPS.
- Owner-only routes reject unauthenticated requests.
- Registration is blocked when already registered unless owner session present.
