from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import socket
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import execution
import folder_paths
from aiohttp import ClientSession, ClientTimeout, TCPConnector, WSMsgType, web
from server import PromptServer

from rpp_globals import (
    BLOCK_REMOTE_ASSET_SAVE,
    GENERATION_SUBMISSION_LOCK,
    KREA2_MODEL_DIR,
    MOBILE_MAX_ACTIVE_JOBS,
    MOBILE_PROMPT_BY_FILENAME,
    MOBILE_RESULT_RECEIVE_GRACE_SECONDS,
    MOBILE_RUNTIME_IMAGES_BY_PROMPT_ID,
    MOBILE_SESSION_JOBS,
    MOBILE_SESSION_JOBS_LOADED,
    MOBILE_SESSION_JOBS_NAME,
    MOBILE_VIDEO_EXTENSIONS,
    MOBILE_VIDEO_OUTPUT_SUBFOLDER,
    MOBILE_VIDEO_PROMPT_BY_FILENAME,
    MOBILE_VIDEO_DIMENSIONS_BY_FILENAME,
    MOBILE_PREFERRED_KREA2_MODELS,
    MOBILE_PREFERRED_ZIB_MODELS,
    MOBILE_PREFERRED_ZIT_MODELS,
    MOBILE_WORKFLOWS,
    MOBILE_WORKFLOW_TEMPLATES,
    MOBILE_WORKFLOW_TEMPLATE_ERRORS,
    NODE_DIR,
    REMOTE_COMFYUI_URL,
    REMOTE_DELETE_OUTPUT,
    REMOTE_HISTORY_TIMEOUT,
    REMOTE_MAC_IMAGE_UPLOAD_URL,
    REMOTE_MAC_SOURCE_IMAGE_URL,
    REMOTE_MAC_VIDEO_UPLOAD_URL,
    REMOTE_OUTPUT_DIR,
    REMOTE_PROGRESS_BY_PROMPT_ID,
    REMOTE_TRANSFER_ALLOWED_IP,
    REMOTE_TRANSFER_TOKEN,
    REMOTE_WEBSOCKET_OUTPUT,
    REMOTE_WS_CLIENT_ID_BY_PROMPT_ID,
    REMOTE_WS_IMAGE_RECEIVED_BY_PROMPT_ID,
    REMOTE_WS_IMAGE_INDEX_BY_PROMPT_ID,
    REMOTE_WS_OUTPUT_MODE_BY_PROMPT_ID,
    REMOTE_WS_OUTPUT_NODES_BY_PROMPT_ID,
    REMOTE_WS_OUTPUT_PREFIX_BY_PROMPT_ID,
    REMOTE_WS_WATCHERS,
    ZIT_MODEL_DIR,
    ZIT_MODEL_EXTENSIONS,
    ZIMAGE_LORA_SUBDIR,
)
from rpp_utils import (
    _mobile_local_output_dir,
    _mobile_validation_error_message,
    _mobile_video_output_dir,
    _remote_transfer_source_is_allowed,
)
from rpp_workflow import (
    _available_loras,
    _force_websocket_only_image_outputs,
    _load_mobile_workflow,
    _mobile_workflow_config,
    _patch_remote_websocket_outputs,
    _unpatched_remote_save_node_classes,
)
from remote_preview_protocol import (
    decode_preview_frame,
    receive_timeout_after_execution_end,
    websocket_connect_kwargs,
)

__all__ = sorted(["__all__", "_available_krea2_models", "_available_mobile_loras", "_available_mobile_zimage_models", "_available_zib_models", "_available_zimage_models", "_available_zit_models", "_clear_remote_mobile_runtime_state", "_download_remote_image", "_download_remote_video", "_ensure_mobile_session_jobs_loaded", "_load_mobile_session_jobs", "_local_uploaded_image_path_for_remote_result", "_lora_dir_display_path", "_mac_proxy_source_image_url", "_mac_proxy_video_upload_url", "_mobile_runtime_images_for_prompt", "_mobile_session_jobs_path", "_normalize_remote_krea2_model_name", "_normalize_remote_output_subfolder", "_normalize_remote_zimage_model_name", "_queue_local_guarded_workflow", "_queue_mobile_workflow", "_queue_remote_mobile_workflow", "_remote_bytes", "_remote_delete_output_file", "_remote_history", "_remote_image_extension_from_bytes", "_remote_json", "_remote_local_path_for_image", "_remote_local_path_for_video", "_remote_queue", "_remote_websocket_image_filename", "_remote_websocket_local_path", "_resolve_krea2_model", "_resolve_zib_model", "_resolve_zit_model", "_save_mobile_session_jobs", "_save_remote_websocket_image", "_sort_krea2_models", "_sort_zib_models", "_sort_zit_models", "_split_remote_krea2_models", "_split_remote_zimage_models", "_store_remote_runtime_image", "_template_krea2_models", "_watch_remote_websocket_outputs", "receive_remote_video"])

def _available_zimage_models(prefix):
    try:
        if not ZIT_MODEL_DIR.exists():
            return []
        paths = list(ZIT_MODEL_DIR.iterdir())
    except OSError:
        return []
    prefix = str(prefix or "").lower()
    return sorted(
        path.name
        for path in paths
        if path.is_file()
        and path.suffix.lower() in ZIT_MODEL_EXTENSIONS
        and path.name.lower().startswith(prefix)
    )


