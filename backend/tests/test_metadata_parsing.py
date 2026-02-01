import unittest
from datetime import datetime, timedelta, timezone

from app.db.enums import AssetType
from app.db.models import Asset
from app.media.metadata import (
    MetadataResult,
    merge_metadata,
    parse_exiftool_payload,
    parse_ffprobe_payload,
)


class ExifParsingTest(unittest.TestCase):
    def test_parse_exiftool_payload_with_offset(self) -> None:
        payload = [
            {
                "DateTimeOriginal": "2020:01:02 03:04:05",
                "OffsetTimeOriginal": "+02:00",
                "ImageWidth": 4000,
                "ImageHeight": 3000,
                "GPSLatitude": 37.5,
                "GPSLongitude": -122.5,
            }
        ]
        result = parse_exiftool_payload(payload)
        self.assertEqual(
            result.captured_at,
            datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=2))),
        )
        self.assertEqual(result.width, 4000)
        self.assertEqual(result.height, 3000)
        self.assertAlmostEqual(result.lat or 0.0, 37.5, places=4)
        self.assertAlmostEqual(result.lon or 0.0, -122.5, places=4)

    def test_parse_exiftool_payload_defaults_to_utc(self) -> None:
        payload = [{"CreateDate": "2020:05:06 07:08:09"}]
        result = parse_exiftool_payload(payload)
        self.assertEqual(
            result.captured_at,
            datetime(2020, 5, 6, 7, 8, 9, tzinfo=timezone.utc),
        )

    def test_parse_exiftool_requires_lat_lon_pair(self) -> None:
        payload = [{"GPSLatitude": 10.0}]
        result = parse_exiftool_payload(payload)
        self.assertIsNone(result.lat)
        self.assertIsNone(result.lon)


class FfprobeParsingTest(unittest.TestCase):
    def test_parse_ffprobe_payload_rotation_and_duration(self) -> None:
        payload = {
            "streams": [
                {
                    "width": 1920,
                    "height": 1080,
                    "tags": {"rotate": "90"},
                }
            ],
            "format": {
                "duration": "12.5",
                "tags": {"creation_time": "2020-01-02T03:04:05Z"},
            },
        }
        result = parse_ffprobe_payload(payload)
        self.assertEqual(result.width, 1080)
        self.assertEqual(result.height, 1920)
        self.assertEqual(result.duration_ms, 12500)
        self.assertEqual(
            result.captured_at,
            datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        )

    def test_parse_ffprobe_payload_duration_tag(self) -> None:
        payload = {
            "streams": [
                {
                    "tags": {"DURATION": "00:00:02.000000000"},
                }
            ],
            "format": {"tags": {"creation_time": "2020-01-02T03:04:05Z"}},
        }
        result = parse_ffprobe_payload(payload)
        self.assertEqual(result.duration_ms, 2000)

    def test_merge_metadata_prefers_exif_dimensions_when_present(self) -> None:
        exif = MetadataResult(width=100, height=200)
        ffprobe = MetadataResult(width=300, duration_ms=4000)
        merged = merge_metadata(exif, ffprobe)
        self.assertEqual(merged.width, 100)
        self.assertEqual(merged.height, 200)
        self.assertEqual(merged.duration_ms, 4000)


class MetadataApplyTest(unittest.TestCase):
    def test_apply_to_asset_can_clear_duration(self) -> None:
        asset = Asset(
            type=AssetType.photo,
            original_path="/tmp/photo.jpg",
            original_bytes=123,
            original_mime="image/jpeg",
        )
        asset.duration_ms = 1200
        result = MetadataResult(duration_ms=2000, width=10, height=20)

        result.apply_to_asset(asset, allow_duration=False)

        self.assertIsNone(asset.duration_ms)
        self.assertEqual(asset.width, 10)
        self.assertEqual(asset.height, 20)


if __name__ == "__main__":
    unittest.main()
