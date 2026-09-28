import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompt_engine import generate_prompt_items


class ConcretePoseTests(unittest.TestCase):

    def test_full_body_reference_pose_has_visible_support_or_floor(self):
        for scale in ("normal", "bold", "bold_no_outfit"):
            for seed in ("anchor-review-0", "anchor-review-1"):
                with self.subTest(scale=scale, seed=seed):
                    item = generate_prompt_items(1, {"scale": scale, "shot": "full_body", "aspect": "portrait"}, seed)[0]
                    prompt = item["positive_prompt"]
                    self.assertNotIn("支撑面", prompt)
                    self.assertNotIn("支撑物", prompt)
                    self.assertNotIn("场景边缘", prompt)
                    self.assertNotIn("场景前缘", prompt)

if __name__ == "__main__":
    unittest.main()
