from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prompt_engine import _apply_environment_anchor_pose, generate_prompt_items


class EraPromptGenerationTest(unittest.TestCase):
    def test_ancient_era_affects_outfit_and_scene_dimensions(self):
        item = generate_prompt_items(
            1,
            {"scale": "bold", "shot": "full_body", "aspect": "portrait", "era": "ancient"},
            seed_text="era-ancient-smoke",
        )[0]

        parts = item["dimension_parts"]

        self.assertNotIn("era", parts)
        ancient_outfit_markers = ("古装", "古典", "古代", "汉服", "中式", "盘扣", "斜襟", "唐制", "襦裙", "披帛", "织金", "裸足", "交领", "高腰裙")
        self.assertTrue(any(marker in parts["outfit"] for marker in ancient_outfit_markers))
        self.assertIn("裸足", parts["outfit"])
        self.assertFalse(any(marker in item["positive_prompt"] for marker in ("云头鞋", "云头绣鞋", "绣鞋", "软底鞋", "舞鞋")))
        self.assertTrue(any(marker in parts["scene_light"] for marker in ("古代", "中式", "宫苑", "屏风", "花窗", "竹帘")))

    def test_modern_era_affects_outfit_and_scene_dimensions(self):
        item = generate_prompt_items(
            1,
            {"scale": "bold", "shot": "full_body", "aspect": "portrait", "era": "modern"},
            seed_text="era-modern-smoke",
        )[0]

        parts = item["dimension_parts"]

        self.assertNotIn("era", parts)
        ancient_outfit_markers = ("古装", "古典", "古代", "汉服", "中式", "盘扣", "斜襟", "唐制", "襦裙", "披帛", "织金", "交领", "高腰裙")
        self.assertFalse(any(marker in parts["outfit"] for marker in ancient_outfit_markers))
        self.assertFalse(any(marker in parts["scene_light"] for marker in ("古代", "宫苑", "屏风", "花窗", "竹帘")))

    def test_keyword_theme_metadata_does_not_leak_into_prompt(self):
        item = generate_prompt_items(
            1,
            {"scale": "bold", "shot": "half_body", "aspect": "portrait", "era": "ancient"},
            seed_text="keyword-theme-metadata",
        )[0]

        parts = item["dimension_parts"]

        self.assertIn("theme_name", parts)
        self.assertIn("theme_keywords", parts)
        self.assertIn("theme_scene_keywords", parts)
        self.assertIn("theme_outfit_keywords", parts)
        self.assertIn("theme_pose_keywords", parts)
        self.assertNotIn("theme_name", item["positive_prompt"])
        self.assertNotIn("theme_keywords", item["positive_prompt"])
        self.assertNotIn("theme_scene_keywords", item["positive_prompt"])
        self.assertNotIn("theme_outfit_keywords", item["positive_prompt"])
        self.assertNotIn("theme_pose_keywords", item["positive_prompt"])
        self.assertNotIn(parts["theme_name"], item["positive_prompt"])

    def test_keyword_theme_tracks_scene_outfit_and_pose_hints(self):
        item = generate_prompt_items(
            1,
            {"scale": "bold", "shot": "half_body", "aspect": "portrait", "era": "modern"},
            seed_text="keyword-theme-three-lanes",
        )[0]

        parts = item["dimension_parts"]
        scene_terms = tuple(term for term in parts["theme_scene_keywords"].split("，") if term)
        outfit_terms = tuple(term for term in parts["theme_outfit_keywords"].split("，") if term)
        pose_terms = tuple(term for term in parts["theme_pose_keywords"].split("，") if term)

        self.assertTrue(scene_terms)
        self.assertTrue(outfit_terms)
        self.assertTrue(pose_terms)
        self.assertTrue(any(term in parts["scene_light"] for term in scene_terms))
        self.assertTrue(any(term in parts["outfit"] for term in outfit_terms))
        self.assertTrue(
            any(term in parts["pose_expression"] for term in pose_terms)
            or parts.get("environment_anchor_locked") == "1"
        )

    def test_ancient_keyword_theme_coordinates_outfit_and_scene(self):
        item = generate_prompt_items(
            1,
            {"scale": "bold", "shot": "half_body", "aspect": "portrait", "era": "ancient"},
            seed_text="keyword-theme-ancient-coordinate",
        )[0]

        parts = item["dimension_parts"]
        theme_terms = tuple(term for term in parts["theme_keywords"].split("，") if term)
        outfit_scene = f'{parts["outfit"]} {parts["scene_light"]}'

        self.assertTrue(any(term in outfit_scene for term in theme_terms))

    def test_seductive_scene_keeps_keyword_theme_location(self):
        item = generate_prompt_items(
            1,
            {"scale": "bold", "shot": "full_body", "aspect": "portrait", "era": "modern"},
            seed_text="kw-sample-bold-full_body-modern",
        )[0]

        parts = item["dimension_parts"]
        location_terms = ("夜店", "吧台", "卧室", "床边", "浴室", "镜面", "泳池", "庭院", "植物", "森林", "木栈道", "酒廊")
        theme_locations = tuple(term for term in parts["theme_keywords"].split("，") if term in location_terms)

        self.assertTrue(theme_locations)
        self.assertTrue(any(marker in parts["scene_light"] for marker in theme_locations))

    def test_head_shot_uses_head_specific_theme_hints(self):
        forbidden_pose_terms = ("全身", "低机位", "脚尖", "裸足", "大腿", "吧椅", "腰线")
        head_scene_terms = ("镜面", "浴室", "卧室", "纱帘", "雾林", "湖边", "花园", "酒吧", "酒廊", "铜镜", "书房", "竹林", "画舫", "民国", "花窗", "温泉", "水汽", "竹帘")
        for era in ("modern", "ancient"):
            item = generate_prompt_items(
                1,
                {"scale": "bold", "shot": "head_shot", "aspect": "portrait", "era": era},
                seed_text=f"head-specific-theme-{era}",
            )[0]
            parts = item["dimension_parts"]

            self.assertFalse(any(term in parts["theme_pose_keywords"] for term in forbidden_pose_terms))
            self.assertTrue(any(term in parts["theme_scene_keywords"] for term in head_scene_terms))
            self.assertTrue(any(term in parts["scene_light"] for term in head_scene_terms))

    def test_head_shot_theme_sampling_stays_head_safe(self):
        forbidden_pose_terms = ("全身", "低机位", "脚尖", "裸足", "大腿", "吧椅", "腰线")
        for era in ("modern", "ancient"):
            for index in range(12):
                item = generate_prompt_items(
                    1,
                    {"scale": "bold", "shot": "head_shot", "aspect": "portrait", "era": era},
                    seed_text=f"head-specific-theme-sampling-{era}-{index}",
                )[0]
                parts = item["dimension_parts"]

                self.assertFalse(any(term in parts["theme_pose_keywords"] for term in forbidden_pose_terms), parts["theme_name"])

    def test_ancient_theme_blueprint_blocks_modern_glamour_mix(self):
        modern_conflict_terms = (
            "连体泳装",
            "泳装",
            "夜店",
            "霓虹",
            "灯带",
            "镜面房",
            "地下酒廊",
            "吊带丝袜",
            "亮钻胸衣",
        )
        ancient_scene_terms = ("古代", "画舫", "雨夜回廊", "宫苑", "书房", "敦煌", "竹林", "苗疆", "民国")
        ancient_outfit_terms = ("交领", "披帛", "高腰", "裸足", "盘扣", "宋制", "唐制", "民国", "苗疆")

        for index in range(12):
            item = generate_prompt_items(
                1,
                {"scale": "bold", "shot": "full_body", "aspect": "portrait", "era": "ancient"},
                seed_text=f"ancient-blueprint-lock-{index}",
            )[0]
            parts = item["dimension_parts"]
            combined = f'{parts["scene_light"]}\n{parts["outfit"]}'

            self.assertEqual(parts.get("theme_blueprint_locked"), "1")
            self.assertTrue(any(term in parts["scene_light"] for term in ancient_scene_terms), parts["scene_light"])
            self.assertTrue(any(term in parts["outfit"] for term in ancient_outfit_terms), parts["outfit"])
            self.assertIn("裸足", parts["outfit"])
            self.assertFalse(any(term in combined for term in ("云头鞋", "云头绣鞋", "绣鞋", "软底鞋", "舞鞋")), combined)
            self.assertFalse(any(term in combined for term in modern_conflict_terms), combined)

    def test_bold_no_outfit_keeps_theme_scene_without_outfit(self):
        for index in range(8):
            item = generate_prompt_items(
                1,
                {"scale": "bold_no_outfit", "shot": "full_body", "aspect": "portrait", "era": "modern"},
                seed_text=f"bold-no-outfit-theme-lock-{index}",
            )[0]
            parts = item["dimension_parts"]
            scene_terms = tuple(term for term in parts["theme_scene_keywords"].split("，") if term)

            self.assertEqual(parts.get("theme_blueprint_locked"), "1")
            self.assertFalse(parts.get("outfit", "").strip())
            self.assertTrue(any(term in parts["scene_light"] for term in scene_terms), parts["scene_light"])

    def test_modern_theme_blueprint_does_not_use_ancient_scene(self):
        ancient_scene_terms = ("古代", "画舫", "雕花窗", "纱帐寝殿", "香炉", "屏风", "铜镜", "竹林月色", "雨夜廊下")
        for index in range(12):
            item = generate_prompt_items(
                1,
                {"scale": "bold", "shot": "full_body", "aspect": "portrait", "era": "modern"},
                seed_text=f"modern-blueprint-lock-{index}",
            )[0]
            parts = item["dimension_parts"]

            self.assertEqual(parts.get("theme_blueprint_locked"), "1")
            self.assertFalse(any(term in parts["scene_light"] for term in ancient_scene_terms), parts["scene_light"])

    def test_full_body_foot_foreground_keeps_leg_connection(self):
        forbidden_terms = ("一只裸足", "一只脚掌", "一只脚尖", "裸足停在", "脚掌和脚尖靠近镜头")
        connection_terms = ("前腿", "小腿", "脚踝", "腿部末端")
        for scale in ("bold", "bold_no_outfit"):
            for aspect in ("portrait", "landscape"):
                for index in range(16):
                    item = generate_prompt_items(
                        1,
                        {"scale": scale, "shot": "full_body", "aspect": aspect, "era": "modern"},
                        seed_text=f"connected-foot-foreground-{scale}-{aspect}-{index}",
                    )[0]
                    prompt = item["positive_prompt"]
                    pose = item["dimension_parts"]["pose_expression"]

                    self.assertFalse(any(term in prompt for term in forbidden_terms), prompt)
                    if "脚掌和脚尖" in pose:
                        self.assertTrue(any(term in pose for term in connection_terms), pose)

    def test_full_body_avoids_high_risk_toe_perspective(self):
        forbidden_terms = (
            "脚掌朝向镜头",
            "脚尖朝向镜头",
            "脚趾甲朝向镜头",
            "脚伸到镜头",
            "脚部在画面下方放大",
            "前脚脚尖",
            "前脚脚背靠近",
            "脚掌和黑色脚趾甲",
            "裸足或脚尖",
            "足弓前景",
            "脚尖成为近景",
            "黑色脚趾甲",
        )
        for scale in ("bold", "bold_no_outfit"):
            for era in ("modern", "ancient"):
                for index in range(20):
                    item = generate_prompt_items(
                        1,
                        {"scale": scale, "shot": "full_body", "aspect": "portrait", "era": era},
                        seed_text=f"full-body-toe-risk-{scale}-{era}-{index}",
                    )[0]
                    prompt = item["positive_prompt"]
                    parts = item["dimension_parts"]

                    self.assertEqual(parts.get("foot_deformation_guard"), "1")
                    self.assertFalse(any(term in prompt for term in forbidden_terms), prompt)

    def test_environment_anchor_pose_rewrites_non_nsfw(self):
        parts = {
            "scene_light": "环境光设定：雨后森林木栈道全身场景，湿木板和深绿色植物压暗成背景",
            "pose_expression": "人物站在低机位镜头前方，左手扶腰，右手贴在大腿上",
            "theme_name": "garden_fog",
        }

        rewritten = _apply_environment_anchor_pose(parts, "bold", "full_body", "portrait")

        self.assertIn("木栈道", rewritten["pose_expression"])
        self.assertTrue(any(term in rewritten["pose_expression"] for term in ("坐在", "跪坐", "手扶")))

    def test_environment_anchor_pose_skips_nsfw(self):
        parts = {
            "scene_light": "环境光设定：深夜卧室床沿全身场景，床头灯和纱帘只形成淡粉暗部",
            "pose_expression": "四档原始姿势文本保持不变",
            "theme_name": "mist_bedroom",
        }

        rewritten = _apply_environment_anchor_pose(parts, "nsfw", "full_body", "portrait")

        self.assertEqual(rewritten["pose_expression"], "四档原始姿势文本保持不变")

    def test_bold_full_body_modern_keeps_theme_outfit_pose_variety(self):
        items = [
            generate_prompt_items(
                1,
                {"scale": "bold", "shot": "full_body", "aspect": "portrait", "era": "modern"},
                seed_text=f"bold-full-body-variety-{index}",
            )[0]
            for index in range(16)
        ]
        parts = [item["dimension_parts"] for item in items]
        themes = {item.get("theme_name") for item in parts}
        outfits = {item.get("outfit") for item in parts}
        poses = {item.get("pose_expression") for item in parts}

        self.assertGreaterEqual(len(themes), 4)
        self.assertGreaterEqual(len(outfits), 4)
        self.assertGreaterEqual(len(poses), 3)

    def test_half_and_full_body_require_environment_interaction(self):
        interaction_terms = (
            "木栈道",
            "木板",
            "树干",
            "树身",
            "树根",
            "枝叶",
            "灌木",
            "草叶",
            "池边",
            "池沿",
            "瓷砖",
            "水面",
            "床沿",
            "床边",
            "床面",
            "床单",
            "纱帘",
            "吧台",
            "吧椅",
            "酒杯",
            "台面",
            "沙发",
            "扶手",
            "坐垫",
            "镜面",
            "镜台",
            "玻璃",
            "窗框",
            "窗棂",
            "门框",
            "低台",
            "低案",
            "案沿",
            "桌案",
            "桌面",
            "卷轴",
            "铜镜",
            "柱",
            "栏杆",
            "地毯",
            "支撑面",
            "支撑物",
            "地面反光",
        )
        for scale in ("normal", "bold", "bold_no_outfit"):
            for shot in ("half_body", "full_body"):
                for index in range(12):
                    item = generate_prompt_items(
                        1,
                        {"scale": scale, "shot": shot, "aspect": "portrait", "era": "modern"},
                        seed_text=f"environment-interaction-required-{scale}-{shot}-{index}",
                    )[0]
                    pose = item["dimension_parts"]["pose_expression"]

                    self.assertTrue(any(term in pose for term in interaction_terms), pose)

    def test_nsfw_does_not_require_environment_interaction(self):
        item = generate_prompt_items(
            1,
            {"scale": "nsfw", "shot": "full_body", "aspect": "portrait", "era": "modern"},
            seed_text="nsfw-no-environment-interaction-rule",
        )[0]

        self.assertNotEqual(item["dimension_parts"].get("environment_interaction_enforced"), "1")

    def test_bold_expression_has_detailed_seductive_face_language(self):
        detail_terms = ("眼尾", "下眼睑", "唇角", "下巴", "呼吸", "唇峰", "睫毛", "眉尾", "狐狸眼", "冷笑")
        for scale in ("bold", "bold_no_outfit"):
            for shot in ("head_shot", "half_body", "full_body"):
                item = generate_prompt_items(
                    1,
                    {"scale": scale, "shot": shot, "aspect": "portrait", "era": "modern"},
                    seed_text=f"detailed-seductive-expression-{scale}-{shot}",
                )[0]
                parts = item["dimension_parts"]
                pose = parts["pose_expression"]

                self.assertEqual(parts.get("emotional_expression_locked"), "1")
                self.assertTrue(any(term in pose for term in detail_terms), pose)

    def test_nsfw_expression_layer_is_not_applied(self):
        item = generate_prompt_items(
            1,
            {"scale": "nsfw", "shot": "full_body", "aspect": "portrait", "era": "modern"},
            seed_text="nsfw-no-emotional-expression-layer",
        )[0]

        self.assertNotEqual(item["dimension_parts"].get("emotional_expression_locked"), "1")

    def test_bold_and_bold_no_outfit_use_reference_seduction_style(self):
        style_terms = ("轻蔑", "冷笑", "狐狸眼", "冷紫", "湿润", "高对比", "黑灰", "压暗")
        for scale in ("bold", "bold_no_outfit"):
            for shot in ("head_shot", "half_body", "full_body"):
                item = generate_prompt_items(
                    1,
                    {"scale": scale, "shot": shot, "aspect": "portrait", "era": "modern"},
                    seed_text=f"reference-seduction-style-{scale}-{shot}",
                )[0]
                parts = item["dimension_parts"]
                combined = f'{parts["pose_expression"]}\n{parts["scene_light"]}'

                self.assertEqual(parts.get("reference_seduction_style_locked"), "1")
                self.assertTrue(any(term in combined for term in style_terms), combined)
                if shot != "head_shot":
                    self.assertTrue(any(term in parts["pose_expression"] for term in ("支撑", "撑住", "倚住", "坐在", "低坐", "支撑面")), parts["pose_expression"])

    def test_head_reference_seduction_style_has_varied_sensual_face_detail(self):
        eye_terms = ("狐狸眼", "眼尾", "下眼睑", "睫毛")
        lip_terms = ("唇峰", "下唇", "唇角", "嘴角", "薄唇", "舌尖")
        hand_terms = ("手", "指尖", "指甲", "指背")
        poses = []
        for index in range(12):
            item = generate_prompt_items(
                1,
                {"scale": "bold", "shot": "head_shot", "aspect": "portrait", "era": "modern"},
                seed_text=f"head-reference-sensual-detail-{index}",
            )[0]
            pose = item["dimension_parts"]["pose_expression"]
            poses.append(pose)

            self.assertTrue(any(term in pose for term in eye_terms), pose)
            self.assertTrue(any(term in pose for term in lip_terms), pose)
            self.assertTrue(any(term in pose for term in hand_terms), pose)

        self.assertGreaterEqual(len(set(poses)), 6)

    def test_reference_seduction_style_skips_normal_and_nsfw(self):
        for scale in ("normal", "nsfw"):
            item = generate_prompt_items(
                1,
                {"scale": scale, "shot": "full_body", "aspect": "portrait", "era": "modern"},
                seed_text=f"reference-seduction-style-skip-{scale}",
            )[0]

            self.assertNotEqual(item["dimension_parts"].get("reference_seduction_style_locked"), "1")

    def test_krea2_portrait_workflow_adds_orientation_guard(self):
        source = (ROOT / "__init__.py").read_text(encoding="utf-8")

        self.assertIn("def _apply_krea2_portrait_orientation_guard", source)
        self.assertIn("Krea2竖屏正立头部构图", source)
        self.assertIn("upright vertical full body portrait", source)
        self.assertIn("人物身体主轴保持竖直方向", source)
        self.assertIn("def _patch_krea2_negative_text_node", source)
        self.assertIn('"class_type"] = "CLIPTextEncode"', source)
        self.assertIn('"title": "Negative Prompt"', source)
        self.assertIn("头顶朝向画面上方", source)
        self.assertIn("rotated image", source)
        self.assertIn("横向脸部", source)
        self.assertIn("positive_prompt, negative_prompt = _apply_krea2_portrait_orientation_guard", source)


if __name__ == "__main__":
    unittest.main()
