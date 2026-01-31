from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_DB_URL = "postgresql+psycopg://myphotos:myphotos@localhost:5432/myphotos"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_WEBAUTHN_RP_NAME = "myphotos"
DEFAULT_SESSION_TTL_SECONDS = 60 * 60 * 24
DEFAULT_SESSION_COOKIE_NAME = "myphotos_session"
DEFAULT_TRUSTED_PROXY_IPS: tuple[str, ...] = ()


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class PathsConfig:
    data_root: Path
    originals: Path
    derived: Path
    temp: Path


@dataclass(frozen=True)
class DatabaseConfig:
    url: str


@dataclass(frozen=True)
class RedisConfig:
    url: str


@dataclass(frozen=True)
class WebAuthnConfig:
    rp_id: str
    rp_name: str
    origins: tuple[str, ...]


@dataclass(frozen=True)
class AppConfig:
    env: str
    host: str
    port: int
    log_level: str
    trusted_proxy_ips: tuple[str, ...]
    frontend_dist_dir: Path | None


@dataclass(frozen=True)
class SessionConfig:
    ttl_seconds: int
    cookie_name: str


@dataclass(frozen=True)
class Config:
    paths: PathsConfig
    database: DatabaseConfig
    redis: RedisConfig
    webauthn: WebAuthnConfig
    app: AppConfig
    session: SessionConfig

    def as_dict(self) -> dict[str, Any]:
        return {
            "paths": {
                "data_root": str(self.paths.data_root),
                "originals": str(self.paths.originals),
                "derived": str(self.paths.derived),
                "temp": str(self.paths.temp),
            },
            "database": {"url": self.database.url},
            "redis": {"url": self.redis.url},
            "webauthn": {
                "rp_id": self.webauthn.rp_id,
                "rp_name": self.webauthn.rp_name,
                "origins": list(self.webauthn.origins),
            },
            "app": {
                "env": self.app.env,
                "host": self.app.host,
                "port": self.app.port,
                "log_level": self.app.log_level,
                "trusted_proxy_ips": list(self.app.trusted_proxy_ips),
                "frontend_dist_dir": (
                    str(self.app.frontend_dist_dir)
                    if self.app.frontend_dist_dir is not None
                    else None
                ),
            },
            "session": {
                "ttl_seconds": self.session.ttl_seconds,
                "cookie_name": self.session.cookie_name,
            },
        }

    def render(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True)


def load_config(environ: Mapping[str, str] | None = None) -> Config:
    env = os.environ if environ is None else environ
    data_root = _path_from_env(env, "DATA_ROOT", Path("./data"))
    originals = _path_from_env(env, "ORIGINALS_DIR", data_root / "originals", base=data_root)
    derived = _path_from_env(env, "DERIVED_DIR", data_root / "derived", base=data_root)
    temp = _path_from_env(env, "TEMP_DIR", data_root / "temp", base=data_root)
    _validate_unique_paths(
        [
            ("originals", originals),
            ("derived", derived),
            ("temp", temp),
        ]
    )

    database = DatabaseConfig(
        url=normalize_database_url(_str_from_env(env, "DB_URL", DEFAULT_DB_URL))
    )
    redis = RedisConfig(url=_str_from_env(env, "REDIS_URL", DEFAULT_REDIS_URL))
    app = AppConfig(
        env=_str_from_env(env, "APP_ENV", "development"),
        host=_str_from_env(env, "APP_HOST", "127.0.0.1"),
        port=_int_from_env(env, "APP_PORT", 8000, min_value=1, max_value=65535),
        log_level=_str_from_env(env, "APP_LOG_LEVEL", "INFO"),
        trusted_proxy_ips=tuple(
            _csv_from_env(env, "TRUSTED_PROXY_IPS", DEFAULT_TRUSTED_PROXY_IPS)
        ),
        frontend_dist_dir=_optional_path_from_env(env, "FRONTEND_DIST_DIR"),
    )
    default_origin = f"http://{app.host}:{app.port}"
    webauthn = WebAuthnConfig(
        rp_id=_str_from_env(env, "WEBAUTHN_RP_ID", app.host),
        rp_name=_str_from_env(env, "WEBAUTHN_RP_NAME", DEFAULT_WEBAUTHN_RP_NAME),
        origins=tuple(_csv_from_env(env, "WEBAUTHN_ORIGINS", [default_origin])),
    )
    session = SessionConfig(
        ttl_seconds=_int_from_env(
            env, "SESSION_TTL_SECONDS", DEFAULT_SESSION_TTL_SECONDS, min_value=1
        ),
        cookie_name=_str_from_env(env, "SESSION_COOKIE_NAME", DEFAULT_SESSION_COOKIE_NAME),
    )

    return Config(
        paths=PathsConfig(
            data_root=data_root,
            originals=originals,
            derived=derived,
            temp=temp,
        ),
        database=database,
        redis=redis,
        webauthn=webauthn,
        app=app,
        session=session,
    )


def normalize_database_url(url: str) -> str:
    """Normalize database URLs to the configured SQLAlchemy driver.

    We default to psycopg (psycopg3). Many examples (and some hosts) still use
    postgresql:// or postgres:// URLs which implicitly select psycopg2.
    """

    if url.startswith("postgresql://"):
        return f"postgresql+psycopg://{url[len('postgresql://') :]}"
    if url.startswith("postgres://"):
        return f"postgresql+psycopg://{url[len('postgres://') :]}"
    return url


def _str_from_env(env: Mapping[str, str], key: str, default: str) -> str:
    raw = env.get(key)
    if raw is None:
        return default
    value = raw.strip()
    if not value:
        raise ConfigError(f"{key} must not be empty")
    return value


def _int_from_env(
    env: Mapping[str, str],
    key: str,
    default: int,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    raw = env.get(key)
    if raw is None:
        value = default
    else:
        try:
            value = int(raw)
        except ValueError as exc:
            raise ConfigError(f"{key} must be an integer") from exc
    if min_value is not None and value < min_value:
        raise ConfigError(f"{key} must be >= {min_value}")
    if max_value is not None and value > max_value:
        raise ConfigError(f"{key} must be <= {max_value}")
    return value


def _path_from_env(
    env: Mapping[str, str], key: str, default: Path, *, base: Path | None = None
) -> Path:
    raw = env.get(key)
    if raw is None:
        return _normalize_path(default)
    if not raw.strip():
        raise ConfigError(f"{key} must not be empty")
    path = Path(raw)
    if base is not None and not path.is_absolute():
        path = base / path
    return _normalize_path(path)


def _optional_path_from_env(env: Mapping[str, str], key: str) -> Path | None:
    raw = env.get(key)
    if raw is None:
        return None
    if not raw.strip():
        raise ConfigError(f"{key} must not be empty")
    return _normalize_path(Path(raw))


def _normalize_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def _csv_from_env(env: Mapping[str, str], key: str, default: Sequence[str]) -> list[str]:
    raw = env.get(key)
    if raw is None:
        return list(default)
    items = [item.strip() for item in raw.split(",")]
    values = [item for item in items if item]
    if not values:
        raise ConfigError(f"{key} must contain at least one value")
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _validate_unique_paths(paths: Sequence[tuple[str, Path]]) -> None:
    seen: dict[Path, str] = {}
    for name, path in paths:
        existing = seen.get(path)
        if existing is not None:
            raise ConfigError(
                f"Path for {name} duplicates {existing}: {path}"
            )
        seen[path] = name
