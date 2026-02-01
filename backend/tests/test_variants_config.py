import unittest
from pathlib import Path

from app.db.enums import AssetType
from app.media.variants import (
    DEFAULT_VIDEO_RENDITION_PROFILES,
    THUMBNAIL_PROFILES,
    profiles_for_asset_type,
    variant_output_path,
    video_renditions_from_config,
)


class VariantConfigTest(unittest.TestCase):
    def test_profiles_for_asset_type_rejects_unknown(self) -> None:
        with self.assertRaises(ValueError):
            profiles_for_asset_type("unknown")  # type: ignore[arg-type]

    def test_variant_output_path_requires_asset_id(self) -> None:
        with self.assertRaises(ValueError):
            variant_output_path(Path("/tmp"), "", THUMBNAIL_PROFILES[0])

    def test_video_renditions_defaults_when_none_or_empty(self) -> None:
        for value in (None, [], [{}]):
            profiles = video_renditions_from_config(
                value if isinstance(value, list) else value,
                source_width=1920,
                source_height=1080,
                source_is_hdr=False,
            )
            self.assertEqual(profiles, DEFAULT_VIDEO_RENDITION_PROFILES)

    def test_video_renditions_filters_invalid_entries(self) -> None:
        profiles = video_renditions_from_config(
            [
                {"name": "", "width": 1280, "height": 720, "video_bitrate_kbps": 1000, "audio_bitrate_kbps": 96},
                {"name": "720p", "width": "1280", "height": 720, "video_bitrate_kbps": 1000, "audio_bitrate_kbps": 96},
                {"name": "720p", "width": 1280, "height": 720, "video_bitrate_kbps": "1000", "audio_bitrate_kbps": 96},
            ],
            source_width=1920,
            source_height=1080,
            source_is_hdr=False,
        )
        # No valid profiles means we fall back to defaults.
        self.assertEqual(profiles, DEFAULT_VIDEO_RENDITION_PROFILES)

    def test_video_renditions_respect_source_minimums(self) -> None:
        renditions = [
            {
                "name": "tiny",
                "width": 320,
                "height": 180,
                "video_bitrate_kbps": 200,
                "audio_bitrate_kbps": 64,
                "min_source_width": 1000,
            },
            {
                "name": "ok",
                "width": 640,
                "height": 360,
                "video_bitrate_kbps": 800,
                "audio_bitrate_kbps": 96,
                "min_source_width": 600,
            },
        ]

        # Unknown dimensions -> min_source_* renditions are skipped.
        unknown = video_renditions_from_config(
            renditions,
            source_width=None,
            source_height=None,
            source_is_hdr=False,
        )
        self.assertEqual(unknown, DEFAULT_VIDEO_RENDITION_PROFILES)

        # Too small -> only "ok" is excluded/included accordingly.
        small = video_renditions_from_config(
            renditions,
            source_width=800,
            source_height=600,
            source_is_hdr=False,
        )
        self.assertEqual(len(small), 1)
        self.assertEqual(small[0].name, "ok")

    def test_video_renditions_hdr_only_for_hdr_sources(self) -> None:
        renditions = [
            {
                "name": "hdr",
                "width": 1280,
                "height": 720,
                "video_bitrate_kbps": 1200,
                "audio_bitrate_kbps": 128,
                "hdr": True,
            },
            {
                "name": "sdr",
                "width": 1280,
                "height": 720,
                "video_bitrate_kbps": 1200,
                "audio_bitrate_kbps": 128,
            },
        ]

        sdr_profiles = video_renditions_from_config(
            renditions,
            source_width=1920,
            source_height=1080,
            source_is_hdr=False,
        )
        self.assertEqual([profile.name for profile in sdr_profiles], ["sdr"])

        hdr_profiles = video_renditions_from_config(
            renditions,
            source_width=1920,
            source_height=1080,
            source_is_hdr=True,
        )
        self.assertEqual([profile.name for profile in hdr_profiles], ["hdr", "sdr"])
        self.assertTrue(hdr_profiles[0].hdr)


if __name__ == "__main__":
    unittest.main()
