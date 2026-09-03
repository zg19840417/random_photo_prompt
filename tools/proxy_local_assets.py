#!/usr/bin/env python3
import json
import os
import re
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web


LOCAL_OUTPUT_DIR = Path(
    os.environ.get(
        "RPP_PROXY_OUTPUT_DIR",
        "/Users/zouge/Documents/Codex/2026-06-02/macbook-air-80/work/ComfyUI/output/4090 生成",
    )
).expanduser()
LOCAL_IMAGE_MAP_PATH = LOCAL_OUTPUT_DIR / ".remote_image_map.json"

CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

LOCAL_IMAGE_MAP = {}
LOCAL_ASSET_ID_MAP = {}


def output_subfolder_name():
    return LOCAL_OUTPUT_DIR.name


def map_storage_key(prompt_id, image):
    filename, subfolder, image_type = local_image_key(image)
    return "|".join((str(prompt_id or ""), filename, subfolder, image_type))


def load_local_image_map():
    if not LOCAL_IMAGE_MAP_PATH.is_file():
        return
    try:
        data = json.loads(LOCAL_IMAGE_MAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(data, dict):
        return
    for key, local_filename in data.items():
        parts = str(key).split("|", 3)
        if len(parts) == 4 and local_filename:
            prompt_id, filename, subfolder, image_type = parts
            LOCAL_IMAGE_MAP[(prompt_id, (filename, subfolder, image_type))] = str(local_filename)


def save_local_image_map():
    LOCAL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "|".join((prompt_id, filename, subfolder, image_type)): local_filename
        for (prompt_id, (filename, subfolder, image_type)), local_filename in LOCAL_IMAGE_MAP.items()
    }
    tmp_path = LOCAL_IMAGE_MAP_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(LOCAL_IMAGE_MAP_PATH)


def normal_local_asset_key(value):
    return str(value or "").replace("\\", "/").strip("/")


def local_asset_id_for_filename(filename):
    key = normal_local_asset_key(filename)
    if not key:
        key = Path(str(filename or "")).name
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"random-photo-prompt-local-asset:{key}"))


def local_asset_relative_name(path):
    try:
        return path.resolve().relative_to(LOCAL_OUTPUT_DIR.resolve()).as_posix()
    except Exception:
        return path.name


def local_asset_files():
    if not LOCAL_OUTPUT_DIR.is_dir():
        return []
    try:
        return [path for path in LOCAL_OUTPUT_DIR.iterdir() if path.is_file() and path.suffix.lower() in CONTENT_TYPES]
    except OSError:
        return []


def local_image_files_recursive():
    if not LOCAL_OUTPUT_DIR.is_dir():
        return []
    try:
        return [path for path in LOCAL_OUTPUT_DIR.rglob("*") if path.is_file() and path.suffix.lower() in CONTENT_TYPES]
    except OSError:
        return []


def refresh_local_asset_id_map():
    LOCAL_ASSET_ID_MAP.clear()
    for path in local_asset_files():
        rel_name = local_asset_relative_name(path)
        LOCAL_ASSET_ID_MAP[local_asset_id_for_filename(rel_name)] = rel_name


def local_asset_path_for_id(asset_id):
    asset_id = str(asset_id or "").strip()
    if not asset_id:
        return None
    for should_refresh in (False, True):
        if should_refresh:
            refresh_local_asset_id_map()
        rel_name = LOCAL_ASSET_ID_MAP.get(asset_id)
        if rel_name:
            path = (LOCAL_OUTPUT_DIR / normal_local_asset_key(rel_name)).resolve()
            try:
                path.relative_to(LOCAL_OUTPUT_DIR.resolve())
            except Exception:
                path = None
            if path and path.is_file():
                return path
    for path in local_asset_files():
        if local_asset_id_for_filename(path.name) == asset_id:
            return path
    return None


def iso_from_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def local_asset_payload(path):
    stat = path.stat()
    rel_name = local_asset_relative_name(path)
    asset_id = local_asset_id_for_filename(rel_name)
    created_at = iso_from_timestamp(stat.st_birthtime if hasattr(stat, "st_birthtime") else stat.st_mtime)
    updated_at = iso_from_timestamp(stat.st_mtime)
    rel_parent = Path(rel_name).parent.as_posix()
    subfolder = output_subfolder_name()
    if rel_parent and rel_parent != ".":
        subfolder = f"{subfolder}/{rel_parent}"
    preview_url = f"/view?{urllib.parse.urlencode({'filename': path.name, 'subfolder': subfolder, 'type': 'output'})}"
    return {
        "id": asset_id,
        "name": path.name,
        "hash": None,
        "asset_hash": None,
        "size": stat.st_size,
        "mime_type": CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream"),
        "tags": [],
        "user_metadata": {"filename": path.name, "subfolder": subfolder, "type": "output", "local_relative_path": rel_name},
        "metadata": {},
        "preview_url": preview_url,
        "preview_id": None,
        "prompt_id": None,
        "job_id": None,
        "created_at": created_at,
        "updated_at": updated_at,
        "last_access_time": updated_at,
        "is_immutable": False,
    }


