import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.auth.sessions import InMemorySessionStore
from app.config import load_config
from app.db.base import Base
from app.db.enums import AssetType
from app.db.models import AlbumZip, Asset
from app.db.session import create_engine_from_config, create_session_factory


class AlbumZipIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config = load_config(
            {
                "DATA_ROOT": self.temp_dir.name,
                "APP_ENV": "test",
                "DB_URL": f"sqlite+pysqlite:///{os.path.join(self.temp_dir.name, 'test.db')}",
            }
        )
        self.engine = create_engine_from_config(self.config)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.session_factory = create_session_factory(self.engine)
        self.session_store = InMemorySessionStore(default_ttl_seconds=300)
        self.app = create_app(
            self.config,
            session_store=self.session_store,
            db_session_factory=self.session_factory,
        )
        self.client = TestClient(self.app)
        session = self.session_store.create("user-1")
        self.client.cookies.set(self.config.session.cookie_name, session.id)
        self.config.paths.originals.mkdir(parents=True, exist_ok=True)
        self._write_file(self.config.paths.originals / "a.jpg", b"alpha")
        self._write_file(self.config.paths.originals / "b.jpg", b"bravo")

    def test_zip_job_create_and_status(self) -> None:
        assets = [
            Asset(
                id="00000000-0000-0000-0000-000000000701",
                type=AssetType.photo,
                original_path="a.jpg",
                original_bytes=5,
                original_mime="image/jpeg",
            ),
            Asset(
                id="00000000-0000-0000-0000-000000000702",
                type=AssetType.photo,
                original_path="b.jpg",
                original_bytes=5,
                original_mime="image/jpeg",
            ),
        ]
        with self.session_factory() as db:
            db.add_all(assets)
            db.commit()

        album_response = self.client.post("/albums", json={"title": "Downloads"})
        self.assertEqual(album_response.status_code, 200)
        album_id = album_response.json()["id"]
        add_response = self.client.post(
            f"/albums/{album_id}/items",
            json={"asset_ids": [asset.id for asset in assets]},
        )
        self.assertEqual(add_response.status_code, 200)

        zip_response = self.client.post(f"/albums/{album_id}/zip")
        self.assertEqual(zip_response.status_code, 200)
        zip_body = zip_response.json()
        self.assertEqual(zip_body["status"], "done")
        self.assertEqual(zip_body["album_id"], album_id)
        self.assertIsNotNone(zip_body.get("job_id"))
        self.assertEqual(zip_body.get("download_url"), f"/albums/{album_id}/zip/download")

        status_response = self.client.get(f"/albums/{album_id}/zip")
        self.assertEqual(status_response.status_code, 200)
        status_body = status_response.json()
        self.assertEqual(status_body["status"], "done")

        with self.session_factory() as db:
            record = (
                db.query(AlbumZip)
                .filter(AlbumZip.album_id == album_id)
                .one()
            )
            zip_path = Path(record.path)
            if not zip_path.is_absolute():
                zip_path = self.config.paths.derived / zip_path
        self.assertTrue(zip_path.exists())
        with zipfile.ZipFile(zip_path, "r") as archive:
            names = sorted(archive.namelist())
            self.assertEqual(names, ["a.jpg", "b.jpg"])
            self.assertEqual(archive.read("a.jpg"), b"alpha")
            self.assertEqual(archive.read("b.jpg"), b"bravo")

    def test_zip_status_idle_before_job(self) -> None:
        album_response = self.client.post("/albums", json={"title": "Empty"})
        self.assertEqual(album_response.status_code, 200)
        album_id = album_response.json()["id"]

        status_response = self.client.get(f"/albums/{album_id}/zip")
        self.assertEqual(status_response.status_code, 200)
        status_body = status_response.json()
        self.assertEqual(status_body["status"], "idle")
        self.assertIsNone(status_body.get("download_url"))

    def _write_file(self, path: Path, payload: bytes) -> None:
        path.write_bytes(payload)


if __name__ == "__main__":
    unittest.main()
