import itertools
import random
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prompt_composer import POOLS, _fitting_poses, _group, _name_hands, _place_allowed, compose_parts
from prompt_engine import build_prompt, render_prompt_lines
from prompt_fluency import fluency_defects

SCALES = ("normal", "bold", "bold_no_outfit")
SCOPES = tuple(itertools.product(("head_shot", "half_body", "full_body"), ("portrait", "landscape", "square"), ("modern", "ancient"), ("solo", "duo")))


class PersonaPlanningTests(unittest.TestCase):
    def test_every_theme_state_has_compatible_poses_in_every_scope(self):
        for scale in SCALES:
            pool = POOLS["PERSONAS"][_group(scale)]
            self.assertEqual(len(pool["states"]), 24)
            self.assertEqual(len(pool["temperaments"]), 20)
            self.assertEqual(set(pool["states"]), {key for theme in pool["temperaments"] for key in theme["states"]})
            for shot, aspect, era, cast in SCOPES:
                places = {name for direction in POOLS["ART_DIRECTIONS"] if _group(scale) in direction["scales"] and era in direction["eras"] for name in direction["places"]}
                profiles = set()
                for name in places:
                    place = POOLS["PLACES"][name]
                    if _place_allowed(place, scale, shot):
                        for pose in _fitting_poses(scale, shot, aspect, era, place["props"], cast):
                            if pose.get("expression_visible", True):
                                profiles.update(pose["persona_profiles"])
                for theme in pool["temperaments"]:
                    for state_id in theme["states"]:
                        with self.subTest(scale=scale, scope=(shot, aspect, era, cast), theme=theme["id"], state=state_id):
                            self.assertTrue(profiles & set(theme["pose_profiles"]) & set(pool["states"][state_id]["pose_profiles"]))

    def test_state_controls_body_and_all_facial_parts_for_all_three_tiers(self):
        for scale in SCALES:
            group = _group(scale)
            pool = POOLS["PERSONAS"][group]
            for state_id, state in pool["states"].items():
                theme = next(t for t in pool["temperaments"] if state_id in t["states"])
                for shot, aspect, era, cast in SCOPES:
                    seed = f"state-{scale}-{state_id}-{shot}-{aspect}-{era}-{cast}"
                    with self.subTest(seed=seed), patch("prompt_composer._choose_persona", return_value=(theme, state_id, state)):
                        parts = compose_parts(scale, shot, aspect, random.Random(seed), render_prompt_lines, era, cast)
                        self.assertEqual(parts["character_state"], state_id)
                        candidates = _fitting_poses(scale, shot, aspect, era, POOLS["PLACES"][parts["art_place"]]["props"], cast)
                        pose = next(p for p in candidates if p["body"] == parts["art_pose"])
                        self.assertTrue(pose.get("expression_visible", True))
                        self.assertTrue(set(pose["persona_profiles"]) & set(state["pose_profiles"]) & set(theme["pose_profiles"]))
                        expressions = ["，".join(frame.values()).format(subject="两人" if cast == "duo" else "她") for frame in state["expressions"]]
                        body = pose["body"] if cast == "duo" else _name_hands(pose["body"])
                        self.assertIn(parts["pose_expression"], [f"{body}。{text}" for text in expressions])
                        prompt = build_prompt(parts)
                        self.assertIn(theme["intro"], prompt.split("\n\n")[0])
                        self.assertEqual(prompt.count(theme["intro"]), 1)
                        self.assertEqual(bool(parts["outfit"]), scale != "bold_no_outfit")
                        self.assertEqual(fluency_defects(render_prompt_lines(parts), scale, shot), [])
                        if state_id in ("hurt", "disappointed", "dejected"):
                            self.assertNotIn("active", pose["persona_profiles"])
                            self.assertNotRegex(body, "笑|开心|欢快|爱心|跳|蹦|奔跑")

    def test_fourth_tier_keeps_complete_pose_opaque_and_has_no_outfit(self):
        text = "她侧身站立。她看向镜头，眉间舒展，嘴唇微张"
        with patch("prompt_composer._fitting_poses", return_value=[{"body": text, "text": text}]):
            parts = compose_parts("nsfw", "full_body", "portrait", random.Random(1), render_prompt_lines)
        self.assertEqual(parts["pose_expression"], text)
        self.assertEqual(parts["art_pose"], text)
        self.assertEqual(parts["character_state"], "")
        self.assertEqual(parts["outfit"], "")
        self.assertIn("人物呈现", parts["camera_line"])


if __name__ == "__main__":
    unittest.main()
