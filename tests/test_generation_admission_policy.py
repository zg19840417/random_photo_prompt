from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GenerationAdmissionPolicyTest(unittest.TestCase):
    def test_mobile_progress_requires_an_exact_prompt_id_match(self):
        mobile = (ROOT / "web" / "mobile.html").read_text(encoding="utf-8")

        self.assertIn(
            "const job = promptId ? state.jobs.get(promptId) : null;",
            mobile,
        )
        self.assertNotIn(
            "state.jobs.get(promptId) || [...state.jobs.values()].find(isActiveJob)",
            mobile,
        )

    def test_remote_generation_uses_the_guarded_submission_endpoint(self):
        plugin = (ROOT / "__init__.py").read_text(encoding="utf-8")

        self.assertIn('"/random_photo_prompt/remote/submit"', plugin)
        self.assertNotIn('_remote_json("POST", "/prompt", json=payload)', plugin)

    def test_remote_sync_includes_direct_runtime_dependencies(self):
        sync_script = (ROOT / "tools" / "sync_prompt_runtime_to_remote.py").read_text(encoding="utf-8")

        self.assertIn('"remote_preview_protocol.py"', sync_script)
        self.assertIn('"workflow_cleanup_policy.py"', sync_script)

    def test_remote_phone_video_replaces_savevideo_without_mac_callback_environment(self):
        workflow = (ROOT / "rpp_workflow.py").read_text(encoding="utf-8")

        self.assertIn(
            'if output_mode == "phone" or REMOTE_MAC_VIDEO_UPLOAD_URL:',
            workflow,
        )

    def test_remote_video_progress_listener_does_not_wait_for_an_image_frame(self):
        remote = (ROOT / "rpp_remote.py").read_text(encoding="utf-8")

        self.assertIn('watch_remote_progress = bool(ws_patch.get("websocket_node_ids"))', remote)
        self.assertIn("expect_image_frames=expect_image_frames", remote)
        self.assertIn('if not expect_image_frames:\n                                break', remote)
        self.assertIn('if message_type == "progress":', remote)
        self.assertIn("async def _connect_remote_websocket", remote)

    def test_remote_requests_bind_to_the_compute_route(self):
        remote = (ROOT / "rpp_remote.py").read_text(encoding="utf-8")

        self.assertIn("def _remote_compute_connector():", remote)
        self.assertIn("TCPConnector(local_addr=(source_ip, 0))", remote)


if __name__ == "__main__":
    unittest.main()
