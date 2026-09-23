import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompt_engine import _enforce_environment_interaction_pose, generate_prompt_items
from prompt_data import POSE_EXPRESSION_OPTIONS, landscape_pose_expression_options


class ConcretePoseTests(unittest.TestCase):
    def test_no_generic_support_is_invented_for_neon_alley(self):
        parts = {
            "scene_light": "霓虹小巷，冷蓝暖粉灯牌在身后晕开",
            "pose_expression": "她侧身站立，抬眼看镜头，左手拨开发丝",
            "variant_seed": "no-furniture",
        }
        result = _enforce_environment_interaction_pose(parts, "normal", "full_body", "portrait")
        self.assertEqual(result["pose_expression"], parts["pose_expression"])

    def test_scene_cues_do_not_invent_missing_furniture(self):
        for scene in ("窗边的纱帘在日光里飘动", "湖面反射暖光", "丝绒帷幕垂在背景", "一只酒杯放在地上"):
            with self.subTest(scene=scene):
                parts = {"scene_light": scene, "pose_expression": "她站立，抬眼看镜头"}
                result = _enforce_environment_interaction_pose(parts, "bold", "full_body", "portrait")
                self.assertEqual(result["pose_expression"], parts["pose_expression"])

    def test_visible_pool_edge_can_anchor_action(self):
        parts = {"scene_light": "泳池边的浅色瓷砖映着日光", "pose_expression": "她站立，抬眼看镜头"}
        result = _enforce_environment_interaction_pose(parts, "bold", "full_body", "portrait")
        self.assertIn("池边", result["pose_expression"])
        self.assertNotIn("支撑面", result["pose_expression"])

    def test_full_body_reference_pose_has_visible_support_or_floor(self):
        for scale in ("normal", "bold", "bold_no_outfit"):
            for seed in ("anchor-review-0", "anchor-review-1"):
                with self.subTest(scale=scale, seed=seed):
                    item = generate_prompt_items(1, {"scale": scale, "shot": "full_body", "aspect": "portrait"}, seed)[0]
                    prompt = item["positive_prompt"]
                    self.assertNotIn("支撑面", prompt)
                    self.assertNotIn("支撑物", prompt)
                    self.assertNotIn("场景边缘", prompt)
                    self.assertNotIn("场景前缘", prompt)
    def test_non_nsfw_pose_pools_name_real_support(self):
        for scale, shots in POSE_EXPRESSION_OPTIONS.items():
            if scale == "nsfw":
                continue
            for shot, options in shots.items():
                for pose in options:
                    self.assertNotIn("支撑面", pose, (scale, shot))
        for scale in ("normal", "bold"):
            for shot in ("half_body", "large_half_body", "full_body"):
                for pose in landscape_pose_expression_options[scale][shot]:
                    self.assertNotIn("支撑面", pose, (scale, shot))


if __name__ == "__main__":
    unittest.main()
