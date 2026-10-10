import ast
import json
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkflowOptions(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_workflow = False
        self.values = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "select" and attrs.get("id") == "workflow":
            self.in_workflow = True
        elif tag == "option" and self.in_workflow:
            self.values.append(attrs.get("value"))

    def handle_endtag(self, tag):
        if tag == "select":
            self.in_workflow = False


class Krea2WorkflowTests(unittest.TestCase):
    def test_registered_mobile_options_match_page(self):
        tree = ast.parse((ROOT / "rpp_globals.py").read_text(encoding="utf-8"))
        registry = next(
            node.value for node in tree.body
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "MOBILE_WORKFLOWS"
                for target in node.targets
            )
        )
        keys = {key.value for key in registry.keys}
        page = WorkflowOptions()
        page.feed((ROOT / "web/mobile.html").read_text(encoding="utf-8"))
        expected = {"zit_single", "zitb_double", "redcraft_krea2", "krea2_double"}
        self.assertEqual(keys - {"minimax_h3"}, expected)
        self.assertEqual(set(page.values), expected)

    def test_krea2_templates_keep_only_active_generation_chain(self):
        for name, expected_steps in (("krea2", (8,)), ("krea2_double", (8, 5))):
            with self.subTest(name=name):
                workflow = json.loads((ROOT / f"mobile_workflow_api_{name}.json").read_text(encoding="utf-8"))
                classes = [node["class_type"] for node in workflow.values()]
                samplers = [node for node in workflow.values() if node["class_type"] == "KSampler"]
                self.assertEqual(tuple(node["inputs"]["steps"] for node in samplers), expected_steps)
                self.assertEqual(classes.count("SaveImage"), 1)
                self.assertEqual(classes.count("ConditioningZeroOut"), 1)
                self.assertFalse(any("SeedVR2" in cls or cls in {"LoadImage", "UltimateSDUpscale"} for cls in classes))
                for node in workflow.values():
                    for value in node["inputs"].values():
                        if isinstance(value, list):
                            self.assertIn(value[0], workflow)
        self.assertEqual(workflow["31"]["inputs"]["samples"], ["3", 0])
        self.assertEqual(workflow["31"]["inputs"]["scale_by"], 1.5)
        self.assertEqual(workflow["32"]["inputs"]["latent_image"], ["31", 0])
        self.assertEqual(workflow["32"]["inputs"]["denoise"], 0.5)
        self.assertEqual(workflow["8"]["inputs"]["samples"], ["32", 0])
        self.assertEqual(workflow["29"]["inputs"]["images"], ["8", 0])


if __name__ == "__main__":
    unittest.main()
