#!/usr/bin/env python3
import subprocess
import sys
import urllib.request
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
REMOTE_SSH = "administrator@192.168.123.111"
REMOTE = f"{REMOTE_SSH}:D:/ComfyUI/ComfyUI/custom_nodes/random_photo_prompt/"

FILES = [
    "__init__.py",
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
    "prompt_planner.py",
    "prompt_postprocess.py",
    "negative_prompt_engine.py",
    "k2_sfw_prompt_rule.py",
    "video_prompt_engine.py",
    "video_resolution.py",
    "prompt_resolution.py",
    "remote_preview_protocol.py",
    "workflow_cleanup_policy.py",
    "mobile_workflow_api_2.json",
]
SUBDIR_FILES = [
    "data/nsfw_pose_expression_options.json",
    "data/prompt_pools.json",
]


def run(args, cwd=PROJECT):
    print("+ " + " ".join(str(arg) for arg in args), flush=True)
    return subprocess.check_call(args, cwd=str(cwd))


def require_idle_queues():
    import json

    for host in ("127.0.0.1", "192.168.123.111"):
        with urllib.request.urlopen(f"http://{host}:8188/queue", timeout=5) as response:
            queue = json.load(response)
        if queue["queue_running"] or queue["queue_pending"]:
            raise RuntimeError(f"{host}:8188 有运行或待执行任务，停止同步重启")
    with urllib.request.urlopen("http://127.0.0.1:8188/random_photo_prompt/mobile/jobs", timeout=5) as response:
        jobs = json.load(response)["jobs"]
    if jobs:
        raise RuntimeError("手机端仍有活动任务，停止同步重启")


def verify_remote_object_info():
    url = "http://192.168.123.111:8188/object_info/RandomPhotoPrompt"
    with urllib.request.urlopen(url, timeout=20) as response:
        body = response.read(500)
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
        remote_dir = f"{REMOTE_SSH}:D:/ComfyUI/ComfyUI/custom_nodes/random_photo_prompt/data/"
        run(["ssh", REMOTE_SSH, "powershell", "-NoProfile", "-Command", "New-Item -ItemType Directory -Force 'D:/ComfyUI/ComfyUI/custom_nodes/random_photo_prompt/data' | Out-Null"])
        run(["scp", str(path), remote_dir])
    require_idle_queues()
    run(["python3", "tools/restart_windows_remote_comfyui.py"])
    verify_remote_object_info()
    return 0


if __name__ == "__main__":
    sys.exit(main())
