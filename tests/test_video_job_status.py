import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


class VideoJobStatusTest(unittest.TestCase):
    def test_video_lifecycle_and_persistence(self):
        code = textwrap.dedent('''
            import asyncio, tempfile, sys
            from pathlib import Path
            from unittest.mock import AsyncMock, patch
            from rpp_folder_paths import LocalFolderPaths
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                sys.modules['folder_paths'] = LocalFolderPaths(tmp)
                import rpp_mobile as m
                import rpp_remote as r
                prefix = 'mobile_video_123456789abc'
                job = {'prompt_id': 'video-id', 'media_type': 'video', 'output_prefix': prefix}
                m.MOBILE_SESSION_JOBS[:] = [job]
                history = {'status': {'status_str': 'success'}, 'prompt': [0, 0, {
                    'out': {'class_type': 'RandomPhotoPromptRemoteUploadVideo',
                            'inputs': {'filename_prefix': prefix}}}]}
                async def check():
                    with patch.object(m, 'REMOTE_COMFYUI_URL', 'http://remote'), \
                         patch.object(m, '_ensure_mobile_session_jobs_loaded'), \
                         patch.object(m, '_remote_queue', AsyncMock(return_value=([], []))), \
                         patch.object(m, '_mobile_remote_history_entry', AsyncMock(return_value=history)), \
                         patch.object(m, '_mobile_image_urls', AsyncMock(return_value=[])), \
                         patch.object(m, '_mobile_video_output_dir', return_value=root), \
                         patch.object(m, '_mobile_video_output_file', side_effect=lambda name: root / name), \
                         patch.object(m, '_video_dimensions_for_file', return_value={'width': 480, 'height': 704}), \
                         patch.object(r, '_mobile_session_jobs_path', return_value=root / 'jobs.json'):
                        assert (await m._mobile_job_status('video-id'))['status'] == 'receiving'
                        assert await m._mobile_active_job_count() == 1
                        path = root / (prefix + '_result.mp4')
                        path.write_bytes(b'video')
                        for _ in range(3):
                            result = await m._mobile_job_status('video-id')
                            assert result['status'] == 'completed', result
                            assert result['videos'][0]['filename'] == path.name
                        assert await m._active_mobile_session_jobs() == []
                        assert await m._mobile_active_job_count() == 0
                        assert m.MOBILE_SESSION_JOBS[0]['media_type'] == 'video'
                        # 重新加载持久记录后仍可找到同一视频。
                        m.MOBILE_SESSION_JOBS[:] = r._load_mobile_session_jobs()
                        assert (await m._mobile_job_status('video-id'))['status'] == 'completed'
                        # 旧版删除的任务可从准确的远端前缀恢复。
                        m.MOBILE_SESSION_JOBS.clear()
                        assert (await m._mobile_job_status('video-id'))['status'] == 'completed'
                        # 失败记录保留视频类型，迟到的本机结果仍可修正失败。
                        job = {'prompt_id': 'late-id', 'media_type': 'video',
                               'output_prefix': 'mobile_video_aaaaaaaaaaaa'}
                        m.MOBILE_SESSION_JOBS[:] = [job]
                        with patch.object(m, 'MOBILE_VIDEO_RESULT_RECEIVE_GRACE_SECONDS', -1):
                            result = await m._mobile_job_status('late-id')
                            assert result['status'] == 'failed', result
                            assert '视频' in result['error']
                        result = await m._mobile_job_status('late-id')
                        assert result['status'] == 'failed' and '视频' in result['error']
                        (root / 'mobile_video_aaaaaaaaaaaa_late.mp4').write_bytes(b'late')
                        assert (await m._mobile_job_status('late-id'))['status'] == 'completed'
                        # 终态数量限制不得挤掉活动任务。
                        m.MOBILE_SESSION_JOBS[:] = [{'prompt_id': 'active'}] + [
                            {'prompt_id': str(i), 'status': 'completed'} for i in range(110)]
                        r._save_mobile_session_jobs()
                        loaded = r._load_mobile_session_jobs()
                        assert len(loaded) == 101 and loaded[0]['prompt_id'] == 'active'
                asyncio.run(check())
        ''')
        result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])


if __name__ == '__main__':
    unittest.main()
