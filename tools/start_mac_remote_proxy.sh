#!/bin/zsh
cd /Users/zouge/Documents/Codex/2026-06-02/macbook-air-80/work/ComfyUI/custom_nodes/random_photo_prompt || exit 1

source tools/proxy_env.sh

exec /Users/zouge/Documents/Codex/2026-06-02/macbook-air-80/work/ComfyUI/.venv/bin/python tools/mac_comfyui_remote_proxy.py