def _sort_zit_models(models):
    preferred_rank = {name: index for index, name in enumerate(MOBILE_PREFERRED_ZIT_MODELS)}
    return sorted(models, key=lambda name: (preferred_rank.get(name, len(preferred_rank)), name.lower()))


def _sort_zib_models(models):
    preferred_rank = {name: index for index, name in enumerate(MOBILE_PREFERRED_ZIB_MODELS)}
    return sorted(models, key=lambda name: (preferred_rank.get(name, len(preferred_rank)), name.lower()))


def _sort_krea2_models(models):
    preferred_rank = {name: index for index, name in enumerate(MOBILE_PREFERRED_KREA2_MODELS)}
    return sorted(models, key=lambda name: (preferred_rank.get(name, len(preferred_rank)), name.lower()))


def _available_zit_models():
    models = _available_zimage_models("zit")
    return _sort_zit_models(models)


def _available_zib_models():
    return _sort_zib_models(_available_zimage_models("zib"))


def _available_krea2_models():
    try:
        if not KREA2_MODEL_DIR.exists():
            return []
        paths = list(KREA2_MODEL_DIR.iterdir())
    except OSError:
        return []
    return _sort_krea2_models(
        [
            path.name
            for path in paths
            if path.is_file() and path.suffix.lower() in ZIT_MODEL_EXTENSIONS
        ]
    )


def _normalize_remote_zimage_model_name(value):
    text = str(value or "").replace("/", "\\").strip().strip("\\")
    if not text:
        return ""
    name = Path(text.replace("\\", "/")).name
    return name if name.lower().startswith(("zit", "zib")) else ""


def _normalize_remote_krea2_model_name(value):
    text = str(value or "").replace("/", "\\").strip().strip("\\")
    if not text:
        return ""
    parts = [part for part in text.split("\\") if part]
    name = Path(text.replace("\\", "/")).name
    if any(part.lower() == "krea2" for part in parts[:-1]):
        return name
    return name if "krea2" in name.lower() else ""


def _split_remote_zimage_models(values):
    zit_models = []
    zib_models = []
    for value in values or []:
        name = _normalize_remote_zimage_model_name(value)
        lower = name.lower()
        if lower.startswith("zit") and name not in zit_models:
            zit_models.append(name)
        elif lower.startswith("zib") and name not in zib_models:
            zib_models.append(name)
    return _sort_zit_models(zit_models), _sort_zib_models(zib_models)


def _split_remote_krea2_models(values):
    models = []
    for value in values or []:
        name = _normalize_remote_krea2_model_name(value)
        if name and name not in models:
            models.append(name)
    return _sort_krea2_models(models)


def _template_krea2_models():
    try:
        template = _load_mobile_workflow("redcraft_krea2")
    except Exception:
        return []
    models = []
    for node in template.values():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict):
            continue
        name = _normalize_remote_krea2_model_name(inputs.get("unet_name"))
        if name and name not in models:
            models.append(name)
    return _sort_krea2_models(models)


async def _available_mobile_zimage_models():
    if REMOTE_COMFYUI_URL:
        object_info, error = await _remote_json("GET", "/object_info/UNETLoader")
        if error:
            raise ValueError(error["error"])
        try:
            registered_models = object_info["UNETLoader"]["input"]["required"]["unet_name"][0]
        except (KeyError, IndexError, TypeError):
            raise ValueError("远端 ComfyUI 未提供 UNETLoader 模型列表。")
        zit_models, zib_models = _split_remote_zimage_models(registered_models)
        krea2_models = _split_remote_krea2_models(registered_models)
        return {
            "source": "remote",
            "zit_models": zit_models,
            "zib_models": zib_models,
            "krea2_models": krea2_models,
        }
    try:
        registered_models = folder_paths.get_filename_list("diffusion_models")
    except Exception:
        registered_models = []
    zit_models, zib_models = _split_remote_zimage_models(registered_models)
    krea2_models = _split_remote_krea2_models(registered_models)
    return {
        "source": "local",
        "zit_models": zit_models,
        "zib_models": zib_models,
        "krea2_models": krea2_models or _template_krea2_models(),
    }


async def _available_mobile_loras():
    if not REMOTE_COMFYUI_URL:
        return _available_loras()
    for node_type in ("LoraLoaderModelOnly", "LoraLoader"):
        object_info, error = await _remote_json("GET", f"/object_info/{node_type}")
        if error:
            continue
        try:
            values = object_info[node_type]["input"]["required"]["lora_name"][0]
        except (KeyError, IndexError, TypeError):
            continue
        return sorted({str(value) for value in values if str(value).strip()})
    raise ValueError("远端 ComfyUI 未提供 LoRA 模型列表。")


def _resolve_zit_model(value=None, available_models=None):
    raw = str(value or "").replace("\\", "/").strip().strip("/")
    model_name = Path(raw).name
    available = list(available_models) if available_models is not None else _available_zit_models()
    if not model_name:
        return available[0] if available else ""
    if model_name not in available:
        raise ValueError(f"没有找到 z_image_turbo 模型：{model_name}")
    return model_name


def _resolve_zib_model(value=None, available_models=None):
    raw = str(value or "").replace("\\", "/").strip().strip("/")
    model_name = Path(raw).name
    available = list(available_models) if available_models is not None else _available_zib_models()
    if not model_name:
        return available[0] if available else ""
    if model_name not in available:
        raise ValueError(f"没有找到 ZIB 模型：{model_name}")
    return model_name


