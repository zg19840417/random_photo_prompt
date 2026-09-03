from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import uuid
from pathlib import Path

import folder_paths
from PIL import Image
from server import PromptServer

from rpp_globals import (
    MOBILE_FAVORITE_BACKUP_DIR,
    MOBILE_FAVORITE_METADATA_NAME,
    MOBILE_GALLERY_EXTENSIONS,
    MOBILE_MAX_ACTIVE_JOBS,
    MOBILE_PROMPT_BY_FILENAME,
    MOBILE_PROMPT_INDEX_NAME,
    MOBILE_RESULT_RECEIVE_GRACE_SECONDS,
    MOBILE_VIDEO_RESULT_RECEIVE_GRACE_SECONDS,
    MOBILE_RUNTIME_IMAGES_BY_PROMPT_ID,
    MOBILE_SESSION_JOBS,
    MOBILE_SESSION_JOBS_LOADED,
    MOBILE_VIDEO_DIMENSIONS_BY_FILENAME,
    MOBILE_VIDEO_EXTENSIONS,
    MOBILE_VIDEO_INPUT_SUBFOLDER,
    MOBILE_VIDEO_OUTPUT_SUBFOLDER,
    MOBILE_VIDEO_PROMPT_BY_FILENAME,
    MOBILE_VIDEO_FAVORITE_BACKUP_DIR,
    MOBILE_VIEWED_INDEX_NAME,
    NODE_DIR,
    QVIEW_APP_PATH,
    REMOTE_COMFYUI_URL,
    REMOTE_HISTORY_TIMEOUT,
    REMOTE_PROGRESS_BY_PROMPT_ID,
    REMOTE_WS_IMAGE_RECEIVED_BY_PROMPT_ID,
    REMOTE_FINISHED_AT_BY_PROMPT_ID,
    REMOTE_WS_OUTPUT_PREFIX_BY_PROMPT_ID,
)
from rpp_utils import (
    _image_longest_side,
    _looks_internal_prompt_link,
    _looks_negative_text,
    _mobile_local_output_dir,
    _mobile_video_output_dir,
    _queue_contains,
    _queue_waiting_count,
)
from rpp_prompts import _mobile_resolution_for_custom_prompt
from rpp_remote import (
    _ensure_mobile_session_jobs_loaded,
    _remote_history,
    _remote_queue,
    _save_mobile_session_jobs,
)
from video_prompt_engine import (
    clean_video_action_text,
    estimate_video_seconds,
    generate_video_action,
    infer_video_pose_family,
    infer_video_scope,
    normalize_video_seconds,
    video_prompt_from_action,
)

__all__ = sorted(["__all__", "_active_mobile_session_jobs", "_clean_video_action_text", "_copy_mobile_gallery_image_to_input", "_estimate_video_seconds", "_image_dimensions_for_file", "_infer_frame_scope_from_prompt", "_infer_pose_family_from_prompt", "_load_image_interrogator", "_load_mobile_favorite_metadata", "_load_mobile_prompt_index", "_mobile_active_job_count", "_mobile_favorite_backup_file", "_mobile_favorite_backup_images", "_mobile_favorite_metadata_path", "_mobile_gallery_images", "_mobile_gallery_videos", "_mobile_image_urls", "_mobile_job_output_prefix", "_mobile_job_status", "_mobile_local_images_for_prompt", "_mobile_output_file", "_mobile_output_file_from_item", "_mobile_output_file_key", "_mobile_output_relative_path", "_mobile_output_subfolder_for_path", "_mobile_prompt_for_gallery_file", "_mobile_prompt_for_video_file", "_mobile_prompt_index_path", "_mobile_prompt_metadata_for_gallery_file", "_mobile_remote_history_entry", "_mobile_session_job", "_mobile_video_input_dir", "_mobile_video_output_file", "_mobile_video_source_path", "_mobile_video_urls", "_mobile_video_urls_sync", "_mobile_video_view_url", "_mobile_view_subfolder", "_mobile_view_url", "_pregenerate_video_action_for_image", "_prompt_text_from_canvas_workflow_metadata", "_prompt_text_from_png_metadata", "_qview_image_path", "_remember_mobile_prompt_file", "_remember_mobile_prompt_images", "_remember_mobile_prompt_videos", "_remote_history_error_message", "_request_from_local_mac_browser", "_save_mobile_favorite_metadata", "_save_mobile_prompt_index", "_video_dimensions_for_file", "_video_motion_text", "_video_prompt_from_action"])

def _video_motion_text(seed_text="", seconds=8):
    return str(generate_video_action(seed_text=seed_text, seconds=seconds).get("action") or "")


def _infer_frame_scope_from_prompt(prompt):
    return infer_video_scope(prompt)


def _infer_pose_family_from_prompt(prompt):
    return infer_video_pose_family(prompt)


def _pregenerate_video_action_for_image(filename, scale="", seed_text="", seconds=8, previous_action=""):
    source_prompt = _mobile_prompt_for_gallery_file(Path(filename).name)
    previous_text = str(previous_action or "").strip()
    result = None
    for _attempt in range(8):
        resolved_seed_text = f"{scale}|{normalize_video_seconds(seconds)}|{Path(filename).name}|{seed_text or ''}|{time.time()}|{uuid.uuid4().hex}|{_attempt}"
        result = generate_video_action(
            source_prompt=source_prompt,
            filename=Path(filename).name,
            seed_text=resolved_seed_text,
            seconds=seconds,
        )
        if not previous_text or str(result.get("action") or "").strip() != previous_text:
            break
    return result["action"], result["pose_family"], result["used_source_prompt"], result["scope"]


