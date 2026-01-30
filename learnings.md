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
