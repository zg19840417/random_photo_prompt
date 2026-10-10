import ast
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import rpp_qwen as qwen
from workflow_cleanup_policy import ensure_model_cleanup

ROOT = Path(__file__).resolve().parents[1]


def functions(filename, names, namespace):
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    body = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    exec(compile(ast.Module(body=body, type_ignores=[]), filename, "exec"), namespace)
    return namespace


class QwenBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        for name in qwen.REQUIRED_FILES:
            target = self.path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("placeholder", encoding="utf-8")
        self.config = {"_class_name": "QwenImage21Pipeline", "sample_sigmas": list(qwen.SAMPLE_SIGMAS)}
        self.write_config()

    def write_config(self):
        (self.path / "model_index.json").write_text(json.dumps(self.config), encoding="utf-8")

    def test_complete_bundle(self):
        self.assertEqual(qwen.validate_bundle(self.path), self.path)

    def test_missing_or_empty_weights_are_rejected(self):
        weight = self.path / "text_encoder/model.safetensors"
        weight.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "text_encoder/model.safetensors"):
            qwen.validate_bundle(self.path)
        weight.unlink()
        with self.assertRaises(ValueError):
            qwen.validate_bundle(self.path)

    def test_old_architecture_and_non_turbo_schedule_rejected(self):
        self.config["_class_name"] = "QwenImagePipeline"
        self.write_config()
        with self.assertRaisesRegex(ValueError, "旧版"):
            qwen.validate_bundle(self.path)
        self.config["_class_name"] = "QwenImage21Pipeline"
        self.config["sample_sigmas"] = [1, 0]
        self.write_config()
        with self.assertRaisesRegex(ValueError, "8 步"):
            qwen.validate_bundle(self.path)

    def test_dependencies_and_missing_packages(self):
        with patch.object(qwen.metadata, "version", side_effect=["0.37.1", "5.5.3", "1.13.0"]):
            self.assertEqual(len(qwen.dependency_errors()), 2)
        with patch.object(qwen.metadata, "version", side_effect=["0.41.0.dev0", "5.17.0", "1.13.0"]):
            self.assertEqual(qwen.dependency_errors(), [])
        with patch.object(qwen.metadata, "version", side_effect=qwen.metadata.PackageNotFoundError):
            self.assertEqual(len(qwen.dependency_errors()), 3)

    def test_input_types_unready_is_not_a_fake_model(self):
        with patch.object(qwen, "readiness_errors", return_value=["missing"]):
            self.assertEqual(qwen.RandomPhotoPromptQwenImage21Turbo.INPUT_TYPES()["required"]["model_name"][0], [])
        with patch.object(qwen, "readiness_errors", return_value=[]):
            self.assertEqual(qwen.RandomPhotoPromptQwenImage21Turbo.INPUT_TYPES()["required"]["model_name"][0], [qwen.MODEL_NAME])