def _clean_video_action_text(value):
    return clean_video_action_text(value)


def _estimate_video_seconds(action_text):
    return estimate_video_seconds(action_text)


def _video_prompt_from_action(action_text, seed_text="", seconds=None, source_prompt="", filename=""):
    return video_prompt_from_action(
        action_text,
        source_prompt=source_prompt,
        filename=filename,
        seed_text=seed_text,
        seconds=seconds,
    )


def _mobile_output_relative_path(path):
    output_dir = _mobile_local_output_dir()
    resolved = Path(path).resolve()
    if resolved == output_dir:
        return ""
    if output_dir not in resolved.parents:
        raise ValueError("文件路径不在 ComfyUI output 目录内。")
    return resolved.relative_to(output_dir).as_posix()


def _mobile_output_subfolder_for_path(path):
    relative = _mobile_output_relative_path(path)
    parent = Path(relative).parent.as_posix()
    return "" if parent == "." else parent


def _mobile_view_subfolder(subfolder=""):
    return str(subfolder or "").replace("\\", "/").strip("/")


def _mobile_output_file_key(filename, subfolder=""):
    safe_name = Path(str(filename or "")).name
    safe_subfolder = str(subfolder or "").replace("\\", "/").strip("/")
    return f"{safe_subfolder}/{safe_name}" if safe_subfolder else safe_name


def _mobile_prompt_index_path():
    return _mobile_local_output_dir() / MOBILE_PROMPT_INDEX_NAME


def _mobile_viewed_index_path():
    return _mobile_local_output_dir() / MOBILE_VIEWED_INDEX_NAME


def _load_mobile_viewed_keys():
    path = _mobile_viewed_index_path()
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    values = data.get("viewed", data) if isinstance(data, dict) else data
    if not isinstance(values, list):
        return set()
    return {str(value).replace("\\", "/").strip("/") for value in values if str(value).strip()}


def _save_mobile_viewed_keys(keys):
    path = _mobile_viewed_index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": int(time.time() * 1000),
        "viewed": sorted({str(key).replace("\\", "/").strip("/") for key in keys if str(key).strip()}),
    }
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _mark_mobile_viewed_keys(keys):
    current = _load_mobile_viewed_keys()
    current.update(str(key).replace("\\", "/").strip("/") for key in keys if str(key).strip())
    _save_mobile_viewed_keys(current)
    return current


def _load_mobile_prompt_index():
    path = _mobile_prompt_index_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    prompts = data.get("prompts", data)
    if not isinstance(prompts, dict):
        return {}
    result = {}
    for key, value in prompts.items():
        filename = str(key or "").replace("\\", "/").strip("/")
        if isinstance(value, dict):
            prompt = str(value.get("prompt") or "").strip()
            seed = value.get("seed")
        else:
            prompt = str(value or "").strip()
            seed = None
        if filename and prompt and not _looks_internal_prompt_link(prompt):
            try:
                seed = int(seed) if seed not in (None, "") else None
            except (TypeError, ValueError):
                seed = None
            result[filename] = {"prompt": prompt, "seed": seed}
    return result


def _save_mobile_prompt_index(index):
    path = _mobile_prompt_index_path()
    serializable = {}
    for key, value in dict(index or {}).items():
        filename = str(key or "").replace("\\", "/").strip("/")
        metadata = value if isinstance(value, dict) else {"prompt": value}
        prompt = str(metadata.get("prompt") or "").strip()
        if not filename or not prompt:
            continue
        item = {"prompt": prompt}
        try:
            seed = metadata.get("seed")
            if seed not in (None, ""):
                item["seed"] = int(seed)
        except (TypeError, ValueError):
            pass
        serializable[filename] = item
    payload = {
        "version": 2,
        "updated_at": int(time.time() * 1000),
        "prompts": serializable,
    }
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _remember_mobile_prompt_file(filename, prompt, subfolder="", seed=None):
    safe_name = _mobile_output_file_key(filename, subfolder)
    prompt = str(prompt or "").strip()
    if not safe_name or not prompt:
        return
    try:
        seed = int(seed) if seed not in (None, "") else None
    except (TypeError, ValueError):
        seed = None
    metadata = {"prompt": prompt, "seed": seed}
    MOBILE_PROMPT_BY_FILENAME[safe_name] = metadata
    index = _load_mobile_prompt_index()
    if index.get(safe_name) == metadata:
        return
    index[safe_name] = metadata
    _save_mobile_prompt_index(index)


def _prompt_text_from_canvas_workflow_metadata(path):
    try:
        from PIL import Image
    except Exception:
        return ""
    try:
        with Image.open(path) as image:
            raw_workflow = image.info.get("workflow", "")
    except Exception:
        return ""
    if not raw_workflow:
        return ""
    try:
        workflow = json.loads(raw_workflow)
    except Exception:
        return ""
    nodes = workflow.get("nodes") if isinstance(workflow, dict) else None
    if not isinstance(nodes, list):
        return ""
    candidates = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type") or "")
        title = str(node.get("title") or "")
        widgets = node.get("widgets_values")
        if not isinstance(widgets, list):
            continue
        if node_type == "RandomPhotoPrompt":
            for value in widgets:
                text = str(value or "").strip()
                if "\n" in text and not _looks_negative_text({"_meta": {"title": title}, "inputs": {"text": text}}):
                    candidates.append(text)
        elif "CLIPTextEncode" in node_type and not _looks_negative_text({"_meta": {"title": title}, "inputs": {"text": widgets[0] if widgets else ""}}):
            for value in widgets:
                text = str(value or "").strip()
                if "\n" in text:
                    candidates.append(text)
    return max(candidates, key=len) if candidates else ""


