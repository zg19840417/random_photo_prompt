#!/usr/bin/env python3
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(os.environ.get("RPP_COMFYUI_ROOT", "/Users/zouge/Documents/ComfyUI"))
PYTHON = ROOT / ".venv/bin/python"
MAIN = ROOT / "main.py"
SERVER = Path(__file__).resolve().parent / "run_mac_local_server.py"
PID_FILE = ROOT / "comfyui-8188.pid"
LOG_FILE = ROOT / "comfyui-codex.log"
ERR_FILE = ROOT / "comfyui-codex.err.log"
TRANSFER_TOKEN_FILE = Path(__file__).resolve().parents[1] / ".rpp_remote_transfer_token"
REMOTE_COMPUTE_IP = "192.168.123.111"
STARTUP_ATTEMPTS = int(os.environ.get("RPP_MAC_LOCAL_STARTUP_ATTEMPTS", "3"))
STARTUP_WAIT_SECONDS = int(os.environ.get("RPP_MAC_LOCAL_STARTUP_WAIT_SECONDS", "45"))


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
    return any(str(path) in output for path in (MAIN, SERVER)) and bool(re.search(r"--port(?:=|\s+)8188(?:\s|$)", output))


def port_listening():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        return sock.connect_ex(("127.0.0.1", 8188)) == 0
    finally:
        sock.close()


def transfer_token():
    try:
        return TRANSFER_TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def remote_transfer_allowed_ips():
    addresses = {REMOTE_COMPUTE_IP}
    try:
        route = subprocess.check_output(
            ["route", "-n", "get", REMOTE_COMPUTE_IP], text=True, stderr=subprocess.DEVNULL
        )
        match = re.search(r"gateway:\s+(\d{1,3}(?:\.\d{1,3}){3})", route)
        if match:
            addresses.add(match.group(1))
    except (OSError, subprocess.CalledProcessError):
        pass
    return ",".join(sorted(addresses))


def stop_existing_service():
    """只停止已识别的本项目服务；PID 文件失效时仍检查 8188 监听者。"""
    candidates = set()
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            if pid > 0 and running(pid) and process_matches(pid):
                candidates.add(pid)
        except ValueError:
            pass
    try:
        listeners = subprocess.check_output(
            ["lsof", "-nP", "-t", "-iTCP:8188", "-sTCP:LISTEN"], text=True
        ).split()
    except subprocess.CalledProcessError as exc:
        if exc.returncode != 1:
            raise
        listeners = []
    for value in listeners:
        pid = int(value)
        if not process_matches(pid):
            raise RuntimeError(f"8188 被非本项目进程 {pid} 占用，拒绝停止。")
        candidates.add(pid)
    if port_listening() and not listeners:
        raise RuntimeError("无法识别 8188 监听进程，拒绝重启。")
    for pid in candidates:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for _ in range(60):
        if not port_listening() and not any(running(pid) for pid in candidates):
            PID_FILE.unlink(missing_ok=True)
            return
        time.sleep(0.25)
    raise RuntimeError("旧 Mac 服务未退出，未启动新进程。")


def service_environment():
    env = os.environ.copy()
    token = transfer_token()
    if not token:
        raise RuntimeError(f"缺少远端视频回传令牌：{TRANSFER_TOKEN_FILE}")
    env.update(
        {
            "RPP_REMOTE_COMFYUI_URL": os.environ.get("RPP_REMOTE_COMFYUI_URL", "http://192.168.123.111:8188"),
            "RPP_REMOTE_OUTPUT_DIR": str(ROOT / "output/4090 生成"),
            "RPP_REMOTE_LORA_DIR": os.environ.get("RPP_REMOTE_LORA_DIR", str(Path.home() / "Desktop/远程模型/loras")),
            "RPP_REMOTE_WEBSOCKET_OUTPUT": os.environ.get("RPP_REMOTE_WEBSOCKET_OUTPUT", "1"),
            "RPP_BLOCK_REMOTE_ASSET_SAVE": "1",
            "RPP_REMOTE_TRANSFER_TOKEN": token,
            "RPP_REMOTE_TRANSFER_ALLOWED_IP": os.environ.get("RPP_REMOTE_TRANSFER_ALLOWED_IP") or remote_transfer_allowed_ips(),
            "RPP_COMFYUI_ROOT": str(ROOT),
        }
    )
    return env


def main():
    env = service_environment()
    stop_existing_service()
    args = [str(PYTHON), str(SERVER), "--listen", "0.0.0.0", "--port", "8188"]
    for attempt in range(1, max(1, STARTUP_ATTEMPTS) + 1):
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
        for _ in range(max(1, STARTUP_WAIT_SECONDS * 2)):
            if process.poll() is not None:
                PID_FILE.unlink(missing_ok=True)
                break
            if port_listening():
                return 0
            time.sleep(0.5)
        if port_listening() and running(process.pid):
            return 0
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=15)
        PID_FILE.unlink(missing_ok=True)
        print(f"local aiohttp startup retry {attempt}/{STARTUP_ATTEMPTS}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    sys.exit(main())
