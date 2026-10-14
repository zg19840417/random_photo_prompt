import ast
import json
import re
import subprocess
import time
import traceback
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiohttp import web
from test_prompt_passthrough import _load_rpp_prompts


ROOT = Path(__file__).resolve().parents[1]


class MobileCustomResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_prompt_custom_size_reaches_workflow_and_job(self):
        prompts = _load_rpp_prompts()
        namespace = {name: getattr(prompts, name) for name in prompts.__all__}
        patch_workflow = Mock(return_value=({}, {}))
        namespace.update({
            "web": web, "time": time, "uuid": uuid, "traceback": traceback,
            "MOBILE_DEFAULT_WORKFLOW_KEY": "zit_single", "MOBILE_MAX_ACTIVE_JOBS": 100,
            "MOBILE_SESSION_JOBS": [],
            "_mobile_workflow_config": lambda key: (key or "zit_single", {"label": "ZIT"}),
            "_load_mobile_workflow": lambda key: {},
            "_available_mobile_zimage_models": AsyncMock(return_value={"zit_models": ["model"]}),
            "_available_mobile_loras": AsyncMock(return_value=[]),
            "_is_krea2_workflow": lambda key: False,
            "_resolve_zit_model": lambda requested, models: models[0],
            "_resolve_mobile_loras": lambda requested, available: [],
            "_mobile_active_job_count": AsyncMock(return_value=0),
            "_patch_mobile_workflow": patch_workflow,
            "_queue_mobile_workflow": AsyncMock(return_value=({"prompt_id": "test"}, None)),
            "_save_mobile_session_jobs": Mock(),
        })
        tree = ast.parse((ROOT / "rpp_endpoints.py").read_text())
        function = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "generate_mobile_image")
        exec(compile(ast.Module(body=[function], type_ignores=[]), "rpp_endpoints.py", "exec"), namespace)
        for size, orientation, expected in (
            ("1280x768", "portrait", (1280, 768, "landscape")),
            ("960x960", "landscape", (960, 960, "square")),
            ("3000x2000", "square", (1920, 1280, "landscape")),
            ("1920x1680", "square", (1920, 1664, "landscape")),
            ("", "portrait", (864, 1536, "portrait")),
        ):
            with self.subTest(size=size):
                request = SimpleNamespace(json=AsyncMock(return_value={
                    "shot": "half_body", "scale": "normal", "orientation": orientation,
                    "custom_prompt": "   ", "custom_prompt_source": "manual", "custom_resolution": size,
                }))
                response = await namespace["generate_mobile_image"](request)
                payload = json.loads(response.body)
                self.assertEqual(response.status, 200, payload)
                job = payload["jobs"][0]
                self.assertEqual((job["width"], job["height"], job["aspect"]), expected)
                self.assertFalse(job["custom_prompt"])
                self.assertEqual(job["custom_resolution"], size)
                self.assertTrue(job["prompt"])
                self.assertEqual(patch_workflow.call_args.args[2:4], expected[:2])
                self.assertEqual(patch_workflow.call_args.args[1]["aspect"], expected[2])


class MobileCustomResolutionUiTests(unittest.TestCase):
    def test_resolution_only_confirm_persist_submit_and_clear(self):
        html = (ROOT / "web/mobile.html").read_text()
        functions = []
        for name in ("updateCustomPromptButton", "buildGeneratePayload", "saveSettings", "restoreSettings"):
            match = re.search(r"    function " + name + r"\([^\n]*\) \{.*?\n    \}", html, re.S)
            self.assertIsNotNone(match, name)
            functions.append(match.group())
        listeners = []
        for name in ("customPromptOk", "customPromptClear"):
            match = re.search(r"    " + name + r'\.addEventListener\("click", \(\) => \{.*?\n    \}\);', html, re.S)
            self.assertIsNotNone(match, name)
            listeners.append(match.group())
        code = r'''
const assert = require("node:assert/strict");
const state = {mode: "image", clientId: "test", customPrompt: "", customResolution: "", customPromptSource: ""};
const handlers = {}, customPromptOk = {addEventListener: (_, cb) => handlers.ok = cb}, customPromptClear = {addEventListener: (_, cb) => handlers.clear = cb};
const customPromptText = {value: "  "}, customPromptResolutionInput = {value: "1280x768"}, customPromptResolution = {value: ""};
const customPromptButton = {classList: {toggle: (_, value) => customPromptButton.active = value}}, copyCustomPrompt = {};
const scaleSelect = {value: "normal"}, eraSelect = {}, castSelect = {}, shotSelect = {}, orientationSelect = {value: "portrait"}, workflowSelect = {value: "zit_single"};
const zitModelSelect = {dataset: {}}, zibModelSelect = {dataset: {}}, krea2ModelSelect = {dataset: {}};
const videoInputModeSelect = {}, videoModelSelect = {dataset: {}}, videoTurboInput = {}, videoTurboStepsSelect = {};
const imageSeedInput = {value: ""}, imageNegativePrompt = {value: ""}, videoActionInput = {}, videoFpsSelect = {}, videoSecondsSelect = {};
const settingsKey = "settings", storage = new Map();
const localStorage = {setItem: (key, value) => storage.set(key, value), getItem: key => storage.get(key)};
const selectedLoras = () => [], imageKey = () => "", currentCount = () => 1, currentVideoCount = () => 1;
const optionExists = () => false, setSelectValue = (select, value) => {select.value = value;};
const switchMode = () => {}, normalizeStoredShot = () => "", setCount = () => {}, setVideoCount = () => {};
const updateCastAvailability = () => {}, updateVideoTurboAvailability = () => {}, updateSourcePicker = () => {}, closePromptDialog = () => {};
'''
        code += "\n".join(functions + listeners)
        code += r'''
handlers.ok();
assert.equal(state.customPrompt, "");
assert.equal(buildGeneratePayload(false, 1).custom_resolution, "1280x768");
assert.equal(buildGeneratePayload(false, 1).custom_prompt, "");
assert.equal(customPromptButton.active, true);
assert.equal(customPromptButton.textContent, "已设定分辨率 1280x768");
assert.equal(copyCustomPrompt.disabled, true);
state.customResolution = "";
state.customPromptSource = "";
restoreSettings();
assert.equal(state.customResolution, "1280x768");
assert.equal(buildGeneratePayload(false, 1).custom_resolution, "1280x768");
handlers.clear();
assert.equal(buildGeneratePayload(false, 1).custom_resolution, "");
assert.equal(customPromptButton.active, false);
'''
        result = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