def _prompt_text_from_png_metadata(path):
    try:
        from PIL import Image
    except Exception:
        return ""
    try:
        with Image.open(path) as image:
            raw_prompt = image.info.get("prompt", "")
    except Exception:
        return ""
    if not raw_prompt:
        return ""
    try:
        workflow = json.loads(raw_prompt)
    except Exception:
        return ""
    if not isinstance(workflow, dict):
        return ""
    candidates = []
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        raw_text = inputs.get("text")
        if not isinstance(raw_text, str):
            continue
        text = raw_text.strip()
        if not text or _looks_negative_text(node):
            continue
        class_type = str(node.get("class_type") or "")
        if "CLIPTextEncode" in class_type or "TextEncode" in class_type or "Conditioning" in class_type:
            candidates.append(text)
    if not candidates:
        return _prompt_text_from_canvas_workflow_metadata(path)
    return max(candidates, key=len)


def _mobile_video_input_dir():
    input_dir = Path(folder_paths.get_input_directory()).resolve()
    target = (input_dir / MOBILE_VIDEO_INPUT_SUBFOLDER).resolve()
    if input_dir not in target.parents and target != input_dir:
        raise ValueError("手机视频输入目录不在 ComfyUI input 目录内。")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _mobile_output_file(filename):
    if not filename:
        raise ValueError("缺少文件名。")
    output_dir = _mobile_local_output_dir()
    safe_name = str(filename or "").replace("\\", "/").strip("/")
    path = (output_dir / safe_name).resolve()
    if output_dir in path.parents and path.is_file():
        return path
    raise ValueError("文件路径不在手机输出目录内。")


def _mobile_output_file_from_item(item):
    key = str(item.get("key") or "").replace("\\", "/").strip("/")
    filename = str(item.get("filename") or "").replace("\\", "/").strip("/")
    subfolder = str(item.get("subfolder") or "").replace("\\", "/").strip("/")
    if key:
        return _mobile_output_file(key)
    if subfolder and filename:
        return _mobile_output_file(_mobile_output_file_key(filename, subfolder))
    return _mobile_output_file(filename)


def _request_from_local_mac_browser(request):
    if platform.system() != "Darwin" or not QVIEW_APP_PATH.is_dir():
        return False
    user_agent = request.headers.get("User-Agent", "")
    if "Macintosh" not in user_agent or "iPhone" in user_agent or "iPad" in user_agent:
        return False
    transport = request.transport
    peer = transport.get_extra_info("peername") if transport else None
    local = transport.get_extra_info("sockname") if transport else None
    peer_host = str(peer[0] if isinstance(peer, tuple) and peer else request.remote or "").split("%", 1)[0]
    local_host = str(local[0] if isinstance(local, tuple) and local else "").split("%", 1)[0]
    return peer_host in {"127.0.0.1", "::1"} or bool(peer_host and local_host and peer_host == local_host)


def _qview_image_path(item):
    if str(item.get("type") or "") == "favorite_backup" or str(item.get("key") or "").startswith("favorite_backup/"):
        path = _mobile_favorite_backup_file(item.get("filename"))
    else:
        path = _mobile_output_file_from_item(item)
    if not path.is_file() or path.suffix.lower() not in MOBILE_GALLERY_EXTENSIONS:
        raise ValueError("图片不存在或格式不受支持。")
    return path


def _mobile_video_output_file(filename):
    if not filename:
        raise ValueError("缺少文件名。")
    path = (_mobile_video_output_dir() / Path(filename).name).resolve()
    if path.parent != _mobile_video_output_dir():
        raise ValueError("文件路径不在手机视频输出目录内。")
    return path


def _mobile_view_url(filename, subfolder=""):
    params = urllib.parse.urlencode(
        {
            "filename": filename,
            "subfolder": _mobile_view_subfolder(subfolder),
            "type": "output",
        }
    )
    return f"/view?{params}"


def _mobile_video_view_url(filename):
    params = urllib.parse.urlencode(
        {
            "filename": filename,
            "subfolder": _mobile_view_subfolder(MOBILE_VIDEO_OUTPUT_SUBFOLDER),
            "type": "output",
        }
    )
    return f"/view?{params}"