def local_assets_response(request):
    files = local_asset_files()
    name_contains = str(request.query.get("name_contains") or "").strip().lower()
    if name_contains:
        files = [path for path in files if name_contains in path.name.lower()]
    reverse = str(request.query.get("order") or "desc").lower() != "asc"
    files.sort(key=lambda path: path.stat().st_mtime, reverse=reverse)
    total = len(files)
    try:
        limit = max(1, int(request.query.get("limit", "50")))
    except ValueError:
        limit = 50
    try:
        offset = max(0, int(request.query.get("offset", "0")))
    except ValueError:
        offset = 0
    page = files[offset : offset + limit]
    assets = [local_asset_payload(path) for path in page]
    return {"assets": assets, "total": total, "has_more": offset + len(page) < total}


def safe_local_path(image, local_filename=None, create_dirs=True):
    filename = Path(str(local_filename or image.get("filename") or "")).name
    if not filename:
        raise ValueError("missing filename")
    subfolder = str(image.get("subfolder") or "").replace("\\", "/").strip("/")
    output_dir = LOCAL_OUTPUT_DIR.resolve()
    output_name = output_dir.name
    if subfolder == output_name:
        subfolder = ""
    elif subfolder.startswith(f"{output_name}/"):
        subfolder = subfolder[len(output_name) + 1 :]
    if subfolder and any(part in {"", ".", ".."} for part in subfolder.split("/")):
        raise ValueError("unsafe subfolder")
    target_dir = (output_dir / subfolder).resolve() if subfolder else output_dir
    if target_dir != output_dir and output_dir not in target_dir.parents:
        raise ValueError("unsafe target")
    if create_dirs:
        target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / filename


def local_image_key(image):
    return (
        Path(str(image.get("filename") or "")).name,
        str(image.get("subfolder") or "").replace("\\", "/").strip("/"),
        str(image.get("type") or "output"),
    )


def unique_local_filename(image, prompt_id=""):
    filename = Path(str(image.get("filename") or "")).name
    if not filename:
        raise ValueError("missing filename")
    stem = Path(filename).stem
    suffix = Path(filename).suffix or ".png"
    token = str(prompt_id or "").replace("-", "")[:12]
    if not token:
        token = "remote"
    return f"{stem}_{token}{suffix}"


def local_subfolder_for_download(image):
    subfolder = str(image.get("subfolder") or "").replace("\\", "/").strip("/")
    if str(image.get("type") or "output") == "temp":
        return ""
    return subfolder


def image_capture_priority(image):
    filename = Path(str(image.get("filename") or "")).name
    subfolder = str(image.get("subfolder") or "").replace("\\", "/").strip("/")
    image_type = str(image.get("type") or "output")
    if not filename:
        return -1
    if image_type == "output":
        return 100
    if subfolder == "PreviewBridge" and filename.startswith("PB-_temp_"):
        return 80
    if filename.startswith("ComfyUI_temp_"):
        return -1
    if filename.startswith("rgthree.compare._temp_"):
        return -1
    return 10 if image_type == "temp" else 20


def history_image_candidates(entry):
    if not isinstance(entry, dict):
        return []
    candidates = []
    seen = set()
    for output in (entry.get("outputs") or {}).values():
        if not isinstance(output, dict):
            continue
        for image in output.get("images") or []:
            if not isinstance(image, dict) or not image.get("filename"):
                continue
            key = (image.get("filename"), image.get("subfolder"), image.get("type", "output"))
            if key in seen:
                continue
            seen.add(key)
            priority = image_capture_priority(image)
            if priority < 0:
                continue
            candidates.append((priority, dict(image)))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [image for _priority, image in candidates]


