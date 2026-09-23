import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prompt_engine import build_prompt


class PromptOutputOrderTests(unittest.TestCase):
    def test_prompt_follows_pose_scene_quality_camera_identity_outfit_makeup_order(self):
        prompt = build_prompt(
            {
                "scale": "normal",
                "shot_key": "half_body",
                "aspect": "landscape",
                "pose_expression": "她侧身倚靠窗边，抬眼看向镜头，嘴角带浅笑，双手停在腰侧",
                "scene_light": "海边彩色露台场景，柔和日光照亮环境，浅色地面反射暖光",
                "quality": "真实胶片质感，细节清晰",
                "camera": "低机位",
                "character": "人物标记，黑发，狐狸眼，黑色渐变的手指甲又细又长",
                "outfit": "珊瑚色服装标记，轻薄布料贴合肩线",
                "makeup": "妆容标记，浅棕眼影，自然薄唇",
            },
        )
        markers = (
            "她侧身倚靠窗边",
            "海边彩色露台场景",
            "真实胶片质感",
            "低机位",
            "人物标记",
            "珊瑚色服装标记",
            "妆容标记",
        )
        positions = [prompt.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))


if __name__ == "__main__":
    unittest.main()
