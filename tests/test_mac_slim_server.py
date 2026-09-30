import errno
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from rpp_folder_paths import LocalFolderPaths

ROOT = Path(__file__).resolve().parents[1]


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LocalPathsTests(unittest.TestCase):
    def test_original_directory_layout_and_unknown_type(self):
        paths = LocalFolderPaths("/Users/zouge/Documents/ComfyUI")
        self.assertEqual(paths.get_output_directory(), "/Users/zouge/Documents/ComfyUI/output")
        self.assertEqual(paths.get_input_directory(), "/Users/zouge/Documents/ComfyUI/input")
        self.assertEqual(paths.models_dir, "/Users/zouge/Documents/ComfyUI/models")
        self.assertEqual(paths.get_directory_by_type("temp"), "/Users/zouge/Documents/ComfyUI/temp")
        self.assertIsNone(paths.get_directory_by_type("../../etc"))

    def test_loras_filter_nested_files_and_follow_model_mount(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mount = root / "mounted"
            mount.mkdir()
            (mount / "model.safetensors").touch()
            (mount / "notes.txt").touch()
            loras = root / "models/loras"
            loras.mkdir(parents=True)
            (loras / "Zimage").symlink_to(mount, target_is_directory=True)
            (mount / "cycle").symlink_to(loras, target_is_directory=True)
            paths = LocalFolderPaths(root)
            self.assertEqual(paths.get_filename_list("loras"), ["Zimage/model.safetensors"])
            self.assertEqual(paths.get_filename_list("diffusion_models"), [])
            with self.assertRaises(KeyError):
                paths.get_filename_list("../../etc")


class DaemonTests(unittest.TestCase):
    def setUp(self):
        self.daemon = load_tool("run_mac_local_comfyui_daemon")

    def test_running_old_service_is_stopped_instead_of_returning(self):
        with tempfile.TemporaryDirectory() as directory:
            pidfile = Path(directory) / "pid"
            pidfile.write_text("123")
            with patch.object(self.daemon, "PID_FILE", pidfile), \
                 patch.object(self.daemon, "running", side_effect=[True, False]), \
                 patch.object(self.daemon, "process_matches", return_value=True), \
                 patch.object(self.daemon.subprocess, "check_output", return_value="123\n"), \
                 patch.object(self.daemon, "port_listening", side_effect=[True, False]), \
                 patch.object(self.daemon.os, "kill") as stop:
                self.daemon.stop_existing_service()
                stop.assert_called_once_with(123, self.daemon.signal.SIGTERM)
                self.assertFalse(pidfile.exists())

    def test_unknown_listener_is_never_stopped(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(self.daemon, "PID_FILE", Path(directory) / "absent"), \
                 patch.object(self.daemon.subprocess, "check_output", return_value="999\n"), \
                 patch.object(self.daemon, "process_matches", return_value=False), \
                 patch.object(self.daemon.os, "kill") as stop:
                with self.assertRaisesRegex(RuntimeError, "非本项目"):
                    self.daemon.stop_existing_service()
                stop.assert_not_called()

    def test_process_identity_accepts_both_migration_hosts(self):
        for entry in (self.daemon.MAIN, self.daemon.SERVER):
            with patch.object(self.daemon.subprocess, "check_output", return_value=f"python {entry} --port 8188"):
                self.assertTrue(self.daemon.process_matches(123))
        with patch.object(self.daemon.subprocess, "check_output", return_value=f"python {self.daemon.SERVER} --port 18188"):
            self.assertFalse(self.daemon.process_matches(123))


class SyncChecksTests(unittest.TestCase):
    def test_mac_stopped_is_allowed_but_remote_is_still_checked(self):
        import io
        sync = load_tool("sync_prompt_runtime_to_remote")
        responses = [urllib.error.URLError(ConnectionRefusedError(errno.ECONNREFUSED, "refused")),
                     io.BytesIO(b'{"queue_running": [], "queue_pending": []}')]
        with patch.object(sync.urllib.request, "urlopen", side_effect=responses) as request:
            sync.require_idle_queues()
            self.assertTrue(request.call_args_list[0].args[0].endswith("/random_photo_prompt/mobile/jobs"))
            self.assertTrue(request.call_args_list[1].args[0].endswith(":8188/queue"))

    def test_http_error_is_not_treated_as_stopped(self):
        sync = load_tool("sync_prompt_runtime_to_remote")
        with patch.object(sync.urllib.request, "urlopen", side_effect=urllib.error.HTTPError("url", 500, "error", {}, None)):
            with self.assertRaises(urllib.error.HTTPError):
                sync.require_idle_queues()

    def test_active_mobile_jobs_prevent_sync(self):
        import io
        sync = load_tool("sync_prompt_runtime_to_remote")
        with patch.object(sync.urllib.request, "urlopen", return_value=io.BytesIO(b'{"jobs": [{"prompt_id": "busy"}]}')):
            with self.assertRaisesRegex(RuntimeError, "活动任务"):
                sync.require_idle_queues()


class StandaloneIntegrationTests(unittest.TestCase):
    def test_routes_media_and_import_boundary_in_clean_process(self):
        # 现有提示词测试向 sys.modules 注入宿主桩；隔离进程才能证明真实导入边界。
        code = r'''
import asyncio, os, sys, tempfile
from pathlib import Path
from unittest.mock import patch
from aiohttp import web, ClientSession
from rpp_server import create_app

async def verify():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        output = root / 'output'
        output.mkdir()
        (output / 'sample.mp4').write_bytes(b'0123456789')
        (root / 'outside.png').write_bytes(b'not public')
        (output / 'escape.png').symlink_to(root / 'outside.png')
        (output / '.secret.png').write_bytes(b'private')
        app = create_app(root)
        import rpp_routes, rpp_endpoints, rpp_remote, rpp_mobile
        routes = web.RouteTableDef()
        rpp_routes.register_routes(routes)
        rpp_routes.register_routes(routes)
        assert len(routes) == 35
        existing = web.RouteTableDef()
        async def old_root(request): pass
        existing.get('/')(old_root)
        rpp_routes.register_routes(existing)
        assert len(existing) == 35 and list(existing)[0].handler is old_root
        async def remote_handler(request): pass
        overrides = web.RouteTableDef()
        rpp_routes.register_routes(overrides, comfy_handlers={'submit_guarded_remote_workflow': remote_handler})
        assert next(r.handler for r in overrides if r.path.endswith('/remote/submit')) is remote_handler
        assert not any(x.split('.')[0] in {'torch','comfy','server','execution'} for x in sys.modules)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        try:
            await site.start()
            port = site._server.sockets[0].getsockname()[1]
            async with ClientSession() as client:
                base = f'http://127.0.0.1:{port}'
                with patch.object(rpp_remote, '_remote_json_request', side_effect=ConnectionRefusedError('offline')):
                    for path in ('/random_photo_prompt/mobile/status', '/random_photo_prompt/local/status?format=json'):
                        async with client.get(base+path) as response:
                            payload = await response.json()
                            assert response.status == 200 and not payload['connected'] and payload['message']
                for path in ('/random_photo_prompt/interrogate','/random_photo_prompt/remote/submit'):
                    async with client.post(base+path,json={}) as response:
                        assert response.status == 503 and (await response.json())['error']
                async with client.ws_connect(base+'/ws?clientId=test-client') as ws:
                    assert (await ws.receive_json())['data']['sid'] == 'test-client'
                    event = {'type':'executing','data':{'prompt_id':'owned','node':None}}
                    await rpp_remote._send_browser_event('test-client', event)
                    assert await ws.receive_json() == event
                    await rpp_remote._send_browser_event('test-client', b'image-frame')
                    assert (await ws.receive()).data == b'image-frame'
                async with client.get(base+'/view?filename=sample.mp4', headers={'Range':'bytes=2-5'}) as response:
                    assert response.status == 206 and await response.read() == b'2345'
                for filename in ('.secret.png', 'escape.png'):
                    async with client.get(base+'/view', params={'filename':filename}) as response:
                        assert response.status == 403
                async with client.get(base+'/view', params={'filename':'outside.png','subfolder':'..'}) as response:
                    assert response.status == 403
            assert not any(x.split('.')[0] in {'torch','comfy','server','execution'} for x in sys.modules)
        finally:
            await runner.cleanup()
asyncio.run(verify())
'''
        env = dict(os.environ, RPP_REMOTE_COMFYUI_URL="http://127.0.0.1:1")
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
