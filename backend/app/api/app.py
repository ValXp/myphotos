from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from sqlalchemy.orm import Session, sessionmaker

from app.auth.sessions import SessionError, SessionStore, create_session_store
from app.auth.webauthn import (
    LoginChallengeStore,
    RegistrationChallengeStore,
    create_login_store,
    create_registration_store,
)
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.webauthn import router as webauthn_router
from app.config import Config, load_config


def create_app(
    config: Config | None = None,
    *,
    session_store: SessionStore | None = None,
    registration_store: RegistrationChallengeStore | None = None,
    login_store: LoginChallengeStore | None = None,
    db_session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    resolved = load_config() if config is None else config
    app = FastAPI(title="myphotos")
    app.state.config = resolved
    app.state.session_store = session_store or create_session_store(resolved)
    app.state.registration_store = registration_store or create_registration_store(resolved)
    app.state.login_store = login_store or create_login_store(resolved)
    if db_session_factory is None:
        app.state.db_engine = None
        app.state.db_session_factory = None
    else:
        app.state.db_engine = None
        app.state.db_session_factory = db_session_factory

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
    app.include_router(health_router)
    app.include_router(webauthn_router)
    return app


app = create_app()
