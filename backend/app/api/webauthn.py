from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import get_config, get_registration_store
from app.auth.webauthn import (
    DEFAULT_REGISTRATION_CHALLENGE_TTL_SECONDS,
    DEFAULT_REGISTRATION_SESSION_COOKIE_NAME,
    DEFAULT_REGISTRATION_TIMEOUT_MS,
    RegistrationChallenge,
    RegistrationChallengeStore,
    generate_challenge,
    generate_user_handle,
)
from app.config import Config

router = APIRouter(prefix="/auth/webauthn")


class RegistrationOptionsRequest(BaseModel):
    display_name: str = Field(default="Owner", min_length=1)


@router.post("/register/options")
def registration_options(
    response: Response,
    request: Request,
    payload: RegistrationOptionsRequest | None = Body(default=None),
    config: Config = Depends(get_config),
    store: RegistrationChallengeStore = Depends(get_registration_store),
) -> dict[str, Any]:
    display_name = payload.display_name if payload is not None else "Owner"
    display_name = display_name.strip()
    if not display_name:
        raise HTTPException(status_code=422, detail="display_name must be non-empty")

    session_id = request.cookies.get(DEFAULT_REGISTRATION_SESSION_COOKIE_NAME)
    if session_id is None:
        session_id = str(uuid.uuid4())

    challenge = generate_challenge()
    user_handle = generate_user_handle()
    record = RegistrationChallenge(
        challenge=challenge,
        user_handle=user_handle,
        user_name=display_name,
        created_at=datetime.now(timezone.utc),
    )
    store.save(session_id, record, ttl_seconds=DEFAULT_REGISTRATION_CHALLENGE_TTL_SECONDS)

    _set_registration_cookie(response, session_id, config)

    return {
        "rp": {"id": config.webauthn.rp_id, "name": config.webauthn.rp_name},
        "user": {
            "id": user_handle,
            "name": display_name,
            "displayName": display_name,
        },
        "challenge": challenge,
        "pubKeyCredParams": [
            {"type": "public-key", "alg": -7},
            {"type": "public-key", "alg": -257},
        ],
        "timeout": DEFAULT_REGISTRATION_TIMEOUT_MS,
        "attestation": "none",
        "excludeCredentials": [],
    }


def _set_registration_cookie(response: Response, session_id: str, config: Config) -> None:
    secure_cookie = config.app.env.lower() == "production"
    response.set_cookie(
        key=DEFAULT_REGISTRATION_SESSION_COOKIE_NAME,
        value=session_id,
        max_age=DEFAULT_REGISTRATION_CHALLENGE_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=secure_cookie,
    )
