from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_config
from app.config import Config

router = APIRouter()


@router.get("/health")
def health(config: Config = Depends(get_config)) -> dict[str, str]:
    return {"status": "ok", "env": config.app.env}
