import tempfile
import unittest
from pathlib import Path

from app.config import (
    DEFAULT_DB_URL,
    DEFAULT_REDIS_URL,
    DEFAULT_SESSION_COOKIE_NAME,
    DEFAULT_SESSION_TTL_SECONDS,
    DEFAULT_WEBAUTHN_RP_NAME,
    ConfigError,
    load_config,
)


class ConfigLoaderTest(unittest.TestCase):
    def test_load_config_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            config = load_config({"DATA_ROOT": root})

            data_root = Path(root).resolve()
            self.assertEqual(config.paths.data_root, data_root)
            self.assertEqual(config.paths.originals, data_root / "originals")
            self.assertEqual(config.paths.derived, data_root / "derived")
            self.assertEqual(config.paths.temp, data_root / "temp")
            self.assertEqual(config.database.url, DEFAULT_DB_URL)
            self.assertEqual(config.redis.url, DEFAULT_REDIS_URL)
            self.assertEqual(config.app.env, "development")
            self.assertEqual(config.app.host, "127.0.0.1")
            self.assertEqual(config.app.port, 8000)
            self.assertEqual(config.app.log_level, "INFO")
            self.assertEqual(config.app.trusted_proxy_ips, ())
            self.assertIsNone(config.app.frontend_dist_dir)
            self.assertEqual(config.webauthn.rp_id, "127.0.0.1")
            self.assertEqual(config.webauthn.rp_name, DEFAULT_WEBAUTHN_RP_NAME)
            self.assertEqual(config.webauthn.origins, ("http://127.0.0.1:8000",))
            self.assertEqual(config.session.ttl_seconds, DEFAULT_SESSION_TTL_SECONDS)
            self.assertEqual(config.session.cookie_name, DEFAULT_SESSION_COOKIE_NAME)

    def test_load_config_overrides_paths(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            config = load_config(
                {
                    "DATA_ROOT": root,
                    "ORIGINALS_DIR": "orig",
                    "DERIVED_DIR": str(Path(root) / "derived-store"),
                    "TEMP_DIR": "tmp",
                }
            )

            data_root = Path(root).resolve()
            self.assertEqual(config.paths.originals, data_root / "orig")
            self.assertEqual(config.paths.derived, data_root / "derived-store")
            self.assertEqual(config.paths.temp, data_root / "tmp")

    def test_invalid_port(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ConfigError):
                load_config({"DATA_ROOT": root, "APP_PORT": "not-a-number"})
            with self.assertRaises(ConfigError):
                load_config({"DATA_ROOT": root, "APP_PORT": "70000"})

    def test_empty_values_are_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ConfigError):
                load_config({"DATA_ROOT": root, "DB_URL": "  "})

    def test_postgres_url_is_normalized_to_psycopg(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            config = load_config(
                {
                    "DATA_ROOT": root,
                    "DB_URL": "postgresql://myphotos:myphotos@localhost:5432/myphotos",
                }
            )
            self.assertEqual(
                config.database.url,
                "postgresql+psycopg://myphotos:myphotos@localhost:5432/myphotos",
            )

    def test_duplicate_paths_raise(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ConfigError):
                load_config(
                    {
                        "DATA_ROOT": root,
                        "ORIGINALS_DIR": "same",
                        "DERIVED_DIR": "same",
                    }
                )

    def test_render_contains_expected_fields(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            config = load_config({"DATA_ROOT": root, "APP_PORT": "8080"})
            rendered = config.render()
            self.assertIn('"paths"', rendered)
            self.assertIn('"database"', rendered)
            self.assertIn('"redis"', rendered)
            self.assertIn('"webauthn"', rendered)
            self.assertIn('"app"', rendered)
            self.assertIn('"session"', rendered)
            self.assertIn('"port": 8080', rendered)
            self.assertIn('"trusted_proxy_ips"', rendered)
            self.assertIn('"frontend_dist_dir"', rendered)

    def test_webauthn_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            config = load_config(
                {
                    "DATA_ROOT": root,
                    "WEBAUTHN_RP_ID": "photos.local",
                    "WEBAUTHN_RP_NAME": "My Photos",
                    "WEBAUTHN_ORIGINS": "https://photos.local, https://photos.corp",
                }
            )

            self.assertEqual(config.webauthn.rp_id, "photos.local")
            self.assertEqual(config.webauthn.rp_name, "My Photos")
            self.assertEqual(
                config.webauthn.origins,
                ("https://photos.local", "https://photos.corp"),
            )

    def test_session_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            config = load_config(
                {
                    "DATA_ROOT": root,
                    "SESSION_TTL_SECONDS": "7200",
                    "SESSION_COOKIE_NAME": "photos_session",
                }
            )

            self.assertEqual(config.session.ttl_seconds, 7200)
            self.assertEqual(config.session.cookie_name, "photos_session")

    def test_trusted_proxy_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            config = load_config(
                {
                    "DATA_ROOT": root,
                    "TRUSTED_PROXY_IPS": "10.0.0.1, 10.0.0.0/24",
                }
            )

            self.assertEqual(
                config.app.trusted_proxy_ips,
                ("10.0.0.1", "10.0.0.0/24"),
            )

    def test_frontend_dist_override(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            dist_path = Path(root) / "dist"
            config = load_config(
                {
                    "DATA_ROOT": root,
                    "FRONTEND_DIST_DIR": str(dist_path),
                }
            )

            self.assertEqual(config.app.frontend_dist_dir, dist_path.resolve())
