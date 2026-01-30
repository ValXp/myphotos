from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Config


def create_engine_from_config(config: Config) -> Engine:
    url = _normalize_database_url(config.database.url)
    connect_args: dict[str, object] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, future=True, connect_args=connect_args)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return f"postgresql+psycopg://{url[len('postgresql://'):]}"
    if url.startswith("postgres://"):
        return f"postgresql+psycopg://{url[len('postgres://'):]}"
    return url
