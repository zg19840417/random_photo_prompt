from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import prompt_data
from prompt_engine import generate_prompt_items, render_prompt_lines
from prompt_fluency import fluency_defects

SHOTS = ("head_shot", "half_body", "full_body")
SOLO_PER_SHOT = 15
DUO_PER_SHOT = 10

# 四档与一至三档共用同一套措辞禁令：非视觉词、否定式改写、构图元话术、抽象判断词、面部泛红。
_BANNED_WORDING = (
    "声音", "轻响", "喘息", "鼻息", "心跳", "呼吸", "呻吟", "气息",
    "不过度", "不朝向", "避开正对", "不抢", "不展开", "不打亮", "不过白", "避免", "禁止",
    "画面下缘", "稳定落点", "画面前缘", "镜头前缘", "强透视", "构图", "节奏", "呼吸感", "镜头只看见",
    "危险感", "侵略感", "迷离感", "克制高级", "高级感", "奢华感", "烟火气", "有镜头感", "支配感",
    "泛红", "红晕", "潮红", "红润", "发红", "染红",
)
_AUDIT_BOILERPLATE = ("形状正常", "粗长匀称", "与下腹", "连成一体", "根部紧连", "根部连着", "他自己的", "冠状沟", "马眼", "青筋")
_SCENE_BOUND = ("床上", "床面", "床边", "床垫", "被褥", "沙发", "躺椅", "靠墙")
_FRAMING_PREFIXES = ("肩部以上近景。", "上半身，头到胸入镜。", "半身，头到腰入镜。", "大半身，头到膝入镜。", "全身入镜。")
_AMBIGUOUS_ACTIONS = ("深含", "含住", "含入", "含进", "舔过", "舔舐", "吮吸", "轻吮", "套弄", "撸动")
# 镜头拍不到的部位：与 prompt_data.NSFW_POSE_OUT_OF_SCOPE 和 prompt_fluency 的镜头范围规则一致。
_OUT_OF_FRAME = {
    "head_shot": ("胸部", "胸前", "乳沟", "腰", "臀", "腿", "脚", "身体曲线", "双手", "左手", "右手", "一手", "大腿", "跪", "腰部", "小腿", "双脚", "脚踩", "胯部"),
    "half_body": ("臀部", "小腿", "双脚", "床面", "腿", "膝", "臀", "脚"),
}
_GAZE = re.compile(r"镜头|看向|直视|望")
_MOUTH = re.compile(r"笑|唇|嘴|神情|眉")


def _solo_pool():
    return prompt_data.POSE_EXPRESSION_OPTIONS["nsfw"]


def _duo_pool():
    return prompt_data.POSE_EXPRESSION_OPTIONS["nsfw_duo"]


def _entries():
    for group, pool in (("solo", _solo_pool()), ("duo", _duo_pool())):
        for shot, options in pool.items():
            for index, text in enumerate(options, 1):
                yield group, shot, index, text


