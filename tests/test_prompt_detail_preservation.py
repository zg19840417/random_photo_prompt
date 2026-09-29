import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prompt_engine import build_prompt, generate_prompt_items, render_prompt_lines


class PromptDetailPreservationTests(unittest.TestCase):
    """最终提示词逐字保留各维度文字：只补句号和“她穿着”，不裁剪、不改写。"""

    def test_pose_keeps_every_detail_verbatim(self):
        text = "下巴微低，左手扶住耳饰，抬眼看向镜头，嘴唇微开，嘴角带笑意"
        self.assertEqual(render_prompt_lines({"pose_expression": text})["pose"], text + "。")

    def test_scene_keeps_lighting_after_many_clauses(self):
        text = "暖调背景，近景散焦，粉色光点，浅蓝反光，空气通透，侧光照亮眼睛"
        self.assertEqual(render_prompt_lines({"scene_light": text})["scene"], text + "。")

    def test_generated_outfit_survives_final_assembly(self):
        for scale in ("normal", "bold"):
            with self.subTest(scale=scale):
                item = generate_prompt_items(1, {"scale": scale, "shot": "head_shot"}, "offline-head-" + scale)[0]
                outfit = item["dimension_parts"]["outfit"]
                self.assertTrue(outfit)
                self.assertIn(f"她穿着{outfit}。", item["positive_prompt"])

    def test_long_visual_details_are_not_trimmed(self):
        detail = "，".join(f"肩带边缘的细密刺绣第{i}针" for i in range(30))
        prompt = build_prompt({"scale": "normal", "shot_key": "head_shot", "outfit": detail})
        self.assertIn(detail, prompt)


if __name__ == "__main__":
    unittest.main()
