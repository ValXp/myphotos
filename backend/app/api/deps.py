from __future__ import annotations

from fastapi import Request

from app.auth.sessions import SessionStore
from app.config import Config


def get_config(request: Request) -> Config:
    return request.app.state.config


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.session_store
