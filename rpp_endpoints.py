from __future__ import annotations

import asyncio
import hmac
import os
import shutil
import subprocess
import time
import traceback
import urllib.parse
import uuid
from pathlib import Path

import folder_paths
from aiohttp import web
from PIL import Image

from rpp_globals import (
    K2_SFW_RULE_KEY,
    MOBILE_DEFAULT_WORKFLOW_KEY,
    MOBILE_ENTRY_URL,
    MOBILE_FAVORITE_BACKUP_DIR,
    MOBILE_GALLERY_EXTENSIONS,
    MOBILE_MAX_ACTIVE_JOBS,
    MOBILE_PAGE_HTML,
    NODE_DIR,
    MANUAL_PAGE_HTML,
    MOBILE_PROMPT_BY_FILENAME,
    MOBILE_RUNTIME_IMAGES_BY_PROMPT_ID,
    MOBILE_SESSION_JOBS,
    MOBILE_VIDEO_EXTENSIONS,
    MOBILE_VIDEO_FAVORITE_BACKUP_DIR,
    MOBILE_VIDEO_INPUT_SUBFOLDER,
    MOBILE_WORKFLOWS,
    MOBILE_VIDEO_WORKFLOW_KEY,
    QVIEW_APP_PATH,
    REMOTE_COMFYUI_URL,
    REMOTE_MAC_SOURCE_IMAGE_URL,
    REMOTE_TRANSFER_ALLOWED_IP,
    REMOTE_TRANSFER_TOKEN,
    ZIT_MODEL_DIR,
)
from rpp_utils import (
    _prompt_signature,
    _remote_transfer_source_is_allowed,
)
from rpp_prompts import (
    _apply_krea2_prompt_item_orientation_guard,
    _build_desktop_prompt_with_mobile_logic,
    _build_mobile_prompt_for_scope,
    _custom_mobile_prompt_item,
    _display_prompt_text,
    _enforce_mobile_ancient_barefoot_text,
    _mobile_custom_resolution,
    _mobile_resolution_for_custom_prompt,
    _mobile_shot_config,
    _normalize_mobile_prompt_rule,
    _prompt_text,
    _use_chinese_negative_prompt,
)
from rpp_workflow import (
    _force_websocket_only_image_outputs,
    _is_krea2_workflow,
    _load_mobile_workflow,
    _mobile_image_workflows,
    _mobile_workflow_config,
    _mobile_workflow_statuses,
    _patch_mobile_video_workflow,
    _patch_mobile_workflow,
    _resolve_mobile_loras,
    _unpatched_remote_save_node_classes,
    _workflow_status_item,
)
from rpp_remote import (
    _available_mobile_loras,
    _available_mobile_zimage_models,
    _clear_remote_mobile_runtime_state,
    _lora_dir_display_path,
    _mac_proxy_source_image_url,
    _mac_proxy_video_upload_url,
    _queue_local_guarded_workflow,
    _queue_mobile_workflow,
    _resolve_krea2_model,
    _resolve_zib_model,
    _resolve_zit_model,
)
from rpp_mobile import (
    _active_mobile_session_jobs,
    _infer_frame_scope_from_prompt,
    _load_image_interrogator,
    _load_mobile_favorite_metadata,
    _load_mobile_prompt_index,
    _mobile_active_job_count,
    _mobile_favorite_backup_file,
    _mobile_favorite_backup_images,
    _mobile_gallery_images,
    _mobile_gallery_videos,
    _mobile_job_status,
    _mobile_local_output_dir,
    _mobile_output_file_from_item,
    _mobile_output_file_key,
    _mobile_output_subfolder_for_path,
    _mobile_prompt_for_gallery_file,
    _mobile_prompt_metadata_for_gallery_file,
    _load_mobile_viewed_keys,
    _mark_mobile_viewed_keys,
    _mobile_video_input_dir,
    _mobile_video_output_file,
    _mobile_video_source_path,
    _pregenerate_video_action_for_image,
    _qview_image_path,
    _request_from_local_mac_browser,
    _save_mobile_favorite_metadata,
    _save_mobile_prompt_index,
    _save_mobile_session_jobs,
    _video_prompt_from_action,
)
from video_prompt_engine import normalize_video_seconds

__all__ = sorted(["__all__", "_local_status_html", "_local_status_item", "_mobile_entry_status", "backup_mobile_favorite_image", "backup_mobile_favorite_video", "clear_remote_mobile_runtime_state", "delete_mobile_favorite_images", "delete_mobile_gallery_images", "delete_mobile_gallery_videos", "delete_remote_output_file", "generate_mobile_image", "generate_mobile_video", "generate_random_photo_prompt", "interrogate_random_photo_prompt", "local_status_page", "manual_generation_page", "mobile_favorite_image_file", "mobile_favorite_images", "mobile_gallery_images", "mobile_gallery_videos", "mobile_generation_page", "mobile_generation_status", "mobile_job_detail", "mobile_remote_video_source_image", "mobile_root_redirect", "mobile_runtime_image", "mobile_session_jobs", "mark_mobile_viewed_images", "open_mobile_gallery_image_in_qview", "pregenerate_mobile_image_prompt", "pregenerate_mobile_video_action", "resolve_random_photo_prompt_resolution", "submit_guarded_remote_workflow", "upload_mobile_video_source"])

