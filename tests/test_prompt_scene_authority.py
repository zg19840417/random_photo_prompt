import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompt_engine import generate_prompt_items


class PromptSceneAuthorityTests(unittest.TestCase):
    def test_generated_prompt_keeps_scene_and_grade_compatible(self):
        selections = {"scale": "bold", "shot": "full_body", "aspect": "portrait"}
        for seed in range(12):
            item = generate_prompt_items(1, selections, f"scene-authority-{seed}")[0]
            scene = item["dimension_parts"]["scene_light"]
            quality = item["positive_prompt"]
            if "书店" in scene:
                self.assertNotIn("泳池私房调色", quality)
                self.assertNotIn("夜景私房调色", quality)


if __name__ == "__main__":
    unittest.main()
