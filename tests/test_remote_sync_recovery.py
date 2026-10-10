import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from tools import sync_prompt_runtime_to_remote as sync


class RemoteSyncRecoveryTest(unittest.TestCase):
    def run_check(self, queue, recovery):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"jobs": []}'
        with patch.object(sync.urllib.request, "urlopen", return_value=response), \
                patch.object(sync, "read_remote_queue", side_effect=queue), \
                patch.object(sync, "recover_stopped_remote", return_value=recovery) as recover:
            sync.require_idle_queues()
            return recover.call_count

    def test_live_idle_queue_needs_no_recovery(self):
        self.assertEqual(self.run_check([{"queue_running": [], "queue_pending": []}], None), 0)

    def test_unreachable_remote_is_recovered_then_checked(self):
        self.assertEqual(self.run_check([urllib.error.URLError("timeout")],
                                       {"queue_running": [], "queue_pending": []}), 1)

    def test_recovered_busy_queue_still_blocks_sync(self):
        with self.assertRaises(RuntimeError):
            self.run_check([TimeoutError()], {"queue_running": [1], "queue_pending": []})

    def test_http_error_does_not_trigger_recovery(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.run_check([urllib.error.HTTPError("url", 503, "failed", None, None)], None)

    def test_ssh_refusal_does_not_poll_or_continue(self):
        import subprocess
        with patch.object(sync.subprocess, "run", side_effect=subprocess.CalledProcessError(2, "ssh")), \
                patch.object(sync, "read_remote_queue") as queue:
            with self.assertRaises(subprocess.CalledProcessError):
                sync.recover_stopped_remote()
            queue.assert_not_called()


if __name__ == "__main__":
    unittest.main()