def _mobile_prompt_metadata_for_gallery_file(filename):
    _ensure_mobile_session_jobs_loaded()
    filename = str(filename or "").replace("\\", "/").strip("/")
    prompt_index = _load_mobile_prompt_index()
    candidates = [filename]
    basename = Path(filename).name
    if basename != filename:
        candidates.append(basename)
    if "/" not in filename:
        for key in list(MOBILE_PROMPT_BY_FILENAME) + list(prompt_index):
            if Path(str(key).replace("\\", "/")).name == basename:
                candidates.append(str(key).replace("\\", "/").strip("/"))
    for key in dict.fromkeys(candidate for candidate in candidates if candidate):
        metadata = MOBILE_PROMPT_BY_FILENAME.get(key) or prompt_index.get(key) or {}
        if isinstance(metadata, str):
            metadata = {"prompt": metadata}
        prompt = str(metadata.get("prompt") or "").strip()
        if prompt:
            result = {"prompt": prompt, "seed": metadata.get("seed")}
            MOBILE_PROMPT_BY_FILENAME[filename] = result
            return result
    for job in MOBILE_SESSION_JOBS:
        prefix = str(job.get("output_prefix") or "")
        if prefix and Path(filename).name.startswith(f"{prefix}_"):
            return {"prompt": str(job.get("prompt") or ""), "seed": job.get("seed")}
    return {"prompt": "", "seed": None}


def _mobile_prompt_for_gallery_file(filename):
    return _mobile_prompt_metadata_for_gallery_file(filename).get("prompt", "")


def _mobile_prompt_for_video_file(filename):
    prompt = MOBILE_VIDEO_PROMPT_BY_FILENAME.get(filename, "")
    if prompt:
        return prompt
    for job in MOBILE_SESSION_JOBS:
        prefix = str(job.get("output_prefix") or "")
        if prefix and filename.startswith(f"{prefix}_"):
            return job.get("prompt", "")
    return ""


def _video_dimensions_for_file(path):
    path = Path(path)
    cached = MOBILE_VIDEO_DIMENSIONS_BY_FILENAME.get(path.name)
    if cached:
        return cached
    width = 0
    height = 0
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=s=x:p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output = (completed.stdout or "").strip().splitlines()[0]
        left, right = output.lower().split("x", 1)
        width = int(left)
        height = int(right)
    except Exception:
        width = 0
        height = 0
    result = {"width": width, "height": height}
    if width and height:
        MOBILE_VIDEO_DIMENSIONS_BY_FILENAME[path.name] = result
    return result


def _image_dimensions_for_file(path):
    path = Path(path)
    try:
        with Image.open(path) as image:
            width, height = image.size
        return {"width": int(width), "height": int(height)}
    except Exception:
        return {"width": 0, "height": 0}


def _mobile_gallery_images():
    prompt_by_filename = _load_mobile_prompt_index()
    prompt_by_filename.update(MOBILE_PROMPT_BY_FILENAME)
    viewed_keys = _load_mobile_viewed_keys()
    items = []
    output_dir = _mobile_local_output_dir()
    favorite_backup_dir = MOBILE_FAVORITE_BACKUP_DIR.resolve()
    seen = set()
    for path in output_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in MOBILE_GALLERY_EXTENSIONS:
            continue
        resolved_path = path.resolve()
        if favorite_backup_dir == resolved_path.parent or favorite_backup_dir in resolved_path.parents:
            continue
        subfolder = _mobile_output_subfolder_for_path(path)
        # This directory contains completed videos only. Images there are legacy video inputs,
        # never generated gallery assets.
        if subfolder == MOBILE_VIDEO_OUTPUT_SUBFOLDER:
            continue
        file_key = _mobile_output_file_key(path.name, subfolder)
        if file_key in seen:
            continue
        seen.add(file_key)
        stat = path.stat()
        duplicate_match = re.match(r"^(.+)_([0-9a-f]{12})$", path.stem)
        if duplicate_match:
            original_path = path.with_name(f"{duplicate_match.group(1)}{path.suffix}")
            if original_path.is_file() and original_path.stat().st_size == stat.st_size:
                continue
        metadata = prompt_by_filename.get(file_key) or _mobile_prompt_metadata_for_gallery_file(file_key)
        if isinstance(metadata, str):
            metadata = {"prompt": metadata}
        prompt = str(metadata.get("prompt") or "")
        seed = metadata.get("seed")
        if not prompt and path.suffix.lower() == ".png":
            prompt = _prompt_text_from_png_metadata(path)
            if prompt:
                _remember_mobile_prompt_file(path.name, prompt, subfolder)
        dimensions = _image_dimensions_for_file(path)
        items.append(
            {
                "filename": path.name,
                "subfolder": subfolder,
                "key": file_key,
                "type": "output",
                "mtime": int(stat.st_mtime * 1000),
                "size": stat.st_size,
                "width": dimensions.get("width", 0),
                "height": dimensions.get("height", 0),
                "prompt": prompt,
                "seed": seed,
                "viewed": file_key in viewed_keys,
                "url": _mobile_view_url(path.name, subfolder),
            }
        )
    items.sort(key=lambda item: (item["mtime"], item["filename"]), reverse=True)
    for prompt_id, runtime_items in MOBILE_RUNTIME_IMAGES_BY_PROMPT_ID.items():
        prompt = ""
        seed = None
        for job in MOBILE_SESSION_JOBS:
            if str(job.get("prompt_id") or "") == str(prompt_id):
                prompt = job.get("prompt", "")
                seed = job.get("seed")
                break
        for runtime_item in runtime_items:
            public_item = {key: value for key, value in runtime_item.items() if key != "bytes"}
            public_item["prompt"] = public_item.get("prompt") or prompt
            public_item["seed"] = public_item.get("seed") or seed
            public_item["key"] = public_item.get("filename", "")
            public_item["viewed"] = public_item.get("key", "") in viewed_keys
            items.append(public_item)
    items.sort(key=lambda item: (item.get("mtime", 0), item.get("filename", "")), reverse=True)
    return items


