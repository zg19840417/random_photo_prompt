import unittest

from prompt_resolution import MOBILE_CUSTOM_RESOLUTION_PRESETS, MOBILE_MAX_IMAGE_EDGE, mobile_custom_resolution


class PromptResolutionTests(unittest.TestCase):
    def test_only_four_text_to_image_presets_remain(self):
        self.assertEqual(
            set(MOBILE_CUSTOM_RESOLUTION_PRESETS),
            {"768x1536", "1024x1536", "1536x1536", "1536x1024"},
        )

    def test_custom_size_is_clamped_to_max_edge(self):
        resolution = mobile_custom_resolution("", "3000x2000")
        self.assertEqual(max(resolution["width"], resolution["height"]), MOBILE_MAX_IMAGE_EDGE)
        self.assertEqual((resolution["width"], resolution["height"]), (1536, 1024))


if __name__ == "__main__":
    unittest.main()
