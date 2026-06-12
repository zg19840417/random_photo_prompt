#!/bin/zsh
cd /Users/zouge/Documents/Codex/2026-06-02/macbook-air-80/work/ComfyUI/custom_nodes/random_photo_prompt || exit 1

: "${RPP_PROXY_REMOTE_URL:=http://192.168.123.111:8188}"
: "${RPP_PROXY_LOCAL_MOBILE_URL:=http://127.0.0.1:8188}"
: "${RPP_PROXY_OUTPUT_DIR:=/Users/zouge/Documents/Codex/2026-06-02/macbook-air-80/work/ComfyUI/output/4090 生成}"
: "${RPP_PROXY_PORT:=18199}"
: "${RPP_PROXY_DELETE_REMOTE_OUTPUT:=1}"
: "${RPP_PROXY_WEBSOCKET_OUTPUT:=1}"
export RPP_PROXY_REMOTE_URL RPP_PROXY_LOCAL_MOBILE_URL RPP_PROXY_OUTPUT_DIR RPP_PROXY_PORT RPP_PROXY_DELETE_REMOTE_OUTPUT RPP_PROXY_WEBSOCKET_OUTPUT

exec /Users/zouge/Documents/Codex/2026-06-02/macbook-air-80/work/ComfyUI/.venv/bin/python tools/mac_comfyui_remote_proxy.py
