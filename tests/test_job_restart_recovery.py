import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


class JobRestartRecoveryTest(unittest.TestCase):
    def test_reconcile_persisted_tasks(self):
        code = textwrap.dedent('''
            import asyncio, sys, tempfile
            from pathlib import Path
            from unittest.mock import AsyncMock, patch
            from rpp_folder_paths import LocalFolderPaths
            with tempfile.TemporaryDirectory() as tmp:
                sys.modules['folder_paths'] = LocalFolderPaths(tmp)
                import rpp_mobile as m
                import rpp_remote as r
                async def check():
                    job = {'prompt_id': 'old', 'remote_client_id': 'original-client'}
                    m.MOBILE_SESSION_JOBS[:] = [job]
                    with patch.object(m, 'REMOTE_COMFYUI_URL', 'http://remote'), \
                         patch.object(m, '_ensure_mobile_session_jobs_loaded'), \
                         patch.object(m, '_remote_queue', AsyncMock(return_value=([], []))) as queue, \
                         patch.object(m, '_mobile_remote_history_entry', AsyncMock(return_value={})) as history, \
                         patch.object(m, '_mobile_image_urls', AsyncMock(return_value=[])) as images, \
                         patch.object(m, '_mobile_video_urls', AsyncMock(return_value=[])), \
                         patch.object(m, '_remember_mobile_prompt_images'), \
                         patch.object(m, '_remember_mobile_prompt_videos'), \
                         patch.object(r, '_mobile_session_jobs_path', return_value=Path(tmp) / 'jobs.json'), \
                         patch.object(m.time, 'time', return_value=100) as now:
                        assert (await m._mobile_job_status('old'))['status'] == 'running'
                        assert job['missing_since'] == 100
                        m.MOBILE_SESSION_JOBS[:] = r._load_mobile_session_jobs()
                        job = m.MOBILE_SESSION_JOBS[0]
                        now.return_value = 116
                        assert (await m._mobile_job_status('old'))['status'] == 'failed'
                        assert await m._mobile_active_job_count() == 0
                        assert await m._active_mobile_session_jobs() == []
                        # A transient queue/history outage is not proof of interruption.
                        job.pop('status'); job.pop('error')
                        queue.side_effect = RuntimeError('offline')
                        try:
                            await m._mobile_job_status('old')
                            assert False
                        except RuntimeError:
                            pass
                        assert 'status' not in job and 'missing_since' not in job
                        queue.side_effect = None
                        history.side_effect = RuntimeError('history offline')
                        try:
                            await m._mobile_job_status('old')
                            assert False
                        except RuntimeError:
                            pass
                        assert 'status' not in job and 'missing_since' not in job
                        queue.return_value = ([[0, 'old', {}]], [])
                        with patch.object(m, '_resume_mobile_job_watcher') as resume:
                            assert (await m._mobile_job_status('old'))['status'] == 'running'
                            resume.assert_called_once_with(job, [0, 'old', {}])
                        queue.return_value = ([], [])
                        history.side_effect = None
                        history.return_value = {'status': {'status_str': 'success'}}
                        job['receiving_since'] = 50
                        assert (await m._mobile_job_status('old'))['status'] == 'failed'
                        assert job['receiving_since'] == 50
                        images.return_value = [{'filename': 'local.png'}]
                        queue.side_effect = RuntimeError('offline')
                        history.side_effect = RuntimeError('offline')
                        assert (await m._mobile_job_status('old'))['status'] == 'completed'
                        # Restore the original client ID and output nodes exactly once.
                        with patch.object(r, '_watch_remote_websocket_outputs', AsyncMock()) as watch:
                            item = [0, 'old', {'out': {'class_type': 'RandomPhotoPromptStreamImage'}}]
                            r._resume_mobile_job_watcher(job, item)
                            r._resume_mobile_job_watcher(job, item)
                            watch.assert_called_once()
                            assert watch.call_args.args == ('old', 'original-client')
                            assert watch.call_args.kwargs['output_nodes'] == {'out'}
                            await r.REMOTE_WS_WATCHERS['old']
                        with patch.object(r, 'REMOTE_COMFYUI_URL', 'http://remote'), \
                             patch.object(r, '_remote_json', AsyncMock(return_value=(None, {'error': 'offline'}))):
                            try:
                                await r._remote_queue()
                                assert False
                            except RuntimeError:
                                pass
                asyncio.run(check())
        ''')
        result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr[-4000:])
