#!/usr/bin/env python3
import os
import signal
import socket
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


def process_matches(pid):
    try:
        output = subprocess.check_output(["ps", "-p", str(pid), "-o", "command="], text=True).strip()
    except Exception:
        return False
    return str(MAIN) in output and "--port 8188" in output


def port_listening():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        return sock.connect_ex(("127.0.0.1", 8188)) == 0
    finally:
        sock.close()


def local_lan_host(remote_host="192.168.123.111", remote_port=8188):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((remote_host, int(remote_port)))
        return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        sock.close()


def main():
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
        except ValueError:
            pid = 0
        if pid and running(pid) and process_matches(pid) and port_listening():
            print(pid)
            return 0
        PID_FILE.unlink(missing_ok=True)

    env = os.environ.copy()
    mac_upload_url = os.environ.get("RPP_MAC_IMAGE_UPLOAD_URL", f"http://{local_lan_host()}:18199/random_photo_prompt/proxy/upload_image")
    env.update(
        {
            "RPP_REMOTE_COMFYUI_URL": os.environ.get("RPP_REMOTE_COMFYUI_URL", "http://192.168.123.111:8188"),
            "RPP_REMOTE_OUTPUT_DIR": str(ROOT / "output/4090 生成"),
            "RPP_REMOTE_LORA_DIR": os.environ.get("RPP_REMOTE_LORA_DIR", str(Path.home() / "Desktop/远程模型/loras")),
            "RPP_REMOTE_DELETE_OUTPUT": os.environ.get("RPP_REMOTE_DELETE_OUTPUT", "1"),
            "RPP_REMOTE_WEBSOCKET_OUTPUT": os.environ.get("RPP_REMOTE_WEBSOCKET_OUTPUT", "1"),
            "RPP_MAC_IMAGE_UPLOAD_URL": mac_upload_url,
            "RPP_MAC_VIDEO_UPLOAD_URL": os.environ.get("RPP_MAC_VIDEO_UPLOAD_URL", mac_upload_url.replace("/upload_image", "/upload_video")),
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
