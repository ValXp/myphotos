from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import get_config, get_session_store
from app.auth.sessions import SessionStore
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


def _clear_session_cookie(response: Response, config: Config) -> None:
    secure_cookie = config.app.env.lower() == "production"
    response.delete_cookie(
        key=config.session.cookie_name,
        httponly=True,
        samesite="lax",
        secure=secure_cookie,
    )
