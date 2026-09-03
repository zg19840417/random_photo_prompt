from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import prompt_data


class NsfwPosePoolTest(unittest.TestCase):
    def test_fourth_tier_uses_the_versioned_thirty_rule_pool(self):
        pool = prompt_data.POSE_EXPRESSION_OPTIONS["nsfw"]

        self.assertEqual(set(pool), {"head_shot", "half_body", "full_body"})
        self.assertEqual(sum(len(options) for options in pool.values()), 30)
        self.assertTrue(all(len(pool[shot]) == 10 for shot in pool))
        self.assertIn("data/nsfw_pose_expression_options.json", prompt_data.PROMPT_DATA_SOURCE)


if __name__ == "__main__":
    unittest.main()
