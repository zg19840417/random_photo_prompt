import json
import unittest
from pathlib import Path


class FixedCharacterNailsTests(unittest.TestCase):
    def test_every_character_scope_contains_required_nails(self):
        path = Path(__file__).resolve().parents[1] / "data" / "prompt_pools.json"
        characters = json.loads(path.read_text(encoding="utf-8"))["CHARACTER_IDENTITY_BY_SHOT"]
        for scope, options in characters.items():
            with self.subTest(scope=scope):
                self.assertTrue(options)
                self.assertTrue(all("黑色渐变的手指甲又细又长" in text for text in options))
                self.assertTrue(all("又细又长的黑色手指甲点缀反光银粉" not in text for text in options))

    def test_full_body_character_states_short_natural_toenails_and_negative_blocks_black_ones(self):
        root = Path(__file__).resolve().parents[1]
        import sys

        sys.path.insert(0, str(root))
        from negative_prompt_engine import build_chinese_negative_prompt, build_negative_prompt

        characters = json.loads((root / "data" / "prompt_pools.json").read_text(encoding="utf-8"))["CHARACTER_IDENTITY_BY_SHOT"]
        for text in characters["full_body"]:
            self.assertIn("黑色渐变的手指甲又细又长", text)
            self.assertIn("脚趾甲短而圆润，涂着自然的裸粉色", text)
        for text in characters["head_shot"] + characters["half_body"]:
            self.assertNotIn("脚趾甲", text)
        self.assertIn("black toenails", build_negative_prompt("", {}, "bold", "full_body", "portrait"))
        self.assertIn("黑色脚趾甲", build_chinese_negative_prompt("", {}, "bold", "full_body", "portrait"))

    def test_character_identity_leaves_makeup_details_to_makeup_dimension(self):
        path = Path(__file__).resolve().parents[1] / "data" / "prompt_pools.json"
        characters = json.loads(path.read_text(encoding="utf-8"))["CHARACTER_IDENTITY_BY_SHOT"]
        makeup_markers = ("妆", "眼线", "眼影", "睫毛", "闪粉", "唇彩")
        for scope, options in characters.items():
            for option in options:
                with self.subTest(scope=scope):
                    self.assertFalse(any(marker in option for marker in makeup_markers), option)


if __name__ == "__main__":
    unittest.main()
