# Plan 09: Observability and Quality Gates

## Goals
- Ensure reliability, debuggability, and test coverage across the system.

## Scope
- Structured logging for API and jobs.
- Health and readiness endpoints.
- Basic metrics placeholders (counters for jobs and API requests).
- CI enforcement of tests and coverage thresholds.
- Integration test suites for major features.

## Out of Scope
- Full production monitoring stack (future work).

## Dependencies
- Cross-cutting; can be implemented incrementally alongside other plans.

## Deliverables
- Consistent logging with request/job IDs.
- `/health` and optional `/ready` endpoints.
- Minimal metrics hook points.
- CI configuration enforcing unit coverage >= 90%.
- Integration test harness for auth, indexing, media pipeline, albums/shares, downloads, timeline.

## Steps
1) Add structured logging with request/job correlation IDs.
2) Implement health/readiness endpoints.
3) Add basic metrics counters and placeholders.
4) Build CI pipeline to run tests and enforce coverage.
5) Expand integration test suites as features land.

## Tests and Acceptance
- Logs include request IDs and job IDs.
- CI fails when unit coverage < 90%.
- Integration tests run against ephemeral DB/Redis and pass reliably.