def _mobile_favorite_backup_file(filename):
    safe_name = Path(str(filename or "")).name
    if not safe_name:
        raise ValueError("缺少文件名。")
    base_dir = MOBILE_FAVORITE_BACKUP_DIR.resolve()
    path = (base_dir / safe_name).resolve()
    if path.parent != base_dir:
        raise ValueError("收藏文件路径不安全。")
    return path


def _mobile_favorite_metadata_path():
    return MOBILE_FAVORITE_BACKUP_DIR.resolve() / MOBILE_FAVORITE_METADATA_NAME


def _load_mobile_favorite_metadata():
    path = _mobile_favorite_metadata_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    records = data.get("favorites", data) if isinstance(data, dict) else {}
    if not isinstance(records, dict):
        return {}
    result = {}
    for key, value in records.items():
        filename = Path(str(key or "")).name
        metadata = value if isinstance(value, dict) else {}
        prompt = str(metadata.get("prompt") or "").strip()
        if not filename or not prompt:
            continue
        try:
            seed = int(metadata.get("seed")) if metadata.get("seed") not in (None, "") else None
        except (TypeError, ValueError):
            seed = None
        source_key = str(metadata.get("source_key") or "").replace("\\", "/").strip("/")
        result[filename] = {"prompt": prompt, "seed": seed, "source_key": source_key}
    return result


def _save_mobile_favorite_metadata(records):
    MOBILE_FAVORITE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    serializable = {}
    for key, value in dict(records or {}).items():
        filename = Path(str(key or "")).name
        metadata = value if isinstance(value, dict) else {}
        prompt = str(metadata.get("prompt") or "").strip()
        if not filename or not prompt:
            continue
        item = {"prompt": prompt}
        try:
            if metadata.get("seed") not in (None, ""):
                item["seed"] = int(metadata["seed"])
        except (TypeError, ValueError):
            pass
        source_key = str(metadata.get("source_key") or "").replace("\\", "/").strip("/")
        if source_key:
            item["source_key"] = source_key
        serializable[filename] = item
    payload = {
        "version": 1,
        "updated_at": int(time.time() * 1000),
        "favorites": serializable,
    }
    path = _mobile_favorite_metadata_path()
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _mobile_favorite_backup_images():
    base_dir = MOBILE_FAVORITE_BACKUP_DIR.resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    favorite_metadata = _load_mobile_favorite_metadata()
    viewed_keys = _load_mobile_viewed_keys()
    items = []
    for path in base_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in MOBILE_GALLERY_EXTENSIONS:
            continue
        stat = path.stat()
        dimensions = _image_dimensions_for_file(path)
        metadata = favorite_metadata.get(path.name) or {}
        items.append(
            {
                "filename": path.name,
                "key": f"favorite_backup/{path.name}",
                "type": "favorite_backup",
                "mtime": int(stat.st_mtime * 1000),
                "size": stat.st_size,
                "width": dimensions.get("width", 0),
                "height": dimensions.get("height", 0),
                "prompt": str(metadata.get("prompt") or ""),
                "seed": metadata.get("seed"),
                "source_key": str(metadata.get("source_key") or ""),
                "viewed": str(metadata.get("source_key") or f"favorite_backup/{path.name}") in viewed_keys,
                "url": f"/random_photo_prompt/mobile/favorite/file/{urllib.parse.quote(path.name, safe='')}",
            }
        )
    items.sort(key=lambda item: (item["mtime"], item["filename"]), reverse=True)
    return items


def _mobile_gallery_videos():
    prompt_by_filename = dict(MOBILE_VIDEO_PROMPT_BY_FILENAME)
    for job in MOBILE_SESSION_JOBS:
        for video in _mobile_video_urls_sync(str(job.get("prompt_id", ""))):
            if video.get("subfolder") == MOBILE_VIDEO_OUTPUT_SUBFOLDER and video.get("filename"):
                prompt_by_filename[video["filename"]] = job.get("prompt", "")
                MOBILE_VIDEO_PROMPT_BY_FILENAME[video["filename"]] = job.get("prompt", "")
    items = []
    for path in _mobile_video_output_dir().iterdir():
        if not path.is_file() or path.suffix.lower() not in MOBILE_VIDEO_EXTENSIONS:
            continue
        stat = path.stat()
        dimensions = _video_dimensions_for_file(path)
        items.append(
            {
                "filename": path.name,
                "subfolder": MOBILE_VIDEO_OUTPUT_SUBFOLDER,
                "type": "output",
                "mtime": int(stat.st_mtime * 1000),
                "size": stat.st_size,
                "width": dimensions.get("width", 0),
                "height": dimensions.get("height", 0),
                "prompt": prompt_by_filename.get(path.name, "") or _mobile_prompt_for_video_file(path.name),
                "url": _mobile_video_view_url(path.name),
            }
        )
    items.sort(key=lambda item: (item["mtime"], item["filename"]), reverse=True)
    return items


def _copy_mobile_gallery_image_to_input(filename):
    source = _mobile_output_file(filename)
    if not source.is_file() or source.suffix.lower() not in MOBILE_GALLERY_EXTENSIONS:
        raise ValueError("没有找到可用于视频的图片。")
    safe_name = f"video_src_{uuid.uuid4().hex[:12]}_{source.name}"
    target = (_mobile_video_input_dir() / safe_name).resolve()
    if target.parent != _mobile_video_input_dir():
        raise ValueError("视频输入文件路径无效。")
    shutil.copy2(source, target)
    return target, f"{MOBILE_VIDEO_INPUT_SUBFOLDER}/{safe_name}"


