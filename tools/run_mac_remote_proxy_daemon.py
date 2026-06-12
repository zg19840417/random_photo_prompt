#!/usr/bin/env python3
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path


ROOT = Path("/Users/zouge/Documents/Codex/2026-06-02/macbook-air-80/work/ComfyUI")
PROJECT = ROOT / "custom_nodes/random_photo_prompt"
PYTHON = ROOT / ".venv/bin/python"
PROXY = PROJECT / "tools/mac_comfyui_remote_proxy.py"
PID_FILE = ROOT / "comfyui-proxy.pid"
LOG_FILE = ROOT / "comfyui-proxy.log"
ERR_FILE = ROOT / "comfyui-proxy.err.log"
REMOTE_URL = os.environ.get("RPP_PROXY_REMOTE_URL", "http://192.168.123.111:8188")
LOCAL_MOBILE_URL = os.environ.get("RPP_PROXY_LOCAL_MOBILE_URL", "http://127.0.0.1:8188")
OUTPUT_DIR = os.environ.get("RPP_PROXY_OUTPUT_DIR", str(ROOT / "output/4090 生成"))
PROXY_PORT = os.environ.get("RPP_PROXY_PORT", "18199")
DELETE_REMOTE_OUTPUT = os.environ.get("RPP_PROXY_DELETE_REMOTE_OUTPUT", "1")
WEBSOCKET_OUTPUT = os.environ.get("RPP_PROXY_WEBSOCKET_OUTPUT", "1")
RESTART_PROXY = os.environ.get("RPP_PROXY_RESTART", "0") == "1"


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
    return str(PROXY) in output


def port_listening(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        return sock.connect_ex(("127.0.0.1", int(port))) == 0
    finally:
        sock.close()


def stop_proxy(pid):
    if not pid or not running(pid):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    for _ in range(30):
        if not running(pid):
            return
        import time

        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def main():
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
        except ValueError:
            pid = 0
        if RESTART_PROXY and pid and running(pid) and process_matches(pid):
            stop_proxy(pid)
            PID_FILE.unlink(missing_ok=True)
        elif pid and running(pid) and process_matches(pid) and port_listening(PROXY_PORT):
            print(pid)
            return
        else:
            PID_FILE.unlink(missing_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "RPP_PROXY_REMOTE_URL": REMOTE_URL,
            "RPP_PROXY_LOCAL_MOBILE_URL": LOCAL_MOBILE_URL,
            "RPP_PROXY_OUTPUT_DIR": OUTPUT_DIR,
            "RPP_PROXY_PORT": PROXY_PORT,
            "RPP_PROXY_DELETE_REMOTE_OUTPUT": DELETE_REMOTE_OUTPUT,
            "RPP_PROXY_WEBSOCKET_OUTPUT": WEBSOCKET_OUTPUT,
        }
    )
    with LOG_FILE.open("ab", buffering=0) as stdout, ERR_FILE.open("ab", buffering=0) as stderr:
        process = subprocess.Popen(
            [str(PYTHON), str(PROXY)],
            cwd=str(PROJECT),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            env=env,
            start_new_session=True,
        )
    PID_FILE.write_text(str(process.pid))
    print(process.pid)


if __name__ == "__main__":
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    sys.exit(main())
