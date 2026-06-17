#!/usr/bin/env python3
import asyncio
import html
import json
import os
import re
import struct
import sys
import urllib.parse
import uuid
from copy import deepcopy
from ipaddress import ip_address, ip_network
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from tools import proxy_local_assets as local_assets
from tools import proxy_config
from tools import proxy_runtime_state as runtime
from tools import proxy_workflow_patch as workflow_patch


REMOTE_URL = proxy_config.REMOTE_URL
LOCAL_MOBILE_URL = proxy_config.LOCAL_MOBILE_URL
LOCAL_OUTPUT_DIR = local_assets.LOCAL_OUTPUT_DIR
POLL_SECONDS = float(proxy_config.POLL_SECONDS or 1.5)
HISTORY_TIMEOUT = float(proxy_config.HISTORY_TIMEOUT or 900)
DELETE_REMOTE_OUTPUT = str(proxy_config.DELETE_REMOTE_OUTPUT).strip().lower() not in {"0", "false", "no", "off"}
USE_WEBSOCKET_OUTPUT = str(proxy_config.WEBSOCKET_OUTPUT).strip().lower() not in {"0", "false", "no", "off"}

CLIENT_TIMEOUT = ClientTimeout(total=None, sock_connect=30, sock_read=None)
LOCAL_IMAGE_MAP = local_assets.LOCAL_IMAGE_MAP
PROMPT_PROGRESS = runtime.PROMPT_PROGRESS
PROMPT_OUTPUT_PREFIX = runtime.PROMPT_OUTPUT_PREFIX
PROMPT_WS_WATCHERS = runtime.PROMPT_WS_WATCHERS
PROMPT_WS_IMAGE_INDEX = runtime.PROMPT_WS_IMAGE_INDEX
WS_OUTPUT_NODE_IDS = runtime.WS_OUTPUT_NODE_IDS
PROMPT_NODE_TOTAL = runtime.PROMPT_NODE_TOTAL


def _mobile_origin_for_request(request):
    explicit = str(request.headers.get("X-RPP-Mobile-Origin") or "").strip().lower()
    if explicit in {"phone", "mac"}:
        return explicit
    user_agent = str(request.headers.get("User-Agent") or "")
    if re.search(r"iPhone|Android.+Mobile|Mobile.+Android", user_agent, re.I):
        return "phone"
    if re.search(r"Macintosh|Windows NT", user_agent, re.I):
        return "mac"
    remote = str(request.remote or "").strip()
    forwarded = str(request.headers.get("X-Forwarded-For") or "").split(",", 1)[0].strip()
    if forwarded:
        remote = forwarded
    try:
        addr = ip_address(remote)
    except Exception:
        return "mac"
    if addr.is_loopback:
        return "mac"
    private_lans = (
        ip_network("10.0.0.0/8"),
        ip_network("172.16.0.0/12"),
        ip_network("192.168.0.0/16"),
    )
    return "phone" if any(addr in network for network in private_lans) else "mac"


_load_local_image_map = local_assets.load_local_image_map
_local_asset_path_for_id = local_assets.local_asset_path_for_id
_local_asset_payload = local_assets.local_asset_payload
_local_assets_response = local_assets.local_assets_response
_save_local_image_map = local_assets.save_local_image_map
_refresh_local_asset_id_map = local_assets.refresh_local_asset_id_map
_local_asset_candidates_from_request_payload = local_assets.local_asset_candidates_from_request_payload
_local_view_response = local_assets.local_view_response


def _log(message):
    print(f"[rpp-proxy] {message}", file=sys.stderr, flush=True)


def _remember_active_prompt(prompt_id):
    runtime.remember_active_prompt(prompt_id)


def _forget_active_prompt(prompt_id):
    runtime.forget_active_prompt(prompt_id)


def _clear_runtime_state(reason=""):
    return runtime.clear_runtime_state(reason, logger=_log)


def _active_prompt_for_progress(data):
    return runtime.active_prompt_for_progress(data)


def _remember_progress_message(message):
    runtime.remember_progress_message(message)


_ensure_unique_save_prefix = workflow_patch.ensure_unique_save_prefix


_safe_local_path = local_assets.safe_local_path
_local_image_key = local_assets.local_image_key
_unique_local_filename = local_assets.unique_local_filename
_local_subfolder_for_download = local_assets.local_subfolder_for_download
_history_image_candidates = local_assets.history_image_candidates
_local_path_candidates = local_assets.local_path_candidates
_mapped_local_filename_for_remote = local_assets.mapped_local_filename_for_remote


async def _local_asset_candidates_for_asset_id(asset_id):
    local_path = _local_asset_path_for_id(asset_id)
    if local_path:
        return [local_path]
    response, body = await _remote_request("GET", f"/api/assets/{urllib.parse.quote(str(asset_id))}", timeout=ClientTimeout(total=15))
    if response.status >= 400:
        _log(f"asset detail fetch failed id={asset_id} status={response.status}")
        return []
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception as exc:
        _log(f"asset detail parse failed id={asset_id} error={exc}")
        return []
    candidates = []
    prompt_id = str(data.get("job_id") or data.get("prompt_id") or "").strip()
    metadata = data.get("user_metadata") if isinstance(data.get("user_metadata"), dict) else {}
    preview_url = str(data.get("preview_url") or "")
    names = [
        metadata.get("filename"),
        data.get("name"),
    ]
    if preview_url:
        parsed = urllib.parse.urlparse(preview_url)
        query = urllib.parse.parse_qs(parsed.query)
        filename = (query.get("filename") or [""])[0]
        subfolder = (query.get("subfolder") or [""])[0]
        image_type = (query.get("type") or ["output"])[0]
        if filename:
            names.append(f"{subfolder}/{filename}" if subfolder else filename)
            mapped = LOCAL_IMAGE_MAP.get((prompt_id, (Path(filename).name, subfolder.replace("\\", "/").strip("/"), image_type)))
            if mapped:
                names.append(mapped)
            mapped = _mapped_local_filename_for_remote(filename, subfolder, image_type)
            if mapped:
                names.append(mapped)
    for raw_name in names:
        raw_name = str(raw_name or "").replace("\\", "/").strip("/")
        if not raw_name:
            continue
        if "/" in raw_name:
            subfolder, filename = raw_name.rsplit("/", 1)
        else:
            subfolder, filename = "", raw_name
        mapped = LOCAL_IMAGE_MAP.get((prompt_id, (Path(filename).name, subfolder, "output"))) or _mapped_local_filename_for_remote(filename, subfolder, "output")
        if mapped:
            candidates.extend(_local_path_candidates(mapped, ""))
        candidates.extend(_local_path_candidates(filename, subfolder))
    unique = []
    seen = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