async def upload_mobile_video_source(request):
    try:
        reader = await request.multipart()
        field = await reader.next()
        if field is None or field.name != "image":
            raise ValueError("没有收到图片文件。")
        original_name = Path(str(field.filename or "source.png").replace("\\", "/")).name
        suffix = Path(original_name).suffix.lower()
        if suffix not in MOBILE_GALLERY_EXTENSIONS:
            suffix = ".png"
        safe_name = f"upload_video_src_{uuid.uuid4().hex[:12]}{suffix}"
        target = (_mobile_video_input_dir() / safe_name).resolve()
        if target.parent != _mobile_video_input_dir():
            raise ValueError("视频输入文件路径无效。")
        size = 0
        with target.open("wb") as file:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                size += len(chunk)
                if size > 50 * 1024 * 1024:
                    raise ValueError("图片文件太大。")
                file.write(chunk)
        if size <= 0:
            raise ValueError("图片文件为空。")
        try:
            with Image.open(target) as image:
                image.verify()
        except Exception:
            target.unlink(missing_ok=True)
            raise ValueError("上传的文件不是可用图片。")
        width = height = 0
        try:
            with Image.open(target) as image:
                width, height = image.size
        except Exception:
            pass
        return web.json_response(
            {
                "filename": safe_name,
                "source_filename": f"{MOBILE_VIDEO_INPUT_SUBFOLDER}/{safe_name}",
                "url": _mac_proxy_source_image_url(f"{MOBILE_VIDEO_INPUT_SUBFOLDER}/{safe_name}") if REMOTE_MAC_SOURCE_IMAGE_URL else f"/view?{urllib.parse.urlencode({'filename': safe_name, 'subfolder': MOBILE_VIDEO_INPUT_SUBFOLDER, 'type': 'input'})}",
                "width": width,
                "height": height,
            }
        )
    except Exception as exc:
        return web.json_response({"error": str(exc), "detail": traceback.format_exc()}, status=400)


async def mobile_remote_video_source_image(request):
    """Serve one Mac-local video source image directly to the authorized remote compute host."""
    try:
        if not REMOTE_TRANSFER_TOKEN or not REMOTE_TRANSFER_ALLOWED_IP:
            raise PermissionError("本机未配置远端视频源图授权。")
        if not _remote_transfer_source_is_allowed(request, REMOTE_TRANSFER_ALLOWED_IP):
            raise PermissionError("远端视频源图请求来源未授权。")
        received_token = str(request.headers.get("X-RPP-Transfer-Token") or "")
        if not hmac.compare_digest(received_token, REMOTE_TRANSFER_TOKEN):
            raise PermissionError("远端视频源图令牌无效。")
        raw_name = str(request.query.get("filename") or "").replace("\\", "/").strip("/")
        prefix = f"{MOBILE_VIDEO_INPUT_SUBFOLDER}/"
        if not raw_name.startswith(prefix):
            raise ValueError("视频源图必须位于本机视频输入目录。")
        safe_name = Path(raw_name).name
        source = (_mobile_video_input_dir() / safe_name).resolve()
        if source.parent != _mobile_video_input_dir() or not source.is_file() or source.suffix.lower() not in MOBILE_GALLERY_EXTENSIONS:
            raise ValueError("没有找到可用的视频源图。")
        return web.FileResponse(source)
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=403 if isinstance(exc, PermissionError) else 400)


async def generate_random_photo_prompt(request):
    try:
        data = await request.json()
        scale = data.get("scale", "澶ц儐")
        shot = data.get("shot", "榛樿")
        era = data.get("era", "modern")
        seed_text = data.get("seed", "")
        prompt_item, resolution = _build_desktop_prompt_with_mobile_logic(scale, shot, seed_text, era)
        prompt = _prompt_text(prompt_item)
        width = int(resolution["width"])
        height = int(resolution["height"])
        normalized_aspect = resolution["aspect"]
        return web.json_response(
            {
                "prompt": prompt,
                "negative_prompt": prompt_item.get("negative_prompt", ""),
                "signature": _prompt_signature(scale, shot, normalized_aspect, era),
                "aspect": normalized_aspect,
                "width": width,
                "height": height,
            }
        )
    except Exception:
        return web.json_response(
            {"error": traceback.format_exc()},
            status=500,
        )


async def resolve_random_photo_prompt_resolution(request):
    try:
        data = await request.json()
        prompt = str(data.get("prompt") or "")
        shot = _mobile_shot_config(data.get("shot") or _infer_frame_scope_from_prompt(prompt) or "全身")["shot"]
        resolution = _mobile_resolution_for_custom_prompt(prompt)
        return web.json_response(
            {
                "shot": shot,
                "aspect": resolution.get("aspect"),
                "width": int(resolution.get("width") or 0),
                "height": int(resolution.get("height") or 0),
            }
        )
    except Exception:
        return web.json_response(
            {"error": traceback.format_exc()},
            status=500,
        )


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


async def pregenerate_mobile_image_prompt(request):
    try:
        data = await request.json()
        scale = data.get("scale", "bold")
        era = data.get("era", "modern")
        prompt_rule = _normalize_mobile_prompt_rule(data.get("prompt_rule"))
        shot_config = _mobile_shot_config(data.get("shot", "full_body_portrait"))
        seed_text = str(data.get("seed") or f"{time.time()}-{uuid.uuid4()}")
        prompt_item, resolution = _build_mobile_prompt_for_scope(scale, shot_config, seed_text, era, prompt_rule)
        width = int(resolution["width"])
        height = int(resolution["height"])
        workflow_key = str(data.get("workflow") or "")
        if _is_krea2_workflow(workflow_key) and prompt_rule != K2_SFW_RULE_KEY:
            prompt_item = _apply_krea2_prompt_item_orientation_guard(prompt_item, width, height)
        return web.json_response(
            {
                "prompt": _prompt_text(prompt_item),
                "display_prompt": _display_prompt_text(prompt_item),
                "negative_prompt": prompt_item.get("negative_prompt", ""),
                "scale": prompt_item.get("scale", scale),
                "prompt_rule": prompt_rule,
                "shot": prompt_item.get("shot_key", shot_config["shot"]),
                "era": prompt_item.get("era", "") if prompt_rule == K2_SFW_RULE_KEY else prompt_item.get("era", era),
                "aspect": resolution.get("aspect", "portrait"),
                "width": width,
                "height": height,
                "resolution": f"{width}x{height}",
                "seed": prompt_item.get("seed", ""),
            }
        )
    except Exception as exc:
        return web.json_response({"error": str(exc), "detail": traceback.format_exc()}, status=400)