class QwenExecutionTests(unittest.TestCase):
    def test_invalid_requests_fail_before_importing_inference(self):
        node = qwen.RandomPhotoPromptQwenImage21Turbo()
        valid = dict(model_name=qwen.MODEL_NAME, prompt="花园", width=864, height=1536, seed=42, research_only=True)
        for change in ({"research_only": False}, {"model_name": "old"}, {"prompt": ""},
                       {"width": 865}, {"height": 2048}, {"width": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                node.generate(**{**valid, **change})
        with patch.object(qwen, "readiness_errors", return_value=["dependency unavailable"]):
            with self.assertRaisesRegex(RuntimeError, "dependency unavailable"):
                node.generate(**valid)

    def test_failure_releases_pipeline_and_does_not_override_schedule(self):
        calls = []
        class Pipeline:
            def __call__(self, prompt, width, height, use_kv_cache, generator, callback_on_step_end, sigmas=None):
                calls.append(dict(prompt=prompt, width=width, height=height, use_kv_cache=use_kv_cache, sigmas=sigmas))
                callback_on_step_end(self, 0, 1000, {})
                raise RuntimeError("test failure")

        pipe = Pipeline()
        pipe.enable_sequential_cpu_offload = Mock()
        pipe.vae = SimpleNamespace(enable_tiling=Mock())
        pipe.remove_all_hooks = Mock()
        Pipeline.from_pretrained = Mock(return_value=pipe)
        diffusers = ModuleType("diffusers")
        diffusers.QwenImage21Pipeline = Pipeline
        torch = ModuleType("torch")
        torch.cuda = SimpleNamespace(is_available=lambda: True)
        torch.bfloat16 = "bf16"
        torch.Generator = Mock()
        comfy = ModuleType("comfy")
        comfy.model_management = ModuleType("comfy.model_management")
        for name in ("throw_exception_if_processing_interrupted", "unload_all_models", "soft_empty_cache"):
            setattr(comfy.model_management, name, Mock())
        comfy.utils = ModuleType("comfy.utils")
        comfy.utils.ProgressBar = Mock()
        modules = {"diffusers": diffusers, "torch": torch, "comfy": comfy,
                   "comfy.model_management": comfy.model_management, "comfy.utils": comfy.utils}
        with patch.dict(sys.modules, modules), patch.object(qwen, "readiness_errors", return_value=[]), \
             patch.object(qwen, "model_directory", return_value=Path("bundle")), \
             patch.object(qwen, "validate_bundle", return_value=Path("bundle")):
            with self.assertRaisesRegex(RuntimeError, "test failure"):
                qwen.RandomPhotoPromptQwenImage21Turbo().generate(qwen.MODEL_NAME, "原样提示词", 864, 1536, 42, True)
        Pipeline.from_pretrained.assert_called_once_with("bundle", dtype="bf16", local_files_only=True)
        pipe.enable_sequential_cpu_offload.assert_called_once()
        pipe.remove_all_hooks.assert_called_once()
        self.assertEqual(comfy.model_management.soft_empty_cache.call_count, 2)
        self.assertIsNone(calls[0]["sigmas"])
        self.assertEqual(calls[0]["prompt"], "原样提示词")


class QwenWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.template = json.loads((ROOT / "mobile_workflow_api_qwen_image21_turbo.json").read_text())
        self.ns = functions("rpp_workflow.py", {"_patch_mobile_workflow", "_patch_remote_websocket_outputs"}, {
            "copy": copy, "Path": Path, "ensure_model_cleanup": ensure_model_cleanup,
            "_prompt_text": lambda item: item["positive_prompt"],
            "REMOTE_WEBSOCKET_OUTPUT": True, "BLOCK_REMOTE_ASSET_SAVE": True,
            "REMOTE_MAC_IMAGE_UPLOAD_URL": "", "REMOTE_MAC_VIDEO_UPLOAD_URL": "",
            "_node_meta": lambda node: node.get("_meta", {}),
        })

    def patch_workflow(self, **kwargs):
        return self.ns["_patch_mobile_workflow"](self.template, {"positive_prompt": "原样\n提示词"},
                                                864, 1536, 123, workflow_key="qwen_image21_turbo",
                                                output_prefix="mobile_qwen_test", **kwargs)

    def test_patch_preserves_exact_prompt_resolution_and_template(self):
        original = copy.deepcopy(self.template)
        workflow, patched = self.patch_workflow()
        self.assertEqual(workflow["1"]["inputs"]["prompt"], "原样\n提示词")
        self.assertEqual(workflow["1"]["inputs"]["seed"], 123)
        self.assertEqual(patched["sampler_steps"], 8)
        self.assertEqual(self.template, original)
        self.assertEqual(patched["exact_output_scale_nodes"], 0)
        self.assertTrue(workflow["3"]["inputs"]["purge_models"])
        self.assertTrue(workflow["3"]["inputs"]["purge_cache"])

    def test_existing_model_or_lora_cannot_leak(self):
        for kwargs in ({"loras": [{"name": "old"}]}, {"zit_model": "old"}, {"zib_model": "old"}, {"krea2_model": "old"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.patch_workflow(**kwargs)

    def test_stream_registered_for_image_watcher_with_unique_prefix(self):
        workflow, _ = self.patch_workflow()
        result = self.ns["_patch_remote_websocket_outputs"](workflow, "phone")
        self.assertEqual(result["websocket_node_ids"], ["2"])
        self.assertEqual(result["output_prefix"], "mobile_qwen_test")
        self.assertIn("3", workflow)
        self.assertFalse(any(node["class_type"].startswith("Save") for node in workflow.values()))

    def test_mobile_readiness_and_lora_visibility_guards(self):
        page = (ROOT / "web/mobile.html").read_text()
        self.assertIn("selectedWorkflow?.runtime_ready !== false", page)
        self.assertIn("state.generationReady !== true", page)
        self.assertIn(".lora-controls[hidden]", page)
        self.assertIn('workflowSelect.value === "qwen_image21_turbo" ? [] : selectedLoras()', page)


class QwenRemoteStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_node_or_empty_models_is_unready_not_connection_failure(self):
        for response in (({}, None), (None, {"error": "missing node"}),
                         ({"RandomPhotoPromptQwenImage21Turbo": {"input": {"required": {"model_name": [[]]}}}}, None)):
            remote = AsyncMock(return_value=response)
            ns = functions("rpp_remote.py", {"_qwen_image21_runtime_status"}, {"_remote_json": remote})
            result = await ns["_qwen_image21_runtime_status"]()
            self.assertFalse(result["runtime_ready"])
            self.assertIn("未就绪", result["message"])

    async def test_registered_official_bundle_ready(self):
        info = {"RandomPhotoPromptQwenImage21Turbo": {"input": {"required": {"model_name": [[qwen.MODEL_NAME]]}}}}
        ns = functions("rpp_remote.py", {"_qwen_image21_runtime_status"}, {"_remote_json": AsyncMock(return_value=(info, None))})
        self.assertTrue((await ns["_qwen_image21_runtime_status"]())["runtime_ready"])


if __name__ == "__main__":
    unittest.main()
