from __future__ import annotations

from datetime import datetime, timezone
import base64
import binascii
from typing import Any
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from webauthn import verify_authentication_response, verify_registration_response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import (
    get_config,
    get_db,
    get_login_store,
    get_registration_store,
    get_session_store,
)
from app.auth.sessions import SessionStore
from app.auth.webauthn import (
    DEFAULT_LOGIN_CHALLENGE_TTL_SECONDS,
    DEFAULT_LOGIN_SESSION_COOKIE_NAME,
    DEFAULT_LOGIN_TIMEOUT_MS,
    DEFAULT_REGISTRATION_CHALLENGE_TTL_SECONDS,
    DEFAULT_REGISTRATION_SESSION_COOKIE_NAME,
    DEFAULT_REGISTRATION_TIMEOUT_MS,
    LoginChallenge,
    LoginChallengeStore,
    RegistrationChallenge,
    RegistrationChallengeStore,
    generate_challenge,
    generate_user_handle,
)
from app.config import Config
from app.db.models import PasskeyCredential, User

router = APIRouter(prefix="/auth/webauthn")


class RegistrationOptionsRequest(BaseModel):
    display_name: str = Field(default="Owner", min_length=1)


class RegistrationVerifyRequest(BaseModel):
    # Full RegistrationCredential payload from the browser (base64url strings).
    credential: dict[str, Any]
    transports: list[str] | None = None


class LoginVerifyRequest(BaseModel):
    # Full AuthenticationCredential payload from the browser (base64url strings).
    credential: dict[str, Any]


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


