from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import prompt_data
from prompt_engine import generate_prompt_items


class NsfwPosePoolTest(unittest.TestCase):
    def test_fourth_tier_uses_the_versioned_fifty_rule_pool(self):
        pool = prompt_data.POSE_EXPRESSION_OPTIONS["nsfw"]

        self.assertEqual(set(pool), {"head_shot", "upper_body", "half_body", "large_half_body", "full_body"})
        self.assertEqual(sum(len(options) for options in pool.values()), 50)
        self.assertTrue(all(len(pool[shot]) == 10 for shot in pool))
        self.assertIn("data/nsfw_pose_expression_options.json", prompt_data.PROMPT_DATA_SOURCE)

    def test_nsfw_pose_line_is_not_rewritten_after_selection(self):
        for shot in ("half_body", "full_body"):
            item = generate_prompt_items(1, {"scale": "nsfw", "shot": shot, "era": "modern"}, f"nsfw-verbatim-{shot}")[0]
            pose = item["dimension_parts"]["pose_expression"].strip("，。 ")
            self.assertIn(pose, item["positive_prompt"])


if __name__ == "__main__":
    unittest.main()
