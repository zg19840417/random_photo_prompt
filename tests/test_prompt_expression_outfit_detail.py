import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompt_engine import generate_prompt_items


class PromptExpressionOutfitDetailTests(unittest.TestCase):

    def test_props_named_in_the_pose_exist_in_the_scene(self):
        for index in range(12):
            parts = generate_prompt_items(
                1, {"scale": "normal", "shot": "half_body", "era": "modern"}, f"detail-normal-mobile-{index}"
            )[0]["dimension_parts"]
            if "栏杆" in parts["pose_expression"]:
                self.assertIn("栏杆", parts["scene_light"])

    def test_final_outfit_and_pose_reach_positive_prompt(self):
        for scale in ("normal", "bold"):
            item = generate_prompt_items(1, {"scale": scale, "shot": "half_body", "era": "modern"}, "detail-0")[0]
            outfit = item["dimension_parts"]["outfit"]
            pose = item["dimension_parts"]["pose_expression"]
            self.assertIn(outfit.split("，")[0], item["positive_prompt"])
            self.assertIn(pose.split("，")[0].replace("人物", "她"), item["positive_prompt"])
            self.assertTrue(any(marker in outfit for marker in ("压线", "接缝", "收省", "折边", "滚边", "袖窿", "车缝")))
        third = generate_prompt_items(1, {"scale": "bold_no_outfit", "shot": "half_body"}, "detail-0")[0]
        self.assertEqual(third["dimension_parts"]["outfit"], "")


if __name__ == "__main__":
    unittest.main()