async def _delete_local_paths(paths, asset_id=""):
    return await local_assets.delete_local_paths(paths, asset_id, logger=_log)


async def _delete_local_assets_from_request(request, path, body, asset_id=""):
    candidates = []
    if asset_id:
        candidates.extend(await _local_asset_candidates_for_asset_id(asset_id))
    candidates.extend(local_assets.local_asset_candidates_from_path(path))
    if body:
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            data = None
        candidates.extend(local_assets.local_asset_candidates_from_request_payload(data))
    result = await _delete_local_paths(candidates, asset_id)
    if result["deleted"]:
        _refresh_local_asset_id_map()
    return result


async def _remote_request(method, path, **kwargs):
    timeout = kwargs.pop("timeout", CLIENT_TIMEOUT)
    async with ClientSession(timeout=timeout) as session:
        async with session.request(method, f"{REMOTE_URL}{path}", **kwargs) as response:
            body = await response.read()
            return response, body


def _replace_save_nodes_with_websocket(payload):
    return workflow_patch.replace_save_nodes_with_websocket(payload, use_websocket_output=USE_WEBSOCKET_OUTPUT)


_unpatched_save_node_classes = workflow_patch.unpatched_save_node_classes
_patch_web_prompt_resolution = workflow_patch.patch_web_prompt_resolution
_patch_web_zib_single_steps = workflow_patch.patch_web_zib_single_steps
_patch_web_zimage_weight_dtype = workflow_patch.patch_web_zimage_weight_dtype
_patch_web_disable_model_purge = workflow_patch.patch_web_disable_model_purge


def _image_extension_from_bytes(image_bytes, image_type=0):
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") or image_type == 2:
        return ".png"
    if image_bytes.startswith(b"\xff\xd8\xff") or image_type == 1:
        return ".jpg"
    return ".png"


def _unique_uploaded_filename(prefix="remote_web", suffix=".png"):
    safe_prefix = Path(str(prefix or "remote_web").replace("\\", "/").strip("/")).name or "remote_web"
    safe_prefix = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in safe_prefix).strip("_") or "remote_web"
    return f"{safe_prefix}_{int(asyncio.get_event_loop().time() * 1000)}_{uuid.uuid4().hex[:8]}{suffix or '.png'}"


def _comfy_output_subfolder_for_local_output():
    return LOCAL_OUTPUT_DIR.name


def _save_websocket_image(prompt_id, image_bytes, image_type=0):
    prompt_id = str(prompt_id or "").strip()
    if not prompt_id or not image_bytes:
        return None
    prefix = PROMPT_OUTPUT_PREFIX.get(prompt_id) or f"mobile_{prompt_id.replace('-', '')[:12]}"
    index = PROMPT_WS_IMAGE_INDEX.get(prompt_id, 0) + 1
    PROMPT_WS_IMAGE_INDEX[prompt_id] = index
    suffix = _image_extension_from_bytes(image_bytes, image_type)
    filename = f"{prefix}_{index:05d}{suffix}"
    local_path = _safe_local_path({"filename": filename, "subfolder": ""})
    tmp_path = local_path.with_name(f".{local_path.name}.tmp")
    tmp_path.write_bytes(image_bytes)
    if not tmp_path.is_file() or tmp_path.stat().st_size <= 0:
        raise RuntimeError("websocket image temp file was not written")
    tmp_path.replace(local_path)
    LOCAL_IMAGE_MAP[(prompt_id, (filename, "", "output"))] = filename
    _save_local_image_map()
    _log(f"websocket image saved prompt_id={prompt_id} path={local_path} bytes={len(image_bytes)}")
    return local_path


async def _watch_prompt_websocket_output(prompt_ref, client_id, ready_event=None, output_nodes=None, output_prefix="", node_total=0):
    if isinstance(prompt_ref, dict):
        prompt_id = str(prompt_ref.get("value") or "").strip()
    else:
        prompt_id = str(prompt_ref or "").strip()
    client_id = str(client_id or "").strip()
    if not client_id:
        return
    remote_url = REMOTE_URL.replace("http://", "ws://").replace("https://", "wss://") + f"/ws?clientId={urllib.parse.quote(client_id)}"
    current_node = ""
    saved = 0
    seen_nodes = []
    node_total = max(1, int(node_total or 0))
    try:
        async with ClientSession(timeout=CLIENT_TIMEOUT) as session:
            async with session.ws_connect(remote_url) as ws:
                if ready_event:
                    ready_event.set()
                async for msg in ws:
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
                                WS_OUTPUT_NODE_IDS[prompt_id] = set(output_nodes)
                            if output_prefix:
                                PROMPT_OUTPUT_PREFIX[prompt_id] = output_prefix
                        if message.get("type") != "executing":
                            continue
                        if message_prompt_id and prompt_id and message_prompt_id != prompt_id:
                            continue
                        current_node = str(data.get("node") or "")
                        if not current_node:
                            if prompt_id:
                                PROMPT_PROGRESS[prompt_id] = {
                                    "value": node_total,
                                    "max": node_total,
                                    "percent": 100,
                                    "node": "",
                                    "type": "node",
                                }
                            break
                        if current_node not in seen_nodes:
                            seen_nodes.append(current_node)
                        if prompt_id:
                            value = max(1, min(node_total, len(seen_nodes)))
                            PROMPT_PROGRESS[prompt_id] = {
                                "value": value,
                                "max": node_total,
                                "percent": max(0, min(100, round((value / node_total) * 100))),
                                "node": current_node,
                                "type": "node",
                            }
                    elif msg.type == WSMsgType.BINARY:
                        ws_nodes = WS_OUTPUT_NODE_IDS.get(prompt_id) or set()
                        raw = bytes(msg.data)
                        if len(raw) <= 8:
                            continue
                        event_type = struct.unpack(">I", raw[:4])[0]
                        if event_type != 1:
                            continue
                        image_type = struct.unpack(">I", raw[4:8])[0]
                        if ws_nodes and current_node not in ws_nodes:
                            continue
                        _save_websocket_image(prompt_id, raw[8:], image_type)
                        saved += 1
        _log(f"websocket watcher done prompt_id={prompt_id} images={saved}")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _log(f"websocket watcher failed prompt_id={prompt_id} error={exc}")


