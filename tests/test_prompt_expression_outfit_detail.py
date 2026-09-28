import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompt_engine import generate_prompt_items
from prompt_postprocess import clean_global_prompt_text, simplify_pose_language


class PromptExpressionOutfitDetailTests(unittest.TestCase):

    def test_two_hands_without_separator_keep_distinct_sides(self):
        pose = simplify_pose_language(
            {"pose_expression": "她倚着栏杆，一手搭栏一手垂落，眼神看向镜头，嘴角带笑"}
        )["pose_expression"]
        self.assertIn("左手搭栏右手垂落", pose)
        self.assertNotIn("左手搭栏左手", pose)

    def test_rail_pose_does_not_invent_rail_without_scene(self):
        pose = "她倚着栏杆，左手搭栏右手垂落，抬眼看镜头"
        no_rail = clean_global_prompt_text(
            {"pose_expression": pose, "scene_light": "酒店落地窗前，阳光照进室内"}, "half_body", "normal"
        )["pose_expression"]
        self.assertNotIn("栏杆", no_rail)
        self.assertIn("左手拢住发尾，右手自然垂落", no_rail)
        with_rail = clean_global_prompt_text(
            {"pose_expression": pose, "scene_light": "阳台栏杆边，阳光照进来"}, "half_body", "normal"
        )["pose_expression"]
        self.assertIn("栏杆", with_rail)
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