def _mobile_video_source_path(filename):
    raw_name = str(filename or "").replace("\\", "/").strip("/")
    safe_name = Path(raw_name).name
    if not safe_name:
        raise ValueError("没有找到可用于视频的图片。")
    if raw_name.startswith(f"{MOBILE_VIDEO_INPUT_SUBFOLDER}/"):
        source = (_mobile_video_input_dir() / safe_name).resolve()
        if source.parent == _mobile_video_input_dir() and source.is_file() and source.suffix.lower() in MOBILE_GALLERY_EXTENSIONS:
            return source, f"{MOBILE_VIDEO_INPUT_SUBFOLDER}/{safe_name}", True
    source = (_mobile_video_input_dir() / safe_name).resolve()
    if source.parent == _mobile_video_input_dir() and source.is_file() and source.suffix.lower() in MOBILE_GALLERY_EXTENSIONS:
        return source, f"{MOBILE_VIDEO_INPUT_SUBFOLDER}/{safe_name}", True
    source, image_load_name = _copy_mobile_gallery_image_to_input(safe_name)
    return source, image_load_name, False


def _mobile_job_output_prefix(prompt_id):
    prompt_id = str(prompt_id or "")
    for job in MOBILE_SESSION_JOBS:
        if str(job.get("prompt_id") or "") == prompt_id:
            return str(job.get("output_prefix") or "")
    return REMOTE_WS_OUTPUT_PREFIX_BY_PROMPT_ID.get(prompt_id, "")


def _mobile_local_images_for_prompt(prompt_id):
    prefix = _mobile_job_output_prefix(prompt_id)
    if not prefix:
        return []
    images = []
    output_dir = _mobile_local_output_dir()
    if not output_dir.is_dir():
        return images
    for path in sorted(output_dir.glob(f"{prefix}_*")):
        if path.suffix.lower() not in MOBILE_GALLERY_EXTENSIONS or not path.is_file() or path.stat().st_size <= 0:
            continue
        subfolder = _mobile_output_subfolder_for_path(path)
        images.append(
            {
                "filename": path.name,
                "subfolder": subfolder,
                "type": "output",
                "url": _mobile_view_url(path.name, subfolder),
            }
        )
    return images


async def _mobile_image_urls(prompt_id):
    local_images = _mobile_local_images_for_prompt(prompt_id)
    if local_images:
        return local_images
    history = PromptServer.instance.prompt_queue.get_history(prompt_id=prompt_id) or {}
    entry = history.get(prompt_id) if isinstance(history, dict) else None
    images = []
    if isinstance(entry, dict):
        for output in (entry.get("outputs") or {}).values():
            if not isinstance(output, dict):
                continue
            for image in output.get("images") or []:
                filename = image.get("filename", "")
                if not filename:
                    continue
                params = urllib.parse.urlencode(
                    {
                        "filename": filename,
                        "subfolder": image.get("subfolder", ""),
                        "type": image.get("type", "output"),
                    }
                )
                images.append({"url": f"/view?{params}", **image})
    return images


async def _mobile_remote_history_entry(prompt_id):
    if not REMOTE_COMFYUI_URL:
        return None
    entry, error = await _remote_history(prompt_id)
    if error:
        raise RuntimeError(error.get("error") or "远端历史记录读取失败。")
    return entry if isinstance(entry, dict) else None


def _remote_history_error_message(entry):
    status = (entry or {}).get("status")
    if not isinstance(status, dict) or status.get("status_str") != "error":
        return ""
    for message in reversed(status.get("messages") or []):
        if not isinstance(message, (list, tuple)) or len(message) < 2:
            continue
        if message[0] != "execution_error" or not isinstance(message[1], dict):
            continue
        node_type = str(message[1].get("node_type") or "远端节点")
        detail = str(message[1].get("exception_message") or message[1].get("exception_type") or "").strip()
        return f"{node_type} 执行失败：{detail}" if detail else f"{node_type} 执行失败。"
    return "远端任务执行失败。"


async def _mobile_video_urls(prompt_id):
    local_videos = _mobile_local_videos_for_prompt(prompt_id)
    if local_videos:
        return local_videos
    history = PromptServer.instance.prompt_queue.get_history(prompt_id=prompt_id) or {}
    entry = history.get(prompt_id) if isinstance(history, dict) else None
    videos = []
    if isinstance(entry, dict):
        for output in (entry.get("outputs") or {}).values():
            if not isinstance(output, dict):
                continue
            for key in ("videos", "gifs"):
                for video in output.get(key) or []:
                    filename = video.get("filename", "")
                    if not filename:
                        continue
                    params = urllib.parse.urlencode(
                        {
                            "filename": filename,
                            "subfolder": video.get("subfolder", ""),
                            "type": video.get("type", "output"),
                        }
                    )
                    item = {"url": f"/view?{params}", **video}
                    if video.get("subfolder") == MOBILE_VIDEO_OUTPUT_SUBFOLDER and filename:
                        path = _mobile_video_output_file(filename)
                        if path.is_file():
                            item.update(_video_dimensions_for_file(path))
                    videos.append(item)
    return videos