async def _local_mobile_request(method, path, **kwargs):
    timeout = kwargs.pop("timeout", CLIENT_TIMEOUT)
    async with ClientSession(timeout=timeout) as session:
        async with session.request(method, f"{LOCAL_MOBILE_URL}{path}", **kwargs) as response:
            body = await response.read()
            return response, body


async def _probe_url(url, path="/", timeout=5):
    target = f"{url.rstrip('/')}{path}"
    try:
        async with ClientSession(timeout=ClientTimeout(total=timeout)) as session:
            async with session.get(target) as response:
                await response.read()
                return {"ok": response.status < 500, "status": response.status, "error": ""}
    except Exception as exc:
        return {"ok": False, "status": 0, "error": str(exc)}


async def _probe_remote_delete_endpoint(timeout=5):
    payload = {"filename": "__random_photo_prompt_probe__.png", "subfolder": "", "type": "output"}
    try:
        response, body = await _remote_request(
            "POST",
            "/random_photo_prompt/remote/delete_output",
            json=payload,
            timeout=ClientTimeout(total=timeout),
        )
        text = body.decode("utf-8", "ignore")
        ok = response.status < 500 and "缺少文件名" not in text and "404" not in text
        return {"ok": ok, "status": response.status, "error": "" if ok else text[:200]}
    except Exception as exc:
        return {"ok": False, "status": 0, "error": str(exc)}


async def _download_remote_image(image, prompt_id=""):
    mapped = LOCAL_IMAGE_MAP.get((prompt_id, _local_image_key(image)))
    if mapped and any(path.is_file() for path in _local_path_candidates(mapped, "")):
        _log(f"download skipped mapped filename={image.get('filename')} local={mapped} prompt_id={prompt_id}")
        await _delete_remote_image(image)
        return _safe_local_path({"filename": mapped, "subfolder": ""})

    local_filename = _unique_local_filename(image, prompt_id)
    local_path = _safe_local_path({**image, "subfolder": _local_subfolder_for_download(image)}, local_filename)
    _log(f"download start filename={image.get('filename')} local={local_filename} subfolder={image.get('subfolder', '')} type={image.get('type', 'output')}")
    tmp_path = local_path.with_name(f".{local_path.name}.tmp")
    params = urllib.parse.urlencode(
        {
            "filename": image.get("filename", ""),
            "subfolder": image.get("subfolder", ""),
            "type": image.get("type", "output"),
        }
    )
    response, body = await _remote_request("GET", f"/view?{params}", timeout=ClientTimeout(total=180))
    if response.status >= 400:
        detail = body.decode("utf-8", "ignore")
        raise RuntimeError(f"download failed status={response.status} body={detail[:300]}")
    if not body:
        raise RuntimeError("download failed: empty image body")
    tmp_path.write_bytes(body)
    if not tmp_path.is_file() or tmp_path.stat().st_size <= 0:
        raise RuntimeError("download failed: temp file was not written")
    tmp_path.replace(local_path)
    LOCAL_IMAGE_MAP[(prompt_id, _local_image_key(image))] = local_filename
    _save_local_image_map()
    _log(f"download ok path={local_path} bytes={len(body)}")
    if local_path.is_file() and local_path.stat().st_size > 0:
        await _delete_remote_image(image)
    else:
        _log(f"remote delete skipped because local copy is missing filename={image.get('filename')}")
    return local_path


async def _delete_remote_image(image):
    if not DELETE_REMOTE_OUTPUT:
        return
    payload = {
        "filename": image.get("filename", ""),
        "subfolder": image.get("subfolder", ""),
        "type": image.get("type", "output"),
    }
    for attempt in range(1, 7):
        try:
            response, body = await _remote_request(
                "POST",
                "/random_photo_prompt/remote/delete_output",
                json=payload,
                timeout=ClientTimeout(total=30),
            )
            if response.status < 400:
                _log(f"remote delete ok filename={payload['filename']} subfolder={payload['subfolder']} attempt={attempt}")
                return
            detail = body.decode("utf-8", "ignore")[:300]
            _log(f"remote delete failed status={response.status} attempt={attempt} body={detail}")
        except Exception as exc:
            _log(f"remote delete exception filename={payload['filename']} attempt={attempt} error={exc}")
        await asyncio.sleep(min(10, attempt * 2))


async def _history(prompt_id):
    response, body = await _remote_request("GET", f"/history/{urllib.parse.quote(prompt_id)}", timeout=ClientTimeout(total=60))
    if response.status >= 400:
        return None
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        return None
    return data.get(prompt_id) if isinstance(data, dict) and prompt_id in data else data


async def _capture_images_from_entry(prompt_id, entry):
    found = 0
    for image in _history_image_candidates(entry)[:1]:
        if _image_has_local_mapping(prompt_id, image):
            await _delete_remote_image(image)
            continue
        try:
            await _download_remote_image(image, prompt_id)
        except Exception as exc:
            _log(f"history download failed prompt_id={prompt_id} filename={image.get('filename')} error={exc}")
        found += 1
    return found


