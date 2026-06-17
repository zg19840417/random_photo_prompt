from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prompt_engine import generate_prompt_items


class EraPromptGenerationTest(unittest.TestCase):
    def test_ancient_era_affects_outfit_and_scene_dimensions(self):
        item = generate_prompt_items(
            1,
            {"scale": "bold", "shot": "full_body", "aspect": "portrait", "era": "ancient"},
            seed_text="era-ancient-smoke",
        )[0]

        parts = item["dimension_parts"]

        self.assertNotIn("era", parts)
        self.assertTrue(any(marker in parts["outfit"] for marker in ("古装", "汉服", "中式", "盘扣", "斜襟")))
        self.assertTrue(any(marker in parts["scene_light"] for marker in ("古代", "中式", "宫苑", "屏风", "花窗", "竹帘")))

    def test_modern_era_affects_outfit_and_scene_dimensions(self):
        item = generate_prompt_items(
            1,
            {"scale": "bold", "shot": "full_body", "aspect": "portrait", "era": "modern"},
            seed_text="era-modern-smoke",
        )[0]

        parts = item["dimension_parts"]

        self.assertNotIn("era", parts)
        self.assertFalse(any(marker in parts["outfit"] for marker in ("古装", "汉服", "中式", "盘扣", "斜襟")))
        self.assertFalse(any(marker in parts["scene_light"] for marker in ("古代", "宫苑", "屏风", "花窗", "竹帘")))


if __name__ == "__main__":
    unittest.main()
