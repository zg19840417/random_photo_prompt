#!/usr/bin/env python3
import subprocess
import sys
import urllib.request
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
REMOTE = "administrator@192.168.123.111:'D:/ComfyUI/ComfyUI/custom_nodes/random_photo_prompt/'"

FILES = [
    "__init__.py",
    "prompt_constants.py",
    "prompt_data.py",
    "prompt_data_generated.py",
    "prompt_engine.py",
    "prompt_normalize.py",
    "prompt_planner.py",
    "prompt_postprocess.py",
    "negative_prompt_engine.py",
    "keyword_expansion_engine.py",
    "video_prompt_engine.py",
    "prompt_resolution.py",
]


def run(args, cwd=PROJECT):
    print("+ " + " ".join(str(arg) for arg in args), flush=True)
    return subprocess.check_call(args, cwd=str(cwd))


def verify_remote_object_info():
    url = "http://192.168.123.111:8188/object_info/RandomPhotoPrompt"
    with urllib.request.urlopen(url, timeout=20) as response:
        body = response.read(500)
    print(f"remote object_info ok: HTTP {response.status} {body[:120]!r}", flush=True)


def main():
    existing = [str(PROJECT / file) for file in FILES if (PROJECT / file).is_file()]
    if not existing:
        raise RuntimeError("no prompt runtime files found")
    run(["scp", *existing, REMOTE])
    run(["python3", "tools/restart_windows_remote_comfyui.py"])
    verify_remote_object_info()
    return 0


if __name__ == "__main__":
    sys.exit(main())