async def _capture_prompt_outputs(prompt_id):
    _log(f"capture start prompt_id={prompt_id}")
    deadline = asyncio.get_running_loop().time() + HISTORY_TIMEOUT
    seen = set()
    while asyncio.get_running_loop().time() < deadline:
        try:
            entry = await _history(prompt_id)
        except Exception as exc:
            _log(f"history fetch failed prompt_id={prompt_id} error={exc}")
            entry = None
        if isinstance(entry, dict):
            for image in _history_image_candidates(entry)[:1]:
                key = (image.get("filename"), image.get("subfolder"), image.get("type", "output"))
                if key in seen:
                    continue
                if _image_has_local_mapping(prompt_id, image):
                    seen.add(key)
                    await _delete_remote_image(image)
                    continue
                seen.add(key)
                try:
                    await _download_remote_image(image, prompt_id)
                except Exception as exc:
                    _log(f"capture download failed prompt_id={prompt_id} filename={image.get('filename')} error={exc}")
            if seen:
                _log(f"capture done prompt_id={prompt_id} images={len(seen)}")
                return
        await asyncio.sleep(POLL_SECONDS)
    _log(f"capture timeout prompt_id={prompt_id}")


def _image_has_local_mapping(prompt_id, image):
    mapped = LOCAL_IMAGE_MAP.get((prompt_id, _local_image_key(image)))
    return bool(mapped and any(path.is_file() for path in _local_path_candidates(mapped, "")))


async def _rewrite_image_to_local(image, prompt_id=""):
    if not isinstance(image, dict) or not image.get("filename"):
        return False
    mapped = LOCAL_IMAGE_MAP.get((prompt_id, _local_image_key(image))) or _mapped_local_filename_for_remote(
        image.get("filename"), image.get("subfolder", ""), image.get("type", "output")
    )
    if not mapped or not any(path.is_file() for path in _local_path_candidates(mapped, "")):
        return False
    image["filename"] = mapped
    image["subfolder"] = _comfy_output_subfolder_for_local_output()
    image["type"] = "output"
    return True


async def _rewrite_ws_message_images_to_local(message):
    if not isinstance(message, dict):
        return message
    data = message.get("data")
    if not isinstance(data, dict):
        return message
    prompt_id = str(data.get("prompt_id") or "")

    output = data.get("output")
    if isinstance(output, dict):
        for image in output.get("images") or []:
            await _rewrite_image_to_local(image, prompt_id)

    outputs = data.get("outputs")
    if isinstance(outputs, dict):
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            for image in node_output.get("images") or []:
                await _rewrite_image_to_local(image, prompt_id)
    return message


def _rewrite_history_images_to_local(data):
    def rewrite_entry(entry, prompt_id=""):
        if not isinstance(entry, dict):
            return
        for output in (entry.get("outputs") or {}).values():
            if not isinstance(output, dict):
                continue
            kept_images = []
            for image in output.get("images") or []:
                filename = image.get("filename")
                if not filename:
                    continue
                mapped = LOCAL_IMAGE_MAP.get((prompt_id, _local_image_key(image)))
                if mapped and any(path.is_file() for path in _local_path_candidates(mapped, "")):
                    image["filename"] = mapped
                    image["subfolder"] = _comfy_output_subfolder_for_local_output()
                    image["type"] = "output"
                    kept_images.append(image)
                    continue
                if any(path.is_file() for path in _local_path_candidates(filename, image.get("subfolder", ""))):
                    kept_images.append(image)
            if "images" in output:
                output["images"] = kept_images

    if isinstance(data, dict):
        if "outputs" in data:
            rewrite_entry(data)
        else:
            for prompt_id, entry in data.items():
                rewrite_entry(entry, prompt_id)
    return data


def _clone_headers(response):
    skip = {"content-length", "content-encoding", "transfer-encoding"}
    return {key: value for key, value in response.headers.items() if key.lower() not in skip}


