from __future__ import annotations

from fastapi import Request

from app.auth.sessions import SessionStore
from app.auth.webauthn import RegistrationChallengeStore
from app.config import Config


def get_config(request: Request) -> Config:
    return request.app.state.config


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.session_store


def get_registration_store(request: Request) -> RegistrationChallengeStore:
    return request.app.state.registration_store
