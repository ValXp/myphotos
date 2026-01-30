from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
import tempfile
import unittest

import redis
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.app import create_app
from app.auth.sessions import SessionStore, create_session_store
from app.auth.webauthn import (
    LoginChallengeStore,
    RegistrationChallengeStore,
    create_login_store,
    create_registration_store,
)
from app.config import Config, load_config
from app.db.base import Base
from app.db.session import create_engine_from_config, create_session_factory
from app.queue import Queue, RedisQueueBackend

INTEGRATION_FLAG = "INTEGRATION_TESTS"
INTEGRATION_DB_ENV = "INTEGRATION_DB_URL"
INTEGRATION_REDIS_ENV = "INTEGRATION_REDIS_URL"


def integration_enabled() -> bool:
    return os.environ.get(INTEGRATION_FLAG) == "1"


def require_integration() -> None:
    if not integration_enabled():
        raise unittest.SkipTest(
            "integration tests disabled; set INTEGRATION_TESTS=1 to enable"
        )


def _get_env_url(key: str, fallback: str) -> str:
    value = os.environ.get(key) or os.environ.get(fallback)
    if value is None or not value.strip():
        raise RuntimeError(f"{key} (or {fallback}) must be set for integration tests")
    return value


@dataclass
class IntegrationHarness:
    config: Config
    engine: Engine
    session_factory: sessionmaker[Session]
    redis_client: redis.Redis[str]
    data_dir: tempfile.TemporaryDirectory

    @classmethod
    def create(cls) -> "IntegrationHarness":
        require_integration()
        data_dir = tempfile.TemporaryDirectory()
        db_url = _get_env_url(INTEGRATION_DB_ENV, "DB_URL")
        redis_url = _get_env_url(INTEGRATION_REDIS_ENV, "REDIS_URL")
        config = load_config(
            {
                "DATA_ROOT": data_dir.name,
                "APP_ENV": "test",
                "DB_URL": db_url,
                "REDIS_URL": redis_url,
            }
        )
        engine = create_engine_from_config(config)
        session_factory = create_session_factory(engine)
        redis_client = redis.from_url(redis_url, decode_responses=True)
        redis_client.ping()
        harness = cls(
            config=config,
            engine=engine,
            session_factory=session_factory,
            redis_client=redis_client,
            data_dir=data_dir,
        )
        harness.reset()
        return harness

    def reset(self) -> None:
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.redis_client.flushdb()
        self._reset_storage()

    def _reset_storage(self) -> None:
        for path in (
            self.config.paths.originals,
            self.config.paths.derived,
            self.config.paths.temp,
        ):
            if path.exists():
                shutil.rmtree(path)
            path.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        try:
            self.redis_client.close()
        except Exception:
            pass
        self.engine.dispose()
        self.data_dir.cleanup()

    def make_session_store(self) -> SessionStore:
        return create_session_store(self.config, client=self.redis_client)

    def make_challenge_stores(
        self,
    ) -> tuple[RegistrationChallengeStore, LoginChallengeStore]:
        registration = create_registration_store(self.config, client=self.redis_client)
        login = create_login_store(self.config, client=self.redis_client)
        return registration, login

    def make_queue(self) -> Queue:
        return Queue(RedisQueueBackend(self.redis_client))

    def make_app(
        self,
        *,
        session_store: SessionStore | None = None,
        registration_store: RegistrationChallengeStore | None = None,
        login_store: LoginChallengeStore | None = None,
        queue: Queue | None = None,
    ):
        resolved_session = session_store or self.make_session_store()
        if registration_store is None or login_store is None:
            reg_store, login_store_resolved = self.make_challenge_stores()
            registration_store = registration_store or reg_store
            login_store = login_store or login_store_resolved
        resolved_queue = queue or self.make_queue()
        return create_app(
            self.config,
            session_store=resolved_session,
            registration_store=registration_store,
            login_store=login_store,
            db_session_factory=self.session_factory,
            queue=resolved_queue,
        )


class IntegrationTestCase(unittest.TestCase):
    harness: IntegrationHarness

    @classmethod
    def setUpClass(cls) -> None:
        require_integration()
        cls.harness = IntegrationHarness.create()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.harness.close()

    def setUp(self) -> None:
        self.harness.reset()