async def handle_prompt(request):
    body = await request.read()
    headers = {"Content-Type": request.headers.get("Content-Type", "application/json")}
    remote_path = request.path
    client_id = ""
    use_internal_watcher = False
    output_prefix = ""
    websocket_node_ids = []
    websocket_watcher = None
    prompt_ref = {"value": ""}
    node_total = 0
    try:
        payload = json.loads(body.decode("utf-8"))
        client_id = str(payload.get("client_id") or "").strip()
        if not client_id:
            client_id = f"rpp_proxy_{uuid.uuid4().hex}"
            payload["client_id"] = client_id
            use_internal_watcher = True
        prefix_token = uuid.uuid4().hex
        zib_steps_patch = _patch_web_zib_single_steps(payload)
        resolution_patch = _patch_web_prompt_resolution(payload)
        weight_dtype_patch = _patch_web_zimage_weight_dtype(payload)
        purge_patch = _patch_web_disable_model_purge(payload)
        changed = _ensure_unique_save_prefix(payload, prefix_token)
        ws_changed, output_prefix, websocket_node_ids = _replace_save_nodes_with_websocket(payload)
        prompt = payload.get("prompt")
        node_total = len(prompt) if isinstance(prompt, dict) else 0
        unpatched_save_classes = _unpatched_save_node_classes(payload)
        if unpatched_save_classes:
            detail = ", ".join(sorted(set(unpatched_save_classes))) or "unknown"
            _log(f"prompt rejected unpatched_save_nodes classes={detail}")
            return web.json_response(
                {
                    "error": "远端代理未能把网页版保存节点改为 Mac 本地回传，已阻止提交，避免资产落到远端。",
                    "node_errors": {},
                },
                status=400,
            )
        if (
            changed
            or ws_changed
            or client_id
            or resolution_patch
            or zib_steps_patch.get("steps_changed")
            or weight_dtype_patch.get("weight_dtype_changed")
            or purge_patch.get("purge_models_disabled")
        ):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if zib_steps_patch.get("zib_model"):
                _log(
                    "prompt zib single steps patch "
                    f"ksamplers={zib_steps_patch.get('ksamplers')} "
                    f"changed={zib_steps_patch.get('steps_changed')} "
                    f"old={zib_steps_patch.get('old_steps')} "
                    f"new={zib_steps_patch.get('new_steps')}"
                )
            if resolution_patch:
                _log(
                    "prompt resolution patched "
                    f"target={resolution_patch.get('target_width')}x{resolution_patch.get('target_height')} "
                    f"base={resolution_patch.get('base_width')}x{resolution_patch.get('base_height')} "
                    f"scale={resolution_patch.get('output_scale')}"
                )
            if purge_patch.get("purge_models_disabled"):
                _log(f"prompt disabled PurgeVRAM purge_models nodes={purge_patch.get('purge_models_disabled')}")
            if weight_dtype_patch.get("weight_dtype_changed"):
                _log(
                    "prompt z-image weight_dtype patched "
                    f"nodes={weight_dtype_patch.get('weight_dtype_changed')} "
                    f"old={','.join(weight_dtype_patch.get('old_values') or [])} "
                    "new=default"
                )
            _log(f"prompt patched save_nodes={changed} websocket_nodes={ws_changed} token={prefix_token[:12]}")
        if USE_WEBSOCKET_OUTPUT and websocket_node_ids and use_internal_watcher:
            ready_event = asyncio.Event()
            websocket_watcher = asyncio.create_task(
                _watch_prompt_websocket_output(
                    prompt_ref,
                    client_id,
                    ready_event=ready_event,
                    output_nodes=websocket_node_ids,
                    output_prefix=output_prefix,
                    node_total=node_total,
                )
            )
            await asyncio.wait_for(ready_event.wait(), timeout=10)
    except Exception as exc:
        if websocket_watcher:
            websocket_watcher.cancel()
        _log(f"prompt save prefix unchanged error={exc}")
    _log(f"prompt submit path={remote_path} bytes={len(body)}")
    response, remote_body = await _remote_request("POST", remote_path, data=body, headers=headers)
    if response.status >= 400 and websocket_watcher:
        websocket_watcher.cancel()
    if response.status < 400:
        try:
            data = json.loads(remote_body.decode("utf-8"))
            prompt_id = str(data.get("prompt_id") or "")
        except Exception:
            prompt_id = ""
        if prompt_id:
            prompt_ref["value"] = prompt_id
            _log(f"prompt accepted prompt_id={prompt_id}")
            _remember_active_prompt(prompt_id)
            if node_total:
                PROMPT_NODE_TOTAL[prompt_id] = node_total
            if output_prefix:
                PROMPT_OUTPUT_PREFIX[prompt_id] = output_prefix
            if websocket_node_ids:
                WS_OUTPUT_NODE_IDS[prompt_id] = set(websocket_node_ids)
            if USE_WEBSOCKET_OUTPUT and client_id and websocket_node_ids and use_internal_watcher:
                old = PROMPT_WS_WATCHERS.pop(prompt_id, None)
                if old:
                    old.cancel()
                PROMPT_WS_WATCHERS[prompt_id] = websocket_watcher
            asyncio.create_task(_capture_prompt_outputs(prompt_id))
        else:
            _log(f"prompt accepted but response has no prompt_id body={remote_body[:300]!r}")
    return web.Response(body=remote_body, status=response.status, headers=_clone_headers(response))


async def handle_history(request):
    response, remote_body = await _remote_request(request.method, request.path_qs)
    if response.status >= 400:
        return web.Response(body=remote_body, status=response.status, headers=_clone_headers(response))
    try:
        data = json.loads(remote_body.decode("utf-8"))
    except Exception:
        return web.Response(body=remote_body, status=response.status, headers=_clone_headers(response))
    prompt_id = request.match_info.get("prompt_id", "")
    if prompt_id:
        entry = data.get(prompt_id) if isinstance(data, dict) else data
        if isinstance(entry, dict):
            asyncio.create_task(_capture_images_from_entry(prompt_id, entry))
    rewritten = json.dumps(_rewrite_history_images_to_local(deepcopy(data)), ensure_ascii=False).encode("utf-8")
    headers = _clone_headers(response)
    headers["Content-Type"] = "application/json"
    return web.Response(body=rewritten, status=response.status, headers=headers)


async def handle_view(request):
    filename = Path(str(request.query.get("filename") or "")).name
    subfolder = str(request.query.get("subfolder") or "").replace("\\", "/").strip("/")
    image_type = str(request.query.get("type") or "output")
    mapped = _mapped_local_filename_for_remote(filename, subfolder, image_type)
    if mapped:
        filename = mapped
        subfolder = ""
    if filename:
        for local_path in _local_path_candidates(filename, subfolder):
            if local_path.is_file():
                _log(f"view local filename={filename} subfolder={subfolder} path={local_path}")
                return _local_view_response(local_path)
    if filename:
        _log(f"view remote filename={filename} subfolder={subfolder}")
    return await proxy_request(request)


async def handle_delete_asset(request):
    asset_id = request.match_info.get("asset_id", "")
    body = await request.read() if request.can_read_body else b""
    _log(f"delete asset request id={asset_id} path={request.path_qs} bytes={len(body)}")
    result = await _delete_local_assets_from_request(request, request.path_qs, body, asset_id)
    if result["deleted"]:
        return web.Response(status=204)
    return web.json_response({"ok": False, **result}, status=404)


async def handle_delete_asset_tags(request):
    return web.Response(status=204)


async def handle_prune_assets(request):
    body = await request.read() if request.can_read_body else b""
    _log(f"asset prune request path={request.path_qs} bytes={len(body)}")
    return web.json_response({"ok": True, "deleted": 0, "missing": 0})


