"""仅由 ComfyUI 节点入口加载的推理端点与队列操作。"""
import asyncio
import sys
import time
import traceback
import uuid

import execution
from aiohttp import web
from server import PromptServer

from rpp_globals import GENERATION_SUBMISSION_LOCK, NODE_DIR
from rpp_utils import _mobile_validation_error_message
from rpp_workflow import _force_websocket_only_image_outputs, _unpatched_remote_save_node_classes

async def _queue_local_guarded_workflow(workflow, client_id="", source="random_photo_prompt_mobile"):
    async with GENERATION_SUBMISSION_LOCK:
        running, pending = PromptServer.instance.prompt_queue.get_current_queue_volatile()
        if running or pending:
            return None, {
                "error": "远端已有生成任务，请等待当前任务完成后再提交。",
                "status": 409,
                "node_errors": {},
            }
        prompt_id = str(uuid.uuid4())
        PromptServer.instance.node_replace_manager.apply_replacements(workflow)
        valid = await execution.validate_prompt(prompt_id, workflow, None)
        if not valid[0]:
            return None, {
                "error": _mobile_validation_error_message(valid[1], valid[3]),
                "raw_error": valid[1],
                "node_errors": valid[3],
            }
        number = PromptServer.instance.number
        PromptServer.instance.number += 1
        extra_data = {"create_time": int(time.time() * 1000), "source": str(source or "random_photo_prompt_mobile")}
        client_id = str(client_id or "").strip()
        if client_id:
            extra_data["client_id"] = client_id
        PromptServer.instance.prompt_queue.put((number, prompt_id, workflow, extra_data, valid[2], {}))
        return {
            "prompt_id": prompt_id,
            "number": number,
            "node_errors": valid[3],
            "node_total": max(1, len(workflow)),
        }, None


def _load_image_interrogator():
    if str(NODE_DIR) not in sys.path:
        sys.path.insert(0, str(NODE_DIR))
    from image_interrogator import ImageInterrogationError, interrogate_image_bytes

    return ImageInterrogationError, interrogate_image_bytes


async def interrogate_random_photo_prompt(request):
    try:
        reader = await request.multipart()
        image_bytes = b""
        async for part in reader:
            if part.name != "image":
                continue
            image_bytes = await part.read(decode=False)
            break
        if not image_bytes:
            return web.json_response({"error": "未收到图片文件。"}, status=400)
        ImageInterrogationError, interrogate_image_bytes = _load_image_interrogator()
        try:
            result = await asyncio.to_thread(interrogate_image_bytes, image_bytes)
        except ImageInterrogationError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(result)
    except Exception:
        return web.json_response(
            {"error": traceback.format_exc()},
            status=500,
        )


async def submit_guarded_remote_workflow(request):
    try:
        data = await request.json()
        workflow = data.get("prompt")
        if not isinstance(workflow, dict) or not workflow:
            return web.json_response({"error": "缺少有效工作流。"}, status=400)
        result = _force_websocket_only_image_outputs(workflow)
        blocked = sorted(set(result["blocked"] + _unpatched_remote_save_node_classes(workflow)))
        if blocked:
            detail = ", ".join(blocked) or "unknown"
            return web.json_response(
                {"error": f"远端工作流仍包含保存节点，已阻止提交：{detail}"},
                status=400,
            )
        extra_data = data.get("extra_data") if isinstance(data.get("extra_data"), dict) else {}
        queued, error = await _queue_local_guarded_workflow(
            workflow,
            data.get("client_id", ""),
            extra_data.get("source", "random_photo_prompt_guarded_remote"),
        )
        if error:
            return web.json_response(error, status=int(error.get("status") or 400))
        return web.json_response(queued)
    except Exception:
        return web.json_response({"error": traceback.format_exc()}, status=500)


COMFY_HANDLERS = {
    "interrogate_random_photo_prompt": interrogate_random_photo_prompt,
    "submit_guarded_remote_workflow": submit_guarded_remote_workflow,
}