@router.post("/login/options")
def login_options(
    response: Response,
    request: Request,
    config: Config = Depends(get_config),
    store: LoginChallengeStore = Depends(get_login_store),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    user = db.execute(select(User).limit(1)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="owner not registered")

    credentials = (
        db.execute(select(PasskeyCredential).where(PasskeyCredential.user_id == user.id))
        .scalars()
        .all()
    )
    if not credentials:
        raise HTTPException(status_code=404, detail="no passkeys registered")

    session_id = request.cookies.get(DEFAULT_LOGIN_SESSION_COOKIE_NAME)
    if session_id is None:
        session_id = str(uuid.uuid4())

    challenge = generate_challenge()
    record = LoginChallenge(
        challenge=challenge,
        user_id=user.id,
        created_at=datetime.now(timezone.utc),
    )
    store.save(session_id, record, ttl_seconds=DEFAULT_LOGIN_CHALLENGE_TTL_SECONDS)
    _set_login_cookie(response, session_id, config)

    allow_credentials: list[dict[str, Any]] = []
    for credential in credentials:
        item: dict[str, Any] = {
            "type": "public-key",
            "id": _base64url_encode_bytes(credential.credential_id),
        }
        if credential.transports:
            item["transports"] = credential.transports
        allow_credentials.append(item)

    return {
        "challenge": challenge,
        "timeout": DEFAULT_LOGIN_TIMEOUT_MS,
        "rpId": config.webauthn.rp_id,
        "allowCredentials": allow_credentials,
        "userVerification": "preferred",
    }


@router.post("/login/verify")
def login_verify(
    response: Response,
    request: Request,
    payload: LoginVerifyRequest,
    config: Config = Depends(get_config),
    store: LoginChallengeStore = Depends(get_login_store),
    session_store: SessionStore = Depends(get_session_store),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    session_id = request.cookies.get(DEFAULT_LOGIN_SESSION_COOKIE_NAME)
    if session_id is None:
        raise HTTPException(status_code=400, detail="login session cookie missing")

    challenge = store.consume(session_id)
    if challenge is None:
        raise HTTPException(status_code=400, detail="login challenge missing or expired")
    try:
        expected_challenge = _base64url_decode(challenge.challenge)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="invalid stored challenge") from exc

    # Identify the credential by id in the payload.
    try:
        credential_id_raw = payload.credential.get("id")
        if not isinstance(credential_id_raw, str) or not credential_id_raw:
            raise ValueError("credential.id missing")
        credential_id = _base64url_decode(credential_id_raw)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    credential = db.execute(
        select(PasskeyCredential).where(PasskeyCredential.credential_id == credential_id)
    ).scalar_one_or_none()
    if credential is None:
        raise HTTPException(status_code=404, detail="credential not registered")
    if credential.user_id != challenge.user_id:
        raise HTTPException(status_code=403, detail="credential user mismatch")

    try:
        verified = verify_authentication_response(
            credential=payload.credential,
            expected_challenge=expected_challenge,
            expected_rp_id=config.webauthn.rp_id,
            expected_origin=list(config.webauthn.origins),
            credential_public_key=credential.public_key,
            credential_current_sign_count=credential.sign_count,
            require_user_verification=False,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    credential.sign_count = verified.new_sign_count
    db.commit()

    session = session_store.create(credential.user_id)
    _set_session_cookie(response, session.id, config)

    return {"status": "ok", "user_id": credential.user_id}


@router.post("/register/verify")
def registration_verify(
    request: Request,
    payload: RegistrationVerifyRequest,
    config: Config = Depends(get_config),
    store: RegistrationChallengeStore = Depends(get_registration_store),
    session_store: SessionStore = Depends(get_session_store),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    session_id = request.cookies.get(DEFAULT_REGISTRATION_SESSION_COOKIE_NAME)
    if session_id is None:
        raise HTTPException(status_code=400, detail="registration session cookie missing")

    user = db.execute(select(User).limit(1)).scalar_one_or_none()
    if user is not None:
        owner_session_id = request.cookies.get(config.session.cookie_name)
        if owner_session_id is None:
            raise HTTPException(status_code=401, detail="owner session required")
        owner_session = session_store.validate(owner_session_id)
        if owner_session is None:
            raise HTTPException(status_code=401, detail="owner session required")
        if owner_session.user_id != user.id:
            raise HTTPException(status_code=403, detail="owner session mismatch")

    challenge = store.consume(session_id)
    if challenge is None:
        raise HTTPException(status_code=400, detail="registration challenge missing or expired")

    try:
        expected_challenge = _base64url_decode(challenge.challenge)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="invalid stored challenge") from exc

    # Verify attestation and derive the credential public key server-side.
    try:
        verified = verify_registration_response(
            credential=payload.credential,
            expected_challenge=expected_challenge,
            expected_rp_id=config.webauthn.rp_id,
            expected_origin=list(config.webauthn.origins),
            require_user_verification=False,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    credential_id = verified.credential_id

    existing_credential = db.execute(
        select(PasskeyCredential).where(PasskeyCredential.credential_id == credential_id)
    ).scalar_one_or_none()
    if existing_credential is not None:
        raise HTTPException(status_code=409, detail="credential already registered")

    if user is None:
        user = User(display_name=challenge.user_name)
        db.add(user)
        db.flush()

    db.add(
        PasskeyCredential(
            user_id=user.id,
            credential_id=credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            transports=payload.transports,
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="credential already registered") from exc

    return {
        "status": "ok",
        "user_id": user.id,
        "credential_id": _base64url_encode_bytes(credential_id),
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


def _set_login_cookie(response: Response, session_id: str, config: Config) -> None:
    secure_cookie = config.app.env.lower() == "production"
    response.set_cookie(
        key=DEFAULT_LOGIN_SESSION_COOKIE_NAME,
        value=session_id,
        max_age=DEFAULT_LOGIN_CHALLENGE_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=secure_cookie,
    )


def _set_session_cookie(response: Response, session_id: str, config: Config) -> None:
    secure_cookie = config.app.env.lower() == "production"
    response.set_cookie(
        key=config.session.cookie_name,
        value=session_id,
        max_age=config.session.ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=secure_cookie,
    )


def _base64url_encode_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    raw = value.strip()
    if not raw:
        raise ValueError("value must be non-empty")
    padded = raw + "=" * (-len(raw) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, binascii.Error) as exc:
        raise ValueError("value must be base64url encoded") from exc
    if not decoded:
        raise ValueError("value must decode to non-empty bytes")
    return decoded