async def handle_delete_local_asset(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    result = await _delete_local_paths(_local_asset_candidates_from_request_payload(data), str(data.get("id") or ""))
    if result["deleted"]:
        _refresh_local_asset_id_map()
    return web.json_response(result)


async def handle_list_assets(request):
    return web.json_response(_local_assets_response(request))


async def handle_get_asset(request):
    path = _local_asset_path_for_id(request.match_info.get("asset_id", ""))
    if not path:
        return await proxy_request(request)
    return web.json_response(_local_asset_payload(path))


async def handle_asset_content(request):
    path = _local_asset_path_for_id(request.match_info.get("asset_id", ""))
    if not path:
        return await proxy_request(request)
    return _local_view_response(path)


async def handle_ws(request):
    remote_query = request.query_string
    remote_url = REMOTE_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
    if remote_query:
        remote_url += f"?{remote_query}"
    client_ws = web.WebSocketResponse()
    await client_ws.prepare(request)
    async with ClientSession(timeout=CLIENT_TIMEOUT) as session:
        async with session.ws_connect(remote_url) as remote_ws:
            ws_prompt_id = ""
            current_node = ""

            async def client_to_remote():
                async for msg in client_ws:
                    if msg.type == WSMsgType.TEXT:
                        await remote_ws.send_str(msg.data)
                    elif msg.type == WSMsgType.BINARY:
                        await remote_ws.send_bytes(msg.data)
                    elif msg.type == WSMsgType.CLOSE:
                        await remote_ws.close()

            async def remote_to_client():
                nonlocal ws_prompt_id, current_node
                async for msg in remote_ws:
                    if msg.type == WSMsgType.TEXT:
                        try:
                            data = json.loads(msg.data)
                        except Exception:
                            await client_ws.send_str(msg.data)
                            continue
                        _remember_progress_message(data)
                        if data.get("type") == "executing":
                            payload = data.get("data") or {}
                            message_prompt_id = str(payload.get("prompt_id") or "").strip()
                            if message_prompt_id:
                                ws_prompt_id = message_prompt_id
                            elif not ws_prompt_id:
                                ws_prompt_id = _active_prompt_for_progress(payload)
                            current_node = str(payload.get("node") or "")
                            progress = PROMPT_PROGRESS.get(ws_prompt_id)
                            if progress:
                                progress_payload = dict(progress)
                                progress_payload["prompt_id"] = ws_prompt_id
                                await client_ws.send_str(
                                    json.dumps({"type": "progress", "data": progress_payload}, ensure_ascii=False)
                                )
                        rewritten = await _rewrite_ws_message_images_to_local(data)
                        await client_ws.send_str(json.dumps(rewritten, ensure_ascii=False))
                    elif msg.type == WSMsgType.BINARY:
                        raw = bytes(msg.data)
                        ws_nodes = WS_OUTPUT_NODE_IDS.get(ws_prompt_id) or set()
                        if USE_WEBSOCKET_OUTPUT and ws_prompt_id and current_node and current_node in ws_nodes and len(raw) > 8:
                            try:
                                event_type = struct.unpack(">I", raw[:4])[0]
                                if event_type == 1:
                                    image_type = struct.unpack(">I", raw[4:8])[0]
                                    _save_websocket_image(ws_prompt_id, raw[8:], image_type)
                            except Exception as exc:
                                _log(f"browser websocket image save failed prompt_id={ws_prompt_id} error={exc}")
                        await client_ws.send_bytes(msg.data)
                    elif msg.type == WSMsgType.CLOSE:
                        await client_ws.close()

            done, pending = await asyncio.wait(
                [asyncio.create_task(client_to_remote()), asyncio.create_task(remote_to_client())],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                if not task.cancelled():
                    task.exception()
    return client_ws


async def proxy_request(request):
    path = request.path_qs
    body = await request.read() if request.can_read_body else None
    if request.path.startswith("/api/assets") or request.path.startswith("/assets"):
        _log(f"asset proxy request method={request.method} path={path} bytes={len(body or b'')}")
    if request.method == "DELETE" and re.fullmatch(r"/(?:api/)?assets/[^/?#]+", request.path):
        _log(f"delete request path={path} bytes={len(body or b'')}")
        result = await _delete_local_assets_from_request(request, path, body or b"")
        if result["deleted"]:
            return web.Response(status=204)
        return web.json_response({"ok": False, **result}, status=404)
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length", "transfer-encoding"}
    }
    response, remote_body = await _remote_request(request.method, path, data=body, headers=headers)
    return web.Response(body=remote_body, status=response.status, headers=_clone_headers(response))


async def proxy_mobile_request(request):
    path = request.path_qs
    body = await request.read() if request.can_read_body else None
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length", "transfer-encoding", "origin", "referer"}
    }
    headers["X-RPP-Mobile-Origin"] = _mobile_origin_for_request(request)
    response, local_body = await _local_mobile_request(request.method, path, data=body, headers=headers)
    if request.method == "GET" and request.path == "/random_photo_prompt/mobile/status" and response.status < 400:
        try:
            payload = json.loads(local_body.decode("utf-8"))
        except Exception:
            payload = None
        if isinstance(payload, dict):
            payload.update(
                {
                    "entry_mode": "proxy",
                    "entry_label": "远端代理模式",
                    "proxy": {
                        "enabled": True,
                        "remote_url": REMOTE_URL,
                        "local_mobile_url": LOCAL_MOBILE_URL,
                        "output_dir": str(LOCAL_OUTPUT_DIR),
                        "delete_remote_output": DELETE_REMOTE_OUTPUT,
                    },
                    "remote": {
                        "enabled": True,
                        "url": REMOTE_URL,
                        "delete_output": DELETE_REMOTE_OUTPUT,
                    },
                    "output": {
                        "dir": str(LOCAL_OUTPUT_DIR),
                        "exists": LOCAL_OUTPUT_DIR.exists(),
                        "writable": os.access(LOCAL_OUTPUT_DIR, os.W_OK),
                    },
                }
            )
            payload["entry_label"] = "统一入口"
            local_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            proxy_headers = _clone_headers(response)
            proxy_headers["Content-Type"] = "application/json"
            return web.Response(body=local_body, status=response.status, headers=proxy_headers)
    if request.method == "GET" and request.path.startswith("/random_photo_prompt/mobile/job/") and response.status < 400:
        try:
            payload = json.loads(local_body.decode("utf-8"))
        except Exception:
            payload = None
        if isinstance(payload, dict):
            prompt_id = str(payload.get("prompt_id") or request.path.rsplit("/", 1)[-1])
            progress = PROMPT_PROGRESS.get(prompt_id)
            if progress:
                payload["progress"] = progress
            images = payload.get("images")
            if isinstance(images, list):
                for image in images:
                    if isinstance(image, dict):
                        await _rewrite_image_to_local(image, prompt_id)
            if payload.get("status") == "completed":
                _forget_active_prompt(prompt_id)
            local_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            proxy_headers = _clone_headers(response)
            proxy_headers["Content-Type"] = "application/json"
            return web.Response(body=local_body, status=response.status, headers=proxy_headers)
    return web.Response(body=local_body, status=response.status, headers=_clone_headers(response))


