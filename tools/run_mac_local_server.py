#!/usr/bin/env python3
"""前台运行 Mac 轻量服务；生产守护启动沿用原 daemon 入口。"""
import argparse
from contextlib import suppress
import json
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run_mac_local_comfyui_daemon import ROOT, service_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen", default=os.environ.get("RPP_MAC_LOCAL_LISTEN", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("RPP_MAC_LOCAL_PORT", "8188")))
    args = parser.parse_args()
    os.environ.update(service_environment())
    os.environ["RPP_MAC_LOCAL_PORT"] = str(args.port)
    # 沿用原启动器的 macOS SO_KEEPALIVE 容错，仅影响当前 Python socket。
    from aiohttp import tcp_helpers

    def tcp_keepalive(transport):
        sock = transport.get_extra_info("socket")
        if sock is not None:
            with suppress(OSError):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    tcp_helpers.tcp_keepalive = tcp_keepalive
    from aiohttp import web
    from rpp_server import create_app

    app = create_app(ROOT)
    forbidden = sorted(name for name in sys.modules if name.split(".")[0] in {"torch", "comfy", "server", "execution"})
    if forbidden:
        raise RuntimeError(f"轻量服务误加载推理模块：{forbidden}")
    print(json.dumps({"service": "rpp-aiohttp", "pid": os.getpid(), "forbidden_modules": forbidden}), flush=True)
    web.run_app(app, host=args.listen, port=args.port)


if __name__ == "__main__":
    main()
