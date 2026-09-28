from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import prompt_data
from prompt_postprocess import strengthen_expression


class NsfwPosePoolTest(unittest.TestCase):
    def test_fourth_tier_uses_the_versioned_fifty_rule_pool(self):
        pool = prompt_data.POSE_EXPRESSION_OPTIONS["nsfw"]

        self.assertEqual(set(pool), {"head_shot", "upper_body", "half_body", "large_half_body", "full_body"})
        self.assertEqual(sum(len(options) for options in pool.values()), 50)
        self.assertTrue(all(len(pool[shot]) == 10 for shot in pool))
        self.assertIn("data/nsfw_pose_expression_options.json", prompt_data.PROMPT_DATA_SOURCE)

    def test_nsfw_cleanup_preserves_action_and_existing_expression(self):
        pose = "动作清楚，眼神直视镜头"
        self.assertEqual(strengthen_expression({"pose_expression": pose}, "nsfw")["pose_expression"], pose)


if __name__ == "__main__":
    unittest.main()