def _health_item(ok, label, detail):
    state = "正常" if ok else "异常"
    class_name = "ok" if ok else "bad"
    return f'<li class="{class_name}"><strong>{html.escape(label)}</strong><span>{state}</span><p>{html.escape(detail)}</p></li>'


async def _proxy_status_payload():
    local_probe, remote_probe, delete_probe = await asyncio.gather(
        _probe_url(LOCAL_MOBILE_URL, "/random_photo_prompt/mobile/status"),
        _probe_url(REMOTE_URL, "/system_stats"),
        _probe_remote_delete_endpoint() if DELETE_REMOTE_OUTPUT else asyncio.sleep(0, result={"ok": True, "status": 0, "error": "远端删除已关闭"}),
    )
    output_ok = LOCAL_OUTPUT_DIR.exists() and os.access(LOCAL_OUTPUT_DIR, os.W_OK)
    return {
        "proxy": True,
        "entry_mode": "proxy",
        "entry_label": "统一入口",
        "mobile_entry": "/random_photo_prompt/mobile",
        "remote_url": REMOTE_URL,
        "local_mobile_url": LOCAL_MOBILE_URL,
        "local_output_dir": str(LOCAL_OUTPUT_DIR),
        "delete_remote_output": DELETE_REMOTE_OUTPUT,
        "mapped_images": len(LOCAL_IMAGE_MAP),
        "checks": {
            "local_mobile": local_probe,
            "remote_comfyui": remote_probe,
            "output_dir": {"ok": output_ok, "status": 0, "error": "" if output_ok else "输出目录不存在或不可写。"},
            "remote_delete": delete_probe,
        },
    }


