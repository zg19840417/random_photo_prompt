import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prompt_engine import _apply_theme_blueprint, _human_pose, _human_scene, build_prompt, generate_prompt_items


class PromptDetailPreservationTests(unittest.TestCase):
    def test_pose_keeps_gaze_lips_and_smile_after_body_and_hand_actions(self):
        pose = _human_pose({
            "scale": "normal",
            "pose_expression": "下巴微低，左手扶住耳饰，抬眼看向镜头，嘴唇微开，嘴角带笑意",
        })
        for detail in ("下巴微低", "左手扶住耳饰", "抬眼看向镜头", "嘴唇微开", "嘴角带笑意"):
            self.assertIn(detail, pose)

    def test_scene_keeps_lighting_after_five_clauses(self):
        scene = _human_scene({"scene_light": "暖调背景，近景散焦，粉色光点，浅蓝反光，空气通透，侧光照亮眼睛"})
        self.assertIn("侧光照亮眼睛", scene)

    def test_third_tier_still_has_no_outfit(self):
        parts = _apply_theme_blueprint(
            {"theme_name": "head_mirror_mist", "variant_seed": "sample"},
            "bold_no_outfit", "head_shot", "portrait", "modern",
        )
        self.assertEqual(parts["outfit"], "")

    def test_generated_outfit_details_survive_final_assembly(self):
        for scale in ("normal", "bold"):
            with self.subTest(scale=scale):
                item = generate_prompt_items(1, {"scale": scale, "shot": "head_shot"}, "offline-head-" + scale)[0]
                outfit = item["dimension_parts"]["outfit"]
                self.assertTrue(outfit)
                garment = outfit.split("，")[0].replace("领口出现在画面下缘", "")
                self.assertIn(garment, item["positive_prompt"])

    def test_long_visual_details_are_not_trimmed(self):
        detail = "，".join(f"肩带边缘的细密刺绣第{i}针" for i in range(30))
        prompt = build_prompt({"scale": "normal", "shot_key": "head_shot", "outfit": detail})
        self.assertIn(detail, prompt)


if __name__ == "__main__":
    unittest.main()
