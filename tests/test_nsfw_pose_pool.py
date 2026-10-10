from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import prompt_data
from prompt_engine import generate_prompt_items


class NsfwPosePoolTest(unittest.TestCase):
    def test_fourth_tier_uses_the_versioned_thirty_rule_pool(self):
        pool = prompt_data.POSE_EXPRESSION_OPTIONS["nsfw"]

        self.assertEqual(set(pool), {"head_shot", "half_body", "full_body"})
        self.assertEqual(sum(len(options) for options in pool.values()), 30)
        self.assertTrue(all(len(pool[shot]) == 10 for shot in pool))
        self.assertIn("data/nsfw_pose_expression_options.json", prompt_data.PROMPT_DATA_SOURCE)

    def test_nsfw_pose_text_drops_unrenderable_audit_boilerplate(self):
        pool = prompt_data.POSE_EXPRESSION_OPTIONS["nsfw"]
        banned = ("形状正常", "粗长匀称", "与下腹", "连成一体", "根部紧连", "根部连着", "他自己的", "冠状沟", "马眼", "青筋")
        framing = ("肩部以上近景。", "上半身，头到胸入镜。", "半身，头到腰入镜。", "大半身，头到膝入镜。", "全身入镜。")
        for shot, options in pool.items():
            for text in options:
                for token in banned:
                    self.assertNotIn(token, text, f"{shot} 仍含审核话术 {token}")
                self.assertFalse(text.startswith(framing), f"{shot} 仍以景别说明开头")

        for shot, options in pool.items():
            for text in options:
                self.assertNotRegex(text, r"[A-Za-z]", f"{shot} 混入拉丁字符")

    def test_nsfw_pose_text_names_body_parts_instead_of_pronouns(self):
        pool = prompt_data.POSE_EXPRESSION_OPTIONS["nsfw"]
        for shot, options in pool.items():
            for text in options:
                # 男性一律写“男人”：图像模型对“他”这类代词的指代支持不可靠。
                self.assertNotIn("他", text, f"{shot} 使用了男性代词“他”")
                # “柱身/根部/整根”必须补齐主体，否则模型不知道要画什么。
                # “大腿根部”指大腿本身，是完整名词搭配，不算指代不明。
                self.assertNotRegex(text, r"(?<!阴茎)柱身", f"{shot} 的“柱身”缺少主体")
                self.assertNotRegex(text, r"(?<!阴茎)(?<!大腿)根部", f"{shot} 的“根部”缺少主体")
                self.assertNotRegex(text, r"整根(?!阴茎)", f"{shot} 的“整根”缺少主体")

    def test_nsfw_pose_text_never_names_the_male_face(self):
        pool = prompt_data.POSE_EXPRESSION_OPTIONS["nsfw"]
        for shot, options in pool.items():
            for text in options:
                # 正向提示词里写“男人的脸在画外”会被模型反向理解为要画脸，
                # 所以正向只许描述入画的身体部位，排除男性脸部必须走负面提示词。
                self.assertNotRegex(text, r"男人[^，。]{0,4}(脸|面孔|头部)", f"{shot} 正向提示词点名了男人脸部")

    def test_fourth_tier_negative_prompt_excludes_the_male_face(self):
        for shot in ("head_shot", "half_body", "full_body"):
            item = generate_prompt_items(1, {"scale": "nsfw", "shot": shot, "era": "modern"}, f"nsfw-neg-{shot}")[0]
            negative = item["negative_prompt"].lower()
            self.assertIn("man's face", negative, f"{shot} 的负面提示词缺少男性脸部排除项")
            self.assertNotIn("man's face", item["positive_prompt"].lower())

    def test_non_nsfw_tiers_do_not_exclude_the_male_face(self):
        for scale in ("normal", "bold", "bold_no_outfit"):
            item = generate_prompt_items(1, {"scale": scale, "shot": "full_body", "era": "modern"}, f"non-nsfw-{scale}")[0]
            self.assertNotIn("man's face", item["negative_prompt"].lower(), f"{scale} 不该带四档专属的男性脸部负面词")

    def test_fourth_tier_pose_text_is_scene_neutral(self):
        # 四档场景由 composer 在 25 个地点里随机生成，姿势不能绑定具体场地，
        # 否则会和场景对不上；所以池里禁止出现床、沙发这类固定道具。
        pool = prompt_data.POSE_EXPRESSION_OPTIONS["nsfw"]
        scene_bound = ("床上", "床面", "床边", "床垫", "被褥", "沙发", "躺椅", "靠墙")
        for shot, options in pool.items():
            for text in options:
                for token in scene_bound:
                    self.assertNotIn(token, text, f"{shot} 绑定了具体场地“{token}”，会与随机场景冲突")

    def test_nsfw_pose_text_names_the_male_body_part_in_every_action(self):
        pool = prompt_data.POSE_EXPRESSION_OPTIONS["nsfw"]
        # 「深含」「舔过顶端」这类动作必须点明作用对象，否则模型不知道要画什么部位。
        # 只有跨坐骑乘这类动作本身就是部位交互，可以不写。
        ambiguous_actions = ("深含", "含住", "含入", "含进", "舔过", "舔舐", "吮吸", "轻吮", "套弄", "撸动")
        for shot, options in pool.items():
            for text in options:
                if any(action in text for action in ambiguous_actions):
                    self.assertRegex(
                        text,
                        r"阴茎|龟头",
                        f"{shot} 的交互动词没有写明作用部位：{text}",
                    )

    def test_nsfw_pose_text_stays_inside_the_shot_framing(self):
        pool = prompt_data.POSE_EXPRESSION_OPTIONS["nsfw"]
        # 特写只到肩部以上，镜头外的手、腿、跪姿写进去会误导构图；半身只到腰部以上。
        out_of_frame = {
            "head_shot": ("双手", "左手", "右手", "一手", "大腿", "跪", "腰部", "臀", "小腿", "双脚", "脚踩", "胯部", "床面"),
            "half_body": ("臀部", "小腿", "双脚", "床面"),
        }
        for shot, banned in out_of_frame.items():
            for text in pool[shot]:
                for token in banned:
                    self.assertNotIn(token, text, f"{shot} 写到了画面外的 {token}")

    def test_nsfw_pose_line_is_not_rewritten_after_selection(self):
        for shot in ("half_body", "full_body"):
            item = generate_prompt_items(1, {"scale": "nsfw", "shot": shot, "era": "modern"}, f"nsfw-verbatim-{shot}")[0]
            pose = item["dimension_parts"]["pose_expression"].strip("，。 ")
            self.assertIn(pose, item["positive_prompt"])


if __name__ == "__main__":
    unittest.main()
