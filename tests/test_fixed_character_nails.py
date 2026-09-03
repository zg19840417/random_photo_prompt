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


if __name__ == "__main__":
    unittest.main()
