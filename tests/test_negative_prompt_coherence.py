from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from negative_prompt_engine import build_chinese_negative_prompt, build_negative_prompt
from prompt_engine import generate_prompt_items

SCALES = ("normal", "bold", "bold_no_outfit", "nsfw")
SHOTS = ("head_shot", "half_body", "full_body")

# 双采工作流的 ZIB 阶段（1ST，cfg=4）真正吃负面词（提交的是中文负面词），
# 英文负面词用于其余入口；两套词表共用同一套拼装规则，这里分别断言。
_TEETH_POSITIVE = "她仰起脸对着镜头笑得露出一点牙齿，眼睛弯成月牙。"
_SOFT_LIGHT_POSITIVE = "柔光均匀地包住她，光线变得柔和而均匀，皮肤像瓷一样细腻。"
_CONTACT_POSITIVE = "两人手臂交缠着搂紧彼此的腰，胸口相贴，四条长腿紧密交叠缠绕着向前伸出。"
_PLAIN_POSITIVE = "她站在窗边，目光平静地看向镜头，嘴唇微张。"


def _chinese(positive, scale="normal", shot="full_body", cast="solo", aspect="portrait"):
    return build_chinese_negative_prompt(positive, {"cast": cast}, scale, shot, aspect, 1024, 1536)


def _english(positive, scale="normal", shot="full_body", cast="solo", aspect="portrait"):
    return build_negative_prompt(positive, {"cast": cast}, scale, shot, aspect, 1024, 1536)


class NegativePromptCoherenceTests(unittest.TestCase):
    def test_toothy_smile_terms_follow_the_positive(self):
        # 正面要求露齿的笑，就不能同时压“大笑露齿 / teeth showing”。
        self.assertNotIn("大笑露齿", _chinese(_TEETH_POSITIVE))
        self.assertNotIn("teeth showing", _english(_TEETH_POSITIVE))
        self.assertNotIn("wide grin", _english(_TEETH_POSITIVE))
        # 正面没有露齿要求时，保持原有压制。
        self.assertIn("大笑露齿", _chinese(_PLAIN_POSITIVE))
        self.assertIn("teeth showing", _english(_PLAIN_POSITIVE))

    def test_front_teeth_are_not_suppressed(self):
        positive = "她看向镜头，嘴唇微张，露出少许门牙。"
        for scale in ("bold", "bold_no_outfit"):
            self.assertNotIn("大笑露齿", _chinese(positive, scale))
            self.assertNotIn("teeth showing", _english(positive, scale))

    def test_missing_feet_terms_only_in_full_body(self):
        for scale in SCALES:
            for shot in SHOTS:
                for aspect in ("portrait", "landscape"):
                    chinese = _chinese(_PLAIN_POSITIVE, scale, shot, "solo", aspect)
                    english = _english(_PLAIN_POSITIVE, scale, shot, "solo", aspect)
                    with self.subTest(scale=scale, shot=shot, aspect=aspect):
                        if shot == "full_body":
                            self.assertIn("缺脚", chinese)
                            self.assertIn("missing feet", english)
                        else:
                            # 头部/半身镜头里没有脚，“缺脚”会和同一条负面词里的“脚部/鞋子”自相矛盾。
                            self.assertNotIn("缺脚", chinese)
                            self.assertNotIn("missing feet", english)

    def test_flat_light_term_follows_the_positive(self):
        self.assertNotIn("平光", _chinese(_SOFT_LIGHT_POSITIVE, "nsfw"))
        self.assertNotIn("flat lighting", _english(_SOFT_LIGHT_POSITIVE, "nsfw"))
        # 正面没有柔光要求时，nsfw 仍保留“平光”压制。
        self.assertIn("平光", _chinese(_PLAIN_POSITIVE, "nsfw"))
        self.assertIn("flat lighting", _english(_PLAIN_POSITIVE, "nsfw"))

    def test_duo_negatives_never_suppress_the_required_close_contact(self):
        # 双人姿势按规则必须写两人贴身、交叠、缠绕的互动，所以负面词里不能出现会压回两人分开的词条。
        for scale, cast_positive in (("bold", _CONTACT_POSITIVE), ("bold", _PLAIN_POSITIVE), ("nsfw", _CONTACT_POSITIVE)):
            chinese = _chinese(cast_positive, scale, "full_body", "duo")
            english = _english(cast_positive, scale, "full_body", "duo")
            with self.subTest(scale=scale):
                self.assertNotIn("身体粘连", chinese)
                self.assertNotIn("肢体融合", chinese)
                self.assertNotIn("fused bodies", english)
                self.assertNotIn("merged limbs", english)
                # 防畸形与人群压制仍由这几条承担。
                self.assertIn("重复肢体", chinese)
                self.assertIn("crowd", english)
                if scale == "nsfw":
                    # 四档双人里的男人是合法第三人，只保留人群压制。
                    self.assertNotIn("第三个人", chinese)
                    self.assertNotIn("third person", english)
                else:
                    self.assertIn("多余手臂", chinese)
                    self.assertIn("extra arms", english)
                    self.assertIn("第三个人", chinese)
        # 单人不受影响：双人专属词条本来就不会加进单人负面词。
        self.assertNotIn("多余手臂", _chinese(_PLAIN_POSITIVE, "bold", "full_body", "solo"))

    def test_generated_negatives_never_contradict_the_positive(self):
        teeth_markers = ("露齿", "牙齿", "门牙", "笑出声", "大笑")
        soft_markers = ("柔光", "散射", "柔和的光", "柔和而均匀", "均匀地包住")
        for scale in SCALES:
            for shot in SHOTS:
                for cast in ("solo", "duo"):
                    for index in range(6):
                        seed = f"neg-coherence-{scale}-{shot}-{cast}-{index}"
                        item = generate_prompt_items(1, {"scale": scale, "shot": shot, "cast": cast, "era": "modern"}, seed)[0]
                        parts = item["dimension_parts"]
                        positive = item["positive_prompt"]
                        chinese = build_chinese_negative_prompt(positive, parts, scale, shot, item["aspect"], item["width"], item["height"])
                        english = build_negative_prompt(positive, parts, scale, shot, item["aspect"], item["width"], item["height"])
                        with self.subTest(scale=scale, shot=shot, cast=cast, index=index):
                            if shot != "full_body":
                                self.assertNotIn("缺脚", chinese)
                                self.assertNotIn("missing feet", english)
                            if any(marker in positive for marker in teeth_markers):
                                self.assertNotIn("大笑露齿", chinese)
                                self.assertNotIn("teeth showing", english)
                            if any(marker in positive for marker in soft_markers):
                                self.assertNotIn("平光", chinese)
                                self.assertNotIn("flat lighting", english)
                            if cast == "duo":
                                self.assertNotIn("身体粘连", chinese)
                                self.assertNotIn("肢体融合", chinese)
                                self.assertNotIn("fused bodies", english)


if __name__ == "__main__":
    unittest.main()
