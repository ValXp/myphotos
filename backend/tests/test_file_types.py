import unittest
from pathlib import Path

from app.ingest.file_types import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    LivePhotoPair,
    find_live_photo_pairs,
    is_image,
    is_live_photo_pair,
    is_supported,
    is_video,
    normalize_extension,
)


class FileTypeRegistryTest(unittest.TestCase):
    def test_normalize_extension(self) -> None:
        self.assertEqual(normalize_extension("photo.JPG"), "jpg")
        self.assertEqual(normalize_extension(Path("video.MP4")), "mp4")
        self.assertEqual(normalize_extension("archive"), "")
        self.assertEqual(normalize_extension("bundle.tar.gz"), "gz")

    def test_is_image_and_video(self) -> None:
        self.assertTrue(is_image("photo.HEIC"))
        self.assertTrue(is_video("movie.MOV"))
        self.assertFalse(is_image("movie.MOV"))
        self.assertFalse(is_video("photo.HEIC"))
        self.assertFalse(is_supported("notes.txt"))
        sample_image = next(iter(IMAGE_EXTENSIONS))
        sample_video = next(iter(VIDEO_EXTENSIONS))
        self.assertTrue(is_image(f"sample.{sample_image}"))
        self.assertTrue(is_video(f"sample.{sample_video}"))

    def test_is_live_photo_pair(self) -> None:
        still = Path("/photos/IMG_0001.HEIC")
        video = Path("/photos/IMG_0001.MOV")
        other_video = Path("/photos/IMG_0002.MOV")
        other_dir_video = Path("/other/IMG_0001.MOV")
        image_b = Path("/photos/IMG_0001.JPG")

        self.assertTrue(is_live_photo_pair(still, video))
        self.assertTrue(is_live_photo_pair(video, still))
        self.assertFalse(is_live_photo_pair(other_video, still))
        self.assertFalse(is_live_photo_pair(other_dir_video, still))
        self.assertFalse(is_live_photo_pair(image_b, still))

    def test_find_live_photo_pairs(self) -> None:
        still = Path("/photos/IMG_0001.HEIC")
        video = Path("/photos/IMG_0001.MOV")
        still_two = Path("/photos/IMG_0002.JPG")
        video_two = Path("/photos/IMG_0002.MP4")
        unrelated = Path("/photos/README.txt")

        pairs = find_live_photo_pairs([still, video, unrelated, still_two, video_two])

        self.assertEqual(
            pairs,
            [
                LivePhotoPair(still=still, video=video),
                LivePhotoPair(still=still_two, video=video_two),
            ],
        )


if __name__ == "__main__":
    unittest.main()