class NsfwPosePoolTest(unittest.TestCase):
    def test_pool_is_split_into_solo_and_duo_with_the_expected_sizes(self):
        self.assertEqual(set(_solo_pool()), set(SHOTS))
        self.assertEqual(set(_duo_pool()), set(SHOTS))
        for shot in SHOTS:
            self.assertEqual(len(_solo_pool()[shot]), SOLO_PER_SHOT, shot)
            self.assertEqual(len(_duo_pool()[shot]), DUO_PER_SHOT, shot)
        self.assertIn("data/nsfw_pose_expression_options.json", prompt_data.PROMPT_DATA_SOURCE)

    def test_every_pose_is_one_action_sentence_plus_one_expression_sentence(self):
        # 与一至三档同一条结构规则：动作句。神情句。，子句数不超过 6，单子句不超过 40 字。
        for group, shot, index, text in _entries():
            with self.subTest(group=group, shot=shot, index=index):
                body = text.rstrip("。")
                sentences = body.split("。")
                self.assertEqual(len(sentences), 2, text)
                action, expression = sentences
                action_clauses = [clause for clause in re.split(r"[，；、]", action) if clause]
                expression_clauses = [clause for clause in re.split(r"[，；、]", expression) if clause]
                self.assertLessEqual(len(action_clauses), 6, text)
                self.assertLessEqual(len(expression_clauses), 4, text)
                for clause in action_clauses + expression_clauses:
                    self.assertLessEqual(len(clause), 40, text)

    def test_every_pose_names_gaze_and_expression(self):
        # 一至三档的硬规则：姿势行必须同时写到视线和表情。
        for group, shot, index, text in _entries():
            with self.subTest(group=group, shot=shot, index=index):
                self.assertRegex(text, _GAZE)
                self.assertRegex(text, _MOUTH)

    def test_pose_text_avoids_banned_wording(self):
        for group, shot, index, text in _entries():
            for token in _BANNED_WORDING:
                with self.subTest(group=group, shot=shot, index=index, token=token):
                    self.assertNotIn(token, text)

    def test_pose_text_stays_inside_the_shot_framing(self):
        # 特写只到肩部以上，半身只到腰部以上：画面外的手、腿、跪姿写进去会误导构图。
        for group, shot, index, text in _entries():
            for token in _OUT_OF_FRAME.get(shot, ()):
                with self.subTest(group=group, shot=shot, index=index, token=token):
                    self.assertNotIn(token, text)

    def test_duo_poses_are_written_for_two_women(self):
        # 与一至三档双人同一条措辞规则：两人之间必须贴身互动，不能写成各自摆姿势或分隔两侧。
        for shot, options in _duo_pool().items():
            for index, text in enumerate(options, 1):
                with self.subTest(shot=shot, index=index):
                    self.assertIn("女生", text)
                    self.assertNotRegex(text, r"左手|右手")
                    self.assertRegex(text, r"贴|靠|挨|抱|环|搁|搂|挽|碰")
                    self.assertNotRegex(text, r"各自|一左一右|隔着|两侧各|并排|并肩|旁边")

    def test_solo_poses_name_each_hand_at_most_once(self):
        for shot, options in _solo_pool().items():
            for index, text in enumerate(options, 1):
                with self.subTest(shot=shot, index=index):
                    for hand in ("左手", "右手"):
                        self.assertLessEqual(text.count(hand), 1, text)

    def test_pose_text_drops_unrenderable_audit_boilerplate(self):
        for group, shot, index, text in _entries():
            for token in _AUDIT_BOILERPLATE:
                with self.subTest(group=group, shot=shot, index=index, token=token):
                    self.assertNotIn(token, text)
            self.assertNotRegex(text, r"[A-Za-z]")
            self.assertFalse(text.startswith(_FRAMING_PREFIXES))

    def test_pose_text_names_body_parts_instead_of_pronouns(self):
        for group, shot, index, text in _entries():
            with self.subTest(group=group, shot=shot, index=index):
                # 男性一律写“男人”：图像模型对“他”这类代词的指代支持不可靠。
                self.assertNotIn("他", text)
                # “柱身/根部/整根”必须补齐主体，否则模型不知道要画什么。
                self.assertNotRegex(text, r"(?<!阴茎)柱身")
                self.assertNotRegex(text, r"(?<!阴茎)(?<!大腿)根部")
                self.assertNotRegex(text, r"整根(?!阴茎)")

    def test_pose_text_never_names_the_male_face(self):
        # 正向提示词里写“男人的脸在画外”会被模型反向理解为要画脸，排除男性脸部必须走负面提示词。
        for group, shot, index, text in _entries():
            with self.subTest(group=group, shot=shot, index=index):
                self.assertNotRegex(text, r"男人[^，。]{0,4}(脸|面孔|头部)")

    def test_pose_text_is_scene_neutral(self):
        # 四档场景由 composer 随机生成，姿势不能绑定具体场地。
        for group, shot, index, text in _entries():
            for token in _SCENE_BOUND:
                with self.subTest(group=group, shot=shot, index=index, token=token):
                    self.assertNotIn(token, text)

    def test_pose_text_names_the_male_body_part_in_every_action(self):
        for group, shot, index, text in _entries():
            if any(action in text for action in _AMBIGUOUS_ACTIONS):
                with self.subTest(group=group, shot=shot, index=index):
                    self.assertRegex(text, r"阴茎|龟头")

    def test_fourth_tier_prompts_have_no_fluency_defects(self):
        # 四档姿势行与其余维度一起过同一套通顺门，单人与双人都要零缺陷。
        for cast in ("solo", "duo"):
            for shot in SHOTS:
                for index in range(6):
                    seed = f"nsfw-{cast}-{shot}-{index}"
                    item = generate_prompt_items(1, {"scale": "nsfw", "shot": shot, "era": "modern", "cast": cast}, seed)[0]
                    parts = item["dimension_parts"]
                    lines = render_prompt_lines({**parts, "shot_key": shot, "scale": "nsfw", "aspect": item["aspect"]})
                    with self.subTest(cast=cast, shot=shot, index=index):
                        self.assertEqual(item["cast"], cast)
                        self.assertEqual(fluency_defects(lines, "nsfw", shot), [])
                        pose = parts["pose_expression"].strip("，。 ")
                        self.assertIn(pose, item["positive_prompt"])

    def test_duo_fourth_tier_uses_two_women_and_keeps_the_male_out_of_the_face(self):
        item = generate_prompt_items(1, {"scale": "nsfw", "shot": "full_body", "cast": "duo"}, "nsfw-duo-full")[0]
        lines = render_prompt_lines({**item["dimension_parts"], "shot_key": "full_body", "scale": "nsfw", "aspect": item["aspect"]})
        negative = item["negative_prompt"].lower()
        self.assertTrue(lines["character"].startswith("两个女生都是"))
        self.assertIn("两人", lines["camera"])
        # 男人是画面里合法的第三个人，两张脸也都该在：不能带第三人/第二张脸这类负面词。
        self.assertIn("man's face", negative)
        self.assertNotIn("third person", negative)
        self.assertNotIn("second face", negative)
        self.assertNotIn("two faces", negative)
        # 双人正面写死了两人贴身互动，防粘连词按规则剔除（见 tests/test_negative_prompt_coherence.py），
        # 但人群压制仍在。
        self.assertIn("crowd", negative)
        self.assertNotIn("fused bodies", negative)

    def test_fourth_tier_negative_prompt_excludes_the_male_face(self):
        for cast in ("solo", "duo"):
            for shot in SHOTS:
                item = generate_prompt_items(1, {"scale": "nsfw", "shot": shot, "cast": cast}, f"nsfw-neg-{cast}-{shot}")[0]
                negative = item["negative_prompt"].lower()
                with self.subTest(cast=cast, shot=shot):
                    self.assertIn("man's face", negative)
                    self.assertNotIn("man's face", item["positive_prompt"].lower())

    def test_non_nsfw_tiers_do_not_exclude_the_male_face(self):
        for scale in ("normal", "bold", "bold_no_outfit"):
            item = generate_prompt_items(1, {"scale": scale, "shot": "full_body", "era": "modern"}, f"non-nsfw-{scale}")[0]
            self.assertNotIn("man's face", item["negative_prompt"].lower(), f"{scale} 不该带四档专属的男性脸部负面词")


if __name__ == "__main__":
    unittest.main()