def local_path_candidates(filename, subfolder):
    image = {"filename": filename, "subfolder": subfolder}
    try:
        yield safe_local_path(image, create_dirs=False)
    except Exception:
        pass
    safe_subfolder = str(subfolder or "").replace("\\", "/").strip("/")
    output_name = LOCAL_OUTPUT_DIR.name
    if safe_subfolder == output_name:
        try:
            yield safe_local_path({"filename": filename, "subfolder": ""}, create_dirs=False)
        except Exception:
            pass
    elif safe_subfolder.startswith(f"{output_name}/"):
        try:
            yield safe_local_path({"filename": filename, "subfolder": safe_subfolder[len(output_name) + 1 :]}, create_dirs=False)
        except Exception:
            pass
    raw_name = str(filename or "").replace("\\", "/").strip("/")
    if raw_name and "/" in raw_name:
        try:
            candidate = (LOCAL_OUTPUT_DIR.resolve() / raw_name).resolve()
            candidate.relative_to(LOCAL_OUTPUT_DIR.resolve())
            yield candidate
        except Exception:
            pass
    basename = Path(str(filename or "")).name
    if basename:
        for path in local_image_files_recursive():
            if path.name == basename:
                yield path


def mapped_local_filename_for_remote(filename, subfolder="", image_type="output"):
    key = (Path(str(filename or "")).name, str(subfolder or "").replace("\\", "/").strip("/"), str(image_type or "output"))
    for (_prompt_id, remote_key), local_filename in LOCAL_IMAGE_MAP.items():
        if remote_key != key:
            continue
        if any(path.is_file() for path in local_path_candidates(local_filename, "")):
            return local_filename
    return ""


def forget_local_image_mapping(local_filename):
    local_filename = Path(str(local_filename or "")).name
    if not local_filename:
        return 0
    removed = 0
    for key, mapped in list(LOCAL_IMAGE_MAP.items()):
        if Path(str(mapped or "")).name == local_filename:
            LOCAL_IMAGE_MAP.pop(key, None)
            removed += 1
    if removed:
        save_local_image_map()
    return removed


def local_asset_candidates_from_request_payload(data):
    names = []
    asset_ids = []

    def collect(value):
        if isinstance(value, dict):
            for key in ("id", "asset_id", "assetId", "reference_id", "referenceId"):
                item = value.get(key)
                if item:
                    asset_ids.append(str(item))
            for key in ("filename", "name", "path", "file_path"):
                item = value.get(key)
                if item:
                    names.append(item)
            preview_url = value.get("preview_url") or value.get("url")
            if preview_url:
                parsed = urllib.parse.urlparse(str(preview_url))
                query = urllib.parse.parse_qs(parsed.query)
                filename = (query.get("filename") or [""])[0]
                subfolder = (query.get("subfolder") or [""])[0]
                if filename:
                    names.append(f"{subfolder}/{filename}" if subfolder else filename)
            for item in value.values():
                if isinstance(item, (dict, list, tuple)):
                    collect(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item)

    if isinstance(data, (dict, list, tuple)):
        collect(data)
    candidates = []
    for asset_id in asset_ids:
        path = local_asset_path_for_id(asset_id)
        if path:
            candidates.append(path)
    for raw_name in names:
        raw_name = str(raw_name or "").replace("\\", "/").strip("/")
        if not raw_name:
            continue
        if "/" in raw_name:
            subfolder, filename = raw_name.rsplit("/", 1)
        else:
            subfolder, filename = "", raw_name
        candidates.extend(local_path_candidates(filename, subfolder))
    return candidates


def local_asset_candidates_from_path(path):
    parsed = urllib.parse.urlparse(str(path or ""))
    request_path = parsed.path
    query = urllib.parse.parse_qs(parsed.query)
    candidates = []
    asset_match = re.fullmatch(r"/(?:api/)?assets/([^/?#]+)", request_path)
    if asset_match:
        local_path = local_asset_path_for_id(urllib.parse.unquote(asset_match.group(1)))
        if local_path:
            candidates.append(local_path)
    filename = (query.get("filename") or query.get("name") or [""])[0]
    subfolder = (query.get("subfolder") or [""])[0]
    if filename:
        candidates.extend(local_path_candidates(filename, subfolder))
    return candidates


async def delete_local_paths(paths, asset_id="", logger=None):
    deleted = 0
    missing = 0
    seen = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        try:
            if path.is_file():
                path.unlink()
                deleted += 1
                forget_local_image_mapping(path.name)
                if logger:
                    logger(f"local asset delete ok id={asset_id} path={path}")
            else:
                missing += 1
        except Exception as exc:
            if logger:
                logger(f"local asset delete failed id={asset_id} path={path} error={exc}")
    return {"deleted": deleted, "missing": missing}


def local_view_response(path):
    suffix = path.suffix.lower()
    return web.FileResponse(path, headers={"Content-Type": CONTENT_TYPES.get(suffix, "application/octet-stream")})
