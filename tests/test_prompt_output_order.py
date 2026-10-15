import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prompt_engine import build_prompt, render_prompt_lines


class PromptOutputOrderTests(unittest.TestCase):
    def test_fingernail_identity_is_scoped_for_all_scales_and_casts(self):
        from prompt_engine import generate_prompt_items

        text = "她微微侧过脸。她看向镜头，唇角微微扬起。"
        with patch("prompt_composer.pose_expression_options_by_aspect", return_value=[text]):
            for scale in ("normal", "bold", "bold_no_outfit", "nsfw"):
                for cast in ("solo", "duo"):
                    for era in ("modern", "ancient"):
                        for shot in ("head_shot", "half_body", "full_body"):
                            for aspect in ("portrait", "landscape", "square"):
                                with self.subTest(scale=scale, cast=cast, era=era, shot=shot, aspect=aspect):
                                    item = generate_prompt_items(1, dict(scale=scale, cast=cast, era=era, shot=shot, aspect=aspect), "nail-scope")[0]
                                    line = render_prompt_lines(item["dimension_parts"])["character"]
                                    self.assertEqual("黑色渐变的手指甲" in line, shot != "full_body")
                                    if shot == "full_body":
                                        self.assertIn("脚趾甲短而圆润，涂着自然的裸粉色", line)

    PARTS = {
        "scale": "normal",
        "shot_key": "half_body",
        "aspect": "landscape",
        "lens": "85mm 人像镜头",
        "camera_line": "低机位，腰部以上的横向半身构图",
        "character": "人物脸部标记，黑色渐变的手指甲，魅惑狐狸眼",
        "body": "性感锁骨，小蛮腰",
        "makeup": "清透裸妆，浅棕眼影，自然薄唇",
        "outfit": "珊瑚色服装标记，轻薄布料贴合肩线",
        "pose_expression": "她侧身倚靠窗边，抬眼看向镜头，嘴角带浅笑，双手停在腰侧",
        "scene_light": "海边彩色露台场景，柔和日光照亮环境，浅色地面反射暖光",
        "quality": "真实胶片调色，画面以红和蓝为主色，高光不过曝",
    }

    def test_prompt_follows_camera_character_outfit_pose_scene_order(self):
        prompt = build_prompt(dict(self.PARTS))
        markers = (
            "85mm 人像镜头",
            "低机位",
            "人物脸部标记",
            "化着清透裸妆",
            "性感锁骨",
            "珊瑚色服装标记",
            "她侧身倚靠窗边",
            "海边彩色露台场景",
            "真实胶片调色",
        )
        positions = [prompt.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))

    def test_lens_joins_camera_line_and_scene_shares_a_paragraph_with_grade(self):
        paragraphs = build_prompt(dict(self.PARTS)).split("\n\n")
        self.assertEqual(len(paragraphs), 5)
        self.assertTrue(paragraphs[0].startswith("85mm 人像镜头，低机位"))
        self.assertIn("化着清透裸妆", paragraphs[1])
        self.assertTrue(paragraphs[4].startswith("海边彩色露台场景"))
        self.assertIn("真实胶片调色", paragraphs[4])
        self.assertNotIn("85mm", paragraphs[4])

    def test_makeup_sits_between_identity_face_and_body_without_changing_their_text(self):
        import random
        from prompt_composer import compose_parts

        for shot in ("head_shot", "half_body", "full_body"):
            with self.subTest(shot=shot):
                parts = compose_parts("normal", shot, "portrait", random.Random(f"identity-{shot}"), render_prompt_lines)
                line = render_prompt_lines({**parts, "shot_key": shot, "scale": "normal", "aspect": "portrait"})["character"]
                if shot == "full_body":
                    self.assertTrue(line.startswith("22岁瓷白冷白皮K-pop韩国美女，瓷器般细腻冷白皮肤"))
                    self.assertNotIn("黑色渐变的手指甲", line)
                else:
                    self.assertTrue(line.startswith("22岁瓷白冷白皮K-pop韩国美女，黑色渐变的手指甲"))
                    self.assertIn("黑色渐变的手指甲，瓷器般细腻冷白皮肤", line)
                self.assertLess(line.index("眼角附近有一颗细小的美人痣"), line.index("化着"))
                if shot == "head_shot":
                    self.assertEqual(parts["body"], "")
                else:
                    self.assertLess(line.index("化着"), line.index("性感锁骨"))
                    self.assertTrue(parts["body"].startswith("性感锁骨"))
                if shot == "full_body":
                    self.assertTrue(line.rstrip("。").endswith("脚趾甲短而圆润，涂着自然的裸粉色"))


if __name__ == "__main__":
    unittest.main()
