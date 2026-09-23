import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompt_engine import _RECENT_SCENE_CATEGORIES, generate_prompt_items


class PromptScenePoseCoherenceTests(unittest.TestCase):
    def sample(self, scale, shot, seed):
        _RECENT_SCENE_CATEGORIES.clear()
        return generate_prompt_items(1, {"scale": scale, "shot": shot, "era": "modern"}, seed)[0]

    def test_full_body_pose_does_not_use_absent_sofa(self):
        item = self.sample("normal", "full_body", "dcf6097809c3cfa3")
        parts = item["dimension_parts"]
        self.assertFalse("沙发" in parts["pose_expression"] and "沙发" not in parts["scene_light"])
        self.assertTrue(any(word in parts["pose_expression"] for word in ("脚", "足", "站立")))

    def test_walkway_pose_does_not_claim_wooden_path_on_balcony(self):
        item = self.sample("normal", "full_body", "1b8cd2ed016f4dc7")
        parts = item["dimension_parts"]
        if "木栈道" not in parts["scene_light"]:
            self.assertNotIn("木栈道", parts["pose_expression"])
        self.assertIn("脚", parts["pose_expression"])

    def test_head_outfit_and_framing_read_naturally(self):
        item = self.sample("bold", "head_shot", "d2cecdce2cbfedcb")
        prompt = item["positive_prompt"]
        self.assertNotIn("裹胸领口出现在", prompt)
        self.assertEqual(prompt.count("肩部以上近景"), 1)
        if "冷蓝与暖粉光点" in prompt:
            self.assertNotIn("亮部暖金高光", prompt)

    def test_bold_full_body_private_scene_and_eye_color_agree(self):
        item = self.sample("bold", "full_body", "8ac7473be1ae2809")
        parts = item["dimension_parts"]
        self.assertNotIn("书店", parts["scene_light"])
        self.assertNotIn("浅棕美瞳", parts["makeup"])
        self.assertNotIn("浅棕瞳孔", parts["makeup"])

    def test_skin_base_makeup_is_not_rewritten_as_backdrop(self):
        from prompt_postprocess import clean_sentence
        self.assertEqual(clean_sentence("冷白底妆保留肤纹", "full_body", "bold"), "冷白底妆保留肤纹")

    def test_bold_studio_pose_makeup_and_scene_are_drawable(self):
        item = self.sample("bold", "full_body", "fd07b2260012bfd6")
        parts = item["dimension_parts"]
        self.assertNotIn("头部大幅后仰后用狐狸眼俯视镜头", item["positive_prompt"])
        self.assertNotIn("有眼神直视镜头", parts["makeup"])
        if "暖色摄影棚" in parts["scene_light"]:
            self.assertIn("哑光地面", parts["scene_light"])
            self.assertIn("柔光", parts["scene_light"])

    def test_reference_sitting_pose_has_readable_gaze_and_lips(self):
        from prompt_engine import _REFERENCE_STYLE_POSE_BY_SHOT
        pose = _REFERENCE_STYLE_POSE_BY_SHOT["full_body"][-1]
        self.assertIn("视线看向镜头，单侧唇角轻轻上扬", pose)
        self.assertNotIn("嘴角带弧度看向镜头", pose)

    def test_head_outfit_subject_precedes_shoulder_detail(self):
        item = self.sample("normal", "head_shot", "a3a1d707d623e15a")
        self.assertNotIn("针织背心的一侧宽肩带", item["positive_prompt"])

    def test_third_tier_scene_avoids_public_venues(self):
        for seed in ("public-0", "private-1", "private-2", "private-3"):
            with self.subTest(seed=seed):
                item = self.sample("bold_no_outfit", "half_body", seed)
                scene = item["dimension_parts"]["scene_light"]
                self.assertFalse(any(word in scene for word in ("甜品店", "咖啡馆", "电影院", "书店")), scene)
                self.assertFalse(item["dimension_parts"]["outfit"])


if __name__ == "__main__":
    unittest.main()