def _resolve_krea2_model(value=None, available_models=None):
    raw = str(value or "").replace("\\", "/").strip().strip("/")
    model_name = Path(raw).name
    available = list(available_models) if available_models is not None else _available_krea2_models()
    if not model_name:
        return available[0] if available else ""
    if model_name not in available:
        raise ValueError(f"没有找到 Krea2 模型：{model_name}")
    return model_name


def _lora_dir_display_path():
    if REMOTE_COMFYUI_URL:
        return f"{REMOTE_COMFYUI_URL}/object_info/LoraLoaderModelOnly"
    return str((Path(folder_paths.models_dir) / "loras" / ZIMAGE_LORA_SUBDIR).resolve())


def _normalize_remote_output_subfolder(subfolder=""):
    safe_subfolder = str(subfolder or "").replace("\\", "/").strip("/")
    if not safe_subfolder or not REMOTE_OUTPUT_DIR:
        return safe_subfolder
    output_name = _mobile_local_output_dir().name
    if safe_subfolder == output_name:
        return ""
    if safe_subfolder.startswith(f"{output_name}/"):
        return safe_subfolder[len(output_name) + 1 :]
    return safe_subfolder


def _clear_remote_mobile_runtime_state():
    _ensure_mobile_session_jobs_loaded()
    before_jobs = len(MOBILE_SESSION_JOBS)
    before_watchers = len(REMOTE_WS_WATCHERS)
    for watcher in list(REMOTE_WS_WATCHERS.values()):
        try:
            watcher.cancel()
        except Exception:
            pass
    MOBILE_SESSION_JOBS[:] = [job for job in MOBILE_SESSION_JOBS if not job.get("remote")]
    REMOTE_WS_WATCHERS.clear()
    REMOTE_WS_OUTPUT_NODES_BY_PROMPT_ID.clear()
    REMOTE_WS_OUTPUT_PREFIX_BY_PROMPT_ID.clear()
    REMOTE_WS_IMAGE_INDEX_BY_PROMPT_ID.clear()
    REMOTE_PROGRESS_BY_PROMPT_ID.clear()
    REMOTE_WS_OUTPUT_MODE_BY_PROMPT_ID.clear()
    REMOTE_WS_CLIENT_ID_BY_PROMPT_ID.clear()
    REMOTE_FINISHED_AT_BY_PROMPT_ID.clear()
    REMOTE_WS_IMAGE_RECEIVED_BY_PROMPT_ID.clear()
    MOBILE_RUNTIME_IMAGES_BY_PROMPT_ID.clear()
    _save_mobile_session_jobs()
    return {
        "jobs_removed": max(0, before_jobs - len(MOBILE_SESSION_JOBS)),
        "watchers_cancelled": before_watchers,
    }


async def receive_remote_video(request):
    """Accept a remote video only from the configured compute host and write it on this Mac."""
    try:
        if not REMOTE_TRANSFER_TOKEN or not REMOTE_TRANSFER_ALLOWED_IP:
            raise PermissionError("本机未配置远端视频回传授权。")
        source_allowed = _remote_transfer_source_is_allowed(request, REMOTE_TRANSFER_ALLOWED_IP)
        received_token = str(request.headers.get("X-RPP-Transfer-Token") or "")
        token_valid = hmac.compare_digest(received_token, REMOTE_TRANSFER_TOKEN)
        if not source_allowed:
            raise PermissionError("远端视频回传来源未授权。")
        if not token_valid:
            raise PermissionError("远端视频回传令牌无效。")
        extension = str(request.headers.get("X-RPP-Video-Extension") or ".mp4").lower()
        if extension not in MOBILE_VIDEO_EXTENSIONS:
            raise ValueError("远端视频格式不支持。")
        raw_prefix = Path(str(request.headers.get("X-RPP-Filename-Prefix") or "remote_video").replace("\\", "/")).name
        safe_prefix = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_prefix).strip("._")[:80] or "remote_video"
        target_dir = _mobile_video_output_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{safe_prefix}_{uuid.uuid4().hex[:12]}{extension}"
        target = (target_dir / filename).resolve()
        if target.parent != target_dir.resolve():
            raise ValueError("远端视频保存路径无效。")
        temporary = target.with_name(f".{target.name}.tmp")
        size = 0
        with temporary.open("wb") as file:
            while True:
                chunk = await request.content.readany()
                if not chunk:
                    break
                size += len(chunk)
                if size > 2 * 1024 * 1024 * 1024:
                    raise ValueError("远端视频文件过大。")
                file.write(chunk)
        if size <= 0:
            raise ValueError("远端视频为空。")
        temporary.replace(target)
        receipt = {
            "filename": filename,
            "subfolder": MOBILE_VIDEO_OUTPUT_SUBFOLDER,
            "type": "output",
        }
        # 回传完成即把文件与尚在轮询的任务绑定。即使远端完成事件先到，状态查询也
        # 可以通过这份收据确认视频，而不是误走图片 WebSocket 的缺失分支。
        for job in MOBILE_SESSION_JOBS:
            if str(job.get("media_type") or "") != "video":
                continue
            if str(job.get("output_prefix") or "") != safe_prefix:
                continue
            receipts = job.setdefault("received_videos", [])
            if not any(str(item.get("filename") or "") == filename for item in receipts if isinstance(item, dict)):
                receipts.append(receipt)
            prompt = str(job.get("prompt") or "")
            if prompt:
                MOBILE_VIDEO_PROMPT_BY_FILENAME[filename] = prompt
            _save_mobile_session_jobs()
            break
        return web.json_response(receipt)
    except Exception as exc:
        return web.json_response({"error": str(exc), "detail": traceback.format_exc()}, status=403 if isinstance(exc, PermissionError) else 400)


