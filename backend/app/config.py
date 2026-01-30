from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_DB_URL = "postgresql://myphotos:myphotos@localhost:5432/myphotos"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"


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
class AppConfig:
    env: str
    host: str
    port: int
    log_level: str


@dataclass(frozen=True)
class Config:
    paths: PathsConfig
    database: DatabaseConfig
    redis: RedisConfig
    app: AppConfig

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
            "app": {
                "env": self.app.env,
                "host": self.app.host,
                "port": self.app.port,
                "log_level": self.app.log_level,
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

    database = DatabaseConfig(url=_str_from_env(env, "DB_URL", DEFAULT_DB_URL))
    redis = RedisConfig(url=_str_from_env(env, "REDIS_URL", DEFAULT_REDIS_URL))
    app = AppConfig(
        env=_str_from_env(env, "APP_ENV", "development"),
        host=_str_from_env(env, "APP_HOST", "127.0.0.1"),
        port=_int_from_env(env, "APP_PORT", 8000, min_value=1, max_value=65535),
        log_level=_str_from_env(env, "APP_LOG_LEVEL", "INFO"),
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
        app=app,
    )


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


def _normalize_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def _validate_unique_paths(paths: Sequence[tuple[str, Path]]) -> None:
    seen: dict[Path, str] = {}
    for name, path in paths:
        existing = seen.get(path)
        if existing is not None:
            raise ConfigError(
                f"Path for {name} duplicates {existing}: {path}"
            )
        seen[path] = name
