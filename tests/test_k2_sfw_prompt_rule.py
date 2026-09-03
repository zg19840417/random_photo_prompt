import unittest

from k2_sfw_prompt_rule import RULE_KEY, generate_prompt_item, select_resolution


class K2SfwPromptRuleTests(unittest.TestCase):
    def test_generates_the_document_ten_part_narrative(self):
        forbidden = ("汗湿", "湿润", "水汽", "nipple", "vagina", "penis", "masterpiece", "best quality")
        item = generate_prompt_item("document-assembly")
        prompt = item["positive_prompt"]
        parts = item["dimension_parts"]

        self.assertEqual(item["prompt_rule"], RULE_KEY)
        self.assertEqual(item["scale"], "k2_sfw")
        self.assertTrue(300 <= len(prompt) <= 600)
        self.assertTrue(all(term not in prompt.lower() for term in forbidden))
        self.assertEqual(parts["k2_self_check"]["fatal"], "9/9 ✅")
        for part in ("camera", "scene_light", "character", "hair", "makeup", "expression", "outfit", "pose_expression", "background", "composition"):
            self.assertTrue(parts[part], part)

    def test_k2_does_not_inherit_project_scale_era_or_shot(self):
        first = generate_prompt_item("same-k2-seed")
        second = generate_prompt_item("same-k2-seed")

        self.assertEqual(first["positive_prompt"], second["positive_prompt"])
        self.assertEqual(first["shot_key"], "k2_sfw")
        self.assertEqual(first["aspect"], first["resolution"]["aspect"])

    def test_resolution_follows_narrative_camera_and_composition(self):
        self.assertEqual(select_resolution("wide", "bird", "构图采用三分法"), {"aspect": "square", "width": 1536, "height": 1536})
        self.assertEqual(select_resolution("wide", "side", "构图采用引导线"), {"aspect": "landscape", "width": 1536, "height": 1024})
        self.assertEqual(select_resolution("medium", "side", "构图采用中心对称"), {"aspect": "square", "width": 1536, "height": 1536})
        self.assertEqual(select_resolution("medium", "side", "构图采用三分法"), {"aspect": "portrait", "width": 1024, "height": 1536})
        self.assertEqual(select_resolution("close", "side", "构图采用框架构图"), {"aspect": "portrait", "width": 1024, "height": 1536})

    def test_uses_multiple_document_lenses_and_viewpoints(self):
        generated = [generate_prompt_item(f"k2-options-{index}")["dimension_parts"] for index in range(40)]
        lenses = {parts["k2_lens"] for parts in generated}
        viewpoints = {parts["k2_viewpoint"] for parts in generated}

        self.assertGreaterEqual(len(lenses), 5)
        self.assertGreaterEqual(len(viewpoints), 6)
        self.assertNotIn("平视正面", " ".join(parts["camera"] for parts in generated))

    def test_scene_context_keeps_each_narrative_part_concrete(self):
        for index in range(100):
            parts = generate_prompt_item(f"k2-scene-context-{index}")["dimension_parts"]
            self.assertGreaterEqual(len(parts["k2_scene_request"]), 20)
            self.assertGreaterEqual(len(parts["pose_expression"]), 20)
            self.assertGreaterEqual(len(parts["background"]), 20)
            self.assertGreaterEqual(len(parts["composition"]), 20)
            self.assertRegex(parts["character"], r"2[02468]岁")


if __name__ == "__main__":
    unittest.main()