def _mac_proxy_source_image_url(filename):
    safe_name = str(filename or "").replace("\\", "/").strip("/")
    if not safe_name or any(part in {"", ".", ".."} for part in safe_name.split("/")):
        raise ValueError("视频源图文件名无效。")
    source_base_url = REMOTE_MAC_SOURCE_IMAGE_URL
    if not source_base_url:
        remote_host = urllib.parse.urlparse(REMOTE_COMFYUI_URL).hostname
        if not remote_host:
            raise ValueError("未配置远端 ComfyUI 地址，无法提供图生视频首帧。")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect((remote_host, 9))
            mac_ip = probe.getsockname()[0]
        source_base_url = f"http://{mac_ip}:8188/random_photo_prompt/remote/video/source_image"
    return f"{source_base_url}?{urllib.parse.urlencode({'filename': safe_name})}"


def _mac_proxy_video_upload_url():
    if REMOTE_MAC_VIDEO_UPLOAD_URL:
        return REMOTE_MAC_VIDEO_UPLOAD_URL
    remote_host = urllib.parse.urlparse(REMOTE_COMFYUI_URL).hostname
    if not remote_host:
        raise ValueError("未配置远端 ComfyUI 地址，无法回传视频。")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect((remote_host, 9))
        mac_ip = probe.getsockname()[0]
    return f"http://{mac_ip}:8188/random_photo_prompt/remote/video/upload"


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


async def _queue_mobile_workflow(workflow, client_id=""):
    if REMOTE_COMFYUI_URL:
        # In remote-compute mode this Mac never queues image/video inference locally.
        # The remote workflow is limited to WebSocket output so assets return to Mac memory first.
        return await _queue_remote_mobile_workflow(workflow, client_id, output_mode="phone")
    if BLOCK_REMOTE_ASSET_SAVE:
        result = _force_websocket_only_image_outputs(workflow)
        blocked = sorted(set(result["blocked"] + _unpatched_remote_save_node_classes(workflow)))
        if blocked:
            detail = ", ".join(blocked) or "unknown"
            return None, {"error": f"远端工作流仍包含保存节点，已阻止提交，避免资产保存在远端：{detail}", "node_errors": {}}
    return await _queue_local_guarded_workflow(workflow, client_id)


def _remote_compute_connector():
    """Bind remote requests to the LAN interface selected for the compute host."""
    try:
        remote_host = urllib.parse.urlparse(REMOTE_COMFYUI_URL).hostname
        if not remote_host:
            return TCPConnector()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect((remote_host, 9))
            source_ip = probe.getsockname()[0]
        return TCPConnector(local_addr=(source_ip, 0))
    except OSError:
        return TCPConnector()


async def _remote_json(method, path, **kwargs):
    url = f"{REMOTE_COMFYUI_URL}{path}"
    timeout = kwargs.pop("timeout", 30)
    request_json = kwargs.pop("json", None)
    if kwargs:
        return None, {"error": f"远端请求包含不支持的参数：{', '.join(sorted(kwargs))}"}
    last_exc = None
    for attempt in range(3):
        try:
            return await asyncio.to_thread(_remote_json_request, method, url, request_json, timeout)
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(0.35 * (attempt + 1))
    return None, {"error": f"远端 ComfyUI 连接失败：{REMOTE_COMFYUI_URL}。请检查远端是否启动、地址端口是否正确、Mac 是否能访问该地址。", "detail": str(last_exc)}


def _remote_json_request(method, url, payload, timeout):
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=str(method).upper())
    try:
        with urllib.request.urlopen(request, timeout=float(timeout)) as response:
            raw = response.read()
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = int(exc.code)
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        data = raw.decode("utf-8", "ignore")
    if status >= 400:
        return None, {"error": data.get("error") if isinstance(data, dict) else str(data), "status": status, "detail": data}
    return data, None


async def _remote_bytes(path, **kwargs):
    url = f"{REMOTE_COMFYUI_URL}{path}"
    timeout = ClientTimeout(total=kwargs.pop("timeout", 120))
    try:
        async with ClientSession(timeout=timeout, connector=_remote_compute_connector()) as session:
            async with session.get(url, **kwargs) as response:
                data = await response.read()
                if response.status >= 400:
                    return b"", {"error": data.decode("utf-8", "ignore"), "status": response.status}
                return data, None
    except Exception as exc:
        return b"", {"error": f"远端图片下载失败：{REMOTE_COMFYUI_URL}。请检查远端连接和 /view 接口。", "detail": str(exc)}


async def _remote_delete_output_file(image):
    if not REMOTE_COMFYUI_URL or not REMOTE_DELETE_OUTPUT:
        return None
    payload = {
        "filename": image.get("filename", ""),
        "subfolder": image.get("subfolder", ""),
        "type": image.get("type", "output"),
    }
    data, error = await _remote_json("POST", "/random_photo_prompt/remote/delete_output", json=payload, timeout=30)
    if error:
        return error
    return data