async def mobile_generation_page(request):
    mobile_entry_url = MOBILE_ENTRY_URL
    if not mobile_entry_url:
        try:
            mobile_entry_url = (NODE_DIR / "mobile_entry_url.txt").read_text(encoding="utf-8").strip().rstrip("/")
        except OSError:
            mobile_entry_url = ""
    if mobile_entry_url:
        raise web.HTTPFound(f"{mobile_entry_url}{request.rel_url.path_qs}")
    return web.Response(
        text=MOBILE_PAGE_HTML,
        content_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


async def manual_generation_page(request):
    return web.Response(text=MANUAL_PAGE_HTML, content_type="text/html")


async def mobile_root_redirect(request):
    raise web.HTTPFound("/random_photo_prompt/mobile")


async def _mobile_entry_status():
    remote_compute = bool(REMOTE_COMFYUI_URL)
    output_dir = _mobile_local_output_dir()
    workflow_statuses = _mobile_workflow_statuses()
    image_workflows_ready = all(item["template_ready"] for item in workflow_statuses.values() if item["type"] == "image")
    video_workflow_ready = workflow_statuses.get(MOBILE_VIDEO_WORKFLOW_KEY, {}).get("template_ready", False)
    zimage_models = await _available_mobile_zimage_models()
    zit_models = zimage_models["zit_models"]
    zib_models = zimage_models["zib_models"]
    krea2_models = zimage_models["krea2_models"]
    loras = await _available_mobile_loras()
    return {
        "entry_mode": "remote_compute" if remote_compute else "local",
        "entry_label": "Mac 本地资产，远端计算" if remote_compute else "Mac 本机计算",
        "remote_compute": remote_compute,
        "output": {
            "dir": str(output_dir),
            "exists": output_dir.exists(),
            "writable": os.access(output_dir, os.W_OK),
        },
        "models": {
            "source": zimage_models["source"],
            "zit_dir": f"{REMOTE_COMFYUI_URL}/object_info/UNETLoader" if remote_compute else str(ZIT_MODEL_DIR),
            "zit_dir_ready": bool(zit_models) if remote_compute else ZIT_MODEL_DIR.exists(),
            "zit_count": len(zit_models),
            "zib_count": len(zib_models),
            "krea2_count": len(krea2_models),
            "lora_dir": _lora_dir_display_path(),
            "lora_count": len(loras),
        },
        "workflow_statuses": workflow_statuses,
        "health": {
            "local_mobile": {
                "ok": True,
                "message": "Mac 手机页接口正常，生成请求仅发送至远端计算。" if remote_compute else "Mac 手机页接口正常。",
            },
            "output_dir": {
                "ok": output_dir.exists() and os.access(output_dir, os.W_OK),
                "message": str(output_dir),
            },
            "image_workflows": {
                "ok": image_workflows_ready,
                "message": "图片工作流模板已准备。" if image_workflows_ready else "至少一个图片工作流模板缺失或格式不对。",
            },
            "video_workflow": {
                "ok": video_workflow_ready,
                "message": "视频工作流模板已准备。" if video_workflow_ready else "视频工作流模板缺失或格式不对。",
            },
            "zit_models": {
                "ok": bool(zit_models),
                "message": f"找到 {len(zit_models)} 个 ZIT 模型（{zimage_models['source']}）。" if zit_models else f"未找到可用 ZIT 模型。",
            },
        },
    }


def _local_status_item(ok, label, message):
    class_name = "ok" if ok else "bad"
    state = "正常" if ok else "需要处理"
    return f'<li class="{class_name}"><strong>{html.escape(label)}</strong><span>{state}</span><p>{html.escape(str(message or ""))}</p></li>'


def _local_status_html(payload):
    health = payload["health"]
    workflows = payload["workflow_statuses"]
    all_ok = health["output_dir"]["ok"] and health["image_workflows"]["ok"] and health["zit_models"]["ok"]
    title = "手机端内部服务正常" if all_ok else "手机端内部服务需要处理"
    workflow_items = "".join(
        _local_status_item(
            item["template_ready"],
            f"{item['label']} · {item['template_name']}",
            item["message"] if item["template_ready"] else f"{item['message']} {item['guidance']} 路径：{item['path']}",
        )
        for item in workflows.values()
    )
    items = [
        _local_status_item(health["local_mobile"]["ok"], "手机端内部服务", health["local_mobile"]["message"]),
        _local_status_item(health["output_dir"]["ok"], "输出目录", health["output_dir"]["message"]),
        _local_status_item(health["zit_models"]["ok"], "ZIT 模型", health["zit_models"]["message"]),
        _local_status_item(True, "ZIB / Krea2 / LoRA", f"ZIB {payload['models']['zib_count']} 个，Krea2 {payload['models']['krea2_count']} 个，LoRA {payload['models']['lora_count']} 个。"),
        _local_status_item(True, "手机入口", "手机和 Mac 直接使用本机 ComfyUI 8188 手机页。"),
    ]
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #101114; color: #f5f5f0; }}
    main {{ max-width: 820px; margin: 0 auto; padding: 28px 18px 42px; }}
    h1 {{ font-size: 26px; margin: 0 0 10px; letter-spacing: 0; }}
    h2 {{ font-size: 17px; margin: 24px 0 10px; }}
    .lead {{ color: #b9b8ad; margin: 0 0 18px; line-height: 1.6; }}
    .entry {{ display: block; padding: 14px 16px; border: 1px solid #3f4743; color: #f5f5f0; text-decoration: none; background: #1b1d20; margin: 18px 0; }}
    ul {{ list-style: none; padding: 0; margin: 12px 0; display: grid; gap: 10px; }}
    li {{ border: 1px solid #373a3d; background: #17191c; padding: 14px; }}
    li strong {{ display: block; font-size: 16px; margin-bottom: 6px; }}
    li span {{ display: inline-block; font-size: 13px; margin-bottom: 8px; }}
    li.ok span {{ color: #7bd88f; }}
    li.bad span {{ color: #ff8a7a; }}
    li p {{ margin: 0; color: #c9c8be; word-break: break-all; line-height: 1.5; }}
    code {{ color: #f2d179; }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <p class="lead">本页检查 Mac 本地手机端、工作流与本地输出目录。</p>
    <a class="entry" href="/random_photo_prompt/mobile">打开手机生成页</a>
    <h2>入口状态</h2>
    <ul>{''.join(items)}</ul>
    <h2>工作流模板</h2>
    <ul>{workflow_items}</ul>
    <p class="lead">JSON 状态：<code>/random_photo_prompt/local/status?format=json</code></p>
  </main>
</body>
</html>"""


async def local_status_page(request):
    payload = await _mobile_entry_status()
    if request.query.get("format") == "json" or "application/json" in request.headers.get("Accept", ""):
        return web.json_response(payload)
    return web.Response(text=_local_status_html(payload), content_type="text/html")


async def mobile_generation_status(request):
    workflow_key, config = _mobile_workflow_config(request.query.get("workflow"))
    workflow_path = config["path"]
    entry_status = await _mobile_entry_status()
    workflow_statuses = entry_status["workflow_statuses"]
    selected_workflow_status = workflow_statuses.get(workflow_key) or _workflow_status_item(workflow_key, config)
    template_ready = selected_workflow_status["template_ready"]
    video_config = MOBILE_WORKFLOWS[MOBILE_VIDEO_WORKFLOW_KEY]
    image_workflows = _mobile_image_workflows()
    zimage_models = await _available_mobile_zimage_models()
    zit_models = zimage_models["zit_models"]
    zib_models = zimage_models["zib_models"]
    krea2_models = zimage_models["krea2_models"]
    loras = await _available_mobile_loras()
    return web.json_response(
        {
            "template_ready": template_ready,
            "template_name": workflow_path.name,
            "workflow": workflow_key,
            "workflow_label": config["label"],
            "workflows": [
                {
                    "key": key,
                    "label": item["label"],
                    "template_name": item["path"].name,
                    "template_ready": workflow_statuses.get(key, {}).get("template_ready", item["path"].exists()),
                    "path": str(item["path"]),
                    "message": workflow_statuses.get(key, {}).get("message", ""),
                    "guidance": workflow_statuses.get(key, {}).get("guidance", ""),
                }
                for key, item in image_workflows.items()
            ],
            "video_workflow": {
                "key": MOBILE_VIDEO_WORKFLOW_KEY,
                "label": video_config["label"],
                "template_name": video_config["path"].name,
                "template_ready": workflow_statuses.get(MOBILE_VIDEO_WORKFLOW_KEY, {}).get("template_ready", video_config["path"].exists()),
                "path": str(video_config["path"]),
                "message": workflow_statuses.get(MOBILE_VIDEO_WORKFLOW_KEY, {}).get("message", ""),
                "guidance": workflow_statuses.get(MOBILE_VIDEO_WORKFLOW_KEY, {}).get("guidance", ""),
            },
            "zit_models": zit_models,
            "zib_models": zib_models,
            "krea2_models": krea2_models,
            "model_source": zimage_models["source"],
            "zit_model_dir_ready": bool(zit_models) if REMOTE_COMFYUI_URL else ZIT_MODEL_DIR.exists(),
            "loras": loras,
            "lora_dir": _lora_dir_display_path(),
            "connected": True,
            "qview_available": _request_from_local_mac_browser(request),
            "message": "" if template_ready else (selected_workflow_status.get("message") or f"请先保存 {workflow_path.name} 后再生成。"),
            "guidance": selected_workflow_status.get("guidance", ""),
            "template_path": str(workflow_path),
            **entry_status,
        }
    )


async def open_mobile_gallery_image_in_qview(request):
    if not _request_from_local_mac_browser(request):
        return web.json_response({"error": "仅允许在 Mac 本机网页中使用 qView。"}, status=403)
    try:
        data = await request.json()
        image = data.get("image") if isinstance(data, dict) else None
        if not isinstance(image, dict):
            return web.json_response({"error": "缺少图片信息。"}, status=400)
        path = _qview_image_path(image)
        subprocess.Popen(
            ["/usr/bin/open", "-a", str(QVIEW_APP_PATH), str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return web.json_response({"ok": True, "filename": path.name})
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=400)


async def generate_mobile_image(request):
    try:
        data = await request.json()
        manual_only = request.path == "/random_photo_prompt/manual/generate"
        if manual_only:
            data["custom_prompt_source"] = "manual"
            if not str(data.get("custom_prompt") or "").strip():
                return web.json_response({"error": "必须填写正向提示词。"}, status=400)
        workflow_key, workflow_config = _mobile_workflow_config(data.get("workflow"))
        if workflow_config.get("type", "image") != "image":
            workflow_key, workflow_config = _mobile_workflow_config(MOBILE_DEFAULT_WORKFLOW_KEY)
        template = _load_mobile_workflow(workflow_key)
        zimage_models = await _available_mobile_zimage_models()
        available_loras = await _available_mobile_loras() if not manual_only else []
        requested_zit_model = str(data.get("zit_model") or "").strip()
        requested_zib_model = str(data.get("zib_model") or "").strip()
        requested_krea2_model = str(data.get("krea2_model") or "").strip()
        if _is_krea2_workflow(workflow_key):
            zit_model = ""
            zib_model = ""
            krea2_model = _resolve_krea2_model(requested_krea2_model, zimage_models["krea2_models"])
        elif workflow_key == "zib_single":
            zit_model = ""
            zib_model = _resolve_zib_model(requested_zib_model, zimage_models["zib_models"])
            krea2_model = ""
        elif workflow_key in {"zitb_double", "zimage_double_v2"}:
            zit_model = _resolve_zit_model(requested_zit_model, zimage_models["zit_models"])
            zib_model = _resolve_zib_model(requested_zib_model, zimage_models["zib_models"])
            krea2_model = ""
        else:
            zit_model = _resolve_zit_model(requested_zit_model, zimage_models["zit_models"])
            zib_model = ""
            krea2_model = ""
        loras = [] if manual_only else _resolve_mobile_loras(data.get("loras"), available_loras)
        scale = data.get("scale", "bold")
        era = data.get("era", "modern")
        prompt_rule = _normalize_mobile_prompt_rule(data.get("prompt_rule"))
        shot_config = _mobile_shot_config(data.get("shot", "full_body_portrait"))
        custom_prompt_source = str(data.get("custom_prompt_source") or "").strip()
        custom_prompt = (
            str(data.get("custom_prompt") or "").strip()
            if custom_prompt_source in {"manual", "pregenerated"}
            else ""
        )
        exact_prompt = manual_only and data.get("exact_prompt") is True
        is_double_workflow = workflow_key in {"zitb_double", "zimage_double_v2"}
        custom_negative_prompt = str(data.get("negative_prompt") or "").strip()
        if not is_double_workflow and custom_negative_prompt:
            return web.json_response({"error": "单采工作流只接受正向提示词。"}, status=400)
        client_id = str(data.get("client_id") or "").strip()
        batch_id = data.get("_batch_id")
        batch_index = max(1, int(data.get("_batch_index") or 1))
        batch_total = max(batch_index, int(data.get("_batch_total") or 1))
        requested_count = 1
        remaining_slots = max(0, MOBILE_MAX_ACTIVE_JOBS - await _mobile_active_job_count())
        if remaining_slots <= 0:
            return web.json_response({"error": f"当前任务数已达到 {MOBILE_MAX_ACTIVE_JOBS}，请等待完成后再添加。"}, status=429)
        count = min(requested_count, remaining_slots)
        jobs = []
        errors = []
        for index in range(count):
            seed_text = f"{time.time()}-{uuid.uuid4()}-{index}"
            if custom_prompt:
                custom_prompt = _enforce_mobile_ancient_barefoot_text(custom_prompt, era)
                prompt_item = _custom_mobile_prompt_item(custom_prompt, seed_text)
                resolution = _mobile_custom_resolution(custom_prompt, data.get("custom_resolution"))
            else:
                prompt_item, resolution = _build_mobile_prompt_for_scope(scale, shot_config, seed_text, era, prompt_rule)
            width = int(resolution["width"])
            height = int(resolution["height"])
            aspect = resolution["aspect"]
            if custom_negative_prompt:
                prompt_item["negative_prompt"] = custom_negative_prompt
            if is_double_workflow and prompt_rule != K2_SFW_RULE_KEY and not custom_negative_prompt:
                _use_chinese_negative_prompt(prompt_item, scale, shot_config, width, height, aspect)
            if _is_krea2_workflow(workflow_key) and prompt_rule != K2_SFW_RULE_KEY and not exact_prompt and not custom_prompt:
                prompt_item = _apply_krea2_prompt_item_orientation_guard(prompt_item, width, height)
            seed = int(data.get("seed") or prompt_item.get("seed") or int(time.time() * 1000))
            if count > 1 and not data.get("seed"):
                seed = int(prompt_item.get("seed") or seed)
            if manual_only:
                output_prefix = f"rpp_manual_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
            else:
                output_prefix = f"mobile_{uuid.uuid4().hex[:12]}"
            workflow, patched = _patch_mobile_workflow(
                template,
                prompt_item,
                width,
                height,
                seed,
                zit_model,
                output_prefix,
                loras,
                zib_model,
                workflow_key,
                krea2_model,
                apply_krea2_orientation_guard=prompt_rule != K2_SFW_RULE_KEY and not exact_prompt,
            )
            queued, error = await _queue_mobile_workflow(workflow, client_id)
            if error:
                errors.append(error)
                continue
            job = {
                **queued,
                "prompt": _display_prompt_text(prompt_item),
                "generation_prompt": _prompt_text(prompt_item),
                "workflow": workflow_key,
                "workflow_label": workflow_config["label"],
                "zit_model": zit_model,
                "zib_model": zib_model,
                "krea2_model": krea2_model,
                "loras": loras,
                "scale": prompt_item.get("scale", scale),
                "prompt_rule": prompt_rule,
                "shot": prompt_item.get("shot_key", shot_config["shot"]),
                "custom_prompt": bool(custom_prompt),
                "custom_resolution": data.get("custom_resolution") if custom_prompt else "",
                "era": prompt_item.get("era", "") if prompt_rule == K2_SFW_RULE_KEY else prompt_item.get("era", era),
                "aspect": aspect,
                "width": width,
                "height": height,
                "seed": seed,
                "output_prefix": output_prefix,
                "batch_id": batch_id,
                "batch_index": batch_index + index,
                "batch_total": batch_total,
                "patched": patched,
                "remote_websocket_output": queued.get("remote_websocket_output", False),
                "created_at": int(time.time() * 1000),
            }
            jobs.append(job)
            MOBILE_SESSION_JOBS.append(job)
            _save_mobile_session_jobs()
        status = 200 if jobs else 400
        return web.json_response({"jobs": jobs, "errors": errors}, status=status)
    except Exception as exc:
        return web.json_response({"error": str(exc), "detail": traceback.format_exc()}, status=400)


async def generate_mobile_video(request):
    try:
        data = await request.json()
        workflow_key, workflow_config = _mobile_workflow_config(MOBILE_VIDEO_WORKFLOW_KEY)
        template = _load_mobile_workflow(workflow_key)
        scale = data.get("scale", "bold")
        client_id = str(data.get("client_id") or "").strip()
        shot_config = _mobile_shot_config(data.get("shot", "full_body"))
        batch_id = data.get("_batch_id")
        batch_index = max(1, int(data.get("_batch_index") or 1))
        batch_total = max(batch_index, int(data.get("_batch_total") or 1))
        requested_count = 1
        remaining_slots = max(0, MOBILE_MAX_ACTIVE_JOBS - await _mobile_active_job_count())
        if remaining_slots <= 0:
            return web.json_response({"error": f"当前任务数已达到 {MOBILE_MAX_ACTIVE_JOBS}，请等待完成后再添加。"}, status=429)
        count = min(requested_count, remaining_slots)
        video_mode = str(data.get("video_mode") or "text").strip().lower()
        if video_mode not in {"text", "image"}:
            raise ValueError("视频模式只能是文生视频或图生视频。")
        source_filename = str(data.get("source_filename") or "")
        source_path = None
        image_load_name = ""
        source_is_uploaded = False
        remote_source_url = ""
        remote_video_upload_url = _mac_proxy_video_upload_url() if REMOTE_COMFYUI_URL else ""
        if video_mode == "image":
            source_path, image_load_name, source_is_uploaded = _mobile_video_source_path(source_filename)
            remote_source_url = _mac_proxy_source_image_url(image_load_name) if REMOTE_COMFYUI_URL else ""
        # Video has its own action field. Never inherit a manual still-image prompt.
        action_text = str(data.get("action_text") or "").strip()
        fps = 24
        requested_seconds = normalize_video_seconds(data.get("seconds", 8))
        source_prompt = "" if video_mode == "text" or source_is_uploaded else _mobile_prompt_for_gallery_file(Path(source_filename).name)
        jobs = []
        errors = []
        for index in range(count):
            seed_text = f"video-{time.time()}-{uuid.uuid4()}-{index}"
            prompt_item, resolution = _build_mobile_prompt_for_scope(scale, shot_config, seed_text)
            video_prompt, seconds = _video_prompt_from_action(
                action_text,
                seed_text=seed_text,
                seconds=requested_seconds,
                source_prompt=source_prompt,
                filename=Path(source_filename).name,
            )
            seed = int(data.get("seed") or prompt_item.get("seed") or int(time.time() * 1000))
            output_prefix = f"mobile_video_{uuid.uuid4().hex[:12]}"
            workflow, patched, video_params = _patch_mobile_video_workflow(
                template,
                prompt_item,
                image_load_name,
                source_path,
                seed,
                seconds,
                fps,
                output_prefix,
                video_prompt,
                remote_source_url,
                remote_video_upload_url,
                video_mode,
            )
            queued, error = await _queue_mobile_workflow(workflow, client_id)
            if error:
                errors.append(error)
                continue
            job = {
                **queued,
                "media_type": "video",
                "prompt": video_prompt,
                "generation_prompt": video_prompt,
                "motion_prompt": video_prompt,
                "workflow": workflow_key,
                "workflow_label": workflow_config["label"],
                "scale": prompt_item.get("scale", scale),
                "shot": prompt_item.get("shot_key", shot_config["shot"]),
                "aspect": resolution["aspect"],
                # Report the dimensions actually patched into the video node,
                # rather than the unrelated still-image prompt resolution.
                "width": int(video_params["width"]),
                "height": int(video_params["height"]),
                "seed": seed,
                "video_mode": video_mode,
                "source_filename": Path(source_filename).name if video_mode == "image" else "",
                "output_prefix": output_prefix,
                "batch_id": batch_id,
                "batch_index": batch_index + index,
                "batch_total": batch_total,
                "patched": patched,
                "video": video_params,
                "created_at": int(time.time() * 1000),
            }
            jobs.append(job)
            MOBILE_SESSION_JOBS.append(job)
            _save_mobile_session_jobs()
        status = 200 if jobs else 400
        return web.json_response({"jobs": jobs, "errors": errors}, status=status)
    except Exception as exc:
        return web.json_response({"error": str(exc), "detail": traceback.format_exc()}, status=400)


async def pregenerate_mobile_video_action(request):
    try:
        if request.method == "GET":
            data = dict(request.query)
        else:
            data = await request.json()
        source_filename = str(data.get("source_filename") or "")
        source_path, _image_load_name, source_is_uploaded = _mobile_video_source_path(source_filename)
        source_filename = source_path.name
        action, family, used_prompt, frame_scope = _pregenerate_video_action_for_image(
            source_filename if not source_is_uploaded else "",
            data.get("scale", "bold"),
            str(data.get("nonce") or ""),
            data.get("seconds", 8),
            data.get("previous_action", ""),
        )
        seconds = normalize_video_seconds(data.get("seconds", 8))
        return web.json_response(
            {
                "action": action,
                "seconds": seconds,
                "pose_family": family,
                "frame_scope": frame_scope,
                "used_source_prompt": used_prompt,
            }
        )
    except Exception as exc:
        return web.json_response({"error": str(exc), "detail": traceback.format_exc()}, status=400)


async def mobile_job_detail(request):
    try:
        prompt_id = request.match_info.get("prompt_id", "")
        if not prompt_id:
            return web.json_response({"error": "缺少任务编号。"}, status=400)
        return web.json_response(await _mobile_job_status(prompt_id))
    except Exception:
        return web.json_response({"error": traceback.format_exc()}, status=500)


async def mobile_session_jobs(request):
    try:
        return web.json_response({"jobs": await _active_mobile_session_jobs()})
    except Exception:
        return web.json_response({"error": traceback.format_exc()}, status=500)


async def clear_remote_mobile_runtime_state(request):
    try:
        result = _clear_remote_mobile_runtime_state()
        return web.json_response({"ok": True, **result})
    except Exception:
        return web.json_response({"error": traceback.format_exc()}, status=500)


async def mobile_runtime_image(request):
    prompt_id = str(request.match_info.get("prompt_id") or "")
    filename = Path(str(request.match_info.get("filename") or "")).name
    for item in MOBILE_RUNTIME_IMAGES_BY_PROMPT_ID.get(prompt_id, []):
        if item.get("filename") == filename:
            return web.Response(body=item.get("bytes") or b"", content_type=item.get("content_type") or "image/png")
    return web.json_response({"error": "临时图片不存在或已清理。"}, status=404)


async def mobile_gallery_images(request):
    try:
        return web.json_response({"images": _mobile_gallery_images()})
    except Exception:
        return web.json_response({"error": traceback.format_exc()}, status=500)


async def mark_mobile_viewed_images(request):
    try:
        data = await request.json()
        raw_keys = data.get("keys") if isinstance(data, dict) else []
        if not isinstance(raw_keys, list):
            raw_keys = [raw_keys]
        keys = [str(key).replace("\\", "/").strip("/") for key in raw_keys if str(key).strip()]
        viewed = _mark_mobile_viewed_keys(keys)
        return web.json_response({"ok": True, "viewed": sorted(viewed)})
    except Exception:
        return web.json_response({"error": traceback.format_exc()}, status=400)


async def mobile_gallery_videos(request):
    try:
        return web.json_response({"videos": _mobile_gallery_videos()})
    except Exception:
        return web.json_response({"error": traceback.format_exc()}, status=500)


async def mobile_favorite_images(request):
    try:
        return web.json_response(
            {"images": _mobile_favorite_backup_images()},
            headers={"Cache-Control": "no-store"},
        )
    except Exception:
        return web.json_response({"error": traceback.format_exc()}, status=500)


async def mobile_favorite_image_file(request):
    try:
        path = _mobile_favorite_backup_file(request.match_info.get("filename"))
        if not path.is_file() or path.suffix.lower() not in MOBILE_GALLERY_EXTENSIONS:
            return web.json_response({"error": "收藏图片不存在。"}, status=404)
        return web.FileResponse(path)
    except Exception:
        return web.json_response({"error": traceback.format_exc()}, status=500)


async def delete_mobile_favorite_images(request):
    try:
        data = await request.json()
        raw_items = data.get("items") or []
        deleted = 0
        missing = 0
        favorite_metadata = _load_mobile_favorite_metadata()
        metadata_changed = False
        for raw in raw_items:
            if not isinstance(raw, dict):
                raw = {"filename": raw}
            filename = str(raw.get("filename") or "")
            try:
                path = _mobile_favorite_backup_file(filename)
            except Exception:
                missing += 1
                continue
            if not path.is_file() or path.suffix.lower() not in MOBILE_GALLERY_EXTENSIONS:
                missing += 1
                continue
            path.unlink()
            if favorite_metadata.pop(path.name, None) is not None:
                metadata_changed = True
            deleted += 1
        if metadata_changed:
            _save_mobile_favorite_metadata(favorite_metadata)
        return web.json_response({"deleted": deleted, "missing": missing, "images": _mobile_favorite_backup_images()})
    except Exception:
        return web.json_response({"error": traceback.format_exc()}, status=500)


async def backup_mobile_favorite_image(request):
    try:
        data = await request.json()
        raw_item = data.get("image") if isinstance(data.get("image"), dict) else data
        path = _mobile_output_file_from_item(raw_item)
        if not path.is_file() or path.suffix.lower() not in MOBILE_GALLERY_EXTENSIONS:
            return web.json_response({"error": "图片不存在或不是可收藏图片。"}, status=404)
        source_subfolder = _mobile_output_subfolder_for_path(path)
        source_key = _mobile_output_file_key(path.name, source_subfolder)
        metadata = _mobile_prompt_metadata_for_gallery_file(source_key)
        if not str(metadata.get("prompt") or "").strip():
            return web.json_response({"error": "原图缺少提示词元数据，无法完整收藏。"}, status=400)
        metadata["source_key"] = source_key
        MOBILE_FAVORITE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        target = (MOBILE_FAVORITE_BACKUP_DIR / path.name).resolve()
        if target.parent != MOBILE_FAVORITE_BACKUP_DIR.resolve():
            return web.json_response({"error": "收藏备份目录不安全。"}, status=403)
        if target.exists():
            target = (MOBILE_FAVORITE_BACKUP_DIR / f"{path.stem}_{uuid.uuid4().hex[:8]}{path.suffix}").resolve()
        shutil.copy2(path, target)
        favorite_metadata = _load_mobile_favorite_metadata()
        favorite_metadata[target.name] = metadata
        _save_mobile_favorite_metadata(favorite_metadata)
        return web.json_response({"ok": True, "path": str(target), "filename": target.name})
    except Exception:
        return web.json_response({"error": traceback.format_exc()}, status=500)


async def backup_mobile_favorite_video(request):
    try:
        data = await request.json()
        raw_item = data.get("video") if isinstance(data.get("video"), dict) else data
        filename = str(raw_item.get("filename") or "")
        path = _mobile_video_output_file(filename)
        if not path.is_file() or path.suffix.lower() not in MOBILE_VIDEO_EXTENSIONS:
            return web.json_response({"error": "视频不存在或不是可收藏视频。"}, status=404)
        MOBILE_VIDEO_FAVORITE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        target = (MOBILE_VIDEO_FAVORITE_BACKUP_DIR / path.name).resolve()
        if target.parent != MOBILE_VIDEO_FAVORITE_BACKUP_DIR.resolve():
            return web.json_response({"error": "视频收藏备份目录不安全。"}, status=403)
        if target.exists():
            target = (MOBILE_VIDEO_FAVORITE_BACKUP_DIR / f"{path.stem}_{uuid.uuid4().hex[:8]}{path.suffix}").resolve()
        shutil.copy2(path, target)
        return web.json_response({"ok": True, "path": str(target), "filename": target.name})
    except Exception:
        return web.json_response({"error": traceback.format_exc()}, status=500)


async def delete_mobile_gallery_images(request):
    try:
        data = await request.json()
        raw_items = data.get("items") or []
        deleted = 0
        missing = 0
        errors = []
        prompt_index = _load_mobile_prompt_index()
        prompt_index_changed = False
        for raw in raw_items:
            if not isinstance(raw, dict):
                raw = {"filename": raw}
            try:
                path = _mobile_output_file_from_item(raw)
            except Exception as exc:
                missing += 1
                errors.append({"item": raw, "error": str(exc)})
                continue
            if not path.is_file() or path.suffix.lower() not in MOBILE_GALLERY_EXTENSIONS:
                missing += 1
                continue
            subfolder = _mobile_output_subfolder_for_path(path)
            file_key = _mobile_output_file_key(path.name, subfolder)
            path.unlink()
            for key in {file_key, path.name}:
                if key in MOBILE_PROMPT_BY_FILENAME:
                    MOBILE_PROMPT_BY_FILENAME.pop(key, None)
                if key in prompt_index:
                    prompt_index.pop(key, None)
                    prompt_index_changed = True
            deleted += 1
        if prompt_index_changed:
            _save_mobile_prompt_index(prompt_index)
        return web.json_response({"deleted": deleted, "missing": missing, "errors": errors, "images": _mobile_gallery_images()})
    except Exception:
        return web.json_response({"error": traceback.format_exc()}, status=500)


async def delete_mobile_gallery_videos(request):
    try:
        data = await request.json()
        raw_items = data.get("items") or []
        deleted = 0
        for raw in raw_items:
            filename = str(raw.get("filename") or "")
            if not filename:
                continue
            path = _mobile_video_output_file(filename)
            if not path.is_file() or path.suffix.lower() not in MOBILE_VIDEO_EXTENSIONS:
                continue
            path.unlink()
            deleted += 1
        return web.json_response({"deleted": deleted, "videos": _mobile_gallery_videos()})
    except Exception:
        return web.json_response({"error": traceback.format_exc()}, status=500)


async def delete_remote_output_file(request):
    try:
        data = await request.json()
        filename = Path(str(data.get("filename") or "")).name
        subfolder = str(data.get("subfolder") or "").replace("\\", "/").strip("/")
        file_type = str(data.get("type") or "output").strip() or "output"
        if not filename:
            return web.json_response({"error": "缺少文件名。"}, status=400)
        if filename.startswith(".") or "/" in filename or "\\" in filename:
            return web.json_response({"error": "文件名不安全。"}, status=400)
        if subfolder and any(part in {"", ".", ".."} for part in subfolder.split("/")):
            return web.json_response({"error": "子目录不安全。"}, status=400)
        base_dir = folder_paths.get_directory_by_type(file_type)
        if not base_dir:
            return web.json_response({"error": "不支持的目录类型。"}, status=400)
        base_dir = Path(base_dir).resolve()
        target_dir = (base_dir / subfolder).resolve() if subfolder else base_dir
        if target_dir != base_dir and base_dir not in target_dir.parents:
            return web.json_response({"error": "路径越界。"}, status=403)
        path = (target_dir / filename).resolve()
        if path.parent != target_dir:
            return web.json_response({"error": "路径越界。"}, status=403)
        if not path.is_file():
            return web.json_response({"deleted": 0, "missing": True})
        last_error = ""
        for attempt in range(1, 7):
            try:
                path.unlink()
                return web.json_response({"deleted": 1, "filename": filename, "subfolder": subfolder, "type": file_type, "attempt": attempt})
            except PermissionError as exc:
                last_error = str(exc)
                await asyncio.sleep(min(10, attempt * 2))
        return web.json_response({"error": "远端文件被占用，删除失败。", "detail": last_error}, status=409)
    except Exception:
        return web.json_response({"error": traceback.format_exc()}, status=500)


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
