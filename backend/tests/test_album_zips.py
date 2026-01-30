import io
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
        self.owner_client = TestClient(self.app)
        self.public_client = TestClient(self.app)
        session = self.session_store.create("user-1")
        self.owner_client.cookies.set(self.config.session.cookie_name, session.id)
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

        album_response = self.owner_client.post("/albums", json={"title": "Downloads"})
        self.assertEqual(album_response.status_code, 200)
        album_id = album_response.json()["id"]
        add_response = self.owner_client.post(
            f"/albums/{album_id}/items",
            json={"asset_ids": [asset.id for asset in assets]},
        )
        self.assertEqual(add_response.status_code, 200)

        zip_response = self.owner_client.post(f"/albums/{album_id}/zip")
        self.assertEqual(zip_response.status_code, 200)
        zip_body = zip_response.json()
        self.assertEqual(zip_body["status"], "done")
        self.assertEqual(zip_body["album_id"], album_id)
        self.assertIsNotNone(zip_body.get("job_id"))
        self.assertEqual(zip_body.get("download_url"), f"/albums/{album_id}/zip/download")

        status_response = self.owner_client.get(f"/albums/{album_id}/zip")
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
        album_response = self.owner_client.post("/albums", json={"title": "Empty"})
        self.assertEqual(album_response.status_code, 200)
        album_id = album_response.json()["id"]

        status_response = self.owner_client.get(f"/albums/{album_id}/zip")
        self.assertEqual(status_response.status_code, 200)
        status_body = status_response.json()
        self.assertEqual(status_body["status"], "idle")
        self.assertIsNone(status_body.get("download_url"))

    def test_zip_download_and_invalidation(self) -> None:
        assets = [
            Asset(
                id="00000000-0000-0000-0000-000000000711",
                type=AssetType.photo,
                original_path="a.jpg",
                original_bytes=5,
                original_mime="image/jpeg",
            ),
            Asset(
                id="00000000-0000-0000-0000-000000000712",
                type=AssetType.photo,
                original_path="b.jpg",
                original_bytes=5,
                original_mime="image/jpeg",
            ),
            Asset(
                id="00000000-0000-0000-0000-000000000713",
                type=AssetType.photo,
                original_path="c.jpg",
                original_bytes=7,
                original_mime="image/jpeg",
            ),
        ]
        self._write_file(self.config.paths.originals / "c.jpg", b"charlie")
        with self.session_factory() as db:
            db.add_all(assets)
            db.commit()

        album_response = self.owner_client.post("/albums", json={"title": "Downloads"})
        self.assertEqual(album_response.status_code, 200)
        album_id = album_response.json()["id"]
        add_response = self.owner_client.post(
            f"/albums/{album_id}/items",
            json={"asset_ids": [assets[0].id, assets[1].id]},
        )
        self.assertEqual(add_response.status_code, 200)

        zip_response = self.owner_client.post(f"/albums/{album_id}/zip")
        self.assertEqual(zip_response.status_code, 200)

        owner_download = self.owner_client.get(f"/albums/{album_id}/zip/download")
        self.assertEqual(owner_download.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(owner_download.content), "r") as archive:
            names = sorted(archive.namelist())
            self.assertEqual(names, ["a.jpg", "b.jpg"])

        share_response = self.owner_client.post(f"/albums/{album_id}/shares")
        self.assertEqual(share_response.status_code, 200)
        token = share_response.json()["token"]
        public_download = self.public_client.get(
            f"/public/shares/{token}/zip/download"
        )
        self.assertEqual(public_download.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(public_download.content), "r") as archive:
            names = sorted(archive.namelist())
            self.assertEqual(names, ["a.jpg", "b.jpg"])

        add_response = self.owner_client.post(
            f"/albums/{album_id}/items",
            json={"asset_ids": [assets[2].id]},
        )
        self.assertEqual(add_response.status_code, 200)

        status_response = self.owner_client.get(f"/albums/{album_id}/zip")
        self.assertEqual(status_response.status_code, 200)
        status_body = status_response.json()
        self.assertEqual(status_body["status"], "idle")
        self.assertIsNone(status_body.get("download_url"))

        invalidated_download = self.owner_client.get(
            f"/albums/{album_id}/zip/download"
        )
        self.assertEqual(invalidated_download.status_code, 404)
        invalidated_public = self.public_client.get(
            f"/public/shares/{token}/zip/download"
        )
        self.assertEqual(invalidated_public.status_code, 404)

        with self.session_factory() as db:
            record = (
                db.query(AlbumZip)
                .filter(AlbumZip.album_id == album_id)
                .one()
            )
            self.assertIsNotNone(record.invalidated_at)

    def _write_file(self, path: Path, payload: bytes) -> None:
        path.write_bytes(payload)


if __name__ == "__main__":
    unittest.main()