def _mobile_video_urls_sync(prompt_id):
    local_videos = _mobile_local_videos_for_prompt(prompt_id)
    if local_videos:
        return local_videos
    history = PromptServer.instance.prompt_queue.get_history(prompt_id=prompt_id) or {}
    entry = history.get(prompt_id) if isinstance(history, dict) else None
    videos = []
    if isinstance(entry, dict):
        for output in (entry.get("outputs") or {}).values():
            if not isinstance(output, dict):
                continue
            for key in ("videos", "gifs"):
                for video in output.get(key) or []:
                    filename = video.get("filename", "")
                    if not filename:
                        continue
                    params = urllib.parse.urlencode(
                        {
                            "filename": filename,
                            "subfolder": video.get("subfolder", ""),
                            "type": video.get("type", "output"),
                        }
                    )
                    item = {"url": f"/view?{params}", **video}
                    if video.get("subfolder") == MOBILE_VIDEO_OUTPUT_SUBFOLDER and filename:
                        path = _mobile_video_output_file(filename)
                        if path.is_file():
                            item.update(_video_dimensions_for_file(path))
                    videos.append(item)
    return videos


def _mobile_local_videos_for_prompt(prompt_id):
    """Return videos that the remote upload node has already written on this Mac."""
    job = next(
        (item for item in MOBILE_SESSION_JOBS if str(item.get("prompt_id") or "") == str(prompt_id or "")),
        {},
    )
    prefix = str(job.get("output_prefix") or "")
    videos = []
    output_dir = _mobile_video_output_dir()
    paths = []
    for receipt in job.get("received_videos", []) if isinstance(job, dict) else []:
        if not isinstance(receipt, dict):
            continue
        path = _mobile_video_output_file(receipt.get("filename", ""))
        if path not in paths:
            paths.append(path)
    if prefix:
        paths.extend(path for path in output_dir.glob(f"{prefix}_*") if path not in paths)
    for path in sorted(paths, key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True):
        if not path.is_file() or path.stat().st_size <= 0 or path.suffix.lower() not in MOBILE_VIDEO_EXTENSIONS:
            continue
        videos.append(
            {
                "filename": path.name,
                "subfolder": MOBILE_VIDEO_OUTPUT_SUBFOLDER,
                "type": "output",
                "url": _mobile_video_view_url(path.name),
                **_video_dimensions_for_file(path),
            }
        )
    return videos


def _remember_mobile_prompt_images(prompt_id, images):
    prompt = ""
    seed = None
    for job in MOBILE_SESSION_JOBS:
        if job.get("prompt_id") == prompt_id:
            prompt = job.get("prompt", "")
            seed = job.get("seed")
            break
    if not prompt:
        return
    for image in images:
        filename = image.get("filename")
        if image.get("type") == "runtime":
            image["prompt"] = prompt
            image["seed"] = seed
            for item in MOBILE_RUNTIME_IMAGES_BY_PROMPT_ID.get(str(prompt_id), []):
                if item.get("filename") == filename:
                    item["prompt"] = prompt
                    item["seed"] = seed
            continue
        if filename:
            _remember_mobile_prompt_file(filename, prompt, image.get("subfolder", ""), seed)
            image["prompt"] = prompt
            image["seed"] = seed


def _remember_mobile_prompt_videos(prompt_id, videos):
    prompt = ""
    for job in MOBILE_SESSION_JOBS:
        if job.get("prompt_id") == prompt_id:
            prompt = job.get("prompt", "")
            break
    if not prompt:
        return
    for video in videos:
        filename = video.get("filename")
        if filename and (
            video.get("subfolder") == MOBILE_VIDEO_OUTPUT_SUBFOLDER
            or any(filename.startswith(f"{job.get('output_prefix')}_") for job in MOBILE_SESSION_JOBS if job.get("prompt_id") == prompt_id and job.get("output_prefix"))
        ):
            MOBILE_VIDEO_PROMPT_BY_FILENAME[filename] = prompt
            video["prompt"] = prompt


