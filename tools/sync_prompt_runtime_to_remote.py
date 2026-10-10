#!/usr/bin/env python3
import base64
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
REMOTE_SSH = "administrator@192.168.123.111"
REMOTE = f"{REMOTE_SSH}:D:/ComfyUI/ComfyUI/custom_nodes/random_photo_prompt/"

FILES = [
    "__init__.py",
    "rpp_routes.py",
    "rpp_comfy.py",
    "rpp_globals.py",
    "rpp_utils.py",
    "rpp_prompts.py",
    "rpp_workflow.py",
    "rpp_remote.py",
    "rpp_mobile.py",
    "rpp_nodes.py",
    "rpp_endpoints.py",
    "prompt_constants.py",
    "prompt_data.py",
    "prompt_engine.py",
    "prompt_normalize.py",
    "prompt_composer.py",
    "prompt_fluency.py",
    "negative_prompt_engine.py",
    "video_prompt_engine.py",
    "video_resolution.py",
    "prompt_resolution.py",
    "remote_preview_protocol.py",
    "workflow_cleanup_policy.py",
    "mobile_workflow_api.json",
    "mobile_workflow_api_2.json",
    "mobile_workflow_api_krea2.json",
    "mobile_workflow_api_krea2_double.json",
    "minimax_h3_workflow_api.json",
]
SUBDIR_FILES = [
    "data/nsfw_pose_expression_options.json",
    "data/prompt_pools.json",
    "data/art_direction_pools.json",
    "web/mobile.html",
]


def run(args, cwd=PROJECT):
    print("+ " + " ".join(str(arg) for arg in args), flush=True)
    return subprocess.check_call(args, cwd=str(cwd))


def read_remote_queue():
    with urllib.request.urlopen("http://192.168.123.111:8188/queue", timeout=5) as response:
        return json.load(response)


def recover_stopped_remote():
    # HTTP 超时不能证明服务停止；由 Windows 本机检查后才允许启动已有任务。
    script = r'''
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$listeners = @(Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -eq 8188 })
$processes = @(Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and ($_.Name -match '^python' -or $_.CommandLine -match 'main\.py')
})
if ($listeners.Count -or $processes.Count) {
    Write-Output 'Remote process/listener exists; refusing automatic recovery.'
    exit 2
}
Start-ScheduledTask -TaskName 'ComfyUI-8188-Interactive'
Write-Output 'Stopped remote: existing startup task requested.'
'''
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", REMOTE_SSH,
         "powershell", "-NoProfile", "-EncodedCommand", encoded],
        check=True, timeout=30,
    )
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        time.sleep(2)
        try:
            return read_remote_queue()
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError):
            pass
    raise RuntimeError("远端启动任务已执行，但 300 秒内队列接口未恢复；停止同步重启")


def require_idle_queues():

    try:
        with urllib.request.urlopen("http://127.0.0.1:8188/random_photo_prompt/mobile/jobs", timeout=5) as response:
            jobs = json.load(response)["jobs"]
    except urllib.error.HTTPError:
        raise  # HTTP 错误不能冒充“本机未启动”。
    except urllib.error.URLError as exc:
        import errno
        if not isinstance(exc.reason, ConnectionRefusedError) and getattr(exc.reason, "errno", None) != errno.ECONNREFUSED:
            raise
        jobs = []  # Mac 未启动时无活动任务；后续启动步骤负责恢复。
    if jobs:
        raise RuntimeError("手机端仍有活动任务，停止同步重启")
    try:
        queue = read_remote_queue()
    except urllib.error.HTTPError:
        raise
    except (urllib.error.URLError, TimeoutError):
        queue = recover_stopped_remote()
    if queue["queue_running"] or queue["queue_pending"]:
        raise RuntimeError("192.168.123.111:8188 有运行或待执行任务，停止同步重启")


def verify_remote_object_info():
    url = "http://192.168.123.111:8188/object_info/RandomPhotoPromptStreamImage"
    with urllib.request.urlopen(url, timeout=20) as response:
        body = response.read(500)
    if b"RandomPhotoPromptStreamImage" not in body:
        # 节点导入失败时接口仍返回 200 和 {}，必须明确报错，不能当作同步成功。
        raise RuntimeError(f"远端没有注册 RandomPhotoPromptStreamImage 节点（custom node 导入失败），返回：{body[:120]!r}")
    print(f"remote object_info ok: HTTP {response.status} {body[:120]!r}", flush=True)


def main():
    require_idle_queues()
    existing = [str(PROJECT / file) for file in FILES if (PROJECT / file).is_file()]
    if not existing:
        raise RuntimeError("no prompt runtime files found")
    run(["scp", *existing, REMOTE])
    for file in SUBDIR_FILES:
        path = PROJECT / file
        if not path.is_file():
            continue
        parent = path.parent.name
        remote_path = f"D:/ComfyUI/ComfyUI/custom_nodes/random_photo_prompt/{parent}"
        remote_dir = f"{REMOTE_SSH}:{remote_path}/"
        run(["ssh", REMOTE_SSH, "powershell", "-NoProfile", "-Command", f"New-Item -ItemType Directory -Force '{remote_path}' | Out-Null"])
        run(["scp", str(path), remote_dir])
    require_idle_queues()
    run(["python3", "tools/restart_windows_remote_comfyui.py"])
    verify_remote_object_info()
    return 0


if __name__ == "__main__":
    sys.exit(main())
