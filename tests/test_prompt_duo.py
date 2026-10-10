import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prompt_composer import POOLS
from prompt_engine import generate_prompt_items, render_prompt_lines
from prompt_fluency import fluency_defects

DUO = POOLS["DUO"]
_SIZES = {"portrait": (864, 1536), "landscape": (1536, 1024), "square": (1536, 1536)}
_OUT_OF_SCOPE = {"head_shot": r"腰|腿|脚|胸前", "half_body": r"脚|腿|臀|膝"}


def _duo_poses():
    for group, aspects in DUO["POSES"].items():
        for aspect, shots in aspects.items():
            for shot, poses in shots.items():
                for pose in poses:
                    yield group, aspect, shot, pose


class DuoPromptTests(unittest.TestCase):
    def sample(self, scale, shot, aspect, seed, era="modern"):
        width, height = _SIZES[aspect]
        return generate_prompt_items(1, {"scale": scale, "shot": shot, "aspect": aspect, "width": width, "height": height, "era": era, "cast": "duo"}, seed)[0]

    def test_duo_pools_cover_every_table_and_energy(self):
        for group in ("normal", "bold"):
            for aspect, shots in (("portrait", ("head_shot", "half_body", "full_body")), ("landscape", ("head_shot", "half_body", "full_body")), ("square", ("half_body", "full_body"))):
                for shot in shots:
                    with self.subTest(group=group, aspect=aspect, shot=shot):
                        self.assertTrue(DUO["POSES"][group][aspect][shot])
            for energy in ("calm", "playful", "dynamic"):
                self.assertTrue(DUO["EXPRESSIONS"][group][energy])

    def test_duo_poses_follow_frame_scope_and_wording_rules(self):
        for group, aspect, shot, pose in _duo_poses():
            body = pose["body"]
            with self.subTest(body=body):
                self.assertIn("两人" if "两人" in body else "女生", body)
                self.assertNotRegex(body, r"左手|右手|画面下缘|稳定落点|构图|节奏|呼吸感|强透视|避免|不过度")
                if aspect == "portrait":
                    self.assertNotRegex(body, r"横向|躺|趴|侧卧|俯卧")
                elif aspect == "landscape":
                    self.assertRegex(body, r"横向|躺|卧|趴|沿.*展开")
                else:
                    self.assertIn("斜", body)
                if shot in _OUT_OF_SCOPE:
                    self.assertNotRegex(body, _OUT_OF_SCOPE[shot])
                if group == "bold":
                    self.assertNotRegex(body, r"衣|裙|裤|领|袖|肩带|丝袜")
                for clause in re.split("[，。]", body):
                    self.assertLessEqual(len(clause), 40)

    def test_duo_expressions_name_gaze_and_expression(self):
        for group in DUO["EXPRESSIONS"].values():
            for options in group.values():
                for text in options:
                    with self.subTest(text=text):
                        self.assertRegex(text, "镜头|看向|直视|望")
                        self.assertRegex(text, "笑|唇|嘴|神情|眉")
                        self.assertNotRegex(text, "泛红|红晕|红润|回头|转身")

    def test_duo_compositions_do_not_imply_a_posture(self):
        texts = [t for options in DUO["COMPOSITION"].values() for t in options]
        texts += [bundle["composition"] for options in DUO["WILD_CAMERA"].values() for bundle in options]
        for text in texts:
            with self.subTest(text=text):
                self.assertNotRegex(text, r"站|坐|躺|走|侧身|前倾")

    def test_duo_prompts_have_two_women_and_no_fluency_defects(self):
        for scale in ("normal", "bold", "bold_no_outfit"):
            for shot in ("head_shot", "half_body", "full_body"):
                for aspect in ("portrait", "landscape", "square"):
                    for index in range(4):
                        item = self.sample(scale, shot, aspect, f"duo-{scale}-{shot}-{aspect}-{index}")
                        parts = item["dimension_parts"]
                        lines = render_prompt_lines({**parts, "shot_key": shot, "scale": scale, "aspect": aspect})
                        with self.subTest(scale=scale, shot=shot, aspect=aspect, index=index):
                            self.assertEqual(item["cast"], "duo")
                            self.assertEqual(fluency_defects(lines, scale, shot), [])
                            self.assertTrue(lines["character"].startswith("两个女生都是"))
                            makeups = re.findall(r"(左边|右边)的女生化着([^，。]+)", lines["character"])
                            self.assertEqual([side for side, _ in makeups], ["左边", "右边"])
                            self.assertNotEqual(makeups[0][1], makeups[1][1])
                            self.assertIn("两人", lines["camera"])
                            self.assertNotRegex(parts["scene_light"], "她(?!们)")
                            self.assertIn("third person", item["negative_prompt"])
                            if scale == "bold_no_outfit":
                                self.assertEqual(lines["outfit"], "")
                            else:
                                self.assertRegex(lines["outfit"], r"^左边的女生穿着.+。右边的女生穿着.+。$")

    def test_ancient_duo_prompts_work(self):
        item = self.sample("normal", "full_body", "portrait", "duo-ancient", era="ancient")
        self.assertEqual(item["dimension_parts"]["era"], "ancient")
        self.assertIn("左边的女生穿着", item["positive_prompt"])

    def test_solo_prompts_are_unchanged_by_default(self):
        item = generate_prompt_items(1, {"scale": "normal", "shot": "half_body", "era": "modern"}, "solo-default")[0]
        self.assertEqual(item["cast"], "solo")
        self.assertNotIn("两个女生", item["positive_prompt"])
        self.assertNotIn("third person", item["negative_prompt"])

    def test_nsfw_rejects_duo(self):
        with self.assertRaisesRegex(ValueError, "四档暂不支持双人"):
            generate_prompt_items(1, {"scale": "nsfw", "shot": "half_body", "cast": "duo"}, "duo-nsfw")


if __name__ == "__main__":
    unittest.main()
