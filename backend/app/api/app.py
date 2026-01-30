from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from sqlalchemy.orm import Session, sessionmaker

from app.auth.sessions import SessionError, SessionStore, create_session_store
from app.auth.webauthn import (
    LoginChallengeStore,
    RegistrationChallengeStore,
    create_login_store,
    create_registration_store,
)
from app.ingest.admin import ScanBackoffPolicy
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.albums import router as albums_router
from app.api.assets import router as assets_router
from app.api.health import router as health_router
from app.api.ready import router as ready_router
from app.api.public import router as public_router
from app.api.webauthn import router as webauthn_router
from app.config import Config, load_config
from app.metrics import record_request
from app.observability import REQUEST_ID_HEADER, configure_logging, request_context
from app.queue import Queue, RedisQueueBackend, create_redis_client

logger = logging.getLogger("app.api")


def _metric_path(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return request.url.path


def create_app(
    config: Config | None = None,
    *,
    session_store: SessionStore | None = None,
    registration_store: RegistrationChallengeStore | None = None,
    login_store: LoginChallengeStore | None = None,
    db_session_factory: sessionmaker[Session] | None = None,
    queue: Queue | None = None,
    scan_backoff: ScanBackoffPolicy | None = None,
) -> FastAPI:
    resolved = load_config() if config is None else config
    configure_logging(resolved.app.log_level)
    app = FastAPI(title="myphotos")
    app.state.config = resolved
    app.state.session_store = session_store or create_session_store(resolved)
    app.state.registration_store = registration_store or create_registration_store(resolved)
    app.state.login_store = login_store or create_login_store(resolved)
    app.state.queue = queue or Queue(RedisQueueBackend(create_redis_client(resolved.redis)))
    app.state.scan_backoff = scan_backoff or ScanBackoffPolicy()
    if db_session_factory is None:
        app.state.db_engine = None
        app.state.db_session_factory = None
    else:
        app.state.db_engine = None
        app.state.db_session_factory = db_session_factory

    @app.middleware("http")
    async def request_logging_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER)
        if request_id is None or not request_id.strip():
            request_id = uuid4().hex
        request.state.request_id = request_id
        start = time.perf_counter()
        metric_path = _metric_path(request)
        with request_context(request_id):
            try:
                response = await call_next(request)
            except Exception:
                duration_ms = int((time.perf_counter() - start) * 1000)
                record_request(request.method, metric_path, None)
                logger.exception(
                    "request.error",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": duration_ms,
                        "client_host": request.client.host if request.client else None,
                    },
                )
                raise
            duration_ms = int((time.perf_counter() - start) * 1000)
            record_request(request.method, metric_path, response.status_code)
            logger.info(
                "request.complete",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "client_host": request.client.host if request.client else None,
                },
            )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    @app.middleware("http")
    async def owner_session_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        session_id = request.cookies.get(resolved.session.cookie_name)
        owner_session = None
        if session_id is not None and session_id.strip():
            try:
                owner_session = app.state.session_store.validate(session_id)
            except (SessionError, ValueError):
                owner_session = None
        request.state.owner_session = owner_session
        return await call_next(request)

    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(albums_router)
    app.include_router(assets_router)
    app.include_router(health_router)
    app.include_router(ready_router)
    app.include_router(public_router)
    app.include_router(webauthn_router)
    return app


app = create_app()
