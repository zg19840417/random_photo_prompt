import random
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prompt_composer import COMPOSER_SCALES, POOLS, compose_parts
from prompt_engine import generate_prompt_items, render_prompt_lines
from prompt_fluency import fluency_defects

_STRUCTURE_MARKERS = ("压线", "接缝", "收省", "折边", "滚边", "袖窿", "车缝")


class PromptComposerTests(unittest.TestCase):
    def test_every_outfit_names_a_visible_structure_detail(self):
        options = [
            (shot, option)
            for key in ("OUTFITS", "OUTFITS_ANCIENT")
            for table in POOLS[key].values()
            for shot, shot_options in table.items()
            for option in shot_options
        ]
        for shot, option in options:
            text = option["text"] if isinstance(option, dict) else option
            with self.subTest(shot=shot, text=text):
                self.assertTrue(any(marker in text for marker in _STRUCTURE_MARKERS))

    def test_composer_prompts_have_no_fluency_defects(self):
        for scale in COMPOSER_SCALES:
            for shot in ("head_shot", "half_body", "full_body"):
                for index in range(10):
                    item = generate_prompt_items(1, {"scale": scale, "shot": shot, "era": "modern"}, f"composer-{scale}-{shot}-{index}")[0]
                    lines = render_prompt_lines({**item["dimension_parts"], "shot_key": shot, "scale": scale, "aspect": item["aspect"]})
                    with self.subTest(scale=scale, shot=shot, index=index):
                        self.assertEqual(fluency_defects(lines, scale, shot), [])

    def test_bold_poses_never_describe_clothing(self):
        for table in POOLS["POSES"]["bold"].values():
            for options in table.values():
                for pose in options:
                    with self.subTest(pose=pose["body"]):
                        self.assertNotRegex(pose["body"], r"衣|裙|裤|领|袖|肩带|丝袜")

    def test_bold_no_outfit_and_bold_full_body_use_private_places(self):
        for scale, shot in (("bold_no_outfit", "half_body"), ("bold", "full_body")):
            for index in range(30):
                parts = compose_parts(scale, shot, "portrait", random.Random(f"private-{scale}-{index}"), render_prompt_lines)
                with self.subTest(scale=scale, index=index):
                    self.assertTrue(POOLS["PLACES"][parts["art_place"]]["private"])
                    if scale == "bold_no_outfit":
                        self.assertEqual(parts["outfit"], "")

    def test_pose_props_exist_in_place_and_barefoot_skips_shoes(self):
        poses = {
            pose["body"]: pose
            for group in POOLS["POSES"].values()
            for table in group.values()
            for options in table.values()
            for pose in options
        }
        for index in range(60):
            scale = COMPOSER_SCALES[index % 2]
            parts = compose_parts(scale, "full_body", "portrait", random.Random(f"props-{index}"), render_prompt_lines)
            pose = poses[parts["art_pose"]]
            place = POOLS["PLACES"][parts["art_place"]]
            with self.subTest(index=index):
                self.assertLessEqual(set(pose.get("props", ())), set(place["props"]))
                if pose.get("barefoot"):
                    self.assertNotIn("脚上是", parts["outfit"])

    def test_art_direction_owns_single_color_grade(self):
        parts = compose_parts("normal", "half_body", "portrait", random.Random("grade"), render_prompt_lines)
        quality = render_prompt_lines({**parts, "shot_key": "half_body", "scale": "normal", "aspect": "portrait"})["quality"]
        self.assertEqual(quality.count("调色"), 1)
        self.assertTrue(quality.endswith("高光不过曝。"))

    def test_ancient_outfit_style_matches_place_and_keeps_bare_feet(self):
        for scale in COMPOSER_SCALES:
            for index in range(20):
                parts = compose_parts(scale, "full_body", "portrait", random.Random(f"ancient-{scale}-{index}"), render_prompt_lines, "ancient")
                place = POOLS["PLACES"][parts["art_place"]]
                with self.subTest(scale=scale, index=index):
                    self.assertIn("ancient", place["eras"])
                    self.assertNotIn("取景框", parts["pose_expression"])
                    if scale != "bold_no_outfit":
                        self.assertIn("裸足", parts["outfit"])
                        self.assertNotIn("脚上是", parts["outfit"])
                        self.assertIn(parts["art_outfit_style"], place["styles"])

    def test_body_axis_matches_frame_orientation(self):
        for group, orientations in POOLS["POSES"].items():
            for shot, options in orientations["portrait"].items():
                for pose in options:
                    with self.subTest(group=group, orientation="portrait", pose=pose["body"]):
                        self.assertNotRegex(pose["body"], r"横向|躺|趴|侧卧|俯卧")
            for shot, options in orientations["landscape"].items():
                if shot == "head_shot":
                    continue
                for pose in options:
                    with self.subTest(group=group, orientation="landscape", pose=pose["body"]):
                        self.assertRegex(pose["body"], r"横向|躺|卧|趴|沿.*展开")

    def test_square_frame_uses_diagonal_poses_and_square_camera(self):
        for shot, options in POOLS["POSES"]["bold"]["square"].items():
            for pose in options:
                with self.subTest(pose=pose["body"]):
                    self.assertRegex(pose["body"], "斜")
        for scale in COMPOSER_SCALES:
            for shot in ("head_shot", "half_body", "full_body"):
                for index in range(15):
                    parts = compose_parts(scale, shot, "square", random.Random(f"sq-{scale}-{shot}-{index}"), render_prompt_lines)
                    with self.subTest(scale=scale, shot=shot, index=index):
                        if shot != "head_shot":
                            self.assertIn("方形", parts["camera_line"])
                        self.assertNotRegex(parts["camera_line"], r"竖向|横向")
                        if scale != "normal" and shot != "head_shot":
                            self.assertRegex(parts["art_pose"], "斜")
                        lines = render_prompt_lines({**parts, "shot_key": shot, "scale": scale, "aspect": "square"})
                        self.assertEqual(fluency_defects(lines, scale, shot), [])

    def test_camera_compositions_do_not_imply_a_posture(self):
        texts = [t for l in POOLS["COMPOSITION"].values() for t in l]
        texts += [t for lt in POOLS["LIGHT_TYPES"].values() for l in lt["compositions"].values() for t in l]
        texts += [b["composition"] for l in POOLS["WILD_CAMERA"].values() for b in l]
        for text in texts:
            with self.subTest(text=text):
                self.assertNotRegex(text, r"站|坐|躺|走|侧身|前倾")

    def test_engine_square_items_are_1536(self):
        item = generate_prompt_items(1, {"scale": "bold", "shot": "full_body", "era": "modern", "aspect": "square", "width": 1536, "height": 1536}, "sq-item")[0]
        self.assertEqual((item["aspect"], item["width"], item["height"]), ("square", 1536, 1536))
        self.assertIn("方形", item["positive_prompt"])

    def test_wild_camera_and_poses_reach_bold_prompts_and_stay_fluent(self):
        for shot in ("head_shot", "half_body", "full_body"):
            for aspect in ("portrait", "landscape"):
                self.assertTrue(any(aspect in bundle["aspects"] for bundle in POOLS["WILD_CAMERA"][shot]))
        wild_camera = wild_pose = total = 0
        for scale in ("bold", "bold_no_outfit"):
            for shot in ("head_shot", "half_body", "full_body"):
                for index in range(20):
                    parts = compose_parts(scale, shot, "portrait", random.Random(f"wild-{scale}-{shot}-{index}"), render_prompt_lines)
                    total += 1
                    wild_camera += bool(parts["art_wild_camera"])
                    wild_pose += any(pose.get("wild") and pose["body"] == parts["art_pose"] for table in POOLS["POSES"]["bold"].values() for options in table.values() for pose in options)
        self.assertGreater(wild_camera, total * 0.3)
        self.assertGreater(wild_pose, total * 0.3)
        normal = compose_parts("normal", "full_body", "portrait", random.Random("wild-normal"), render_prompt_lines)
        self.assertEqual(normal["art_wild_camera"], "")

    def test_nsfw_matches_bold_no_outfit_except_pose(self):
        for era in ("modern", "ancient"):
            for shot in ("head_shot", "half_body", "full_body"):
                selections = {"shot": shot, "era": era, "aspect": "portrait"}
                nsfw = generate_prompt_items(1, {**selections, "scale": "nsfw"}, f"nsfw-{era}-{shot}")[0]["dimension_parts"]
                bold = generate_prompt_items(1, {**selections, "scale": "bold_no_outfit"}, f"nsfw-{era}-{shot}")[0]["dimension_parts"]
                with self.subTest(era=era, shot=shot):
                    for name in ("art_direction", "art_place", "scene_light", "camera_line", "quality", "character", "makeup"):
                        self.assertEqual(nsfw[name], bold[name])
                    self.assertEqual(nsfw["outfit"], "")


if __name__ == "__main__":
    unittest.main()
