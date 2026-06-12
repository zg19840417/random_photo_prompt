#!/usr/bin/env python3
import os
import signal
import subprocess
import sys
from pathlib import Path


ROOT = Path("/Users/zouge/Documents/Codex/2026-06-02/macbook-air-80/work/ComfyUI")
PYTHON = ROOT / ".venv/bin/python"
MAIN = ROOT / "main.py"
PID_FILE = ROOT / "comfyui-8188.pid"
LOG_FILE = ROOT / "comfyui-codex.log"
ERR_FILE = ROOT / "comfyui-codex.err.log"


def running(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def main():
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
        except ValueError:
            pid = 0
        if pid and running(pid):
            print(pid)
            return 0

    env = os.environ.copy()
    env.update(
        {
            "RPP_REMOTE_COMFYUI_URL": os.environ.get("RPP_REMOTE_COMFYUI_URL", "http://192.168.123.111:8188"),
            "RPP_REMOTE_OUTPUT_DIR": str(ROOT / "output/4090 生成"),
            "RPP_REMOTE_LORA_DIR": os.environ.get("RPP_REMOTE_LORA_DIR", str(Path.home() / "Desktop/远程模型/loras")),
            "RPP_REMOTE_DELETE_OUTPUT": os.environ.get("RPP_REMOTE_DELETE_OUTPUT", "1"),
            "RPP_REMOTE_WEBSOCKET_OUTPUT": os.environ.get("RPP_REMOTE_WEBSOCKET_OUTPUT", "1"),
        }
    )
    args = [
        str(PYTHON),
        str(MAIN),
        "--listen",
        "127.0.0.1",
        "--port",
        "8188",
        "--disable-api-nodes",
    ]
    with LOG_FILE.open("ab", buffering=0) as stdout, ERR_FILE.open("ab", buffering=0) as stderr:
        process = subprocess.Popen(
            args,
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            env=env,
            start_new_session=True,
        )
    PID_FILE.write_text(str(process.pid))
    print(process.pid)
    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    sys.exit(main())
