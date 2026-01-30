# Learnings

- 2026-01-29 22:22: No build or test commands found in repo; cannot verify build/tests for initial tasks.
- 2026-01-29 22:28: Plan expansion tasks are meta; no build/test commands required for this run.

- 2026-01-29 22:30: Plan 02 does not specify build or test commands; added tasks with explicit integration test criteria.
- 2026-01-29 22:32: Plan 03 does not specify build or test commands; added tasks with explicit unit/integration test criteria.

- 2026-01-29 22:34: Plan 04 does not specify build or test commands; added tasks with explicit integration/unit test criteria.
- 2026-01-29 22:35: Plan 05 does not specify build or test commands; added tasks with explicit integration test criteria.

- 2026-01-29 22:37: Plan 06 does not specify build or test commands; added tasks with explicit integration test criteria.

- 2026-01-29 22:39: Plan 07 does not specify build or test commands; added tasks with explicit UI/test criteria.
- 2026-01-29 22:41: Plan 08 does not specify build or test commands; added tasks with explicit UI/test criteria.
- 2026-01-29 22:43: Plan 09 does not specify build/test commands; repo still lacks build/test commands, blocking completion under build/test requirement.
- 2026-01-29 22:45: Plan 09 tasks already appended; no new tasks added this run and no build/test commands required for the meta task.
- 2026-01-29 22:49: python3 is available but pytest is not installed; used a unittest smoke test for the initial test run.

- 2026-01-29 22:55: `python` is not available; use `python3` for tests.
- 2026-01-29 23:05 MST: Pip is blocked by PEP 668; use a venv (e.g., /root/myphotos/.venv) for installing Python deps.
- 2026-01-29 23:05 MST: SQLAlchemy relationship annotations cannot use a stringified union ("AlbumZip" | None); avoid `| None` in quotes to prevent MappedAnnotationError.
- 2026-01-29 23:11 MST: Queue tests require the `redis` package; install backend deps in the venv before running the suite.
- 2026-01-29 23:17 MST: Health endpoint tests use FastAPI TestClient; install fastapi/httpx in the venv before running the suite.
- 2026-01-29 23:25 MST: Project venv is at /root/myphotos/.venv; run tests from backend with ../.venv/bin/python.

- 2026-01-29 23:41 MST: Avoid eager DB engine creation in app startup; default Postgres URL loads psycopg2 which is not installed in the venv, so create the engine lazily when a DB session is requested.

- 2026-01-29 23:52 MST: FastAPI set-cookie headers render SameSite as lowercase (SameSite=lax); test cookie attribute checks should be case-insensitive.
- 2026-01-30 00:08 MST: In-memory SQLite tests should dispose engines to avoid ResourceWarning messages.
- 2026-01-30 00:26 MST: Reconciliation relies on asset identity columns (original_device/original_inode/original_mtime_ns) populated during scans for move matching.
- 2026-01-30 00:35 MST: Enqueueing jobs for newly created assets needs a session flush so the asset ID is available for job payloads before commit.
- 2026-01-30 01:06 MST: exiftool, ffprobe, and ffmpeg are not installed in this environment; metadata integration tests were skipped.
- 2026-01-30 01:17 MST: pyvips is not installed in the venv; thumbnail integration test is skipped.
- 2026-01-30 01:24 MST: ffmpeg is not installed; transcode integration test is skipped.
- 2026-01-30 01:39 MST: Live video variant creation needs a session flush so new AssetVariant rows are queryable in tests.
- 2026-01-30 02:20 MST: Added auth coverage for /assets endpoints; no new environment issues.

- 2026-01-30 02:55 MST: ZIP status should treat invalidated album zips as idle even if the latest job is done, otherwise status stays done after album changes.
- 2026-01-30 03:03 MST: Frontend npm install reports 2 moderate vulnerabilities; run `npm audit` / `npm audit fix --force` if addressing.
- 2026-01-30 03:24 MST: Frontend npm install reports 4 moderate vulnerabilities and a deprecation warning for whatwg-encoding; run `npm audit` / `npm audit fix --force` if addressing.
- 2026-01-30 03:24 MST: React Router emits v7 future-flag warnings during frontend tests; optional to enable v7_startTransition and v7_relativeSplatPath flags.
- 2026-01-30 03:33 MST: Pytest was missing from /root/myphotos/.venv; installed it to run backend tests.

- 2026-01-30 04:10 MST: Frontend tests continue to emit React Router v7 future-flag warnings during vitest runs.

- 2026-01-30 04:23 MST: Frontend tests can leave duplicate DOM nodes without cleanup; call React Testing Library cleanup in tests when using multiple renders.
- 2026-01-30 04:53 MST: MemoryRouter initialEntries are only applied on mount; use cleanup/new render (or a keyed router) to change routes in tests.
- 2026-01-30 05:07 MST: Public share ZIP preparation/status endpoints are `/public/shares/{token}/zip`, returning a share-scoped download URL.
- 2026-01-30 05:17 MST: Structured logging is JSON formatted with request/job correlation IDs (request IDs default to `X-Request-ID`).
- 2026-01-30 05:24 MST: Readiness endpoint tests set `app.state.redis_client` to a FakeRedis to avoid needing a real Redis server.
- 2026-01-30 05:38 MST: Installed pytest-cov in /root/myphotos/.venv to run coverage tests locally.
- 2026-01-30 05:38 MST: Backend tests warn about unclosed sqlite connections during share link tests; keep an eye on ResourceWarning output.
- 2026-01-30 05:38 MST: CI coverage uses backend/.coveragerc to focus unit coverage gating on non-API, non-external-tool modules.
- 2026-01-30 05:50 MST: Integration tests are gated by INTEGRATION_TESTS=1 and require INTEGRATION_DB_URL/INTEGRATION_REDIS_URL with psycopg for Postgres connectivity.
- 2026-01-30 08:29 MST: Integration tests require running Redis/Postgres services; installed and started redis-server and postgresql locally.
- 2026-01-30 08:29 MST: Normalized postgres URLs without an explicit driver to use psycopg, avoiding a psycopg2 dependency.

- 2026-01-30 09:06 MST: Starlette URL uses the Host header ahead of scope server; honoring X-Forwarded-Host requires updating scope headers (TestClient client host is "testclient").

- 2026-01-30 09:14 MST: Frontend dist assets use /assets; serve static files before routing to avoid API path conflicts and fallback to index for SPA routes.
- 2026-01-30 09:26 MST: Vitest/jsdom defaults window.location.origin to http://localhost:3000; use window.location.origin when asserting share URLs.
- 2026-01-30 09:35 MST: Frontend vitest runs still emit React Router v7 future-flag warnings.

- 2026-01-30 09:40 MST: Media worker tests need AppConfig.frontend_dist_dir set (use None) now that frontend_dist_dir is required.
