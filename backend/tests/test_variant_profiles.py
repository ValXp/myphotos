import unittest
from pathlib import Path

from app.db.enums import AssetType, AssetVariantKind
from app.media.variants import (
    LIVE_VIDEO_PROFILE,
    THUMBNAIL_PROFILES,
    VIDEO_POSTER_PROFILE,
    VIDEO_RENDITION_PROFILES,
    build_variant_record,
    profiles_for_asset_type,
    variant_output_path,
)


class VariantProfilesTest(unittest.TestCase):
    def test_profiles_for_photo(self) -> None:
        profiles = profiles_for_asset_type(AssetType.photo)
        self.assertEqual(profiles, THUMBNAIL_PROFILES)
        self.assertTrue(all(profile.kind == AssetVariantKind.thumb for profile in profiles))

    def test_profiles_for_video_include_posters_and_renditions(self) -> None:
        profiles = profiles_for_asset_type(AssetType.video)
        self.assertIn(VIDEO_POSTER_PROFILE, profiles)
        for profile in VIDEO_RENDITION_PROFILES:
            self.assertIn(profile, profiles)
        self.assertTrue(
            any(profile.kind == AssetVariantKind.video_transcode for profile in profiles)
        )

    def test_profiles_for_live_photo_include_live_video(self) -> None:
        profiles = profiles_for_asset_type(AssetType.live_photo)
        self.assertIn(LIVE_VIDEO_PROFILE, profiles)
        self.assertTrue(
            any(profile.kind == AssetVariantKind.live_video for profile in profiles)
        )
        for profile in VIDEO_RENDITION_PROFILES:
            self.assertIn(profile, profiles)

    def test_variant_output_path(self) -> None:
        derived_root = Path("/data/derived")
        asset_id = "asset-123"
        profile = THUMBNAIL_PROFILES[0]
        expected = derived_root / asset_id / profile.kind.value / profile.filename()
        self.assertEqual(variant_output_path(derived_root, asset_id, profile), expected)

    def test_build_variant_record(self) -> None:
        derived_root = Path("/data/derived")
        asset_id = "asset-456"
        profile = VIDEO_RENDITION_PROFILES[0]
        record = build_variant_record(
            derived_root,
            asset_id,
            profile,
            size_bytes=2048,
        )
        self.assertEqual(record.asset_id, asset_id)
        self.assertEqual(record.kind, AssetVariantKind.video_transcode)
        self.assertEqual(record.profile, profile.name)
        self.assertEqual(
            record.path,
            str(variant_output_path(derived_root, asset_id, profile)),
        )
        self.assertEqual(record.bytes, 2048)


if __name__ == "__main__":
    unittest.main()
