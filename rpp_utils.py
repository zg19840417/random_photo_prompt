from __future__ import annotations

import hashlib
import random
import re
import sys
import time
from pathlib import Path

import folder_paths

from rpp_globals import (
    MOBILE_VIDEO_OUTPUT_SUBFOLDER,
    NODE_DIR,
)
from prompt_resolution import MOBILE_RESOLUTION_MULTIPLE

__all__ = sorted(["__all__", "_clean_mobile_prompt_clause_text", "_load_prompt_generator", "_looks_internal_prompt_link", "_looks_negative_text", "_mobile_local_output_dir", "_mobile_output_dir", "_mobile_validation_error_message", "_mobile_video_output_dir", "_node_meta", "_node_title", "_normalize_aspect", "_nsfw_pose_data_hash", "_prompt_clauses", "_prompt_signature", "_queue_contains", "_queue_waiting_count", "_remote_transfer_source_is_allowed", "_remove_mobile_clauses_with_markers"])

def _load_prompt_generator():
    if str(NODE_DIR) not in sys.path:
        sys.path.insert(0, str(NODE_DIR))
    from prompt_engine import generate_prompt_items

    return generate_prompt_items


def _normalize_aspect(value, width=None, height=None):
    if str(NODE_DIR) not in sys.path:
        sys.path.insert(0, str(NODE_DIR))
    from prompt_normalize import normalize_aspect

    return normalize_aspect(value, width, height)


def _nsfw_pose_data_hash():
    path = NODE_DIR / "data" / "nsfw_pose_expression_options.json"
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except OSError:
        return "missing"


def _prompt_signature(scale, shot, aspect="portrait", era="modern"):
    return f"mobile-logic-v15-ancient-barefoot|{_nsfw_pose_data_hash()}|{scale or ''}|{shot or ''}|{era or 'modern'}"


def _remote_transfer_source_is_allowed(request, allowed_ips):
    configured = {value.strip() for value in str(allowed_ips or "").split(",") if value.strip()}
    return bool(configured) and str(request.remote or "") in configured


def _mobile_validation_error_message(error, node_errors=None):
    if isinstance(error, dict):
        message = error.get("message") or error.get("error") or error.get("exception_message")
        details = error.get("details") or error.get("type")
        if message and details:
            return f"{message}（{details}）"
        if message:
            return str(message)
    elif error not in (None, "", 0, "0"):
        return str(error)
    if node_errors:
        return f"工作流校验失败，涉及 {len(node_errors)} 个节点，请检查电脑端工作流模板。"
    return "工作流校验失败，请检查电脑端 workflow 模板是否可直接运行。"


def _clean_mobile_prompt_clause_text(text):
    return "，".join(part.strip("，。 \n\t") for part in str(text or "").replace("；", "，").split("，") if part.strip("，。 \n\t"))


def _remove_mobile_clauses_with_markers(text, markers):
    clauses = [
        clause
        for clause in _prompt_clauses(text)
        if not any(marker in clause for marker in markers)
    ]
    return "，".join(clauses)






def _prompt_clauses(text):
    return [part.strip("，。 \n\t") for part in str(text or "").replace("；", "，").split("，") if part.strip("，。 \n\t")]




def _node_meta(node):
    meta = node.get("_meta") if isinstance(node, dict) else None
    return meta if isinstance(meta, dict) else {}


def _node_title(node):
    meta = _node_meta(node)
    return str(meta.get("title") or node.get("class_type") or "").lower()


def _looks_negative_text(node):
    title = _node_title(node)
    text = str((node.get("inputs") or {}).get("text") or "").lower()
    markers = ("negative", "璐熼潰", "鍙嶅悜", "鍙嶆帹璐熼潰", "bad quality", "worst quality")
    return any(marker in title or marker in text for marker in markers)


def _looks_internal_prompt_link(text):
    text = str(text or "").strip()
    return bool(re.fullmatch(r"\[['\"][^'\"]+['\"],\s*\d+\]", text))




def _queue_contains(prompt_id, items):
    return any(len(item) > 1 and item[1] == prompt_id for item in items)


def _queue_waiting_count(prompt_id, running, pending):
    """Return the number of ComfyUI jobs ahead of this prompt, if queued."""
    prompt_id = str(prompt_id or "")
    if not prompt_id:
        return None
    if _queue_contains(prompt_id, running):
        return 0
    for index, item in enumerate(pending):
        if len(item) > 1 and str(item[1]) == prompt_id:
            return len(running) + index
    return None


def _mobile_output_dir():
    output_dir = Path(folder_paths.get_output_directory()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _mobile_local_output_dir():
    return _mobile_output_dir()


def _mobile_video_output_dir():
    output_dir = _mobile_local_output_dir()
    target = (output_dir / MOBILE_VIDEO_OUTPUT_SUBFOLDER).resolve()
    if output_dir not in target.parents and target != output_dir:
        raise ValueError("手机视频输出目录不在本地输出目录内。")
    target.mkdir(parents=True, exist_ok=True)
    return target


