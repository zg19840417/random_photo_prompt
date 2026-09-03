#!/usr/bin/env python3
import os
from pathlib import Path


ROOT = Path(os.environ.get("RPP_COMFYUI_ROOT", "/Users/zouge/Documents/Codex/2026-06-02/macbook-air-80/work/ComfyUI"))
PROJECT = ROOT / "custom_nodes/random_photo_prompt"
PYTHON = ROOT / ".venv/bin/python"
PROXY = PROJECT / "tools/mac_comfyui_remote_proxy.py"
PID_FILE = ROOT / "comfyui-proxy.pid"
LOG_FILE = ROOT / "comfyui-proxy.log"
ERR_FILE = ROOT / "comfyui-proxy.err.log"

REMOTE_URL = os.environ.get("RPP_PROXY_REMOTE_URL", "http://192.168.123.111:8188").rstrip("/")
LOCAL_MOBILE_URL = os.environ.get("RPP_PROXY_LOCAL_MOBILE_URL", "http://127.0.0.1:8188").rstrip("/")
OUTPUT_DIR = Path(os.environ.get("RPP_PROXY_OUTPUT_DIR", str(ROOT / "output/4090 生成"))).expanduser()
PROXY_PORT = os.environ.get("RPP_PROXY_PORT", "18199")
DELETE_REMOTE_OUTPUT = os.environ.get("RPP_PROXY_DELETE_REMOTE_OUTPUT", "1")
WEBSOCKET_OUTPUT = os.environ.get("RPP_PROXY_WEBSOCKET_OUTPUT", "1")
POLL_SECONDS = os.environ.get("RPP_PROXY_POLL_SECONDS", "1.5")
HISTORY_TIMEOUT = os.environ.get("RPP_PROXY_HISTORY_TIMEOUT", "900")


def proxy_env():
    env = os.environ.copy()
    env.update(
        {
            "RPP_PROXY_REMOTE_URL": REMOTE_URL,
            "RPP_PROXY_LOCAL_MOBILE_URL": LOCAL_MOBILE_URL,
            "RPP_PROXY_OUTPUT_DIR": str(OUTPUT_DIR),
            "RPP_PROXY_PORT": str(PROXY_PORT),
            "RPP_PROXY_DELETE_REMOTE_OUTPUT": str(DELETE_REMOTE_OUTPUT),
            "RPP_PROXY_WEBSOCKET_OUTPUT": str(WEBSOCKET_OUTPUT),
            "RPP_PROXY_POLL_SECONDS": str(POLL_SECONDS),
            "RPP_PROXY_HISTORY_TIMEOUT": str(HISTORY_TIMEOUT),
        }
    )
    return env
