from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import get_config, get_session_store, require_owner_session
from app.auth.sessions import Session as OwnerSession, SessionStore
from app.config import Config

router = APIRouter(prefix="/auth")


@router.post("/logout")
def logout(
    response: Response,
    request: Request,
    config: Config = Depends(get_config),
    session_store: SessionStore = Depends(get_session_store),
) -> dict[str, str]:
    session_id = request.cookies.get(config.session.cookie_name)
    if session_id is not None and session_id.strip():
        session_store.revoke(session_id)

    _clear_session_cookie(response, config)
    return {"status": "ok"}


@router.get("/session")
def session_status(
    owner_session: OwnerSession = Depends(require_owner_session),
) -> dict[str, str]:
    return {"status": "ok", "user_id": owner_session.user_id}


def _clear_session_cookie(response: Response, config: Config) -> None:
    secure_cookie = config.app.env.lower() == "production"
    response.delete_cookie(
        key=config.session.cookie_name,
        httponly=True,
        samesite="lax",
        secure=secure_cookie,
    )
