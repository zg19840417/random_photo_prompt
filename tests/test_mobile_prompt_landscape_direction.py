import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = r'''
import asyncio
import json
import sys
import tempfile
import types

sys.path.insert(0, sys.argv[2])
sys.path.insert(0, sys.argv[1])

folder_paths = types.ModuleType("folder_paths")
folder_paths.models_dir = tempfile.gettempdir()
folder_paths.get_output_directory = tempfile.gettempdir
folder_paths.get_input_directory = tempfile.gettempdir
folder_paths.get_filename_list = lambda _category: []
sys.modules["folder_paths"] = folder_paths

server = types.ModuleType("server")
class PromptServer:
    instance = types.SimpleNamespace()
server.PromptServer = PromptServer
sys.modules["server"] = server

from rpp_endpoints import pregenerate_mobile_image_prompt

class Request:
    async def json(self):
        return {
            "scale": sys.argv[3],
            "shot": "half_body",
            "seed": sys.argv[4],
        }

async def main():
    response = await pregenerate_mobile_image_prompt(Request())
    print(response.text)

asyncio.run(main())
'''


class MobilePromptLandscapeDirectionTests(unittest.TestCase):
    def _prompt(self, scale, seed):
        result = subprocess.run(
            [sys.executable, "-c", _SCRIPT, str(ROOT), str(Path(sys.executable).absolute().parents[2]), scale, seed],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_mobile_endpoint_matches_camera_direction_to_inferred_landscape(self):
        payload = self._prompt("bold", "isolated-landscape-half_body-4")
        self.assertEqual(payload["aspect"], "landscape")
        self.assertEqual(payload["resolution"], "1536x1024")
        self.assertIn("腰部以上的横向半身构图", payload["prompt"])
        self.assertNotIn("竖向半身构图", payload["prompt"])
        self.assertNotIn("大腿以上", payload["display_prompt"])

    def test_mobile_half_body_waist_scope_for_normal_and_no_outfit(self):
        for scale, seed in (("normal", "waist-sample-一档-0"), ("bold_no_outfit", "waist-sample-三档-0")):
            with self.subTest(scale=scale):
                payload = self._prompt(scale, seed)
                self.assertEqual(payload["aspect"], "portrait")
                self.assertIn("腰部以上的竖向半身构图", payload["prompt"])
                self.assertNotIn("大腿以上", payload["display_prompt"])


if __name__ == "__main__":
    unittest.main()
