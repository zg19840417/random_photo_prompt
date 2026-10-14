import unittest

from prompt_resolution import MOBILE_CUSTOM_RESOLUTION_PRESETS, MOBILE_MAX_IMAGE_EDGE, mobile_custom_resolution, mobile_resolution_for_custom_prompt


class PromptResolutionTests(unittest.TestCase):
    def test_only_four_text_to_image_presets_remain(self):
        self.assertEqual(
            set(MOBILE_CUSTOM_RESOLUTION_PRESETS),
            {"864x1536", "1024x1536", "1536x1536", "1536x1024"},
        )

    def test_custom_size_is_clamped_to_max_edge(self):
        resolution = mobile_custom_resolution("", "3000x2000")
        self.assertEqual(max(resolution["width"], resolution["height"]), MOBILE_MAX_IMAGE_EDGE)
        self.assertEqual((resolution["width"], resolution["height"]), (1920, 1280))

    def test_custom_size_at_new_max_edge_is_not_scaled_down(self):
        self.assertEqual(MOBILE_MAX_IMAGE_EDGE, 1920)
        for size, expected in (("1920x1664", (1920, 1664)), ("1920x1680", (1920, 1664)), ("1664x1920", (1664, 1920))):
            with self.subTest(size=size):
                resolution = mobile_custom_resolution("", size)
                self.assertEqual((resolution["width"], resolution["height"]), expected)

    def test_custom_square_uses_square_aspect(self):
        resolution = mobile_custom_resolution("", "960x960")
        self.assertEqual(resolution["aspect"], "square")

    def test_portrait_output_is_exact_nine_sixteen(self):
        for text in ("站立全身", "半身", "头部特写", ""):
            result = mobile_resolution_for_custom_prompt(text)
            self.assertEqual((result["width"], result["height"]), (864, 1536))
        result = mobile_custom_resolution("", "864x1536")
        self.assertEqual((result["width"], result["height"]), (864, 1536))


if __name__ == "__main__":
    unittest.main()
