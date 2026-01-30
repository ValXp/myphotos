from __future__ import annotations

from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from app.auth.sessions import SessionStore
from app.auth.webauthn import LoginChallengeStore, RegistrationChallengeStore
from app.config import Config
from app.db.session import create_engine_from_config, create_session_factory


def get_config(request: Request) -> Config:
    return request.app.state.config


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.session_store


def get_registration_store(request: Request) -> RegistrationChallengeStore:
    return request.app.state.registration_store


def get_login_store(request: Request) -> LoginChallengeStore:
    return request.app.state.login_store


def get_db(request: Request) -> Generator[Session, None, None]:
    session_factory: sessionmaker[Session] | None = request.app.state.db_session_factory
    if session_factory is None:
        engine = create_engine_from_config(request.app.state.config)
        session_factory = create_session_factory(engine)
        request.app.state.db_engine = engine
        request.app.state.db_session_factory = session_factory
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