async def _queue_remote_mobile_workflow(workflow, client_id="", output_mode="mac"):
    output_mode = "phone" if str(output_mode or "").strip().lower() == "phone" else "mac"
    websocket_client_id = f"random_photo_prompt_mac_{uuid.uuid4().hex}"
    ws_patch = _patch_remote_websocket_outputs(workflow, output_mode=output_mode)
    unpatched_save_classes = _unpatched_remote_save_node_classes(workflow)
    if unpatched_save_classes:
        detail = ", ".join(sorted(set(unpatched_save_classes))) or "unknown"
        return None, {
            "error": f"远端工作流仍包含保存节点，已阻止提交，避免资产保存在远端：{detail}",
            "node_errors": {},
        }
    node_total = max(1, len(workflow))
    watcher = None
    prompt_ref = {"value": ""}
    # 视频经远端内存编码后直接 HTTP 回传 Mac；它没有图片帧，不能因可选的
    # WebSocket 进度监听失败而拒绝提交。只有图片工作流必须建立该连接。
    watch_remote_progress = bool(ws_patch.get("websocket_node_ids"))
    expect_image_frames = bool(ws_patch.get("websocket_node_ids"))
    if watch_remote_progress:
        ready_event = asyncio.Event()
        watcher = asyncio.create_task(
            _watch_remote_websocket_outputs(
                prompt_ref,
                websocket_client_id,
                ready_event=ready_event,
                output_nodes=ws_patch["websocket_node_ids"],
                output_prefix=ws_patch.get("output_prefix") or "",
                node_total=node_total,
                output_mode=output_mode,
                expect_image_frames=expect_image_frames,
            )
        )
        ready_waiter = asyncio.create_task(ready_event.wait())
        try:
            done, _ = await asyncio.wait(
                {watcher, ready_waiter},
                timeout=10,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if ready_waiter in done and ready_event.is_set():
                pass
            elif watcher in done:
                watcher.result()
                raise RuntimeError("远端 WebSocket 在功能协商前结束。")
            else:
                raise TimeoutError("远端未在 10 秒内完成 WebSocket 功能协商。")
        except Exception as exc:
            detail = str(exc).strip() or "远端未在 10 秒内完成 WebSocket 功能协商。"
            if watcher.done():
                try:
                    watcher.result()
                except Exception as watcher_exc:
                    detail = str(watcher_exc).strip() or detail
            watcher.cancel()
            return None, {"error": f"远端 WebSocket 回传连接失败：{detail}"}
        finally:
            if not ready_waiter.done():
                ready_waiter.cancel()
    payload = {"prompt": workflow, "client_id": websocket_client_id, "extra_data": {"source": "random_photo_prompt_mac_remote"}}
    data, error = await _remote_json("POST", "/random_photo_prompt/remote/submit", json=payload)
    if error:
        if watcher:
            watcher.cancel()
        return None, error
    if not isinstance(data, dict):
        if watcher:
            watcher.cancel()
        return None, {"error": "远端 /prompt 返回了非 JSON 对象。", "detail": data}
    prompt_id = str(data.get("prompt_id") or "")
    if prompt_id and watch_remote_progress:
        prompt_ref["value"] = prompt_id
        REMOTE_WS_OUTPUT_NODES_BY_PROMPT_ID[prompt_id] = set(ws_patch.get("websocket_node_ids") or [])
        REMOTE_WS_OUTPUT_PREFIX_BY_PROMPT_ID[prompt_id] = ws_patch.get("output_prefix") or f"mobile_{prompt_id.replace('-', '')[:12]}"
        REMOTE_WS_OUTPUT_MODE_BY_PROMPT_ID[prompt_id] = output_mode
        REMOTE_WS_CLIENT_ID_BY_PROMPT_ID[prompt_id] = websocket_client_id
        old = REMOTE_WS_WATCHERS.pop(prompt_id, None)
        if old:
            old.cancel()
        REMOTE_WS_WATCHERS[prompt_id] = watcher
    return {
        "prompt_id": prompt_id,
        "number": data.get("number"),
        "node_errors": data.get("node_errors", {}),
        "remote": True,
        "output_mode": output_mode,
        "remote_websocket_output": bool(ws_patch.get("websocket_node_ids")),
        "remote_client_id": websocket_client_id,
        "node_total": node_total if watch_remote_progress else 0,
    }, None


async def _remote_history(prompt_id):
    if not REMOTE_COMFYUI_URL or not prompt_id:
        return None, None
    data, error = await _remote_json("GET", f"/history/{urllib.parse.quote(str(prompt_id))}", timeout=REMOTE_HISTORY_TIMEOUT)
    if error or not isinstance(data, dict):
        return None, error
    return data.get(prompt_id) if prompt_id in data else data, None


async def _remote_queue():
    if not REMOTE_COMFYUI_URL:
        return [], []
    data, error = await _remote_json("GET", "/queue", timeout=15)
    if error or not isinstance(data, dict):
        return [], []
    return data.get("queue_running") or [], data.get("queue_pending") or []


def _remote_image_extension_from_bytes(image_bytes, image_type=0):
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") or image_type == 2:
        return ".png"
    if image_bytes.startswith(b"\xff\xd8\xff") or image_type == 1:
        return ".jpg"
    return ".png"


def _remote_websocket_local_path(prompt_id, image_bytes, image_type=0):
    prompt_id = str(prompt_id or "").strip()
    prefix = REMOTE_WS_OUTPUT_PREFIX_BY_PROMPT_ID.get(prompt_id) or f"mobile_{prompt_id.replace('-', '')[:12]}"
    index = REMOTE_WS_IMAGE_INDEX_BY_PROMPT_ID.get(prompt_id, 0) + 1
    REMOTE_WS_IMAGE_INDEX_BY_PROMPT_ID[prompt_id] = index
    filename = f"{prefix}_{index:05d}{_remote_image_extension_from_bytes(image_bytes, image_type)}"
    output_dir = _mobile_local_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / filename


def _remote_websocket_image_filename(prompt_id, image_bytes, image_type=0):
    prompt_id = str(prompt_id or "").strip()
    prefix = REMOTE_WS_OUTPUT_PREFIX_BY_PROMPT_ID.get(prompt_id) or f"mobile_{prompt_id.replace('-', '')[:12]}"
    index = REMOTE_WS_IMAGE_INDEX_BY_PROMPT_ID.get(prompt_id, 0) + 1
    REMOTE_WS_IMAGE_INDEX_BY_PROMPT_ID[prompt_id] = index
    return f"{prefix}_{index:05d}{_remote_image_extension_from_bytes(image_bytes, image_type)}"


def _store_remote_runtime_image(prompt_id, image_bytes, image_type=0):
    if not prompt_id or not image_bytes:
        return None
    filename = _remote_websocket_image_filename(prompt_id, image_bytes, image_type)
    content_type = "image/jpeg" if filename.lower().endswith((".jpg", ".jpeg")) else "image/png"
    prompt = ""
    for job in MOBILE_SESSION_JOBS:
        if str(job.get("prompt_id") or "") == str(prompt_id):
            prompt = str(job.get("prompt") or "")
            break
    item = {
        "filename": filename,
        "subfolder": "",
        "type": "runtime",
        "url": f"/random_photo_prompt/mobile/runtime_image/{urllib.parse.quote(str(prompt_id), safe='')}/{urllib.parse.quote(filename)}",
        "content_type": content_type,
        "bytes": bytes(image_bytes),
        "mtime": int(time.time() * 1000),
        "size": len(image_bytes),
        "prompt": prompt,
    }
    MOBILE_RUNTIME_IMAGES_BY_PROMPT_ID.setdefault(str(prompt_id), []).append(item)
    print(f"[random_photo_prompt] remote websocket runtime image stored prompt_id={prompt_id} filename={filename} bytes={len(image_bytes)}", flush=True)
    return item


def _mobile_runtime_images_for_prompt(prompt_id):
    items = MOBILE_RUNTIME_IMAGES_BY_PROMPT_ID.get(str(prompt_id or ""), [])
    result = []
    for item in items:
        result.append({key: value for key, value in item.items() if key != "bytes"})
    return result


def _save_remote_websocket_image(prompt_id, image_bytes, image_type=0):
    if not prompt_id or not image_bytes:
        return None
    local_path = _remote_websocket_local_path(prompt_id, image_bytes, image_type)
    tmp_path = local_path.with_name(f".{local_path.name}.tmp")
    tmp_path.write_bytes(image_bytes)
    if not tmp_path.is_file() or tmp_path.stat().st_size <= 0:
        raise RuntimeError("远端 WebSocket 图片临时文件未写入。")
    tmp_path.replace(local_path)
    # WebSocket 回传成功即持久化提示词，不能依赖浏览器后续轮询任务状态。
    # 否则服务重启或用户直接切到瀑布流时，图片会保留而提示词索引丢失。
    prompt = ""
    seed = None
    for job in MOBILE_SESSION_JOBS:
        if str(job.get("prompt_id") or "") == str(prompt_id):
            prompt = str(job.get("prompt") or "").strip()
            seed = job.get("seed")
            break
    if prompt:
        from rpp_mobile import _remember_mobile_prompt_file

        _remember_mobile_prompt_file(local_path.name, prompt, seed=seed)
    REMOTE_WS_IMAGE_RECEIVED_BY_PROMPT_ID[str(prompt_id)] = True
    print(f"[random_photo_prompt] remote websocket image saved prompt_id={prompt_id} path={local_path} bytes={len(image_bytes)}", flush=True)
    return local_path


async def _watch_remote_websocket_outputs(prompt_ref, client_id, ready_event=None, output_nodes=None, output_prefix="", node_total=0, output_mode="mac", expect_image_frames=True):
    if isinstance(prompt_ref, dict):
        prompt_id = str(prompt_ref.get("value") or "").strip()
    else:
        prompt_id = str(prompt_ref or "").strip()
    client_id = str(client_id or "").strip()
    if not REMOTE_COMFYUI_URL or not client_id:
        return
    remote_ws_url = REMOTE_COMFYUI_URL.replace("http://", "ws://").replace("https://", "wss://") + f"/ws?clientId={urllib.parse.quote(client_id)}"
    current_node = ""
    seen_nodes = []
    received_image_count = 0
    execution_finished_at = None
    node_total = max(1, int(node_total or 0))
    try:
        async with ClientSession(
            timeout=ClientTimeout(total=None, sock_connect=30, sock_read=None),
            connector=_remote_compute_connector(),
        ) as session:
            async with await _connect_remote_websocket(session, remote_ws_url) as ws:
                await ws.send_json({"type": "feature_flags", "data": {"supports_preview_metadata": True}})
                while True:
                    negotiation = await ws.receive()
                    if negotiation.type == WSMsgType.TEXT:
                        try:
                            negotiation_message = json.loads(negotiation.data)
                        except Exception:
                            continue
                        if negotiation_message.get("type") == "feature_flags":
                            break
                    if negotiation.type in {WSMsgType.CLOSED, WSMsgType.ERROR}:
                        raise RuntimeError("远端 WebSocket 在图片协议协商完成前断开。")
                print(f"[random_photo_prompt] remote websocket metadata protocol ready client_id={client_id}", flush=True)
                if ready_event:
                    ready_event.set()
                while True:
                    if not prompt_id and isinstance(prompt_ref, dict):
                        prompt_id = str(prompt_ref.get("value") or "").strip()
                    receive_timeout = None
                    if execution_finished_at is not None:
                        remaining = receive_timeout_after_execution_end(received_image_count) - (time.monotonic() - execution_finished_at)
                        if remaining <= 0:
                            if expect_image_frames and received_image_count == 0:
                                raise RuntimeError("远端已结束执行，但 Mac 在接收窗口内未收到图片帧。")
                            break
                        receive_timeout = remaining
                    try:
                        msg = await ws.receive(timeout=receive_timeout)
                    except asyncio.TimeoutError:
                        if expect_image_frames and received_image_count == 0:
                            raise RuntimeError("远端已结束执行，但 Mac 在接收窗口内未收到图片帧。")
                        break
                    if msg.type in {WSMsgType.CLOSED, WSMsgType.CLOSE, WSMsgType.ERROR}:
                        if expect_image_frames and execution_finished_at is not None and received_image_count == 0:
                            raise RuntimeError("远端 WebSocket 在结果图片回传前关闭。")
                        break
                    if msg.type == WSMsgType.TEXT:
                        try:
                            message = json.loads(msg.data)
                        except Exception:
                            continue
                        data = message.get("data") or {}
                        message_prompt_id = str(data.get("prompt_id") or "").strip()
                        if not prompt_id and message_prompt_id:
                            prompt_id = message_prompt_id
                            if isinstance(prompt_ref, dict):
                                prompt_ref["value"] = prompt_id
                            if output_nodes:
                                REMOTE_WS_OUTPUT_NODES_BY_PROMPT_ID[prompt_id] = set(output_nodes)
                            if output_prefix:
                                REMOTE_WS_OUTPUT_PREFIX_BY_PROMPT_ID[prompt_id] = output_prefix
                            REMOTE_WS_OUTPUT_MODE_BY_PROMPT_ID[prompt_id] = "phone" if str(output_mode or "").strip().lower() == "phone" else "mac"
                        message_type = message.get("type")
                        if message_type == "progress":
                            if message_prompt_id and prompt_id and message_prompt_id != prompt_id:
                                continue
                            try:
                                value = max(0, int(data.get("value") or 0))
                                maximum = max(1, int(data.get("max") or 1))
                            except (TypeError, ValueError):
                                continue
                            if prompt_id:
                                REMOTE_PROGRESS_BY_PROMPT_ID[prompt_id] = {
                                    "value": min(value, maximum),
                                    "max": maximum,
                                    "percent": max(0, min(100, round((value / maximum) * 100))),
                                    "node": str(data.get("node") or current_node),
                                    "type": "step",
                                }
                            continue
                        if message_type != "executing":
                            continue
                        if message_prompt_id and prompt_id and message_prompt_id != prompt_id:
                            continue
                        current_node = str(data.get("node") or "")
                        print(
                            "[random_photo_prompt] remote progress event "
                            f"prompt_id={prompt_id or message_prompt_id or '-'} "
                            f"node={current_node or '<done>'} "
                            f"total={node_total}",
                            flush=True,
                        )
                        if not current_node:
                            if prompt_id:
                                REMOTE_PROGRESS_BY_PROMPT_ID[prompt_id] = {
                                    "value": node_total,
                                    "max": node_total,
                                    "percent": 100,
                                    "node": "",
                                    "type": "node",
                                }
                            execution_finished_at = time.monotonic()
                            print(
                                f"[random_photo_prompt] remote execution ended; waiting for result frame prompt_id={prompt_id}",
                                flush=True,
                            )
                            if not expect_image_frames:
                                break
                            continue
                        if current_node not in seen_nodes:
                            seen_nodes.append(current_node)
                        if prompt_id:
                            value = max(1, min(node_total, len(seen_nodes)))
                            REMOTE_PROGRESS_BY_PROMPT_ID[prompt_id] = {
                                "value": value,
                                "max": node_total,
                                "percent": max(0, min(100, round((value / node_total) * 100))),
                                "node": current_node,
                                "type": "node",
                            }
                            print(
                                "[random_photo_prompt] remote progress stored "
                                f"prompt_id={prompt_id} value={value}/{node_total}",
                                flush=True,
                            )
                    elif msg.type == WSMsgType.BINARY:
                        if not expect_image_frames:
                            continue
                        output_nodes = REMOTE_WS_OUTPUT_NODES_BY_PROMPT_ID.get(prompt_id) or set()
                        frame = decode_preview_frame(msg.data)
                        if frame is None:
                            continue
                        if frame["prompt_id"] and prompt_id and frame["prompt_id"] != prompt_id:
                            continue
                        if output_nodes and frame["node_id"] not in output_nodes:
                            continue
                        _save_remote_websocket_image(prompt_id, frame["image_bytes"], frame["image_type"])
                        received_image_count += 1
    except asyncio.CancelledError:
        raise
    except Exception:
        traceback.print_exc()
        # The submitter must receive a failed pre-queue handshake immediately.
        # Swallowing this exception leaves the phone page waiting for a task
        # which was never accepted by the remote ComfyUI queue.
        raise


async def _connect_remote_websocket(session, remote_ws_url):
    last_error = None
    for attempt in range(3):
        try:
            return await session.ws_connect(remote_ws_url, **websocket_connect_kwargs())
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                await asyncio.sleep(0.4 * (attempt + 1))
    raise last_error


def _remote_local_path_for_image(image):
    filename = Path(str(image.get("filename") or "")).name
    if not filename:
        raise ValueError("远端图片缺少文件名。")
    subfolder = _normalize_remote_output_subfolder(image.get("subfolder", ""))
    output_dir = _mobile_local_output_dir()
    target_dir = (output_dir / subfolder).resolve() if subfolder else output_dir
    if output_dir != target_dir and output_dir not in target_dir.parents:
        raise ValueError("远端图片子目录不安全。")
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / filename


def _local_uploaded_image_path_for_remote_result(image):
    filename = Path(str((image or {}).get("filename") or "")).name
    if not filename:
        return None
    output_dir = _mobile_local_output_dir()
    candidates = []
    subfolder = _normalize_remote_output_subfolder((image or {}).get("subfolder", ""))
    if subfolder:
        candidates.append((output_dir / subfolder / filename).resolve())
    candidates.append((output_dir / filename).resolve())
    for path in candidates:
        if path.is_file() and path.stat().st_size > 0 and (path == output_dir or output_dir in path.parents):
            return path
    matches = []
    try:
        matches = [path for path in output_dir.rglob(filename) if path.is_file() and path.stat().st_size > 0]
    except Exception:
        matches = []
    for path in matches:
        resolved = path.resolve()
        if resolved == output_dir or output_dir in resolved.parents:
            return resolved
    return None


async def _download_remote_image(image):
    uploaded_path = _local_uploaded_image_path_for_remote_result(image)
    if uploaded_path:
        return uploaded_path
    local_path = _remote_local_path_for_image(image)
    if local_path.is_file() and local_path.stat().st_size > 0:
        await _remote_delete_output_file(image)
        return local_path
    params = urllib.parse.urlencode(
        {
            "filename": image.get("filename", ""),
            "subfolder": image.get("subfolder", ""),
            "type": image.get("type", "output"),
        }
    )
    data, error = await _remote_bytes(f"/view?{params}")
    if error:
        raise RuntimeError(error.get("error") or "下载远端图片失败。")
    if not data:
        raise RuntimeError("下载远端图片失败：远端返回空文件。")
    tmp_path = local_path.with_name(f".{local_path.name}.tmp")
    tmp_path.write_bytes(data)
    if not tmp_path.is_file() or tmp_path.stat().st_size <= 0:
        raise RuntimeError("下载远端图片失败：本地临时文件未写入。")
    tmp_path.replace(local_path)
    if local_path.is_file() and local_path.stat().st_size > 0:
        await _remote_delete_output_file(image)
    return local_path


def _remote_local_path_for_video(video):
    filename = Path(str(video.get("filename") or "")).name
    if not filename:
        raise ValueError("远端视频缺少文件名。")
    if Path(filename).suffix.lower() not in MOBILE_VIDEO_EXTENSIONS:
        raise ValueError("远端视频格式不支持。")
    local_path = (_mobile_video_output_dir() / filename).resolve()
    if local_path.parent != _mobile_video_output_dir():
        raise ValueError("远端视频本地路径不安全。")
    return local_path


async def _download_remote_video(video):
    local_path = _remote_local_path_for_video(video)
    if local_path.is_file() and local_path.stat().st_size > 0:
        await _remote_delete_output_file(video)
        return local_path
    params = urllib.parse.urlencode(
        {
            "filename": video.get("filename", ""),
            "subfolder": video.get("subfolder", ""),
            "type": video.get("type", "output"),
        }
    )
    data, error = await _remote_bytes(f"/view?{params}", timeout=300)
    if error:
        raise RuntimeError(error.get("error") or "下载远端视频失败。")
    if not data:
        raise RuntimeError("下载远端视频失败：远端返回空文件。")
    tmp_path = local_path.with_name(f".{local_path.name}.tmp")
    tmp_path.write_bytes(data)
    if not tmp_path.is_file() or tmp_path.stat().st_size <= 0:
        raise RuntimeError("下载远端视频失败：本地临时文件未写入。")
    tmp_path.replace(local_path)
    if local_path.is_file() and local_path.stat().st_size > 0:
        await _remote_delete_output_file(video)
    return local_path



def _mobile_session_jobs_path():
    return _mobile_local_output_dir() / MOBILE_SESSION_JOBS_NAME


def _load_mobile_session_jobs():
    path = _mobile_session_jobs_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    jobs = data.get("jobs", data) if isinstance(data, dict) else data
    if not isinstance(jobs, list):
        return []
    return [job for job in jobs if isinstance(job, dict) and job.get("prompt_id")]


def _save_mobile_session_jobs():
    path = _mobile_session_jobs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    deduped = {}
    for job in MOBILE_SESSION_JOBS[-MOBILE_MAX_ACTIVE_JOBS:]:
        prompt_id = str(job.get("prompt_id") or "")
        if prompt_id:
            deduped[prompt_id] = job
    payload = {
        "version": 1,
        "updated_at": int(time.time() * 1000),
        "jobs": list(deduped.values()),
    }
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _ensure_mobile_session_jobs_loaded():
    global MOBILE_SESSION_JOBS_LOADED
    if MOBILE_SESSION_JOBS_LOADED:
        return
    MOBILE_SESSION_JOBS.extend(_load_mobile_session_jobs())
    MOBILE_SESSION_JOBS_LOADED = True
