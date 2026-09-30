import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RemoteProgressDenominatorTest(unittest.TestCase):
    def test_step_denominator_is_always_the_workflow_node_total(self):
        # 远端会同时发“节点执行”和“采样步数”两种进度；步骤 x/y 的 y 必须始终是节点总数。
        code = r'''
import asyncio, json, tempfile
from pathlib import Path
from unittest.mock import patch
from rpp_server import create_app

class Recorder(dict):
    def __init__(self):
        super().__init__()
        self.history = []
    def __setitem__(self, key, value):
        self.history.append(dict(value))
        super().__setitem__(key, value)

class FakeMessage:
    def __init__(self, payload):
        self.type = __import__("aiohttp").WSMsgType.TEXT
        self.data = json.dumps(payload)

class FakeWs:
    def __init__(self, payloads):
        self.queue = [FakeMessage(item) for item in payloads]
    async def send_json(self, _data):
        return None
    async def receive(self, timeout=None):
        return self.queue.pop(0)
    async def __aenter__(self):
        return self
    async def __aexit__(self, *_exc):
        return False

class FakeSession:
    async def __aenter__(self):
        return self
    async def __aexit__(self, *_exc):
        return False

PID = "prompt-1"
events = [
    {"type": "feature_flags", "data": {}},
    {"type": "execution_cached", "data": {"prompt_id": PID, "nodes": ["1", "2"]}},
    {"type": "executing", "data": {"prompt_id": PID, "node": "3"}},
    {"type": "progress", "data": {"prompt_id": PID, "node": "3", "value": 4, "max": 14}},
    {"type": "executing", "data": {"prompt_id": PID, "node": "4"}},
    {"type": "progress", "data": {"prompt_id": PID, "node": "4", "value": 9, "max": 27}},
    {"type": "executing", "data": {"prompt_id": PID, "node": "5"}},
    {"type": "executing", "data": {"prompt_id": PID, "node": None}},
]

async def run():
    with tempfile.TemporaryDirectory() as directory:
        create_app(Path(directory))
        import rpp_remote
        recorder = Recorder()
        async def connect(*_args, **_kwargs):
            return FakeWs(events)
        with patch.object(rpp_remote, "REMOTE_COMFYUI_URL", "http://127.0.0.1:1"), \
             patch.object(rpp_remote, "REMOTE_PROGRESS_BY_PROMPT_ID", recorder), \
             patch.object(rpp_remote, "ClientSession", lambda *a, **k: FakeSession()), \
             patch.object(rpp_remote, "_connect_remote_websocket", connect), \
             patch.object(rpp_remote, "_send_browser_event", lambda *a, **k: asyncio.sleep(0)):
            await rpp_remote._watch_remote_websocket_outputs(PID, "client", node_total=5, expect_image_frames=False)
        assert recorder.history, "没有记录任何进度"
        maxima = {item["max"] for item in recorder.history}
        assert maxima == {5}, maxima
        values = [item["value"] for item in recorder.history]
        assert values == sorted(values), values
        assert values[0] == 2, values          # 缓存跳过的两个节点先算作已经过
        assert values[-1] == 5, values         # 结束时正好走满
        assert all(item["type"] == "node" for item in recorder.history)
        sampler = [item["sampler"] for item in recorder.history if "sampler" in item]
        assert {"value": 4, "max": 14} in sampler and {"value": 9, "max": 27} in sampler, sampler

asyncio.run(run())
'''
        env = dict(os.environ, RPP_REMOTE_COMFYUI_URL="http://127.0.0.1:1")
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
