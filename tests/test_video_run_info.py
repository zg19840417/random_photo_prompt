import ast
import hmac
import json
import re
import subprocess
import sys
import tempfile
import textwrap
import traceback
import unittest
import uuid
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]


class VideoRunInfoTest(unittest.TestCase):
    def test_run_info_saved_and_survives_reregister(self):
        # 现有测试会向 sys.modules 注入宿主桩，故在干净子进程里验证真实模块。
        code = textwrap.dedent(f"""
            import sys, tempfile
            from pathlib import Path
            from unittest import mock
            sys.path.insert(0, {str(ROOT)!r})
            from rpp_folder_paths import LocalFolderPaths
            tmp = tempfile.mkdtemp()
            sys.modules["folder_paths"] = LocalFolderPaths(tmp)
            import rpp_mobile
            index_path = Path(tmp) / "index.json"
            with mock.patch.object(rpp_mobile, "_mobile_prompt_index_path", return_value=index_path):
                sub = rpp_mobile.MOBILE_VIDEO_OUTPUT_SUBFOLDER
                rpp_mobile._remember_mobile_prompt_file("a.mp4", "动作", sub, 1, {{"turbo": True, "elapsed_seconds": 176}})
                rpp_mobile._remember_mobile_prompt_file("a.mp4", "动作", sub, 1)
                assert rpp_mobile._mobile_video_run_info("a.mp4") == {{"turbo": True, "elapsed_seconds": 176}}, rpp_mobile._mobile_video_run_info("a.mp4")
        """)
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])

    def test_detail_line_uses_actual_steps_and_old_record_default(self):
        html = (ROOT / "web/mobile.html").read_text()
        start = html.index("      const runInfo = record.video.run_info || {};")
        end = html.index("      viewerCount.textContent", start)
        fragment = html[start:end]
        cases = [
            ({"turbo": True, "turbo_steps": 4, "elapsed_seconds": 176}, "Turbo 4 步"),
            ({"turbo": True, "turbo_steps": 8, "elapsed_seconds": 176}, "Turbo 8 步"),
            ({"turbo": True, "elapsed_seconds": 176}, "Turbo 8 步"),
            ({"turbo": False, "turbo_steps": None, "elapsed_seconds": 176}, "标准采样"),
        ]
        for info, label in cases:
            with self.subTest(info=info):
                code = "const record = " + json.dumps({"video": {"run_info": info}, "prompt": "动作"}) + ";\n"
                code += "const viewerPrompt = {};\n" + fragment + "\nconsole.log(viewerPrompt.textContent);"
                result = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, f"耗时：176 秒（含排队与加载）· {label}\n视频提示词：\n动作\n")


class VideoReturnRunInfoTest(unittest.IsolatedAsyncioTestCase):
    async def test_return_records_actual_steps_and_legacy_default(self):
        tree = ast.parse((ROOT / "rpp_remote.py").read_text())
        function = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "receive_remote_video")
        mobile = ModuleType("rpp_mobile")
        mobile._remember_mobile_prompt_file = Mock()
        for turbo, steps, expected_steps in ((True, 4, 4), (True, 8, 8), (True, "missing", 8), (False, None, None)):
            with self.subTest(turbo=turbo, steps=steps), tempfile.TemporaryDirectory() as directory:
                job = {"media_type": "video", "output_prefix": "test_video", "generation_prompt": "动作",
                       "turbo": turbo, "created_at": 100000, "seed": 1}
                if steps != "missing":
                    job["turbo_steps"] = steps
                namespace = {
                    "web": web, "Path": Path, "hmac": hmac, "re": re, "uuid": uuid, "traceback": traceback,
                    "time": SimpleNamespace(time=lambda: 276),
                    "REMOTE_TRANSFER_TOKEN": "test-token", "REMOTE_TRANSFER_ALLOWED_IP": "test-only",
                    "MOBILE_VIDEO_EXTENSIONS": {".mp4"}, "MOBILE_VIDEO_OUTPUT_SUBFOLDER": "videos",
                    "MOBILE_SESSION_JOBS": [job], "MOBILE_VIDEO_PROMPT_BY_FILENAME": {},
                    "_remote_transfer_source_is_allowed": lambda *args: True,
                    "_mobile_video_output_dir": lambda: Path(directory), "_save_mobile_session_jobs": Mock(),
                }
                exec(compile(ast.Module(body=[function], type_ignores=[]), "rpp_remote.py", "exec"), namespace)
                request = SimpleNamespace(headers={"X-RPP-Transfer-Token": "test-token", "X-RPP-Filename-Prefix": "test_video"},
                                          content=SimpleNamespace(readany=AsyncMock(side_effect=[b"test-video", b""])))
                with patch.dict(sys.modules, {"rpp_mobile": mobile}):
                    response = await namespace["receive_remote_video"](request)
                self.assertEqual(response.status, 200, response.body)
                filename = json.loads(response.body)["filename"]
                self.assertEqual((Path(directory) / filename).read_bytes(), b"test-video")
                self.assertEqual(mobile._remember_mobile_prompt_file.call_args.args[-1], {
                    "turbo": turbo, "turbo_steps": expected_steps, "elapsed_seconds": 176,
                })


if __name__ == "__main__":
    unittest.main()
