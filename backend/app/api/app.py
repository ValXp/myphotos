from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from app.auth.sessions import SessionStore, create_session_store
from app.auth.webauthn import RegistrationChallengeStore, create_registration_store
from app.api.health import router as health_router
from app.api.webauthn import router as webauthn_router
from app.config import Config, load_config


def create_app(
    config: Config | None = None,
    *,
    session_store: SessionStore | None = None,
    registration_store: RegistrationChallengeStore | None = None,
    db_session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    resolved = load_config() if config is None else config
    app = FastAPI(title="myphotos")
    app.state.config = resolved
    app.state.session_store = session_store or create_session_store(resolved)
    app.state.registration_store = registration_store or create_registration_store(resolved)
    if db_session_factory is None:
        app.state.db_engine = None
        app.state.db_session_factory = None
    else:
        app.state.db_engine = None
        app.state.db_session_factory = db_session_factory
    app.include_router(health_router)
    app.include_router(webauthn_router)
    return app


app = create_app()
