import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompt_data import pose_expression_options_by_aspect
from prompt_engine import _apply_emotional_seduction_expression, _apply_reference_seduction_style, generate_prompt_items
from prompt_postprocess import clean_global_prompt_text, simplify_pose_language


class PromptExpressionOutfitDetailTests(unittest.TestCase):
    def test_normal_expression_only_fills_missing_face_cues(self):
        pose = "她坐在窗边，下巴微抬，右手拢住发尾，眼神看向镜头，嘴角带笑"
        parts = _apply_emotional_seduction_expression({"pose_expression": pose}, "normal", "half_body", "portrait")
        self.assertEqual(parts["pose_expression"], pose)
        missing = _apply_emotional_seduction_expression(
            {"pose_expression": "她站在镜前，头部微低，手指拨开发丝"}, "normal", "half_body", "portrait"
        )["pose_expression"]
        self.assertIn("头部微低", missing)
        self.assertIn("手指拨开发丝", missing)
        self.assertIn("嘴", missing)
        self.assertTrue("眼神" in missing or "视线" in missing)

    def test_bold_pose_options_have_distinct_visible_actions_after_cleanup(self):
        options = set()
        for i in range(30):
            pose = _apply_reference_seduction_style(
                {"pose_expression": f"起始动作{i}", "variant_seed": str(i), "scene_light": "阳光阳台"},
                "bold", "half_body", "portrait",
            )["pose_expression"]
            pose = clean_global_prompt_text({"pose_expression": pose}, "half_body", "bold")["pose_expression"]
            options.add(pose)
            self.assertNotIn("窄光", pose)
            self.assertNotIn("脚", pose)
        self.assertGreaterEqual(len(options), 7)

    def test_two_hands_without_separator_keep_distinct_sides(self):
        pose = simplify_pose_language(
            {"pose_expression": "她倚着栏杆，一手搭栏一手垂落，眼神看向镜头，嘴角带笑"}
        )["pose_expression"]
        self.assertIn("左手搭栏右手垂落", pose)
        self.assertNotIn("左手搭栏左手", pose)
        normalized = pose_expression_options_by_aspect("normal", "half_body", "portrait")
        self.assertTrue(any("左手搭栏右手垂落" in item for item in normalized))

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
        generated = generate_prompt_items(
            1, {"scale": "normal", "shot": "half_body", "era": "modern"}, "detail-normal-mobile"
        )[0]["dimension_parts"]["pose_expression"]
        self.assertIn("左手拢住发尾，右手自然垂落", generated)
        self.assertNotIn("栏杆", generated)

    def test_final_outfit_and_pose_reach_positive_prompt(self):
        for scale in ("normal", "bold"):
            item = generate_prompt_items(1, {"scale": scale, "shot": "half_body", "era": "modern"}, "detail-0")[0]
            outfit = item["dimension_parts"]["outfit"]
            pose = item["dimension_parts"]["pose_expression"]
            self.assertIn(outfit.split("，")[0], item["positive_prompt"])
            self.assertIn(pose.split("，")[0].replace("人物", "她"), item["positive_prompt"])
            self.assertTrue(any(marker in outfit for marker in ("压线", "接缝", "收省", "折边", "滚边", "袖窿", "车缝线")))
        third = generate_prompt_items(1, {"scale": "bold_no_outfit", "shot": "half_body"}, "detail-0")[0]
        self.assertEqual(third["dimension_parts"]["outfit"], "")


if __name__ == "__main__":
    unittest.main()
