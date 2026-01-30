from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import text

from app.api.deps import get_config
from app.config import Config
from app.db.session import create_engine_from_config, create_session_factory
from app.queue import create_redis_client

router = APIRouter()


@router.get("/ready")
def ready(
    request: Request,
    response: Response,
    config: Config = Depends(get_config),
) -> dict[str, Any]:
    db_ready = _check_db(request, config)
    redis_ready = _check_redis(request, config)
    overall_ready = db_ready and redis_ready
    response.status_code = (
        status.HTTP_200_OK if overall_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return {
        "status": "ok" if overall_ready else "error",
        "dependencies": {
            "db": "ok" if db_ready else "error",
            "redis": "ok" if redis_ready else "error",
        },
    }


def _check_db(request: Request, config: Config) -> bool:
    try:
        session_factory = request.app.state.db_session_factory
        if session_factory is None:
            engine = create_engine_from_config(config)
            session_factory = create_session_factory(engine)
            request.app.state.db_engine = engine
            request.app.state.db_session_factory = session_factory
        session = session_factory()
        try:
            session.execute(text("SELECT 1"))
        finally:
            session.close()
        return True
    except Exception:
        return False


def _check_redis(request: Request, config: Config) -> bool:
    try:
        client = getattr(request.app.state, "redis_client", None)
        if client is None:
            client = create_redis_client(config.redis)
            request.app.state.redis_client = client
        client.ping()
        return True
    except Exception:
        return False
