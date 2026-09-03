import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from video_prompt_engine import normalize_video_seconds
from video_resolution import image_to_video_resolution


class VideoRuntimeLimitsTests(unittest.TestCase):
    def test_four_second_default_is_allowed(self):
        self.assertEqual(normalize_video_seconds(4), 4)
        self.assertEqual(normalize_video_seconds(None), 4)

    def test_image_to_video_resolution_preserves_aspect_ratio_and_caps_runtime_limits(self):
        cases = {
            (1920, 1280): (960, 640),
            (1280, 1920): (640, 960),
            (1536, 1536): (768, 768),
            (789, 1080): (672, 896),
        }
        with tempfile.TemporaryDirectory() as directory:
            for source_size, expected_size in cases.items():
                image_path = Path(directory) / f"{source_size[0]}x{source_size[1]}.png"
                Image.new("RGB", source_size).save(image_path)
                width, height = image_to_video_resolution(image_path)
                self.assertEqual((width, height), expected_size)
                self.assertLessEqual(max(width, height), 960)
                self.assertLessEqual(width * height, 620_000)
                self.assertEqual(width % 32, 0)
                self.assertEqual(height % 32, 0)


if __name__ == "__main__":
    unittest.main()
