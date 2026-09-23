import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompt_engine import _apply_environment_anchor_pose, _apply_theme_blueprint, generate_prompt_items


class PromptSceneAuthorityTests(unittest.TestCase):
    def test_theme_cannot_rewrite_other_scene_pose_and_grade(self):
        parts = {
            "theme_name": "pool_noon",
            "scene_light": "书店落地窗前，自然光映暖白侧脸，书架在背景里",
            "pose_expression": "她倚着书架回望镜头",
            "quality": "暖色自然光写真",
            "outfit": "蓝色棉衬衫",
        }
        result = _apply_theme_blueprint(parts, "bold", "full_body", "portrait", "modern")
        for name in ("pose_expression", "quality", "outfit"):
            self.assertEqual(result[name], parts[name])

    def test_environment_anchor_only_uses_final_scene(self):
        parts = {
            "scene_light": "书店落地窗前，暖白光照亮书架",
            "theme_scene_keywords": "森林，木栈道，湿木板",
            "theme_name": "garden_fog",
            "pose_expression": "她倚着书架回望镜头",
        }
        result = _apply_environment_anchor_pose(parts, "normal", "half_body", "portrait")
        self.assertEqual(result["pose_expression"], parts["pose_expression"])

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
