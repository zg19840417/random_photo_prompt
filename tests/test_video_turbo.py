import ast
import copy
import hashlib
import json
import time
import traceback
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiohttp import web
from workflow_cleanup_policy import ensure_model_cleanup


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_MODEL = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
TURBO_LORA = "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
TURBO_4STEP_LORA = "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors"
COMMUNITY_MODELS = ("h3ErosMax_beta5_fp8.safetensors", "DasiwaMinimaxH3_dasiwaHybridV2_int8.safetensors")


def load_workflow_functions():
    tree = ast.parse((ROOT / "rpp_workflow.py").read_text())
    names = {
        "_patch_mobile_video_workflow", "_patch_mobile_video_turbo",
        "_validate_mobile_video_turbo_model", "_resolve_mobile_video_turbo_lora",
        "_validate_mobile_video_turbo_steps",
        "_next_workflow_node_id", "_reroute_lora_model_consumers", "_resolve_lora_name",
    }
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    namespace = {
        "copy": copy, "Path": Path,
        "ensure_model_cleanup": ensure_model_cleanup,
        "image_to_video_resolution": lambda path: (480, 704),
        "MAXIMUM_VIDEO_SIDE": 720,
        "_node_title": lambda node: node.get("_meta", {}).get("title", "").lower(),
        "_looks_negative_text": lambda node: False,
        "MOBILE_VIDEO_OUTPUT_SUBFOLDER": "videos",
    }
    constants = {"MOBILE_VIDEO_TURBO_MODEL", "MOBILE_VIDEO_TURBO_LORA", "MOBILE_VIDEO_TURBO_4STEP_LORA"}
    for node in ast.parse((ROOT / "rpp_globals.py").read_text()).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in constants:
                    namespace[target.id] = ast.literal_eval(node.value)
    exec(compile(ast.Module(body=functions, type_ignores=[]), "rpp_workflow.py", "exec"), namespace)
    return namespace


class VideoTurboWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.namespace = load_workflow_functions()
        self.patch_workflow = self.namespace["_patch_mobile_video_workflow"]
        self.template = json.loads((ROOT / "minimax_h3_workflow_api.json").read_text())

    def patch(self, mode="image", model=OFFICIAL_MODEL, **kwargs):
        return self.patch_workflow(
            self.template, {}, "source.png", "source.png", 123,
            seconds=4, positive_prompt="镜头前移", video_mode=mode, video_model=model, **kwargs,
        )

    def test_disabled_and_omitted_turbo_preserve_prechange_bytes(self):
        # 修改前采集的完整返回值摘要，包含工作流节点顺序、清理节点及参数。
        baselines = {
            "text": (
                "3f0932b4e8b18b6e870e4ea319c69cd32f279f771d50a9594419fb2badde8cb2",
                "5ae825f8f49caa9f8a0fdc18945486b94dbb6ab7a4c2419e7c7fb1be20f9924d",
                "a29251c63472402386d71ca34327e1eace8ea2cb30512a5c5c8079ae698b6878",
            ),
            "image": (
                "e057cfb65e1c84800f449b9a6f66bd4cd9572e0d0af7e773e814f1b923be0484",
                "0eb5deed935681f80308a4975d0eeda1ab84d6df9f7eb96093e215a5ac5738c6",
                "96b680fd66255fd25f51e1c1d038a83eea64173c55edc9267b5b42721af06cee",
            ),
        }
        for mode, digests in baselines.items():
            for model, digest in zip((OFFICIAL_MODEL, *COMMUNITY_MODELS), digests):
                for options in ({}, {"turbo": False, "available_loras": []},
                                {"turbo": False, "turbo_steps": 4},
                                {"turbo": False, "turbo_steps": "invalid"}):
                    with self.subTest(mode=mode, model=model, options=options):
                        result = self.patch(mode, model, **options)
                        serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
                        self.assertEqual(hashlib.sha256(serialized).hexdigest(), digest)

    def test_eight_step_default_and_explicit_preserve_prechange_bytes(self):
        baselines = {
            "text": "97f85f72342270a33c7973b46a37647ac492cc8cad45ba98b0a3ac6ffa4754b1",
            "image": "bc5117105bd9d0451ddfb3b2f63534ff1dcca8105e292b56a9d21668829338f8",
        }
        for mode, digest in baselines.items():
            for options in ({}, {"turbo_steps": 8}):
                with self.subTest(mode=mode, options=options):
                    result = self.patch(mode, turbo=True, available_loras=[TURBO_LORA], **options)
                    serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
                    self.assertEqual(hashlib.sha256(serialized).hexdigest(), digest)

    def test_enabled_turbo_topology_and_sampling_match_reference(self):
        original_template = copy.deepcopy(self.template)
        for mode, steps, lora in ((mode, steps, lora) for mode in ("text", "image")
                                  for steps, lora in ((8, TURBO_LORA), (4, TURBO_4STEP_LORA))):
            with self.subTest(mode=mode, steps=steps):
                standard, _, _ = self.patch(mode)
                workflow, _, _ = self.patch(mode, turbo=True, turbo_steps=steps, available_loras=[lora])
                added = set(workflow) - set(standard)
                self.assertEqual(len(added), 2)
                lora_id = next(n for n in added if workflow[n]["class_type"] == "LoraLoaderModelOnly")
                sigma_id = next(n for n in added if workflow[n]["class_type"] == "MiniMaxH3SigmaShift")
                self.assertEqual(workflow[lora_id]["inputs"], {
                    "model": ["163", 0], "lora_name": lora, "strength_model": 1.0,
                })
                self.assertEqual(workflow[sigma_id]["inputs"], {
                    "model": [lora_id, 0], "shift_video": 12.0, "shift_audio": 3.0,
                })
                self.assertEqual(workflow["138"]["inputs"]["model"], [sigma_id, 0])
                self.assertEqual(workflow["155"]["inputs"], {
                    "model": [sigma_id, 0], "scheduler": "simple", "steps": steps, "denoise": 1.0,
                })
                self.assertEqual(workflow["139"]["inputs"]["sampler_name"], "euler")
                self.assertNotIn("CFGGuider", [n["class_type"] for n in workflow.values()])
                for node_id, node in standard.items():
                    if node_id not in {"138", "155", "139"}:
                        self.assertEqual(workflow[node_id], node)
        self.assertEqual(self.template, original_template)

    def test_community_models_reject_turbo_in_chinese(self):
        for model in COMMUNITY_MODELS:
            with self.subTest(model=model), self.assertRaisesRegex(ValueError, "Turbo 加速仅支持官方模型"):
                self.patch(model=model, turbo=True, available_loras=[TURBO_LORA])

    def test_missing_lora_rejects_turbo_in_chinese(self):
        for steps, lora, other in ((8, TURBO_LORA, TURBO_4STEP_LORA), (4, TURBO_4STEP_LORA, TURBO_LORA)):
            for available in (None, [], ["other.safetensors"], [other]):
                with self.subTest(steps=steps, available=available), self.assertRaisesRegex(ValueError, "远端缺少 " + lora):
                    self.patch(turbo=True, turbo_steps=steps, available_loras=available)

    def test_invalid_steps_rejected_by_workflow(self):
        for value in (12, 0, "4", 4.0, True, False, None, [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "turbo_steps 参数必须是整数 8 或 4"):
                self.patch(turbo=True, turbo_steps=value, available_loras=[TURBO_LORA, TURBO_4STEP_LORA])

    def test_registered_subdirectory_paths_are_preserved(self):
        model = "MiniMax\\" + OFFICIAL_MODEL
        for steps, filename in ((8, TURBO_LORA), (4, TURBO_4STEP_LORA)):
            with self.subTest(steps=steps):
                lora = "MiniMax\\" + filename
                workflow, _, _ = self.patch(model=model, turbo=True, turbo_steps=steps, available_loras=[lora])
                lora_node = next(n for n in workflow.values() if n["class_type"] == "LoraLoaderModelOnly")
                self.assertEqual(lora_node["inputs"]["lora_name"], lora)
                self.assertEqual(workflow["163"]["inputs"]["model_name"], model)


class VideoTurboEndpointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.namespace = load_workflow_functions()
        template = json.loads((ROOT / "minimax_h3_workflow_api.json").read_text())
        self.namespace.update({
            "web": web, "time": time, "uuid": uuid, "traceback": traceback,
            "MOBILE_VIDEO_WORKFLOW_KEY": "minimax_h3", "MOBILE_MAX_ACTIVE_JOBS": 12,
            "REMOTE_COMFYUI_URL": "", "MOBILE_SESSION_JOBS": [],
            "_mobile_workflow_config": lambda key: (key, {"label": "MiniMax H3"}),
            "_load_mobile_workflow": lambda key: template,
            "_available_mobile_video_models": AsyncMock(return_value=[OFFICIAL_MODEL, *COMMUNITY_MODELS]),
            "_available_mobile_loras": AsyncMock(return_value=[TURBO_LORA, TURBO_4STEP_LORA]),
            "_mobile_active_job_count": AsyncMock(return_value=0),
            "_mobile_shot_config": lambda shot: {"shot": shot},
            "_mobile_video_source_path": Mock(return_value=("source.png", "source.png", True)),
            "normalize_video_seconds": lambda seconds: seconds,
            "_build_mobile_prompt_for_scope": lambda *args: ({"seed": 123}, {"aspect": "portrait"}),
            "resolve_video_submission_prompt": lambda action, **kwargs: (action, kwargs["seconds"]),
            "_queue_mobile_workflow": AsyncMock(return_value=({"prompt_id": "test-only"}, None)),
            "_save_mobile_session_jobs": Mock(),
        })
        tree = ast.parse((ROOT / "rpp_endpoints.py").read_text())
        function = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "generate_mobile_video")
        exec(compile(ast.Module(body=[function], type_ignores=[]), "rpp_endpoints.py", "exec"), self.namespace)

    async def submit(self, mode="text", model=OFFICIAL_MODEL, **kwargs):
        request = SimpleNamespace(json=AsyncMock(return_value={
            "video_mode": mode, "video_model": model, "action_text": "镜头前移", **kwargs,
        }))
        response = await self.namespace["generate_mobile_video"](request)
        return response.status, json.loads(response.body)

    async def test_default_and_false_skip_lora_lookup(self):
        for options in ({}, {"turbo": False}, {"turbo": False, "turbo_steps": 4},
                        {"turbo": False, "turbo_steps": "invalid"}):
            with self.subTest(options=options):
                status, payload = await self.submit(**options)
                self.assertEqual(status, 200, payload)
                self.assertIs(payload["jobs"][0]["turbo"], False)
                self.assertIsNone(payload["jobs"][0]["turbo_steps"])
        self.namespace["_available_mobile_loras"].assert_not_awaited()

    async def test_enabled_turbo_reaches_workflow_and_job_metadata(self):
        for mode in ("text", "image"):
            with self.subTest(mode=mode):
                status, payload = await self.submit(mode=mode, turbo=True)
                self.assertEqual(status, 200, payload)
                self.assertIs(payload["jobs"][0]["turbo"], True)
                self.assertEqual(payload["jobs"][0]["turbo_steps"], 8)
                workflow = self.namespace["_queue_mobile_workflow"].await_args.args[0]
                self.assertEqual(workflow["155"]["inputs"]["steps"], 8)
                self.assertEqual(workflow["139"]["inputs"]["sampler_name"], "euler")

    async def test_four_step_turbo_reaches_workflow_and_job_metadata(self):
        for mode in ("text", "image"):
            with self.subTest(mode=mode):
                status, payload = await self.submit(mode=mode, turbo=True, turbo_steps=4)
                self.assertEqual(status, 200, payload)
                job = payload["jobs"][0]
                self.assertIs(job["turbo"], True)
                self.assertEqual(job["turbo_steps"], 4)
                self.assertEqual(self.namespace["MOBILE_SESSION_JOBS"][-1]["turbo_steps"], 4)
                workflow = self.namespace["_queue_mobile_workflow"].await_args.args[0]
                self.assertEqual(workflow["155"]["inputs"]["steps"], 4)
                lora = next(n for n in workflow.values() if n["class_type"] == "LoraLoaderModelOnly")
                self.assertEqual(lora["inputs"]["lora_name"], TURBO_4STEP_LORA)

    async def test_community_model_is_rejected_before_lora_lookup_or_queue(self):
        for model in COMMUNITY_MODELS:
            with self.subTest(model=model):
                status, payload = await self.submit(model=model, turbo=True)
                self.assertEqual(status, 400)
                self.assertIn("Turbo 加速仅支持官方模型", payload["error"])
        self.namespace["_available_mobile_loras"].assert_not_awaited()
        self.namespace["_queue_mobile_workflow"].assert_not_awaited()

    async def test_missing_remote_lora_is_rejected_before_queue(self):
        self.namespace["_available_mobile_loras"].return_value = []
        for mode in ("text", "image"):
            with self.subTest(mode=mode):
                status, payload = await self.submit(mode=mode, turbo=True)
                self.assertEqual(status, 400)
                self.assertIn("远端缺少 " + TURBO_LORA, payload["error"])
        self.namespace["_mobile_active_job_count"].assert_not_awaited()
        self.namespace["_mobile_video_source_path"].assert_not_called()
        self.namespace["_queue_mobile_workflow"].assert_not_awaited()

    async def test_missing_four_step_lora_never_falls_back_to_eight(self):
        self.namespace["_available_mobile_loras"].return_value = [TURBO_LORA]
        for mode in ("text", "image"):
            with self.subTest(mode=mode):
                status, payload = await self.submit(mode=mode, turbo=True, turbo_steps=4)
                self.assertEqual(status, 400)
                self.assertIn("远端缺少 " + TURBO_4STEP_LORA, payload["error"])
        self.namespace["_queue_mobile_workflow"].assert_not_awaited()

    async def test_invalid_steps_rejected_before_remote_lookup_or_queue(self):
        for value in (12, 0, "4", 4.0, True, False, None, [], {}):
            with self.subTest(value=value):
                status, payload = await self.submit(turbo=True, turbo_steps=value)
                self.assertEqual(status, 400, payload)
                self.assertIn("turbo_steps 参数必须是整数 8 或 4", payload["error"])
        self.namespace["_available_mobile_video_models"].assert_not_awaited()
        self.namespace["_available_mobile_loras"].assert_not_awaited()
        self.namespace["_queue_mobile_workflow"].assert_not_awaited()

    async def test_non_boolean_values_are_rejected(self):
        for value in ("true", "false", 1, None):
            with self.subTest(value=value):
                status, payload = await self.submit(turbo=value)
                self.assertEqual(status, 400)
                self.assertIn("turbo 参数必须是布尔值", payload["error"])
        self.namespace["_queue_mobile_workflow"].assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
