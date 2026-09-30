"""Mac aiohttp 宿主。必须在导入业务模块之前绑定轻量目录接口。"""
import asyncio
import sys
import uuid
from pathlib import Path

from aiohttp import web

from rpp_folder_paths import LocalFolderPaths


def create_app(root):
    if "folder_paths" in sys.modules:
        raise RuntimeError("独立服务必须在全新进程启动，不能复用 ComfyUI 的 folder_paths。")
    paths = LocalFolderPaths(root)
    sys.modules["folder_paths"] = paths
    from rpp_routes import register_routes
    from rpp_globals import MOBILE_GALLERY_EXTENSIONS, MOBILE_VIDEO_EXTENSIONS
    import rpp_remote

    sockets = {}

    async def publish(client_id, payload):
        for ws in tuple(sockets.get(client_id, ())):
            try:
                send = ws.send_bytes(payload) if isinstance(payload, bytes) else ws.send_json(payload)
                await asyncio.wait_for(send, timeout=1)
            except (OSError, RuntimeError, asyncio.TimeoutError):
                sockets.get(client_id, set()).discard(ws)

    async def browser_events(request):
        client_id = request.query.get("clientId") or uuid.uuid4().hex
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        sockets.setdefault(client_id, set()).add(ws)
        try:
            await ws.send_json({"type": "status", "data": {"sid": client_id}})
            async for message in ws:
                if message.type == web.WSMsgType.ERROR:
                    break
        finally:
            sockets.get(client_id, set()).discard(ws)
            if not sockets.get(client_id):
                sockets.pop(client_id, None)
        return ws

    async def shutdown(app):
        await asyncio.gather(*(ws.close() for group in list(sockets.values()) for ws in tuple(group)))
        if rpp_remote._browser_event_callback is publish:
            rpp_remote._browser_event_callback = None

    rpp_remote._browser_event_callback = publish

    async def view_file(request):
        base = paths.get_directory_by_type(request.query.get("type", "output"))
        filename = request.query.get("filename", "")
        subfolder = request.query.get("subfolder", "").replace("\\", "/")
        if not base or not filename or "/" in filename or "\\" in filename:
            raise web.HTTPBadRequest(text="目录类型或文件名无效。")
        parts = Path(subfolder).parts + (filename,)
        if any(part.startswith(".") for part in parts):
            raise web.HTTPForbidden(text="不允许访问隐藏文件或父目录。")
        base = Path(base).resolve()
        target = (base / subfolder / filename).resolve()
        if base not in target.parents:
            raise web.HTTPForbidden(text="文件路径越界。")
        if target.suffix.lower() not in MOBILE_GALLERY_EXTENSIONS | MOBILE_VIDEO_EXTENSIONS or not target.is_file():
            raise web.HTTPNotFound(text="媒体文件不存在。")
        return web.FileResponse(target)

    app = web.Application(client_max_size=100 * 1024 * 1024)
    app.on_shutdown.append(shutdown)
    routes = web.RouteTableDef()
    register_routes(routes)
    # 保留图库已有 URL；FileResponse 同时支持视频 Range 请求。
    routes.get("/view")(view_file)
    routes.get("/ws")(browser_events)
    app.add_routes(routes)
    return app
