# Plan 01: Foundations and Tooling

## Goals
- Establish the backend project structure, config system, and storage layout.
- Stand up database migrations and a job-queue wrapper.
- Provide minimal API scaffolding for later features.

## Scope
- Project layout and dependency management.
- Config loader with defaults for paths, DB, Redis, and app settings.
- Storage layout conventions: originals, derived, temp.
- Postgres schema and migrations for core entities (users, passkeys, assets, variants, albums, shares, jobs, zips).
- Redis connection and queue abstraction.
- Minimal API shell with `/health`.

## Out of Scope
- Auth, indexing, media processing, and UI features.

## Dependencies
- None.

## Deliverables
- Backend project skeleton with typed Python tooling (mypy/pyright + ruff).
- Alembic migrations that create all required tables.
- Queue wrapper that can enqueue/dequeue test jobs.
- Health endpoint confirming API wiring.

## Steps
1) Create backend project layout (app, tests, migrations, workers).
2) Implement config loader and storage path resolution; print effective config at startup.
3) Define ORM models and Alembic migrations for core entities.
4) Add Redis connection and queue wrapper with a test job.
5) Add `/health` endpoint and basic dependency injection wiring.

## Tests and Acceptance
- Unit tests for config parsing and validation.
- Migration test: `migrate up` creates all required tables.
- Queue smoke test enqueues and processes a no-op job.
- `/health` returns 200 with expected payload.
