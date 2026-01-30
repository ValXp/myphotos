from __future__ import annotations

from fastapi import FastAPI

from app.api.health import router as health_router
from app.config import Config, load_config


def create_app(config: Config | None = None) -> FastAPI:
    resolved = load_config() if config is None else config
    app = FastAPI(title="myphotos")
    app.state.config = resolved
    app.include_router(health_router)
    return app


app = create_app()