def _proxy_status_html(payload):
    checks = payload["checks"]
    all_ok = all(item.get("ok") for item in checks.values())
    title = "统一入口正常" if all_ok else "统一入口需要处理"
    items = [
        _health_item(checks["local_mobile"]["ok"], "手机端内部服务", checks["local_mobile"].get("error") or f"HTTP {checks['local_mobile'].get('status')}"),
        _health_item(checks["remote_comfyui"]["ok"], "远端 4090 ComfyUI", checks["remote_comfyui"].get("error") or f"HTTP {checks['remote_comfyui'].get('status')}"),
        _health_item(checks["output_dir"]["ok"], "本地输出目录", checks["output_dir"].get("error") or payload["local_output_dir"]),
        _health_item(checks["remote_delete"]["ok"], "远端删除接口", checks["remote_delete"].get("error") or ("已关闭" if not payload["delete_remote_output"] else f"HTTP {checks['remote_delete'].get('status')}")),
    ]
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #101114; color: #f5f5f0; }}
    main {{ max-width: 760px; margin: 0 auto; padding: 28px 18px 42px; }}
    h1 {{ font-size: 26px; margin: 0 0 10px; letter-spacing: 0; }}
    .lead {{ color: #b9b8ad; margin: 0 0 20px; line-height: 1.6; }}
    .entry {{ display: block; padding: 14px 16px; border: 1px solid #3f4743; color: #f5f5f0; text-decoration: none; background: #1b1d20; margin: 18px 0; }}
    ul {{ list-style: none; padding: 0; margin: 20px 0; display: grid; gap: 10px; }}
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
    <p class="lead">网页端和手机端统一从 18199 进入；本页只检查入口链路，不会提交生成任务。</p>
    <a class="entry" href="/">打开网页端</a>
    <a class="entry" href="/random_photo_prompt/mobile">打开手机端</a>
    <ul>{''.join(items)}</ul>
    <p class="lead">统一入口：<code>:18199</code><br>远端算力：<code>{html.escape(payload["remote_url"])}</code><br>输出目录：<code>{html.escape(payload["local_output_dir"])}</code></p>
  </main>
</body>
</html>"""


async def handle_proxy_status(request):
    payload = await _proxy_status_payload()
    accept = request.headers.get("Accept", "")
    if request.query.get("format") == "json" or "application/json" in accept:
        return web.json_response(payload)
    return web.Response(text=_proxy_status_html(payload), content_type="text/html")


async def handle_clear_runtime_state(request):
    reason = ""
    try:
        if request.can_read_body:
            data = await request.json()
            reason = str((data or {}).get("reason") or "")
    except Exception:
        reason = ""
    result = _clear_runtime_state(reason or "remote_restart")
    local_clear = None
    try:
        response, body = await _local_mobile_request(
            "POST",
            "/random_photo_prompt/mobile/remote_runtime/clear",
            json={"reason": reason or "remote_restart"},
            timeout=ClientTimeout(total=10),
        )
        try:
            local_clear = json.loads(body.decode("utf-8"))
        except Exception:
            local_clear = {"status": response.status, "body": body.decode("utf-8", "ignore")[:500]}
    except Exception as exc:
        local_clear = {"error": str(exc)}
    return web.json_response({"ok": True, **result, "local_mobile": local_clear})


async def handle_remote_image_upload(request):
    image_bytes = await request.read()
    if not image_bytes:
        return web.json_response({"error": "empty image body"}, status=400)
    content_type = request.headers.get("Content-Type", "")
    if "png" not in content_type and not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return web.json_response({"error": "only png upload is supported"}, status=400)
    prefix = request.headers.get("X-RPP-Filename-Prefix", "remote_web")
    filename = _unique_uploaded_filename(prefix, ".png")
    image = {"filename": filename, "subfolder": "", "type": "output"}
    response_subfolder = _comfy_output_subfolder_for_local_output()
    local_path = _safe_local_path(image)
    tmp_path = local_path.with_name(f".{local_path.name}.tmp")
    tmp_path.write_bytes(image_bytes)
    if not tmp_path.is_file() or tmp_path.stat().st_size <= 0:
        return web.json_response({"error": "local write failed"}, status=500)
    tmp_path.replace(local_path)
    _log(f"remote upload saved path={local_path} bytes={len(image_bytes)}")
    return web.json_response(
        {
            "ok": True,
            "filename": filename,
            "subfolder": response_subfolder,
            "type": "output",
            "url": f"/view?{urllib.parse.urlencode({'filename': filename, 'subfolder': response_subfolder, 'type': 'output'})}",
            "bytes": len(image_bytes),
        }
    )


async def handle_remote_video_upload(request):
    video_bytes = await request.read()
    if not video_bytes:
        return web.json_response({"ok": False, "error": "empty upload"}, status=400)
    prefix = request.headers.get("X-RPP-Filename-Prefix", "remote_video")
    suffix = request.headers.get("X-RPP-Video-Extension", ".mp4")
    suffix = "." + str(suffix or ".mp4").replace("\\", "/").strip().lstrip(".")
    if suffix.lower() not in {".mp4", ".webm", ".mov", ".mkv"}:
        suffix = ".mp4"
    filename = _unique_uploaded_filename(prefix, suffix)
    subfolder = "random_photo_prompt_mobile_video"
    local_dir = (LOCAL_OUTPUT_DIR / subfolder).resolve()
    if LOCAL_OUTPUT_DIR not in local_dir.parents:
        return web.json_response({"ok": False, "error": "unsafe output dir"}, status=400)
    local_dir.mkdir(parents=True, exist_ok=True)
    local_path = (local_dir / filename).resolve()
    if local_path.parent != local_dir:
        return web.json_response({"ok": False, "error": "unsafe filename"}, status=400)
    tmp_path = local_path.with_name(f".{local_path.name}.tmp")
    tmp_path.write_bytes(video_bytes)
    if not tmp_path.is_file() or tmp_path.stat().st_size <= 0:
        return web.json_response({"ok": False, "error": "upload temp write failed"}, status=500)
    tmp_path.replace(local_path)
    _log(f"remote video upload saved path={local_path} bytes={len(video_bytes)}")
    params = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": "output"})
    return web.json_response(
        {
            "ok": True,
            "filename": filename,
            "subfolder": subfolder,
            "type": "output",
            "url": f"/view?{params}",
            "bytes": len(video_bytes),
        }
    )


async def handle_source_image(request):
    raw_name = str(request.query.get("filename") or "").replace("\\", "/").strip("/")
    if not raw_name:
        return web.json_response({"ok": False, "error": "missing filename"}, status=400)
    if "/" in raw_name:
        subfolder, filename = raw_name.rsplit("/", 1)
    else:
        subfolder, filename = "", raw_name
    filename = Path(filename).name
    for local_path in _local_path_candidates(filename, subfolder):
        if local_path.is_file():
            _log(f"source image local filename={filename} subfolder={subfolder} path={local_path}")
            return _local_view_response(local_path)
    return web.json_response({"ok": False, "error": "source image not found"}, status=404)


async def handle_root(request):
    return await proxy_request(request)


def create_app():
    LOCAL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _load_local_image_map()
    _refresh_local_asset_id_map()
    app = web.Application(client_max_size=1024**3)
    app.router.add_route("GET", "/", handle_root)
    app.router.add_route("GET", "/random_photo_prompt/proxy/status", handle_proxy_status)
    app.router.add_route("POST", "/random_photo_prompt/proxy/runtime/clear", handle_clear_runtime_state)
    app.router.add_route("POST", "/random_photo_prompt/proxy/upload_image", handle_remote_image_upload)
    app.router.add_route("POST", "/random_photo_prompt/proxy/upload_video", handle_remote_video_upload)
    app.router.add_route("GET", "/random_photo_prompt/proxy/source_image", handle_source_image)
    app.router.add_route("POST", "/random_photo_prompt/proxy/delete_local_asset", handle_delete_local_asset)
    app.router.add_route("*", "/random_photo_prompt/mobile", proxy_mobile_request)
    app.router.add_route("*", "/random_photo_prompt/mobile/{tail:.*}", proxy_mobile_request)
    app.router.add_route("GET", "/ws", handle_ws)
    app.router.add_route("POST", "/prompt", handle_prompt)
    app.router.add_route("POST", "/api/prompt", handle_prompt)
    app.router.add_route("GET", "/history", handle_history)
    app.router.add_route("GET", "/history/{prompt_id}", handle_history)
    app.router.add_route("GET", "/api/history", handle_history)
    app.router.add_route("GET", "/api/history/{prompt_id}", handle_history)
    app.router.add_route("GET", "/view", handle_view)
    app.router.add_route("GET", "/api/view", handle_view)
    app.router.add_route("GET", "/assets", handle_list_assets)
    app.router.add_route("GET", "/assets/{asset_id}", handle_get_asset)
    app.router.add_route("GET", "/assets/{asset_id}/content", handle_asset_content)
    app.router.add_route("DELETE", "/assets/{asset_id}", handle_delete_asset)
    app.router.add_route("GET", "/api/assets", handle_list_assets)
    app.router.add_route("POST", "/api/assets/prune", handle_prune_assets)
    app.router.add_route("GET", "/api/assets/{asset_id}", handle_get_asset)
    app.router.add_route("GET", "/api/assets/{asset_id}/content", handle_asset_content)
    app.router.add_route("DELETE", "/api/assets/{asset_id}/tags", handle_delete_asset_tags)
    app.router.add_route("DELETE", "/api/assets/{asset_id}", handle_delete_asset)
    app.router.add_route("*", "/{tail:.*}", proxy_request)
    return app


if __name__ == "__main__":
    port = int(proxy_config.PROXY_PORT or 18199)
    web.run_app(create_app(), host="0.0.0.0", port=port)