async def _mobile_job_status(prompt_id):
    _ensure_mobile_session_jobs_loaded()
    prompt_id = str(prompt_id or "")
    media_type = next(
        (str(job.get("media_type") or "") for job in MOBILE_SESSION_JOBS if str(job.get("prompt_id") or "") == prompt_id),
        "",
    )
    running, pending = PromptServer.instance.prompt_queue.get_current_queue_volatile()
    if REMOTE_COMFYUI_URL:
        remote_running, remote_pending = await _remote_queue()
        if remote_running or remote_pending:
            running, pending = remote_running, remote_pending
    queue_ahead = _queue_waiting_count(prompt_id, running, pending)
    images = await _mobile_image_urls(prompt_id)
    videos = await _mobile_video_urls(prompt_id)
    _remember_mobile_prompt_images(prompt_id, images)
    _remember_mobile_prompt_videos(prompt_id, videos)
    history = PromptServer.instance.prompt_queue.get_history(prompt_id=prompt_id) or {}
    history_entry = history.get(prompt_id) if isinstance(history, dict) else None
    remote_entry = None
    remote_error = ""
    remote_finished = False
    remote_history_missing = False
    if REMOTE_COMFYUI_URL:
        try:
            remote_entry = await _mobile_remote_history_entry(prompt_id)
            remote_error = _remote_history_error_message(remote_entry)
            remote_status = (remote_entry or {}).get("status")
            remote_finished = isinstance(remote_status, dict) and remote_status.get("status_str") == "success"
            remote_history_missing = not remote_entry
        except Exception as exc:
            remote_error = str(exc)
    if images or videos:
        status = "completed"
    elif remote_error:
        status = "failed"
    elif remote_finished:
        if REMOTE_WS_IMAGE_RECEIVED_BY_PROMPT_ID.get(prompt_id):
            # 图片已由 WebSocket 流式回传落盘，但本次轮询的 images 快照可能尚未捕获；
            # 重新查询本地图（文件此时必然存在），确保前端能拿到图片 URL。
            images = await _mobile_image_urls(prompt_id)
            status = "completed"
        else:
            # grace 窗口必须从"远端完成时刻"起算，而非任务创建时刻：
            # 重图生成耗时可能远超 MOBILE_RESULT_RECEIVE_GRACE_SECONDS，
            # 若从创建时刻起算，远端一完成 elapsed 就已超窗，会误报"未收到图片"。
            if prompt_id not in REMOTE_FINISHED_AT_BY_PROMPT_ID:
                REMOTE_FINISHED_AT_BY_PROMPT_ID[prompt_id] = time.monotonic()
            elapsed = time.monotonic() - REMOTE_FINISHED_AT_BY_PROMPT_ID[prompt_id]
            grace_seconds = MOBILE_VIDEO_RESULT_RECEIVE_GRACE_SECONDS if media_type == "video" else MOBILE_RESULT_RECEIVE_GRACE_SECONDS
            status = "receiving" if elapsed <= grace_seconds else "failed"
    elif _queue_contains(prompt_id, running):
        status = "running"
    elif _queue_contains(prompt_id, pending):
        status = "pending"
    elif remote_history_missing:
        created_at = int(next((job.get("created_at", 0) for job in MOBILE_SESSION_JOBS if str(job.get("prompt_id")) == prompt_id), 0) or 0)
        elapsed = max(0, time.time() - (created_at / 1000)) if created_at else REMOTE_HISTORY_TIMEOUT + 1
        if elapsed > REMOTE_HISTORY_TIMEOUT:
            remote_error = "远端未保留该任务的历史记录，无法确认生成结果。"
            status = "failed"
        else:
            status = "running"
    elif remote_entry is not None:
        status = "running"
    elif _remote_history_error_message(history_entry):
        status = "failed"
    elif history_entry is not None:
        status = "completed"
    else:
        status = "unknown"
    if status in {"completed", "failed"}:
        before = len(MOBILE_SESSION_JOBS)
        MOBILE_SESSION_JOBS[:] = [job for job in MOBILE_SESSION_JOBS if str(job.get("prompt_id")) != prompt_id]
        if len(MOBILE_SESSION_JOBS) != before:
            _save_mobile_session_jobs()
    result = {"prompt_id": prompt_id, "status": status, "images": images, "videos": videos}
    if queue_ahead is not None:
        result["queue_ahead"] = queue_ahead
    if prompt_id in REMOTE_PROGRESS_BY_PROMPT_ID:
        result["progress"] = REMOTE_PROGRESS_BY_PROMPT_ID[prompt_id]
    if status == "failed":
        missing_result = "远端已完成，但 Mac 未收到视频回传。" if media_type == "video" else "远端已完成，但 Mac 未收到内存回传图片。"
        result["error"] = remote_error or _remote_history_error_message(history_entry) or missing_result
    return result


async def _mobile_active_job_count():
    count = 0
    for item in MOBILE_SESSION_JOBS:
        if (await _mobile_job_status(item.get("prompt_id", ""))).get("status") in {"running", "pending"}:
            count += 1
    return count


async def _mobile_session_job(item):
    status = await _mobile_job_status(item.get("prompt_id", ""))
    return {
        **item,
        "status": status.get("status", "unknown"),
        "images": status.get("images", []),
        "videos": status.get("videos", []),
        "node_total": item.get("node_total", 0),
        "progress": status.get("progress"),
        "queue_ahead": status.get("queue_ahead"),
    }


async def _active_mobile_session_jobs():
    _ensure_mobile_session_jobs_loaded()
    items = list(MOBILE_SESSION_JOBS)
    active_jobs = []
    changed = False
    for item in items:
        prompt_id = str(item.get("prompt_id") or "")
        if not prompt_id:
            changed = True
            continue
        status = await _mobile_job_status(prompt_id)
        state = status.get("status", "unknown")
        if state not in {"running", "pending", "receiving"}:
            changed = True
            continue
        active_jobs.append(
            {
                **item,
                "status": state,
                "images": status.get("images", []),
                "videos": status.get("videos", []),
                "node_total": item.get("node_total", 0),
                "progress": status.get("progress"),
                "error": status.get("error", ""),
            }
        )
    if changed:
        active_ids = {str(job.get("prompt_id") or "") for job in active_jobs}
        before = len(MOBILE_SESSION_JOBS)
        MOBILE_SESSION_JOBS[:] = [
            job for job in MOBILE_SESSION_JOBS if str(job.get("prompt_id") or "") in active_ids
        ]
        if len(MOBILE_SESSION_JOBS) != before:
            _save_mobile_session_jobs()
    return active_jobs


def _load_image_interrogator():
    if str(NODE_DIR) not in sys.path:
        sys.path.insert(0, str(NODE_DIR))
    from image_interrogator import ImageInterrogationError, interrogate_image_bytes

    return ImageInterrogationError, interrogate_image_bytes
