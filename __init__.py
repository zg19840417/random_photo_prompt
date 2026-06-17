import sys
import time
import traceback
import json
import asyncio
import copy
import hashlib
import html
import os
import platform
import random
import re
import shutil
import struct
import subprocess
import uuid
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

import execution
import folder_paths
import numpy as np
import torch
from aiohttp import ClientSession, ClientTimeout, WSMsgType, web
from PIL import Image, ImageOps
from server import PromptServer


NODE_DIR = Path(__file__).resolve().parent
if str(NODE_DIR) not in sys.path:
    sys.path.insert(0, str(NODE_DIR))

from video_prompt_engine import (
    clean_video_action_text,
    estimate_video_seconds,
    generate_video_action,
    infer_video_pose_family,
    infer_video_scope,
    normalize_video_seconds,
    video_prompt_from_action,
)
from keyword_expansion_engine import CHARACTER_BY_SHOT
from keyword_expansion_engine import generate_keyword_expansion_prompt
from prompt_postprocess import clean_prompt_text
from prompt_resolution import (
    MOBILE_CUSTOM_RESOLUTION_PRESETS,
    MOBILE_MAX_IMAGE_EDGE,
    MOBILE_RESOLUTION_DOWNSHIFT,
    MOBILE_RESOLUTION_MULTIPLE,
    MOBILE_STANDING_FULL_BODY_RESOLUTION,
    base_resolution_for_workflow,
    clamp_mobile_resolution,
    linked_float_value,
    mobile_custom_resolution,
    mobile_resolution_for_custom_prompt,
    round_to_multiple,
    workflow_output_scale,
)
MOBILE_PAGE_PATH = NODE_DIR / "web" / "mobile.html"
MOBILE_WORKFLOW_PATH = NODE_DIR / "mobile_workflow_api.json"
MOBILE_WORKFLOWS = {
    "zit_single": {"label": "单采-ZIT", "path": MOBILE_WORKFLOW_PATH, "type": "image"},
    "zib_single": {"label": "单采-ZIB", "path": NODE_DIR / "mobile_workflow_api_2.json", "type": "image"},
    "zitb_double": {"label": "双采-ZIT+ZIB", "path": NODE_DIR / "mobile_workflow_api_2.json", "type": "image"},
    "ltx_video": {"label": "图生视频", "path": NODE_DIR / "mobile_workflow_api_3.json", "type": "video"},
}
MOBILE_DEFAULT_WORKFLOW_KEY = "zit_single"
MOBILE_VIDEO_WORKFLOW_KEY = "ltx_video"
ZIT_MODEL_DIR = Path(folder_paths.models_dir) / "diffusion_models" / "z_image"
ZIT_MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".gguf"}
MOBILE_PREFERRED_ZIT_MODELS = (
    "ZIT-pornmasterV35_bf16.safetensors",
    "ZIT-moodyPornMix_zitV10R1DPO_fp16.safetensors",
    "ZIT-大师pornmasterZImage_turboV35_bf16.safetensors",
    "ZIT-beyondREALITY_V30.safetensors",
)
MOBILE_PREFERRED_ZIB_MODELS = (
    "ZIB-moodyWildMix_v40Distilled10STEPS.safetensors",
)
REMOTE_BLOCKED_ZIT_MODELS = set()
ZIMAGE_LORA_SUBDIR = "Zimage"
LORA_MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt"}
REMOTE_LORA_DIR = Path(
    os.environ.get("RPP_REMOTE_LORA_DIR", "~/Desktop/远程模型/loras")
).expanduser()
MOBILE_OUTPUT_SUBFOLDER = "random_photo_prompt_mobile"
MOBILE_VIDEO_OUTPUT_SUBFOLDER = "random_photo_prompt_mobile_video"
MOBILE_VIDEO_INPUT_SUBFOLDER = "random_photo_prompt_mobile_video"
REMOTE_COMFYUI_URL = os.environ.get("RPP_REMOTE_COMFYUI_URL", "").rstrip("/")
REMOTE_OUTPUT_DIR = Path(os.environ.get("RPP_REMOTE_OUTPUT_DIR", "")).expanduser() if os.environ.get("RPP_REMOTE_OUTPUT_DIR") else None
REMOTE_HISTORY_TIMEOUT = float(os.environ.get("RPP_REMOTE_HISTORY_TIMEOUT", "600") or 600)
REMOTE_DELETE_OUTPUT = os.environ.get("RPP_REMOTE_DELETE_OUTPUT", "1").strip().lower() not in {"0", "false", "no", "off"}
REMOTE_WEBSOCKET_OUTPUT = os.environ.get("RPP_REMOTE_WEBSOCKET_OUTPUT", "1").strip().lower() not in {"0", "false", "no", "off"}
BLOCK_REMOTE_ASSET_SAVE = os.environ.get("RPP_BLOCK_REMOTE_ASSET_SAVE", "0").strip().lower() in {"1", "true", "yes", "on"}
REMOTE_MAC_IMAGE_UPLOAD_URL = os.environ.get("RPP_MAC_IMAGE_UPLOAD_URL", "").strip()
REMOTE_MAC_VIDEO_UPLOAD_URL = os.environ.get("RPP_MAC_VIDEO_UPLOAD_URL", "").strip() or REMOTE_MAC_IMAGE_UPLOAD_URL.replace("/upload_image", "/upload_video")
REMOTE_MAC_SOURCE_IMAGE_URL = os.environ.get("RPP_MAC_SOURCE_IMAGE_URL", "").strip() or REMOTE_MAC_IMAGE_UPLOAD_URL.replace("/upload_image", "/source_image")
MOBILE_SCOPE_PRESETS = {
    "head_shot": {"shot": "head_shot", "aspect": "portrait", "width": 1536, "height": 1536},
    "half_body": {"shot": "half_body", "aspect": "portrait", "width": 1280, "height": 1920},
    "full_body": {"shot": "full_body", "aspect": "portrait", "width": 1088, "height": 1920},
}
MOBILE_MAX_ACTIVE_JOBS = 100
MOBILE_SESSION_JOBS = []
MOBILE_SESSION_JOBS_LOADED = False
MOBILE_PROMPT_BY_FILENAME = {}
MOBILE_VIDEO_PROMPT_BY_FILENAME = {}
MOBILE_VIDEO_DIMENSIONS_BY_FILENAME = {}
REMOTE_WS_OUTPUT_NODES_BY_PROMPT_ID = {}
REMOTE_WS_OUTPUT_PREFIX_BY_PROMPT_ID = {}
REMOTE_WS_IMAGE_INDEX_BY_PROMPT_ID = {}
REMOTE_WS_WATCHERS = {}
REMOTE_PROGRESS_BY_PROMPT_ID = {}
REMOTE_WS_OUTPUT_MODE_BY_PROMPT_ID = {}
REMOTE_WS_CLIENT_ID_BY_PROMPT_ID = {}
MOBILE_RUNTIME_IMAGES_BY_PROMPT_ID = {}
MOBILE_PROMPT_INDEX_NAME = ".random_photo_prompt_mobile_prompts.json"
MOBILE_SESSION_JOBS_NAME = ".random_photo_prompt_mobile_jobs.json"
MOBILE_GALLERY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MOBILE_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv"}
MAX_POSITIVE_PROMPT_LENGTH = 800
PROMPT_DISPLAY_PART_ORDER = (
    "camera",
    "character",
    "outfit",
    "pose_expression",
    "scene_light",
    "quality",
)
PROMPT_LIMIT_PART_ORDER = ("camera", "character", "outfit", "pose_expression", "scene_light", "quality")

MOBILE_RESOLUTION_RULES = {
    "full_body": (
        (
            ("大字", "四肢展开", "双臂自然向两侧展开", "手脚乱舞", "跳", "跃起", "腾空"),
            {"aspect": "landscape", "width": 1920, "height": 1280, "framing": "横向全身动态构图"},
        ),
        (
            ("俯拍", "顶视角", "正上方", "仰躺", "侧躺", "横躺", "平躺", "趴", "横向展开", "沿宽画幅", "床中央", "睡", "睡着"),
            {"aspect": "landscape", "width": 1920, "height": 1280, "framing": "横向全身构图，身体沿宽画幅展开，从头到脚完整入镜"},
        ),
        (
            ("近大远小", "强透视", "前景", "靠近镜头", "脚伸到镜头", "手掌和脚尖", "脚尖和脚踝因近大远小"),
            {"aspect": "portrait", "width": 1280, "height": 1920, "framing": "竖向全身强透视构图"},
        ),
        (
            ("站立", "站姿", "直立", "倚靠", "靠墙", "迈步", "行走", "走姿"),
            MOBILE_STANDING_FULL_BODY_RESOLUTION,
        ),
        (
            ("坐", "坐姿", "坐在", "侧坐", "跪", "跪姿", "跪坐", "膝", "蹲", "半蹲", "蜷", "抱膝"),
            {"aspect": "portrait", "width": 1280, "height": 1920, "framing": "竖向全身坐跪构图"},
        ),
        (
            ("扭腰", "回望", "转身", "侧身", "交叉点地", "向后拉长", "双手一上一下"),
            {"aspect": "portrait", "width": 1088, "height": 1920, "framing": "竖向全身动态姿势构图"},
        ),
    ),
    "half_body": (
        (
            ("横躺", "侧躺", "仰躺", "平躺", "俯拍", "顶视角", "床", "横向", "横跨", "横向靠", "横向坐", "横向趴", "沿宽画幅", "斜向铺"),
            {"aspect": "landscape", "width": 1920, "height": 1280, "framing": "横向半身镜头，大腿以上入镜"},
        ),
        (
            ("坐", "坐姿", "跪", "跪坐", "膝", "直立", "站", "站立", "竖向", "纵向"),
            {"aspect": "portrait", "width": 1280, "height": 1920, "framing": "竖向半身镜头，大腿以上入镜"},
        ),
    ),
    "head_shot": (
        (
            ("横向", "侧脸", "躺", "侧躺"),
            {"aspect": "portrait", "width": 1536, "height": 1536, "framing": "方形头部镜头，肩膀及以上入镜，头顶完整"},
        ),
    ),
}
MOBILE_FRAMING_COMPACT_REPLACEMENTS = {
    "横向全身动态宽构图，四肢外轮廓完整，四周留环境边距": "横向全身动态构图",
    "横向全身构图，身体沿宽画幅展开，从头到脚完整入镜": "横向宽构图，身体沿画幅展开",
    "竖向全身非站姿构图，头部、手臂、腿部、脚部和姿势外轮廓完整": "竖向全身非站姿构图",
    "窄长全身构图，从头顶到脚掌完整入镜，脚下留地面边距": "窄长全身构图，脚下留地面边距",
    "横向半身镜头，大腿以上入镜": "横向半身构图，大腿以上入镜",
    "竖向半身镜头，大腿以上入镜": "竖向半身构图，大腿以上入镜",
    "横向头部镜头，肩膀及以上入镜，头顶完整": "横向头部构图，头顶完整",
    "竖向全身构图，从头到脚完整入镜，姿势外轮廓完整": "竖向全身构图",
    "头部镜头，肩膀及以上入镜，头顶完整": "竖向头部构图，头顶完整",
}
MOBILE_DEFAULT_RESOLUTIONS = {
    "full_body": {"aspect": "portrait", "width": 1088, "height": 1920, "framing": "竖向全身构图"},
    "half_body": {"aspect": "portrait", "width": 1280, "height": 1920, "framing": "竖向半身镜头，大腿以上入镜"},
    "head_shot": {"aspect": "portrait", "width": 1536, "height": 1536, "framing": "方形头部镜头，肩膀及以上入镜，头顶完整"},
}
MOBILE_DIRECTOR_RESOLUTION_RULES = {
    "sunny_multicolor_pool_glamour": {
        "full_body": {"aspect": "portrait", "width": 1088, "height": 1920, "framing": "竖向全身阳光水光构图，从头到脚完整入镜，脚下留地面或池边边距"},
        "half_body": {"aspect": "portrait", "width": 1216, "height": 1664, "framing": "竖向半身多色反光构图，大腿以上入镜"},
    },
    "beach_vivid_glamour": {
        "full_body": {"aspect": "portrait", "width": 1088, "height": 1920, "framing": "竖向全身海边构图，从头到脚完整入镜，脚下沙面边距清楚"},
        "half_body": {"aspect": "landscape", "width": 1920, "height": 1088, "framing": "横向半身海边构图，大腿以上入镜，保留海风空间"},
    },
    "garden_waterlight_seduction": {
        "full_body": {"aspect": "portrait", "width": 1280, "height": 1920, "framing": "竖向全身花园构图，从头到脚完整入镜，脚下草地或地面边距清楚"},
        "half_body": {"aspect": "portrait", "width": 1216, "height": 1664, "framing": "竖向半身花园水光构图，大腿以上入镜"},
    },
    "glass_balcony_colorlight": {
        "full_body": {"aspect": "portrait", "width": 1280, "height": 1920, "framing": "竖向全身玻璃反射构图，从头到脚完整入镜，脚下地面边距清楚"},
        "half_body": {"aspect": "portrait", "width": 1216, "height": 1664, "framing": "竖向半身玻璃彩光构图，大腿以上入镜"},
        "head_shot": {"aspect": "portrait", "width": 1536, "height": 1536, "framing": "方形头部玻璃反光近景，肩膀及以上入镜，头顶完整"},
    },
    "bright_studio_color_fashion": {
        "full_body": {"aspect": "portrait", "width": 1280, "height": 1920, "framing": "竖向全身彩色棚拍构图，从头到脚完整入镜，脚下地面边距清楚"},
        "half_body": {"aspect": "portrait", "width": 1216, "height": 1664, "framing": "竖向半身彩色棚拍构图，大腿以上入镜"},
        "head_shot": {"aspect": "portrait", "width": 1536, "height": 1536, "framing": "方形头部彩色棚拍近景，肩膀及以上入镜，头顶完整"},
    },
    "tropical_terrace_sensuality": {
        "full_body": {"aspect": "portrait", "width": 1088, "height": 1920, "framing": "竖向全身热带露台构图，从头到脚完整入镜，脚下甲板或地面边距清楚"},
        "half_body": {"aspect": "landscape", "width": 1920, "height": 1088, "framing": "横向半身热带露台构图，大腿以上入镜"},
    },
    "sweet_vivid_tease": {
        "full_body": {"aspect": "portrait", "width": 1280, "height": 1920, "framing": "竖向全身甜艳构图，从头到脚完整入镜，脚下边距清楚"},
        "half_body": {"aspect": "portrait", "width": 1216, "height": 1664, "framing": "竖向半身甜艳构图，大腿以上入镜"},
        "head_shot": {"aspect": "portrait", "width": 1536, "height": 1536, "framing": "方形头部甜艳近景，肩膀及以上入镜，头顶完整"},
    },
    "forced_perspective_focus": {
        "full_body": {"aspect": "portrait", "width": 1280, "height": 1920, "framing": "竖向全身强透视构图，从头到脚完整入镜，前景肢体和脚下地面边距清楚"},
        "half_body": {"aspect": "portrait", "width": 1216, "height": 1664, "framing": "竖向半身强透视构图，大腿以上入镜，手部动作清楚"},
        "head_shot": {"aspect": "portrait", "width": 1536, "height": 1536, "framing": "方形头部强透视近景，肩膀及以上入镜，头顶完整"},
    },
}


def _load_prompt_generator():
    if str(NODE_DIR) not in sys.path:
        sys.path.insert(0, str(NODE_DIR))
    from prompt_engine import generate_prompt_items

    return generate_prompt_items


def _normalize_aspect(value, width=None, height=None):
    text = str(value or "").strip().lower()
    if text in {"landscape", "horizontal", "妯睆", "妯悜", "wide"}:
        return "landscape"
    if text in {"portrait", "vertical", "绔栧睆", "绔栧悜", "tall"}:
        return "portrait"
    try:
        parsed_width = int(width) if width is not None else None
        parsed_height = int(height) if height is not None else None
    except (TypeError, ValueError):
        parsed_width = None
        parsed_height = None
    if parsed_width and parsed_height and parsed_width > parsed_height:
        return "landscape"
    return "portrait"


def _nsfw_pose_data_hash():
    path = NODE_DIR / "data" / "nsfw_pose_expression_options.json"
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except OSError:
        return "missing"


def _prompt_signature(scale, shot, aspect="portrait", era="modern"):
    return f"mobile-logic-v2|{_nsfw_pose_data_hash()}|{scale or ''}|{shot or ''}|{era or 'modern'}"


def _as_bool(value, default=True):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"false", "0", "off", "no"}:
            return False
        if text in {"true", "1", "on", "yes"}:
            return True
    return default


def _route_exists(method, path):
    for route in getattr(PromptServer.instance.routes, "_items", []):
        if getattr(route, "method", None) == method and getattr(route, "path", None) == path:
            return True
    return False


def _build_prompt_item(scale, shot, seed_text="", aspect="portrait", width=None, height=None, era="modern"):
    generate_prompt_items = _load_prompt_generator()
    scale_map = {
        "一档": "normal",
        "二档": "bold",
        "三档": "bold_no_outfit",
        "四档": "nsfw",
        "普通": "normal",
        "大胆": "bold",
        "NSFW": "nsfw",
        "normal": "normal",
        "bold": "bold",
        "bold_no_outfit": "bold_no_outfit",
        "no_outfit": "bold_no_outfit",
        "nsfw": "nsfw",
    }
    if str(shot or "").strip().lower() in {"随机", "random"}:
        normalized_shot = random.Random(str(seed_text or time.time())).choice(["头部", "半身", "全身"])
    else:
        normalized_shot = "" if shot == "默认" else shot
    normalized_aspect = _normalize_aspect(aspect, width, height)
    return generate_prompt_items(
        1,
        {
            "scale": scale_map.get(scale, "bold"),
            "shot": normalized_shot,
            "aspect": normalized_aspect,
            "width": width,
            "height": height,
            "era": era,
        },
        seed_text,
    )[0]


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


def _build_mobile_prompt_item(scale, shot_config, seed_text, era="modern"):
    shot = shot_config["shot"]
    aspect = shot_config["aspect"]
    width = shot_config["width"]
    height = shot_config["height"]
    return _build_prompt_item(scale, shot, seed_text, aspect, width, height, era)


FIXED_CHARACTER_IDENTITY = "22岁冷白皮K-pop韩国女生"


def _ensure_scoped_character_prompt(prompt_item):
    item = copy.deepcopy(prompt_item)
    parts = item.get("dimension_parts")
    if isinstance(parts, dict):
        shot_key = item.get("shot_key") or ""
        parts = _clean_mobile_prompt_parts(parts, shot_key)
        character = str(parts.get("character") or "").strip()
        if not character:
            character = CHARACTER_BY_SHOT.get(shot_key) or CHARACTER_BY_SHOT["full_body"]
        elif FIXED_CHARACTER_IDENTITY not in character:
            character = f"{FIXED_CHARACTER_IDENTITY}，{character}"
        parts["character"] = character
        item["dimension_parts"] = parts
        prompt = _rebuild_prompt_text_from_parts(parts)
        item["positive_prompt"] = prompt
        item["compact_prompt"] = prompt
    else:
        prompt = _prompt_text(item)
        if FIXED_CHARACTER_IDENTITY not in prompt:
            prompt = f"{FIXED_CHARACTER_IDENTITY}\n\n{prompt}"
            item["positive_prompt"] = prompt
            item["compact_prompt"] = prompt
    return item


def _mobile_prompt_text_for_resolution(prompt_item):
    parts = prompt_item.get("dimension_parts") or {}
    return "，".join(
        str(parts.get(name, ""))
        for name in ("camera", "pose_expression", "scene_light")
        if parts.get(name)
    )


def _prompt_text(prompt_item):
    return clean_prompt_text(prompt_item.get("compact_prompt") or prompt_item["positive_prompt"])


def _rebuild_prompt_text_from_parts(parts):
    lines = [
        clean_prompt_text(str(parts.get(name, "")).strip())
        for name in PROMPT_LIMIT_PART_ORDER
        if str(parts.get(name, "")).strip()
    ]
    return clean_prompt_text("\n\n".join(f"{line.rstrip('，。')}。" for line in lines))


def _clean_mobile_prompt_clause_text(text):
    return "，".join(part.strip("，。 \n\t") for part in str(text or "").replace("；", "，").split("，") if part.strip("，。 \n\t"))


def _remove_mobile_clauses_with_markers(text, markers):
    clauses = [
        clause
        for clause in _prompt_clauses(text)
        if not any(marker in clause for marker in markers)
    ]
    return "，".join(clauses)


def _strip_outfit_palette_clause(text):
    cleaned = re.sub(r"阳光鲜艳配色以[^，。]+为主", "", str(text or ""))
    cleaned = re.sub(r"，{2,}", "，", cleaned)
    return cleaned.strip("，、 \n\t")


def _clean_mobile_prompt_parts(parts, shot_key):
    cleaned = dict(parts or {})
    cleaned["outfit"] = _strip_outfit_palette_clause(cleaned.get("outfit", ""))
    if shot_key == "head_shot":
        for name in ("pose_expression", "scene_light", "outfit", "camera"):
            text = str(cleaned.get(name) or "")
            text = text.replace("完整胸部和上腰短截", "胸部上缘")
            text = text.replace("完整胸部与一小段腰部", "胸部线条")
            text = text.replace("完整胸部和少量上腰", "胸部线条")
            text = text.replace("和上腰短截", "")
            text = _remove_mobile_clauses_with_markers(text, ("腰线", "细腰", "腰部", "腰侧", "腰缘", "身体曲线"))
            cleaned[name] = _clean_mobile_prompt_clause_text(text)
    if shot_key == "head_shot":
        for name in ("pose_expression", "scene_light", "outfit", "camera"):
            cleaned[name] = _remove_mobile_clauses_with_markers(
                cleaned.get(name, ""),
                ("胸部", "胸前", "乳沟", "腰", "臀", "腿", "脚"),
            )
    return cleaned


def _prompt_len_from_parts(parts):
    return len(_rebuild_prompt_text_from_parts(parts))


def _prompt_clauses(text):
    return [part.strip("，。 \n\t") for part in str(text or "").replace("；", "，").split("，") if part.strip("，。 \n\t")]


def _enforce_prompt_length(parts, max_length=MAX_POSITIVE_PROMPT_LENGTH):
    compacted = dict(parts or {})
    if _prompt_len_from_parts(compacted) <= max_length:
        return compacted
    compacted["quality"] = ""
    if _prompt_len_from_parts(compacted) <= max_length:
        return compacted
    for name in ("scene_light", "outfit", "pose_expression", "camera"):
        clauses = _prompt_clauses(compacted.get(name, ""))
        while len(clauses) > 1 and _prompt_len_from_parts(compacted) > max_length:
            clauses.pop()
            compacted[name] = "，".join(clauses)
        if _prompt_len_from_parts(compacted) <= max_length:
            break
    return compacted


def _display_prompt_text(prompt_item):
    parts = prompt_item.get("dimension_parts") or {}
    lines = [
        clean_prompt_text(str(parts.get(name, "")).strip())
        for name in PROMPT_DISPLAY_PART_ORDER
        if str(parts.get(name, "")).strip()
    ]
    if lines:
        return clean_prompt_text("\n\n".join(lines))
    return _prompt_text(prompt_item)


def _custom_mobile_prompt_item(prompt_text, seed_text=""):
    text = str(prompt_text or "").strip()
    if not text:
        return None
    try:
        import prompt_data
        negative_prompt = getattr(prompt_data, "NEGATIVE_PROMPT", "")
    except Exception:
        negative_prompt = ""
    rng = random.Random(str(seed_text or time.time()))
    try:
        from prompt_engine import build_negative_prompt, normalize_aspect, normalize_shot
        resolution = _mobile_resolution_for_custom_prompt(text)
        aspect = normalize_aspect(resolution.get("aspect", ""), resolution.get("width"), resolution.get("height"))
        shot = normalize_shot(text)
        negative_prompt = build_negative_prompt(text, {"camera": text}, "custom", shot, aspect, resolution.get("width"), resolution.get("height"))
    except Exception:
        pass
    return {
        "scale": "custom",
        "shot": "自定义",
        "shot_key": "custom",
        "aspect": "portrait",
        "dimension_parts": {"camera": text},
        "positive_prompt": text,
        "compact_prompt": text,
        "negative_prompt": negative_prompt,
        "seed": rng.randint(1, 2**48 - 1),
        "prompt_audit_issues": [],
    }


def _use_chinese_negative_prompt(prompt_item, scale, shot_config, width, height, aspect):
    try:
        from negative_prompt_engine import build_chinese_negative_prompt
        prompt_item["negative_prompt"] = build_chinese_negative_prompt(
            _prompt_text(prompt_item),
            prompt_item.get("dimension_parts") or {},
            scale,
            (shot_config or {}).get("shot") or prompt_item.get("shot_key") or "full_body",
            aspect,
            width,
            height,
        )
    except Exception:
        pass
    return prompt_item


def _mobile_resolution_for_custom_prompt(prompt_text):
    return mobile_resolution_for_custom_prompt(prompt_text)


def _mobile_custom_resolution(prompt_text, preset=""):
    return mobile_custom_resolution(prompt_text, preset)


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


def _mobile_resolution_for_prompt(prompt_item, shot):
    text = _mobile_prompt_text_for_resolution(prompt_item)
    for markers, resolution in MOBILE_RESOLUTION_RULES.get(shot, ()):
        if any(marker in text for marker in markers):
            return _clamp_mobile_resolution(resolution)
    director = str((prompt_item.get("dimension_parts") or {}).get("director") or "")
    director_resolution = MOBILE_DIRECTOR_RESOLUTION_RULES.get(director, {}).get(shot)
    if director_resolution:
        return _clamp_mobile_resolution(director_resolution)
    return _clamp_mobile_resolution(MOBILE_DEFAULT_RESOLUTIONS[shot])


def _clamp_mobile_resolution(resolution):
    return clamp_mobile_resolution(resolution)


def _mobile_ground_anchor(parts):
    context = "，".join(
        str(parts.get(name, ""))
        for name in ("scene_light", "camera", "pose_expression")
        if parts.get(name)
    )
    ground_options = (
        (("沙滩", "海边", "海岸", "沙面", "海浪", "阳光海"), "浅金沙面和脚印纹理"),
        (("泳池", "池边", "水面", "池水", "水光"), "湿润湖蓝泳池瓷砖"),
        (("花园", "草地", "庭院", "热带", "花丛", "植物"), "鲜绿色草地和花影"),
        (("露台", "阳台", "屋顶", "甲板"), "暖色木质露台地板"),
        (("玻璃", "橱窗", "镜面", "反射"), "浅彩玻璃反射地面"),
        (("棚拍", "影棚", "彩色背景", "彩色棚"), "高饱和彩色棚拍地面"),
        (("街", "路面", "城市", "霓虹", "雨夜", "停车场"), "带反光的彩色街道路面"),
        (("房间", "酒店", "套房", "室内", "浴室", "更衣"), "暖色室内地面"),
    )
    for markers, anchor in ground_options:
        if any(marker in context for marker in markers):
            return anchor
    return "浅暖色地面纹理"


def _resolve_mobile_framing(framing, parts):
    if "{ground_anchor}" in framing:
        return framing.replace("{ground_anchor}", _mobile_ground_anchor(parts))
    return framing


def _round_to_multiple(value, multiple=MOBILE_RESOLUTION_MULTIPLE):
    return max(multiple, int(round(float(value) / multiple) * multiple))


def _apply_mobile_framing(prompt_item, resolution):
    framing = resolution.get("framing")
    if not framing:
        return prompt_item
    item = copy.deepcopy(prompt_item)
    parts = item.setdefault("dimension_parts", {})
    framing = _resolve_mobile_framing(framing, parts)
    camera = str(parts.get("camera") or "")
    if any(marker in camera for marker in ("入镜", "镜头", "构图", "画面", "头顶", "完整")):
        framing = MOBILE_FRAMING_COMPACT_REPLACEMENTS.get(framing, framing)
    # 去重：如果camera的开头分句与framing的开头分句重复，跳过追加
    camera_first = re.split(r"[，,]", camera)[0].strip() if camera else ""
    framing_first = re.split(r"[，,]", framing)[0].strip()
    scope_markers = ("大腿以上入镜", "肩膀及以上入镜", "从头到脚完整入镜", "头顶完整")
    camera_has_full_body_framing = "全身" in camera and "构图" in camera
    framing_has_full_body_framing = "全身" in framing and "构图" in framing
    already_covered = (
        framing in camera or
        camera_first == framing_first or
        camera_first in framing or
        framing_first in camera or
        any(marker in camera and marker in framing for marker in scope_markers) or
        (camera_has_full_body_framing and framing_has_full_body_framing)
    )
    if not already_covered:
        parts["camera"] = f"{camera}，{framing}" if camera else framing
    parts = _clean_mobile_prompt_parts(parts, item.get("shot_key") or "")
    parts = _enforce_prompt_length(parts)
    item["dimension_parts"] = parts
    prompt = _rebuild_prompt_text_from_parts(parts)
    item["compact_prompt"] = prompt
    item["positive_prompt"] = prompt
    return item


def _build_mobile_prompt_for_scope(scale, shot_config, seed_text, era="modern"):
    initial = _build_mobile_prompt_item(scale, shot_config, seed_text, era)
    initial = _ensure_scoped_character_prompt(initial)
    resolution = _mobile_resolution_for_prompt(initial, shot_config["shot"])
    if resolution["aspect"] != shot_config["aspect"]:
        resolved_config = {
            **shot_config,
            "aspect": resolution["aspect"],
            "width": resolution["width"],
            "height": resolution["height"],
        }
        initial = _build_mobile_prompt_item(scale, resolved_config, f"{seed_text}-{resolution['aspect']}", era)
        initial = _ensure_scoped_character_prompt(initial)
        resolution = _mobile_resolution_for_prompt(initial, shot_config["shot"])
    return _apply_mobile_framing(initial, resolution), resolution


def _build_prompt_with_mobile_logic(scale, shot, seed_text="", era="modern"):
    shot_config = _mobile_shot_config(shot)
    item, _resolution = _build_mobile_prompt_for_scope(scale, shot_config, seed_text, era)
    return _prompt_text(item)


def _build_desktop_prompt_with_mobile_logic(scale, shot, seed_text="", era="modern"):
    shot_config = _mobile_shot_config(shot)
    item, resolution = _build_mobile_prompt_for_scope(scale, shot_config, seed_text, era)
    return item, resolution


def _build_prompt(scale, shot, seed_text="", aspect="portrait", width=None, height=None, era="modern"):
    return _build_prompt_with_mobile_logic(scale, shot, seed_text, era)


def _mobile_workflow_config(value=None):
    key = str(value or MOBILE_DEFAULT_WORKFLOW_KEY).strip()
    return key, MOBILE_WORKFLOWS.get(key) or MOBILE_WORKFLOWS[MOBILE_DEFAULT_WORKFLOW_KEY]


def _mobile_image_workflows():
    return {
        key: item
        for key, item in MOBILE_WORKFLOWS.items()
        if item.get("type", "image") == "image"
    }


def _available_zimage_models(prefix):
    if not ZIT_MODEL_DIR.exists():
        return []
    prefix = str(prefix or "").lower()
    return sorted(
        path.name
        for path in ZIT_MODEL_DIR.iterdir()
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


def _available_zit_models():
    models = _available_zimage_models("zit")
    return _sort_zit_models(models)


def _available_zib_models():
    return _sort_zib_models(_available_zimage_models("zib"))


def _normalize_remote_zimage_model_name(value):
    text = str(value or "").replace("/", "\\").strip().strip("\\")
    if not text:
        return ""
    name = Path(text.replace("\\", "/")).name
    return name if name.lower().startswith(("zit", "zib")) else ""


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


async def _remote_unet_models():
    if not REMOTE_COMFYUI_URL:
        return None
    data, error = await _remote_json("GET", "/object_info/UNETLoader", timeout=10)
    if error or not isinstance(data, dict):
        return None
    try:
        values = data["UNETLoader"]["input"]["required"]["unet_name"][0]
    except Exception:
        return None
    if not isinstance(values, list):
        return None
    zit_models, zib_models = _split_remote_zimage_models(values)
    return {"source": "remote", "zit_models": zit_models, "zib_models": zib_models}


async def _available_mobile_zimage_models():
    remote_models = await _remote_unet_models()
    if remote_models is not None:
        return remote_models
    return {
        "source": "local",
        "zit_models": _available_zit_models(),
        "zib_models": _available_zib_models(),
    }


def _available_loras():
    if REMOTE_COMFYUI_URL:
        if not REMOTE_LORA_DIR.exists():
            return []
        return sorted(
            path.relative_to(REMOTE_LORA_DIR).as_posix()
            for path in REMOTE_LORA_DIR.rglob("*")
            if path.is_file() and path.suffix.lower() in LORA_MODEL_EXTENSIONS
        )
    try:
        return sorted(
            name.replace("\\", "/")
            for name in folder_paths.get_filename_list("loras")
            if name.replace("\\", "/").startswith(f"{ZIMAGE_LORA_SUBDIR}/")
        )
    except Exception:
        lora_dir = Path(folder_paths.models_dir) / "loras" / ZIMAGE_LORA_SUBDIR
        if not lora_dir.exists():
            return []
        return sorted(
            f"{ZIMAGE_LORA_SUBDIR}/{path.relative_to(lora_dir).as_posix()}"
            for path in lora_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in LORA_MODEL_EXTENSIONS
        )


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


def _zimage_unet_value(model_name):
    model_name = Path(str(model_name or "").replace("\\", "/")).name
    if not model_name:
        return ""
    if REMOTE_COMFYUI_URL:
        return f"z_image\\{model_name}"
    return f"z_image/{model_name}"


def _resolve_lora_name(value=None):
    raw = str(value or "").replace("\\", "/").strip().strip("/")
    if not raw:
        return ""
    available = _available_loras()
    if raw in available:
        return raw
    raw_name = Path(raw).name
    matches = [name for name in available if Path(name.replace("\\", "/")).name == raw_name]
    if len(matches) == 1:
        return matches[0]
    raise ValueError(f"没有找到 LoRA：{raw}")


def _lora_dir_display_path():
    if REMOTE_COMFYUI_URL:
        return str(REMOTE_LORA_DIR.resolve())
    return str((Path(folder_paths.models_dir) / "loras" / ZIMAGE_LORA_SUBDIR).resolve())


def _resolve_lora_strength(value=None):
    try:
        strength = float(value)
    except (TypeError, ValueError):
        strength = 0.8
    return max(-2.0, min(2.0, strength))


def _patch_existing_lora_nodes(workflow, lora_name="", strength=0.8):
    resolved_lora = _resolve_lora_name(lora_name)
    if not resolved_lora:
        return _bypass_lora_nodes(workflow)
    strength = _resolve_lora_strength(strength) if resolved_lora else 0
    patched = 0
    lora_value = resolved_lora
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        class_type = str(node.get("class_type") or "").lower()
        title = _node_title(node)
        has_lora_identity = "lora" in class_type or "lora" in title or any("lora" in str(key).lower() for key in inputs)
        if not has_lora_identity:
            continue
        node_patched = False
        for key in list(inputs):
            lower_key = str(key).lower()
            key_text = str(key)
            if lora_value and (
                lower_key in {"lora_name", "lora", "lora_name_1"}
                or ("lora" in lower_key and "name" in lower_key)
                or key_text in {"LoRA名称", "Lora名称", "lora名称", "名称"}
            ):
                inputs[key] = lora_value
                node_patched = True
        for key in list(inputs):
            lower_key = str(key).lower()
            key_text = str(key)
            if lower_key in {"strength_model", "strength_clip", "model_strength", "clip_strength", "strength"} or (
                "strength" in lower_key and isinstance(inputs.get(key), (int, float, str))
            ) or (
                key_text in {"模型强度", "强度", "CLIP强度", "clip强度"} and isinstance(inputs.get(key), (int, float, str))
            ):
                inputs[key] = strength
                node_patched = True
        if node_patched:
            patched += 1
    if patched < 1:
        raise ValueError("工作流模板里没有找到可复用的 LoRA 节点。请确认 API 工作流里保留 LoRA 节点后重新保存。")
    return patched


def _bypass_lora_nodes(workflow):
    bypasses = {}
    for node_id, node in list(workflow.items()):
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        class_type = str(node.get("class_type") or "").lower()
        title = _node_title(node)
        has_lora_identity = "lora" in class_type or "lora" in title or any("lora" in str(key).lower() for key in inputs)
        model_input = inputs.get("model")
        if has_lora_identity and isinstance(model_input, list) and len(model_input) >= 2:
            bypasses[str(node_id)] = list(model_input)
            workflow.pop(str(node_id), None)
    if not bypasses:
        return 0
    for node in workflow.values():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict):
            continue
        for key, value in list(inputs.items()):
            if isinstance(value, list) and value and str(value[0]) in bypasses:
                inputs[key] = list(bypasses[str(value[0])])
    return len(bypasses)


def _is_zit_turbo_model_name(value):
    name = Path(str(value or "").replace("\\", "/")).name.lower()
    return name.startswith(("zit-", "zit_", "z_image"))


def _workflow_model_consumers(workflow):
    consumers = {}
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for value in inputs.values():
            if isinstance(value, list) and value:
                consumers.setdefault(str(value[0]), set()).add(str(node_id))
    return consumers


def _load_mobile_workflow(workflow_key=None):
    _key, config = _mobile_workflow_config(workflow_key)
    workflow_path = config["path"]
    if not workflow_path.exists():
        raise FileNotFoundError(f"请先在电脑端 ComfyUI 导出 API 工作流，并保存为 {workflow_path.name}。")
    try:
        data = json.loads(workflow_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"{workflow_path.name} 读取失败：{exc}") from exc
    if isinstance(data, dict) and isinstance(data.get("prompt"), dict):
        data = data["prompt"]
    if isinstance(data, dict) and isinstance(data.get("nodes"), list):
        raise ValueError(
            f"{workflow_path.name} 现在是普通工作流格式，不是 API 格式。"
            "请在 ComfyUI 设置里打开开发者选项，然后使用“保存(API 格式)”重新导出。"
        )
    if not isinstance(data, dict) or not data:
        raise ValueError(f"{workflow_path.name} 不是有效的 ComfyUI API 工作流。")
    return data


def _workflow_status_item(key, config):
    path = config["path"]
    status = {
        "key": key,
        "label": config["label"],
        "type": config.get("type", "image"),
        "template_name": path.name,
        "path": str(path),
        "template_ready": path.exists(),
        "format": "missing",
        "message": "",
        "guidance": "",
    }
    if not path.exists():
        status["message"] = f"缺少 {path.name}。"
        status["guidance"] = "在 ComfyUI 电脑端打开对应工作流，开启开发者选项后使用“保存(API 格式)”，保存到本插件目录。"
        return status
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        status["format"] = "invalid_json"
        status["message"] = f"{path.name} 读取失败：{exc}"
        status["guidance"] = "重新从 ComfyUI 导出 API 格式工作流，覆盖这个文件。"
        return status
    if isinstance(data, dict) and isinstance(data.get("prompt"), dict):
        data = data["prompt"]
    if isinstance(data, dict) and isinstance(data.get("nodes"), list):
        status["format"] = "ui_workflow"
        status["template_ready"] = False
        status["message"] = f"{path.name} 是普通工作流格式，不是 API 格式。"
        status["guidance"] = "请在 ComfyUI 设置里打开开发者选项，然后使用“保存(API 格式)”重新导出。"
        return status
    if not isinstance(data, dict) or not data:
        status["format"] = "invalid_api"
        status["template_ready"] = False
        status["message"] = f"{path.name} 不是有效的 ComfyUI API 工作流。"
        status["guidance"] = "请确认保存的是 API 格式 JSON。"
        return status
    status["format"] = "api"
    status["message"] = "API 工作流已准备。"
    return status


def _mobile_workflow_statuses():
    return {key: _workflow_status_item(key, config) for key, config in MOBILE_WORKFLOWS.items()}


def _node_title(node):
    meta = node.get("_meta") if isinstance(node, dict) else {}
    return str(meta.get("title") or node.get("class_type") or "").lower()


def _looks_negative_text(node):
    title = _node_title(node)
    text = str((node.get("inputs") or {}).get("text") or "").lower()
    markers = ("negative", "璐熼潰", "鍙嶅悜", "鍙嶆帹璐熼潰", "bad quality", "worst quality")
    return any(marker in title or marker in text for marker in markers)


def _mobile_output_dir():
    output_dir = Path(folder_paths.get_output_directory()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _mobile_local_output_dir():
    output_dir = Path(REMOTE_OUTPUT_DIR).resolve() if REMOTE_OUTPUT_DIR else _mobile_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


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
    safe_subfolder = str(subfolder or "").replace("\\", "/").strip("/")
    if not REMOTE_OUTPUT_DIR:
        return safe_subfolder
    comfy_output_dir = _mobile_output_dir()
    remote_output_dir = _mobile_local_output_dir()
    if remote_output_dir != comfy_output_dir and comfy_output_dir not in remote_output_dir.parents:
        return safe_subfolder
    remote_relative = "" if remote_output_dir == comfy_output_dir else remote_output_dir.relative_to(comfy_output_dir).as_posix()
    parts = [part for part in (remote_relative, safe_subfolder) if part]
    return "/".join(parts)


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


def _mobile_output_file_key(filename, subfolder=""):
    safe_name = Path(str(filename or "")).name
    safe_subfolder = str(subfolder or "").replace("\\", "/").strip("/")
    return f"{safe_subfolder}/{safe_name}" if safe_subfolder else safe_name


def _mobile_prompt_index_path():
    return _mobile_local_output_dir() / MOBILE_PROMPT_INDEX_NAME


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
    MOBILE_RUNTIME_IMAGES_BY_PROMPT_ID.clear()
    _save_mobile_session_jobs()
    return {
        "jobs_removed": max(0, before_jobs - len(MOBILE_SESSION_JOBS)),
        "watchers_cancelled": before_watchers,
    }


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
        prompt = str(value or "").strip()
        if filename and prompt and not _looks_internal_prompt_link(prompt):
            result[filename] = prompt
    return result


def _save_mobile_prompt_index(index):
    path = _mobile_prompt_index_path()
    serializable = {
        str(key or "").replace("\\", "/").strip("/"): str(value or "")
        for key, value in dict(index or {}).items()
        if str(key or "").replace("\\", "/").strip("/") and str(value or "").strip()
    }
    payload = {
        "version": 1,
        "updated_at": int(time.time() * 1000),
        "prompts": serializable,
    }
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _remember_mobile_prompt_file(filename, prompt, subfolder=""):
    safe_name = _mobile_output_file_key(filename, subfolder)
    prompt = str(prompt or "").strip()
    if not safe_name or not prompt:
        return
    MOBILE_PROMPT_BY_FILENAME[safe_name] = prompt
    index = _load_mobile_prompt_index()
    if index.get(safe_name) == prompt:
        return
    index[safe_name] = prompt
    _save_mobile_prompt_index(index)


def _looks_internal_prompt_link(text):
    text = str(text or "").strip()
    return bool(re.fullmatch(r"\[['\"][^'\"]+['\"],\s*\d+\]", text))


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


def _mobile_video_output_dir():
    output_dir = _mobile_local_output_dir()
    target = (output_dir / MOBILE_VIDEO_OUTPUT_SUBFOLDER).resolve()
    if output_dir not in target.parents and target != output_dir:
        raise ValueError("手机视频输出目录不在本地输出目录内。")
    target.mkdir(parents=True, exist_ok=True)
    return target


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


def _mobile_prompt_for_gallery_file(filename):
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
        prompt = MOBILE_PROMPT_BY_FILENAME.get(key, "") or prompt_index.get(key, "")
        if prompt:
            MOBILE_PROMPT_BY_FILENAME[filename] = prompt
            return prompt
    for job in MOBILE_SESSION_JOBS:
        prefix = str(job.get("output_prefix") or "")
        if prefix and Path(filename).name.startswith(f"{prefix}_"):
            return job.get("prompt", "")
    return ""


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


def _mobile_gallery_images():
    prompt_by_filename = _load_mobile_prompt_index()
    prompt_by_filename.update(MOBILE_PROMPT_BY_FILENAME)
    items = []
    output_dir = _mobile_local_output_dir()
    seen = set()
    for path in output_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in MOBILE_GALLERY_EXTENSIONS:
            continue
        subfolder = _mobile_output_subfolder_for_path(path)
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
        prompt = prompt_by_filename.get(file_key, "") or _mobile_prompt_for_gallery_file(file_key)
        if not prompt and path.suffix.lower() == ".png":
            prompt = _prompt_text_from_png_metadata(path)
            if prompt:
                _remember_mobile_prompt_file(path.name, prompt, subfolder)
        items.append(
            {
                "filename": path.name,
                "subfolder": subfolder,
                "key": file_key,
                "type": "output",
                "mtime": int(stat.st_mtime * 1000),
                "size": stat.st_size,
                "prompt": prompt,
                "url": _mobile_view_url(path.name, subfolder),
            }
        )
    items.sort(key=lambda item: (item["mtime"], item["filename"]), reverse=True)
    for prompt_id, runtime_items in MOBILE_RUNTIME_IMAGES_BY_PROMPT_ID.items():
        prompt = ""
        for job in MOBILE_SESSION_JOBS:
            if str(job.get("prompt_id") or "") == str(prompt_id):
                prompt = job.get("prompt", "")
                break
        for runtime_item in runtime_items:
            public_item = {key: value for key, value in runtime_item.items() if key != "bytes"}
            public_item["prompt"] = public_item.get("prompt") or prompt
            public_item["key"] = public_item.get("filename", "")
            items.append(public_item)
    items.sort(key=lambda item: (item.get("mtime", 0), item.get("filename", "")), reverse=True)
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


def _linked_float_value(workflow, value, default=1.0):
    return linked_float_value(workflow, value, default)


def _mobile_workflow_output_scale(workflow, include_ultimate=True):
    return workflow_output_scale(workflow, include_ultimate)


def _workflow_has_mobile_upscale(workflow):
    return any(
        isinstance(node, dict) and str(node.get("class_type") or "") == "UltimateSDUpscale"
        for node in workflow.values()
    )


def _mobile_base_resolution_for_workflow(template, width, height):
    return base_resolution_for_workflow(template, width, height)


def _remove_mobile_auxiliary_outputs(workflow):
    removed = 0
    remove_ids = set()
    for node_id, node in list(workflow.items()):
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        title = _node_title(node)
        if class_type in {"Image Comparer (rgthree)", "easy cleanGpuUsed"} or "compare" in title or "cleangpu" in title:
            remove_ids.add(str(node_id))
    for node_id, node in list(workflow.items()):
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if any(isinstance(value, list) and value and str(value[0]) in remove_ids for value in inputs.values()):
            class_type = str(node.get("class_type") or "")
            title = _node_title(node)
            if class_type in {"Image Comparer (rgthree)", "easy cleanGpuUsed"} or "compare" in title or "cleangpu" in title:
                remove_ids.add(str(node_id))
    for node_id in remove_ids:
        if workflow.pop(node_id, None) is not None:
            removed += 1
    return removed


def _remove_unreferenced_mobile_prompt_nodes(workflow):
    referenced = set()
    for node in workflow.values():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict):
            continue
        for value in inputs.values():
            if isinstance(value, list) and value:
                referenced.add(str(value[0]))
    removed = 0
    for node_id, node in list(workflow.items()):
        if str(node_id) in referenced:
            continue
        if isinstance(node, dict) and str(node.get("class_type") or "") == "RandomPhotoPrompt":
            workflow.pop(str(node_id), None)
            removed += 1
    return removed


def _remove_unreferenced_workflow_nodes(workflow):
    referenced = set()
    for node in workflow.values():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict):
            continue
        for value in inputs.values():
            if isinstance(value, list) and value:
                referenced.add(str(value[0]))
    removed = 0
    changed = True
    while changed:
        changed = False
        for node_id, node in list(workflow.items()):
            if str(node_id) in referenced:
                continue
            if not isinstance(node, dict):
                continue
            class_type = str(node.get("class_type") or "")
            inputs = node.get("inputs") if isinstance(node, dict) else None
            is_output = class_type in {"SaveImage", "PreviewImage", "SaveImageWebsocket"} or "filename_prefix" in (inputs or {})
            if is_output:
                continue
            workflow.pop(str(node_id), None)
            removed += 1
            changed = True
            referenced = set()
            for other in workflow.values():
                other_inputs = other.get("inputs") if isinstance(other, dict) else None
                if not isinstance(other_inputs, dict):
                    continue
                for value in other_inputs.values():
                    if isinstance(value, list) and value:
                        referenced.add(str(value[0]))
            break
    return removed


def _bypass_mobile_upscale_outputs(workflow):
    if not isinstance(workflow, dict):
        return 0
    upscale_image_inputs = {}
    for node_id, node in workflow.items():
        if not isinstance(node, dict) or str(node.get("class_type") or "") != "UltimateSDUpscale":
            continue
        image_input = (node.get("inputs") or {}).get("image")
        if isinstance(image_input, list) and image_input:
            upscale_image_inputs[str(node_id)] = [str(image_input[0]), int(image_input[1] if len(image_input) > 1 else 0)]
    if not upscale_image_inputs:
        return 0
    changed = 0
    for node in workflow.values():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict):
            continue
        images = inputs.get("images")
        if isinstance(images, list) and images and str(images[0]) in upscale_image_inputs:
            inputs["images"] = upscale_image_inputs[str(images[0])]
            changed += 1
    changed += _remove_unreferenced_workflow_nodes(workflow)
    return changed


def _route_zib_single_outputs(workflow):
    if not isinstance(workflow, dict) or "547" not in workflow:
        return 0
    changed = 0
    for node in workflow.values():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict):
            continue
        images = inputs.get("images")
        if isinstance(images, list) and images:
            inputs["images"] = ["547", 0]
            changed += 1
    changed += _remove_unreferenced_workflow_nodes(workflow)
    return changed


def _workflow_link_consumers(workflow):
    consumers = {}
    if not isinstance(workflow, dict):
        return consumers
    for node_id, node in workflow.items():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict):
            continue
        for value in inputs.values():
            if isinstance(value, list) and value:
                consumers.setdefault(str(value[0]), set()).add(str(node_id))
    return consumers


def _ultimate_sd_upscale_node_ids(workflow):
    if not isinstance(workflow, dict):
        return set()
    return {
        str(node_id)
        for node_id, node in workflow.items()
        if isinstance(node, dict) and str(node.get("class_type") or "") == "UltimateSDUpscale"
    }


def _prune_non_final_image_outputs(workflow):
    upscale_ids = _ultimate_sd_upscale_node_ids(workflow)
    if not upscale_ids:
        return 0
    removed = 0
    for node_id, node in list(workflow.items()):
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        images = inputs.get("images")
        if not isinstance(images, list) or not images:
            continue
        class_type = str(node.get("class_type") or "")
        is_output = (
            class_type in {"SaveImage", "PreviewImage", "SaveImageWebsocket"}
            or "filename_prefix" in inputs
            or class_type.startswith("Save")
            or "Save" in class_type
        )
        if not is_output:
            continue
        if str(images[0]) in upscale_ids:
            continue
        workflow.pop(str(node_id), None)
        removed += 1
    return removed


def _patch_remote_websocket_outputs(workflow, output_mode="mac"):
    if not REMOTE_WEBSOCKET_OUTPUT or not isinstance(workflow, dict):
        return {"replaced_save_nodes": 0, "output_prefix": "", "websocket_node_ids": []}
    replaced = 0
    output_prefix = ""
    websocket_node_ids = []
    for node_id, node in list(workflow.items()):
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        class_type = str(node.get("class_type") or "")
        images = inputs.get("images")
        if not isinstance(images, list) or not images:
            continue
        if class_type not in {"SaveImage", "PreviewImage"} and "filename_prefix" not in inputs:
            continue
        if not output_prefix:
            output_prefix = Path(str(inputs.get("filename_prefix") or "mobile").replace("\\", "/").strip("/")).name or "mobile"
        if REMOTE_MAC_IMAGE_UPLOAD_URL and output_mode != "phone":
            node["class_type"] = "RandomPhotoPromptRemoteUploadImage"
            node["inputs"] = {"images": list(images), "filename_prefix": output_prefix}
        else:
            node["class_type"] = "SaveImageWebsocket"
            node["inputs"] = {"images": list(images)}
            websocket_node_ids.append(str(node_id))
        replaced += 1
    if REMOTE_MAC_VIDEO_UPLOAD_URL and output_mode != "phone":
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict) or str(node.get("class_type") or "") != "SaveVideo":
                continue
            video = inputs.get("video")
            if not isinstance(video, list) or not video:
                continue
            output_prefix = output_prefix or Path(str(inputs.get("filename_prefix") or "mobile_video").replace("\\", "/").strip("/")).name or "mobile_video"
            node["class_type"] = "RandomPhotoPromptRemoteUploadVideo"
            node["inputs"] = {
                "video": list(video),
                "filename_prefix": output_prefix,
                "format": inputs.get("format", "mp4"),
                "codec": inputs.get("codec", "h264"),
            }
            replaced += 1
    return {"replaced_save_nodes": replaced, "output_prefix": output_prefix, "websocket_node_ids": websocket_node_ids}


def _unpatched_remote_save_node_classes(workflow):
    if not isinstance(workflow, dict):
        return []
    classes = []
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if class_type in {"SaveImageWebsocket", "RandomPhotoPromptRemoteUploadImage", "RandomPhotoPromptRemoteUploadVideo"}:
            continue
        if class_type == "PreviewImage" or "filename_prefix" in inputs or class_type.startswith("Save") or "Save" in class_type:
            classes.append(class_type or "unknown")
    return classes


def _force_websocket_only_image_outputs(workflow):
    if not isinstance(workflow, dict):
        return {"replaced": 0, "blocked": []}
    _prune_non_final_image_outputs(workflow)
    replaced = 0
    blocked = []
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if class_type in {"RandomPhotoPromptRemoteUploadImage", "RandomPhotoPromptRemoteUploadVideo"}:
            continue
        images = inputs.get("images")
        if (
            (class_type in {"SaveImage", "PreviewImage"} or "filename_prefix" in inputs or class_type.startswith("Save") or "Save" in class_type)
            and isinstance(images, list)
            and images
        ):
            output_prefix = Path(str(inputs.get("filename_prefix") or "remote_web").replace("\\", "/").strip("/")).name or "remote_web"
            if REMOTE_MAC_IMAGE_UPLOAD_URL:
                node["class_type"] = "RandomPhotoPromptRemoteUploadImage"
                node["inputs"] = {"images": list(images), "filename_prefix": output_prefix}
            else:
                node["class_type"] = "SaveImageWebsocket"
                node["inputs"] = {"images": list(images)}
            replaced += 1
            continue
        if class_type == "SaveImageWebsocket":
            continue
        if class_type == "SaveVideo" and isinstance(inputs.get("video"), list) and inputs.get("video"):
            if REMOTE_MAC_VIDEO_UPLOAD_URL:
                output_prefix = Path(str(inputs.get("filename_prefix") or "remote_video").replace("\\", "/").strip("/")).name or "remote_video"
                node["class_type"] = "RandomPhotoPromptRemoteUploadVideo"
                node["inputs"] = {
                    "video": list(inputs["video"]),
                    "filename_prefix": output_prefix,
                    "format": inputs.get("format", "mp4"),
                    "codec": inputs.get("codec", "h264"),
                }
                replaced += 1
                continue
            blocked.append(class_type or "unknown")
            continue
        if "filename_prefix" in inputs or class_type.startswith("Save") or "Save" in class_type:
            blocked.append(class_type or "unknown")
    return {"replaced": replaced, "blocked": blocked}


def _block_remote_asset_save_on_prompt(json_data):
    if not BLOCK_REMOTE_ASSET_SAVE or not isinstance(json_data, dict):
        return json_data
    prompt = json_data.get("prompt")
    result = _force_websocket_only_image_outputs(prompt)
    if result["blocked"]:
        detail = ", ".join(sorted(set(result["blocked"]))) or "unknown"
        json_data["prompt"] = {
            "random_photo_prompt_remote_asset_save_blocked": {
                "class_type": f"RPP_RemoteAssetSaveBlocked_{detail}",
                "inputs": {},
            }
        }
        extra_data = json_data.setdefault("extra_data", {})
        if isinstance(extra_data, dict):
            extra_data["random_photo_prompt_blocked_reason"] = f"已阻止远端资产落盘保存节点：{detail}"
        return json_data
    if result["replaced"]:
        extra_data = json_data.setdefault("extra_data", {})
        if isinstance(extra_data, dict):
            extra_data["random_photo_prompt_websocket_only"] = True
    return json_data


class RandomPhotoPromptRemoteUploadImage:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"images": ("IMAGE",), "filename_prefix": ("STRING", {"default": "remote_web"})}}

    RETURN_TYPES = ()
    FUNCTION = "upload_images"
    OUTPUT_NODE = True
    CATEGORY = "Random Photo"

    def upload_images(self, images, filename_prefix="remote_web"):
        if not REMOTE_MAC_IMAGE_UPLOAD_URL:
            raise RuntimeError("RPP_MAC_IMAGE_UPLOAD_URL is not configured.")
        results = []
        for image in images:
            i = 255.0 * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
            buffer = BytesIO()
            img.save(buffer, format="PNG", compress_level=4)
            request = urllib.request.Request(
                REMOTE_MAC_IMAGE_UPLOAD_URL,
                data=buffer.getvalue(),
                headers={
                    "Content-Type": "image/png",
                    "X-RPP-Filename-Prefix": str(filename_prefix or "remote_web"),
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict) and payload.get("filename"):
                results.append(
                    {
                        "filename": payload.get("filename"),
                        "subfolder": payload.get("subfolder", ""),
                        "type": payload.get("type", "output"),
                    }
                )
        return {"ui": {"images": results}}


class RandomPhotoPromptRemoteLoadImageFromMac:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"source_url": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("IMAGE", "MASK")
    FUNCTION = "load_image"
    CATEGORY = "Random Photo"

    def load_image(self, source_url=""):
        source_url = str(source_url or "").strip()
        if not source_url:
            raise RuntimeError("Mac source image URL is empty.")
        with urllib.request.urlopen(source_url, timeout=120) as response:
            image_bytes = response.read()
        if not image_bytes:
            raise RuntimeError("Mac source image is empty.")
        img = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes)))
        image = img.convert("RGB")
        image_tensor = torch.from_numpy(np.asarray(image).astype(np.float32) / 255.0)[None,]
        if "A" in img.getbands():
            alpha = np.asarray(img.getchannel("A")).astype(np.float32) / 255.0
            mask = 1.0 - torch.from_numpy(alpha)[None,]
        else:
            mask = torch.zeros((1, image.height, image.width), dtype=torch.float32)
        return image_tensor, mask

    @classmethod
    def IS_CHANGED(cls, source_url=""):
        return str(source_url or "")

    @classmethod
    def VALIDATE_INPUTS(cls, source_url=""):
        return True


class RandomPhotoPromptRemoteUploadVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO",),
                "filename_prefix": ("STRING", {"default": "remote_video"}),
                "format": (["mp4", "webm", "mov", "mkv", "auto"], {"default": "mp4"}),
                "codec": (["h264", "h265", "vp9", "av1", "auto"], {"default": "h264"}),
            }
        }

    RETURN_TYPES = ()
    FUNCTION = "upload_video"
    OUTPUT_NODE = True
    CATEGORY = "Random Photo"

    def upload_video(self, video, filename_prefix="remote_video", format="mp4", codec="h264"):
        if not REMOTE_MAC_VIDEO_UPLOAD_URL:
            raise RuntimeError("RPP_MAC_VIDEO_UPLOAD_URL is not configured.")
        import tempfile
        from comfy_api.latest import Types

        safe_prefix = Path(str(filename_prefix or "remote_video").replace("\\", "/").strip("/")).name or "remote_video"
        extension = Types.VideoContainer.get_extension(format)
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(prefix=f"{safe_prefix}_", suffix=f".{extension}", delete=False) as temp_file:
                temp_path = temp_file.name
            metadata = {}
            video.save_to(temp_path, format=Types.VideoContainer(format), codec=codec, metadata=metadata)
            with open(temp_path, "rb") as file:
                video_bytes = file.read()
            request = urllib.request.Request(
                REMOTE_MAC_VIDEO_UPLOAD_URL,
                data=video_bytes,
                headers={
                    "Content-Type": f"video/{extension}",
                    "X-RPP-Filename-Prefix": safe_prefix,
                    "X-RPP-Video-Extension": f".{extension}",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=300) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    pass
        result = {
            "filename": payload.get("filename"),
            "subfolder": payload.get("subfolder", MOBILE_VIDEO_OUTPUT_SUBFOLDER),
            "type": payload.get("type", "output"),
        }
        return {"ui": {"videos": [result]}}


def _image_longest_side(path):
    try:
        from PIL import Image
        with Image.open(path) as image:
            width, height = image.size
        return max(int(width), int(height))
    except Exception:
        return 640


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


def _mac_proxy_source_image_url(filename):
    if not REMOTE_MAC_SOURCE_IMAGE_URL:
        return ""
    safe_name = str(filename or "").replace("\\", "/").strip("/")
    if not safe_name or any(part in {"", ".", ".."} for part in safe_name.split("/")):
        raise ValueError("视频源图文件名无效。")
    return f"{REMOTE_MAC_SOURCE_IMAGE_URL}?{urllib.parse.urlencode({'filename': safe_name})}"


def _patch_mobile_workflow(template, prompt_item, width, height, seed, zit_model="", output_prefix=None, lora_name="", lora_strength=0.8, zib_model=""):
    workflow = copy.deepcopy(template)
    removed_auxiliary_outputs = _remove_mobile_auxiliary_outputs(workflow)
    positive_prompt = _prompt_text(prompt_item)
    negative_prompt = prompt_item.get("negative_prompt", "")
    resolved_zit_model = Path(str(zit_model or "").replace("\\", "/")).name
    resolved_zib_model = Path(str(zib_model or "").replace("\\", "/")).name
    use_zib_single = bool(resolved_zib_model and not resolved_zit_model)
    if use_zib_single:
        base_width, base_height, output_scale = int(width), int(height), 1.0
    else:
        base_width, base_height, output_scale = _mobile_base_resolution_for_workflow(template, width, height)
    patched = {
        "positive_text": 0,
        "negative_text": 0,
        "width": 0,
        "height": 0,
        "seed": 0,
        "steps": 0,
        "filename_prefix": 0,
        "zit_model": 0,
        "zib_model": 0,
        "lora": 0,
        "purge_models_disabled": 0,
        "base_width": base_width,
        "base_height": base_height,
        "output_scale": output_scale,
        "removed_auxiliary_outputs": removed_auxiliary_outputs,
        "bypassed_upscale_nodes": 0,
        "zib_single_output_rerouted": 0,
    }
    text_nodes = []
    if use_zib_single:
        patched["zib_single_output_rerouted"] = _route_zib_single_outputs(workflow)
    patched["lora"] = _patch_existing_lora_nodes(workflow, lora_name, lora_strength)
    sampler_steps = 8
    zit_unet_value = _zimage_unet_value(resolved_zit_model)
    zib_unet_value = _zimage_unet_value(resolved_zib_model)
    model_consumers = _workflow_model_consumers(workflow)
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        class_type = str(node.get("class_type") or "")
        if class_type == "LayerUtility: PurgeVRAM V2" and inputs.get("purge_models") is True:
            inputs["purge_models"] = False
            patched["purge_models_disabled"] += 1
        if "text" in inputs and ("CLIPTextEncode" in class_type or "TextEncode" in class_type or "Conditioning" in class_type):
            text_nodes.append(node)
        if resolved_zit_model and "unet_name" in inputs:
            current_unet = str(inputs.get("unet_name") or "")
            if _is_zit_turbo_model_name(current_unet):
                inputs["unet_name"] = zit_unet_value
                if inputs.get("weight_dtype") in {"fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"}:
                    inputs["weight_dtype"] = "default"
                patched["zit_model"] += 1
        if resolved_zib_model and "unet_name" in inputs:
            current_unet = str(inputs.get("unet_name") or "")
            normalized_unet = current_unet.replace("/", "\\").lower()
            consumers = model_consumers.get(str(node_id), set())
            is_zib_slot = normalized_unet.startswith("z_image\\zib") or "483" in consumers or (use_zib_single and _is_zit_turbo_model_name(current_unet))
            if is_zib_slot:
                inputs["unet_name"] = zib_unet_value
                if inputs.get("weight_dtype") in {"fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2", "bf16"}:
                    inputs["weight_dtype"] = "default"
                patched["zib_model"] += 1
        for key in ("width", "W", "image_width", "latent_width", "empty_latent_width", "瀹藉害"):
            if key in inputs and isinstance(inputs.get(key), (int, float, str)):
                inputs[key] = int(base_width)
                patched["width"] += 1
        for key in ("height", "H", "image_height", "latent_height", "empty_latent_height", "楂樺害"):
            if key in inputs and isinstance(inputs.get(key), (int, float, str)):
                inputs[key] = int(base_height)
                patched["height"] += 1
        for key in ("seed", "noise_seed"):
            if key in inputs and isinstance(inputs.get(key), (int, float, str)):
                inputs[key] = int(seed)
                patched["seed"] += 1
        if not use_zib_single and class_type == "KSampler" and "steps" in inputs and isinstance(inputs.get("steps"), (int, float, str)):
            inputs["steps"] = sampler_steps
            patched["steps"] += 1
        if "filename_prefix" in inputs and isinstance(inputs.get("filename_prefix"), str):
            raw_prefix = str(inputs.get("filename_prefix") or "ComfyUI").replace("\\", "/").strip("/")
            base_prefix = Path(raw_prefix).name or "ComfyUI"
            final_prefix = output_prefix or base_prefix
            inputs["filename_prefix"] = final_prefix
            patched["filename_prefix"] += 1
    negative_nodes = {id(node) for node in text_nodes if _looks_negative_text(node)}
    if not negative_nodes and len(text_nodes) >= 2:
        negative_nodes.add(id(text_nodes[1]))
    for node in text_nodes:
        inputs = node["inputs"]
        if id(node) in negative_nodes:
            inputs["text"] = negative_prompt
            patched["negative_text"] += 1
        else:
            inputs["text"] = positive_prompt
            patched["positive_text"] += 1
    if patched["positive_text"] < 1:
        raise ValueError("工作流模板里没有找到可写入的正向提示词节点。")
    if resolved_zit_model and patched["zit_model"] < 1:
        raise ValueError("工作流模板里没有找到可替换的 z_image_turbo 模型节点。")
    if resolved_zib_model and patched["zib_model"] < 1:
        raise ValueError("工作流模板里没有找到可替换的 ZIB 模型节点。")
    patched["removed_prompt_nodes"] = _remove_unreferenced_mobile_prompt_nodes(workflow)
    return workflow, patched


def _patch_mobile_video_workflow(template, prompt_item, image_load_name, source_image_path, seed, seconds=8, fps=16, output_prefix=None, positive_prompt=None, remote_source_url=""):
    workflow = copy.deepcopy(template)
    positive_prompt = positive_prompt or _prompt_text(prompt_item)
    negative_prompt = prompt_item.get("negative_prompt", "")
    scale_to_length = max(32, min(960, int(_image_longest_side(source_image_path) or 960)))
    seconds = max(1, min(30, int(seconds or 6)))
    fps = max(1, min(60, int(fps or 16)))
    patched = {
        "positive_text": 0,
        "negative_text": 0,
        "load_image": 0,
        "scale_to_length": 0,
        "seconds": 0,
        "fps": 0,
        "seed": 0,
        "filename_prefix": 0,
        "removed_preview_override": 0,
    }
    preview_override_replacements = {}
    for node_id, node in list(workflow.items()):
        if not isinstance(node, dict):
            continue
        if str(node.get("class_type") or "") != "LTX2SamplingPreviewOverride":
            continue
        model_input = (node.get("inputs") or {}).get("model")
        if isinstance(model_input, list) and model_input:
            preview_override_replacements[str(node_id)] = model_input
        workflow.pop(str(node_id), None)
        patched["removed_preview_override"] += 1
    if preview_override_replacements:
        for node in workflow.values():
            inputs = node.get("inputs") if isinstance(node, dict) else None
            if not isinstance(inputs, dict):
                continue
            for key, value in list(inputs.items()):
                if isinstance(value, list) and value and str(value[0]) in preview_override_replacements:
                    inputs[key] = list(preview_override_replacements[str(value[0])])
    text_nodes = []
    for node_id, node in list(workflow.items()):
        if not isinstance(node, dict):
            continue
        if str(node.get("class_type") or "") == "PreviewImage":
            workflow.pop(str(node_id), None)
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        class_type = str(node.get("class_type") or "")
        title = _node_title(node)
        if "text" in inputs and ("CLIPTextEncode" in class_type or "TextEncode" in class_type or "Conditioning" in class_type):
            text_nodes.append(node)
        if class_type == "LoadImage" and "image" in inputs:
            if remote_source_url:
                node["class_type"] = "RandomPhotoPromptRemoteLoadImageFromMac"
                node["inputs"] = {"source_url": remote_source_url}
            else:
                inputs["image"] = image_load_name
            patched["load_image"] += 1
        if "scale_to_length" in inputs:
            inputs["scale_to_length"] = scale_to_length
            patched["scale_to_length"] += 1
        if "value" in inputs and isinstance(inputs.get("value"), (int, float, str)):
            if "秒" in title or "second" in title:
                inputs["value"] = seconds
                patched["seconds"] += 1
            elif "帧" in title or "fps" in title or "frame" in title:
                inputs["value"] = fps
                patched["fps"] += 1
        for key in ("seed", "noise_seed"):
            if key in inputs and isinstance(inputs.get(key), (int, float, str)):
                inputs[key] = int(seed)
                patched["seed"] += 1
        if "filename_prefix" in inputs and isinstance(inputs.get("filename_prefix"), str):
            raw_prefix = str(inputs.get("filename_prefix") or "video").replace("\\", "/").strip("/")
            base_prefix = Path(raw_prefix).name or "video"
            final_prefix = output_prefix or base_prefix
            inputs["filename_prefix"] = f"{MOBILE_VIDEO_OUTPUT_SUBFOLDER}/{final_prefix}"
            patched["filename_prefix"] += 1
    negative_nodes = {id(node) for node in text_nodes if _looks_negative_text(node)}
    if not negative_nodes and len(text_nodes) >= 2:
        negative_nodes.add(id(text_nodes[1]))
    for node in text_nodes:
        inputs = node["inputs"]
        if id(node) in negative_nodes:
            inputs["text"] = negative_prompt
            patched["negative_text"] += 1
        else:
            inputs["text"] = positive_prompt
            patched["positive_text"] += 1
    if patched["positive_text"] < 1:
        raise ValueError("视频工作流模板里没有找到可写入的正向提示词节点。")
    if patched["load_image"] < 1:
        raise ValueError("视频工作流模板里没有找到 LoadImage 节点。")
    if patched["filename_prefix"] < 1:
        raise ValueError("视频工作流模板里没有找到 SaveVideo 文件名前缀。")
    return workflow, patched, {"scale_to_length": scale_to_length, "seconds": seconds, "fps": fps}


async def _queue_mobile_workflow(workflow, client_id="", output_mode="mac"):
    if REMOTE_COMFYUI_URL:
        return await _queue_remote_mobile_workflow(workflow, client_id, output_mode=output_mode)
    prompt_id = str(uuid.uuid4())
    PromptServer.instance.node_replace_manager.apply_replacements(workflow)
    valid = await execution.validate_prompt(prompt_id, workflow, None)
    if not valid[0]:
        return None, {"error": _mobile_validation_error_message(valid[1], valid[3]), "raw_error": valid[1], "node_errors": valid[3]}
    number = PromptServer.instance.number
    PromptServer.instance.number += 1
    extra_data = {"create_time": int(time.time() * 1000), "source": "random_photo_prompt_mobile"}
    client_id = str(client_id or "").strip()
    if client_id:
        extra_data["client_id"] = client_id
    PromptServer.instance.prompt_queue.put((number, prompt_id, workflow, extra_data, valid[2], {}))
    return {"prompt_id": prompt_id, "number": number, "node_errors": valid[3]}, None


async def _remote_json(method, path, **kwargs):
    url = f"{REMOTE_COMFYUI_URL}{path}"
    timeout = ClientTimeout(total=kwargs.pop("timeout", 30))
    try:
        async with ClientSession(timeout=timeout) as session:
            async with session.request(method, url, **kwargs) as response:
                body = await response.read()
                try:
                    data = json.loads(body.decode("utf-8"))
                except Exception:
                    data = body.decode("utf-8", "ignore")
                if response.status >= 400:
                    return None, {"error": data.get("error") if isinstance(data, dict) else str(data), "status": response.status, "detail": data}
                return data, None
    except Exception as exc:
        return None, {"error": f"远端 ComfyUI 连接失败：{REMOTE_COMFYUI_URL}。请检查远端是否启动、地址端口是否正确、Mac 是否能访问该地址。", "detail": str(exc)}


async def _remote_bytes(path, **kwargs):
    url = f"{REMOTE_COMFYUI_URL}{path}"
    timeout = ClientTimeout(total=kwargs.pop("timeout", 120))
    try:
        async with ClientSession(timeout=timeout) as session:
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
    if ws_patch.get("websocket_node_ids"):
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
            )
        )
        try:
            await asyncio.wait_for(ready_event.wait(), timeout=10)
        except Exception as exc:
            watcher.cancel()
            return None, {"error": f"远端 WebSocket 回传连接失败：{exc}"}
    payload = {"prompt": workflow, "client_id": websocket_client_id, "extra_data": {"source": "random_photo_prompt_mac_remote"}}
    data, error = await _remote_json("POST", "/prompt", json=payload)
    if error:
        if watcher:
            watcher.cancel()
        return None, error
    if not isinstance(data, dict):
        if watcher:
            watcher.cancel()
        return None, {"error": "远端 /prompt 返回了非 JSON 对象。", "detail": data}
    prompt_id = str(data.get("prompt_id") or "")
    if prompt_id and ws_patch.get("websocket_node_ids"):
        prompt_ref["value"] = prompt_id
        REMOTE_WS_OUTPUT_NODES_BY_PROMPT_ID[prompt_id] = set(ws_patch["websocket_node_ids"])
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
        "node_total": node_total,
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
    print(f"[random_photo_prompt] remote websocket image saved prompt_id={prompt_id} path={local_path} bytes={len(image_bytes)}", flush=True)
    return local_path


async def _watch_remote_websocket_outputs(prompt_ref, client_id, ready_event=None, output_nodes=None, output_prefix="", node_total=0, output_mode="mac"):
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
    node_total = max(1, int(node_total or 0))
    try:
        async with ClientSession(timeout=ClientTimeout(total=None, sock_connect=30, sock_read=None)) as session:
            async with session.ws_connect(remote_ws_url) as ws:
                print(f"[random_photo_prompt] remote websocket connected client_id={client_id}", flush=True)
                if ready_event:
                    ready_event.set()
                async for msg in ws:
                    if not prompt_id and isinstance(prompt_ref, dict):
                        prompt_id = str(prompt_ref.get("value") or "").strip()
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
                        if message.get("type") != "executing":
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
                            break
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
                        output_nodes = REMOTE_WS_OUTPUT_NODES_BY_PROMPT_ID.get(prompt_id) or set()
                        raw = bytes(msg.data)
                        if len(raw) <= 8:
                            continue
                        event_type = struct.unpack(">I", raw[:4])[0]
                        if event_type != 1:
                            continue
                        image_type = struct.unpack(">I", raw[4:8])[0]
                        if output_nodes and current_node not in output_nodes and image_type != 2:
                            continue
                        _save_remote_websocket_image(prompt_id, raw[8:], image_type)
    except asyncio.CancelledError:
        raise
    except Exception:
        traceback.print_exc()


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


async def _download_remote_image(image):
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


def _queue_contains(prompt_id, items):
    return any(len(item) > 1 and item[1] == prompt_id for item in items)


def _queue_client_id(prompt_id, items):
    prompt_id = str(prompt_id or "")
    for item in items:
        if len(item) > 3 and str(item[1]) == prompt_id and isinstance(item[3], dict):
            return str(item[3].get("client_id") or "")
    return ""


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
    runtime_images = _mobile_runtime_images_for_prompt(prompt_id)
    if runtime_images:
        return runtime_images
    local_images = _mobile_local_images_for_prompt(prompt_id)
    if local_images:
        return local_images
    if REMOTE_COMFYUI_URL:
        entry, error = await _remote_history(prompt_id)
        if error:
            raise RuntimeError(error.get("error") or "远端历史记录读取失败。")
    else:
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
                item = {"url": f"/view?{params}", **image}
                if REMOTE_COMFYUI_URL:
                    try:
                        local_path = await _download_remote_image(image)
                        subfolder = _mobile_output_subfolder_for_path(local_path)
                        item["filename"] = local_path.name
                        item["subfolder"] = subfolder
                        item["type"] = "output"
                        item["url"] = _mobile_view_url(local_path.name, subfolder)
                    except Exception as exc:
                        item["download_error"] = str(exc)
                images.append(item)
    return images


async def _mobile_video_urls(prompt_id):
    if REMOTE_COMFYUI_URL:
        entry, error = await _remote_history(prompt_id)
        if error:
            raise RuntimeError(error.get("error") or "远端历史记录读取失败。")
    else:
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
                    if REMOTE_COMFYUI_URL:
                        try:
                            local_path = await _download_remote_video(video)
                            item["filename"] = local_path.name
                            item["subfolder"] = MOBILE_VIDEO_OUTPUT_SUBFOLDER
                            item["type"] = "output"
                            item["url"] = _mobile_video_view_url(local_path.name)
                            item.update(_video_dimensions_for_file(local_path))
                        except Exception as exc:
                            item["download_error"] = str(exc)
                    elif video.get("subfolder") == MOBILE_VIDEO_OUTPUT_SUBFOLDER and filename:
                        path = _mobile_video_output_file(filename)
                        if path.is_file():
                            item.update(_video_dimensions_for_file(path))
                    videos.append(item)
    return videos


def _mobile_video_urls_sync(prompt_id):
    if REMOTE_COMFYUI_URL:
        return []
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


def _remember_mobile_prompt_images(prompt_id, images):
    prompt = ""
    for job in MOBILE_SESSION_JOBS:
        if job.get("prompt_id") == prompt_id:
            prompt = job.get("prompt", "")
            break
    if not prompt:
        return
    for image in images:
        filename = image.get("filename")
        if image.get("type") == "runtime":
            image["prompt"] = prompt
            for item in MOBILE_RUNTIME_IMAGES_BY_PROMPT_ID.get(str(prompt_id), []):
                if item.get("filename") == filename:
                    item["prompt"] = prompt
            continue
        if filename:
            _remember_mobile_prompt_file(filename, prompt, image.get("subfolder", ""))
            image["prompt"] = prompt


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
    if REMOTE_COMFYUI_URL:
        running, pending = await _remote_queue()
    else:
        running, pending = PromptServer.instance.prompt_queue.get_current_queue_volatile()
    if REMOTE_COMFYUI_URL and _queue_contains(prompt_id, running):
        queue_client_id = _queue_client_id(prompt_id, running)
        known_client_id = REMOTE_WS_CLIENT_ID_BY_PROMPT_ID.get(str(prompt_id), "")
        watcher = REMOTE_WS_WATCHERS.get(str(prompt_id))
        if queue_client_id and (queue_client_id != known_client_id or not watcher or watcher.done()):
            REMOTE_WS_CLIENT_ID_BY_PROMPT_ID[str(prompt_id)] = queue_client_id
            old = REMOTE_WS_WATCHERS.pop(str(prompt_id), None)
            if old:
                old.cancel()
            node_total = 0
            output_prefix = ""
            output_nodes = set()
            output_mode = "mac"
            for job in MOBILE_SESSION_JOBS:
                if str(job.get("prompt_id") or "") == str(prompt_id):
                    node_total = int(job.get("node_total") or 0)
                    output_prefix = str(job.get("output_prefix") or "")
                    output_mode = str(job.get("output_mode") or "mac")
                    break
            output_nodes = REMOTE_WS_OUTPUT_NODES_BY_PROMPT_ID.get(str(prompt_id)) or set()
            REMOTE_WS_WATCHERS[str(prompt_id)] = asyncio.create_task(
                _watch_remote_websocket_outputs(
                    {"value": str(prompt_id)},
                    queue_client_id,
                    output_nodes=output_nodes,
                    output_prefix=output_prefix,
                    node_total=node_total,
                    output_mode=output_mode,
                )
            )
    images = await _mobile_image_urls(prompt_id)
    videos = await _mobile_video_urls(prompt_id)
    _remember_mobile_prompt_images(prompt_id, images)
    _remember_mobile_prompt_videos(prompt_id, videos)
    if images or videos:
        status = "completed"
    elif _queue_contains(prompt_id, running):
        status = "running"
    elif _queue_contains(prompt_id, pending):
        status = "pending"
    elif REMOTE_COMFYUI_URL and (watcher := REMOTE_WS_WATCHERS.get(str(prompt_id))) and not watcher.done():
        status = "running"
    else:
        status = "unknown"
    if status == "completed":
        before = len(MOBILE_SESSION_JOBS)
        MOBILE_SESSION_JOBS[:] = [job for job in MOBILE_SESSION_JOBS if str(job.get("prompt_id")) != str(prompt_id)]
        if len(MOBILE_SESSION_JOBS) != before:
            _save_mobile_session_jobs()
    result = {"prompt_id": prompt_id, "status": status, "images": images, "videos": videos}
    if REMOTE_COMFYUI_URL and prompt_id in REMOTE_PROGRESS_BY_PROMPT_ID:
        result["progress"] = REMOTE_PROGRESS_BY_PROMPT_ID[prompt_id]
    elif REMOTE_COMFYUI_URL:
        node_total = 0
        for job in MOBILE_SESSION_JOBS:
            if str(job.get("prompt_id") or "") == str(prompt_id):
                node_total = int(job.get("node_total") or 0)
                break
        if node_total > 0:
            if status == "completed":
                result["progress"] = {"value": node_total, "max": node_total, "percent": 100, "node": "", "type": "node"}
            elif status == "running":
                result["progress"] = {"value": 1, "max": node_total, "percent": max(1, round(100 / node_total)), "node": "", "type": "node"}
            elif status == "pending":
                result["progress"] = {"value": 0, "max": node_total, "percent": 0, "node": "", "type": "node"}
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
    }


def _load_image_interrogator():
    if str(NODE_DIR) not in sys.path:
        sys.path.insert(0, str(NODE_DIR))
    from image_interrogator import ImageInterrogationError, interrogate_image_bytes

    return ImageInterrogationError, interrogate_image_bytes


class RandomPhotoPrompt:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "scale": (["一档", "二档", "三档", "四档"], {"default": "二档"}),
                "era": (["现代", "古装"], {"default": "现代"}),
                "shot": (
                    [
                        "随机",
                        "头部",
                        "半身",
                        "全身",
                    ],
                    {"default": "随机"},
                ),
                "use_pregenerated_prompt": ("BOOLEAN", {"default": True}),
                "auto_resolution": ("BOOLEAN", {"default": True}),
                "cached_prompt": ("STRING", {"default": "", "multiline": True}),
                "cached_negative_prompt": ("STRING", {"default": "", "multiline": True}),
                "cached_signature": ("STRING", {"default": ""}),
                "cached_aspect": ("STRING", {"default": "portrait"}),
                "cached_prompt_source": ("STRING", {"default": ""}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("positive_prompt", "negative_prompt")
    FUNCTION = "generate"
    CATEGORY = "Random Photo"

    @classmethod
    def IS_CHANGED(cls):
        return time.time()

    def generate(self, scale, era, shot, use_pregenerated_prompt=True, auto_resolution=True, cached_prompt="", cached_negative_prompt="", cached_signature="", cached_aspect="portrait", cached_prompt_source=""):
        try:
            aspect = _normalize_aspect(cached_aspect)
            signature = _prompt_signature(scale, shot, aspect, era)
            if use_pregenerated_prompt and cached_prompt and str(cached_signature or "") == signature:
                return (clean_prompt_text(cached_prompt), cached_negative_prompt)
            item, _resolution = _build_desktop_prompt_with_mobile_logic(scale, shot, str(time.time()), era)
            return (_prompt_text(item), item.get("negative_prompt", ""))
        except Exception:
            message = f"RandomPhotoPrompt error:\n{traceback.format_exc()}"
            return (message, "")


class RandomPhotoImageInterrogator:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "cached_prompt": ("STRING", {"default": "", "multiline": True}),
                "cached_signature": ("STRING", {"default": ""}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "generate"
    CATEGORY = "Random Photo"

    def generate(self, cached_prompt="", cached_signature=""):
        return (clean_prompt_text(cached_prompt) or "请在节点上选择图片并点击反推提示词。",)


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


async def expand_keyword_photo_prompt(request):
    try:
        data = await request.json()
        seed_text = data.get("seed", "")
        result = generate_keyword_expansion_prompt(
            seed_text=seed_text,
            scale=data.get("scale", ""),
            shot=data.get("shot", ""),
        )
        return web.json_response(
            {
                "prompt": clean_prompt_text(result["prompt"]),
                "negative_prompt": result.get("negative_prompt", ""),
                "signature": result.get("signature", ""),
                "aspect": data.get("aspect") or "portrait",
                "source": result.get("source", "keyword_expansion"),
            }
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
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
        shot_config = _mobile_shot_config(data.get("shot", "full_body_portrait"))
        seed_text = str(data.get("seed") or f"{time.time()}-{uuid.uuid4()}")
        prompt_item, resolution = _build_mobile_prompt_for_scope(scale, shot_config, seed_text, era)
        width = int(resolution["width"])
        height = int(resolution["height"])
        return web.json_response(
            {
                "prompt": _prompt_text(prompt_item),
                "display_prompt": _display_prompt_text(prompt_item),
                "negative_prompt": prompt_item.get("negative_prompt", ""),
                "scale": prompt_item.get("scale", scale),
                "shot": prompt_item.get("shot_key", shot_config["shot"]),
                "era": prompt_item.get("era", era),
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
    try:
        return web.FileResponse(MOBILE_PAGE_PATH)
    except Exception:
        return web.Response(text=traceback.format_exc(), status=500)


async def mobile_root_redirect(request):
    raise web.HTTPFound("/random_photo_prompt/mobile")


async def _mobile_entry_status():
    output_dir = _mobile_local_output_dir()
    remote_enabled = bool(REMOTE_COMFYUI_URL)
    workflow_statuses = _mobile_workflow_statuses()
    image_workflows_ready = all(item["template_ready"] for item in workflow_statuses.values() if item["type"] == "image")
    video_workflow_ready = workflow_statuses.get(MOBILE_VIDEO_WORKFLOW_KEY, {}).get("template_ready", False)
    zimage_models = await _available_mobile_zimage_models()
    zit_models = zimage_models["zit_models"]
    zib_models = zimage_models["zib_models"]
    loras = _available_loras()
    return {
        "entry_mode": "remote_direct" if remote_enabled else "local",
        "entry_label": "内部远端服务" if remote_enabled else "内部本机服务",
        "remote": {
            "enabled": remote_enabled,
            "url": REMOTE_COMFYUI_URL,
            "history_timeout": REMOTE_HISTORY_TIMEOUT,
            "delete_output": REMOTE_DELETE_OUTPUT,
        },
        "output": {
            "dir": str(output_dir),
            "exists": output_dir.exists(),
            "writable": os.access(output_dir, os.W_OK),
        },
        "models": {
            "source": zimage_models["source"],
            "zit_dir": str(ZIT_MODEL_DIR),
            "zit_dir_ready": ZIT_MODEL_DIR.exists(),
            "zit_count": len(zit_models),
            "zib_count": len(zib_models),
            "lora_dir": _lora_dir_display_path(),
            "lora_count": len(loras),
        },
        "workflow_statuses": workflow_statuses,
        "health": {
            "local_mobile": {"ok": True, "message": "本机手机页接口正常。"},
            "remote_comfyui": {
                "ok": not remote_enabled,
                "message": f"已配置远端 {REMOTE_COMFYUI_URL}，统一入口会通过 18199 访问。" if remote_enabled else "未设置 RPP_REMOTE_COMFYUI_URL，当前仅作为内部本机服务。",
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
        _local_status_item(True, "ZIB / LoRA", f"ZIB {payload['models']['zib_count']} 个，LoRA {payload['models']['lora_count']} 个。"),
        _local_status_item(True, "统一入口", "用户入口统一使用 18199；本服务只作为内部接口。"),
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
    <p class="lead">本页只检查手机端内部服务，不作为用户入口；网页端和手机端统一从 18199 进入。</p>
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
    loras = _available_loras()
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
            "model_source": zimage_models["source"],
            "zit_model_dir_ready": ZIT_MODEL_DIR.exists(),
            "loras": loras,
            "lora_dir": _lora_dir_display_path(),
            "connected": True,
            "message": "" if template_ready else (selected_workflow_status.get("message") or f"请先保存 {workflow_path.name} 后再生成。"),
            "guidance": selected_workflow_status.get("guidance", ""),
            "template_path": str(workflow_path),
            **entry_status,
        }
    )


def _mobile_shot_config(value):
    text = str(value or "").strip()
    if text in {"random", "随机", "随机镜头"}:
        key = random.choice(("head_shot", "half_body", "full_body"))
        return MOBILE_SCOPE_PRESETS[key]
    shot_map = {
        "full_body": "full_body",
        "全身": "full_body",
        "全身像": "full_body",
        "half_body": "half_body",
        "半身": "half_body",
        "半身像": "half_body",
        "半身镜头": "half_body",
        "大腿以上": "half_body",
        "大腿以上镜头": "half_body",
        "head_shot": "head_shot",
        "头部": "head_shot",
        "头部镜头": "head_shot",
        "肩膀及以上": "head_shot",
        "肩膀及以上镜头": "head_shot",
        "肩部以上": "head_shot",
        "肩部以上镜头": "head_shot",
        "肩部以上特写": "head_shot",
    }
    key = text if text in MOBILE_SCOPE_PRESETS else shot_map.get(text)
    if key not in MOBILE_SCOPE_PRESETS:
        raise ValueError(f"不支持的镜头：{text}")
    return MOBILE_SCOPE_PRESETS[key]


async def generate_mobile_image(request):
    try:
        data = await request.json()
        workflow_key, workflow_config = _mobile_workflow_config(data.get("workflow"))
        if workflow_config.get("type", "image") != "image":
            workflow_key, workflow_config = _mobile_workflow_config(MOBILE_DEFAULT_WORKFLOW_KEY)
        template = _load_mobile_workflow(workflow_key)
        zimage_models = await _available_mobile_zimage_models()
        requested_zit_model = str(data.get("zit_model") or "").strip()
        requested_zib_model = str(data.get("zib_model") or "").strip()
        if workflow_key == "zib_single":
            zit_model = ""
            zib_model = _resolve_zib_model(requested_zib_model, zimage_models["zib_models"])
        elif workflow_key == "zitb_double":
            zit_model = _resolve_zit_model(requested_zit_model, zimage_models["zit_models"])
            zib_model = _resolve_zib_model(requested_zib_model, zimage_models["zib_models"])
        else:
            zit_model = _resolve_zit_model(requested_zit_model, zimage_models["zit_models"])
            zib_model = ""
        lora_name = _resolve_lora_name(data.get("lora_name"))
        lora_strength = _resolve_lora_strength(data.get("lora_strength"))
        scale = data.get("scale", "bold")
        era = data.get("era", "modern")
        shot_config = _mobile_shot_config(data.get("shot", "full_body_portrait"))
        custom_prompt = str(data.get("custom_prompt") or "").strip()
        client_id = str(data.get("client_id") or "").strip()
        output_mode = "mac"
        requested_count = max(1, min(int(data.get("count", 1) or 1), 64))
        remaining_slots = max(0, MOBILE_MAX_ACTIVE_JOBS - await _mobile_active_job_count())
        if remaining_slots <= 0:
            return web.json_response({"error": f"当前任务数已达到 {MOBILE_MAX_ACTIVE_JOBS}，请等待完成后再添加。"}, status=429)
        count = min(requested_count, remaining_slots)
        jobs = []
        errors = []
        for index in range(count):
            seed_text = f"{time.time()}-{uuid.uuid4()}-{index}"
            if custom_prompt:
                prompt_item = _custom_mobile_prompt_item(custom_prompt, seed_text)
                resolution = _mobile_custom_resolution(custom_prompt, data.get("custom_resolution"))
            else:
                prompt_item, resolution = _build_mobile_prompt_for_scope(scale, shot_config, seed_text, era)
            width = int(resolution["width"])
            height = int(resolution["height"])
            aspect = resolution["aspect"]
            if workflow_key == "zitb_double":
                _use_chinese_negative_prompt(prompt_item, scale, shot_config, width, height, aspect)
            seed = int(data.get("seed") or prompt_item.get("seed") or int(time.time() * 1000))
            if count > 1 and not data.get("seed"):
                seed = int(prompt_item.get("seed") or seed)
            output_prefix = f"mobile_{uuid.uuid4().hex[:12]}"
            workflow, patched = _patch_mobile_workflow(template, prompt_item, width, height, seed, zit_model, output_prefix, lora_name, lora_strength, zib_model)
            queued, error = await _queue_mobile_workflow(workflow, client_id, output_mode=output_mode)
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
                "lora_name": lora_name,
                "lora_strength": lora_strength,
                "scale": prompt_item.get("scale", scale),
                "shot": prompt_item.get("shot_key", shot_config["shot"]),
                "custom_prompt": bool(custom_prompt),
                "custom_resolution": data.get("custom_resolution") if custom_prompt else "",
                "era": prompt_item.get("era", era),
                "aspect": aspect,
                "width": width,
                "height": height,
                "seed": seed,
                "output_prefix": output_prefix,
                "output_mode": output_mode,
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
        requested_count = max(1, min(int(data.get("count", 1) or 1), 64))
        remaining_slots = max(0, MOBILE_MAX_ACTIVE_JOBS - await _mobile_active_job_count())
        if remaining_slots <= 0:
            return web.json_response({"error": f"当前任务数已达到 {MOBILE_MAX_ACTIVE_JOBS}，请等待完成后再添加。"}, status=429)
        count = min(requested_count, remaining_slots)
        source_filename = str(data.get("source_filename") or "")
        source_path, image_load_name = _copy_mobile_gallery_image_to_input(source_filename)
        remote_source_url = _mac_proxy_source_image_url(source_filename) if REMOTE_COMFYUI_URL else ""
        action_text = data.get("action_text", "")
        fps = data.get("fps", 16)
        requested_seconds = normalize_video_seconds(data.get("seconds", 8))
        source_prompt = _mobile_prompt_for_gallery_file(Path(source_filename).name)
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
                "width": int(resolution["width"]),
                "height": int(resolution["height"]),
                "seed": seed,
                "source_filename": Path(source_filename).name,
                "output_prefix": output_prefix,
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
        _mobile_output_file(source_filename)
        action, family, used_prompt, frame_scope = _pregenerate_video_action_for_image(
            source_filename,
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
        _ensure_mobile_session_jobs_loaded()
        return web.json_response({"jobs": [await _mobile_session_job(item) for item in MOBILE_SESSION_JOBS]})
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


async def mobile_gallery_videos(request):
    try:
        return web.json_response({"videos": _mobile_gallery_videos()})
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


if not _route_exists("POST", "/random_photo_prompt/generate"):
    PromptServer.instance.routes.post("/random_photo_prompt/generate")(generate_random_photo_prompt)
if not _route_exists("POST", "/random_photo_prompt/keyword_expand"):
    PromptServer.instance.routes.post("/random_photo_prompt/keyword_expand")(expand_keyword_photo_prompt)
if not _route_exists("POST", "/random_photo_prompt/resolve_resolution"):
    PromptServer.instance.routes.post("/random_photo_prompt/resolve_resolution")(resolve_random_photo_prompt_resolution)
if not _route_exists("POST", "/random_photo_prompt/interrogate"):
    PromptServer.instance.routes.post("/random_photo_prompt/interrogate")(interrogate_random_photo_prompt)
if not _route_exists("GET", "/"):
    PromptServer.instance.routes.get("/")(mobile_root_redirect)
if not _route_exists("GET", "/random_photo_prompt/mobile"):
    PromptServer.instance.routes.get("/random_photo_prompt/mobile")(mobile_generation_page)
if not _route_exists("GET", "/random_photo_prompt/mobile/status"):
    PromptServer.instance.routes.get("/random_photo_prompt/mobile/status")(mobile_generation_status)
if not _route_exists("GET", "/random_photo_prompt/local/status"):
    PromptServer.instance.routes.get("/random_photo_prompt/local/status")(local_status_page)
if not _route_exists("POST", "/random_photo_prompt/mobile/prompt"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/prompt")(pregenerate_mobile_image_prompt)
if not _route_exists("POST", "/random_photo_prompt/mobile/generate"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/generate")(generate_mobile_image)
if not _route_exists("POST", "/random_photo_prompt/mobile/video/generate"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/video/generate")(generate_mobile_video)
if not _route_exists("POST", "/random_photo_prompt/mobile/video/action"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/video/action")(pregenerate_mobile_video_action)
if not _route_exists("GET", "/random_photo_prompt/mobile/video/action"):
    PromptServer.instance.routes.get("/random_photo_prompt/mobile/video/action")(pregenerate_mobile_video_action)
if not _route_exists("GET", "/random_photo_prompt/mobile/job/{prompt_id}"):
    PromptServer.instance.routes.get("/random_photo_prompt/mobile/job/{prompt_id}")(mobile_job_detail)
if not _route_exists("GET", "/random_photo_prompt/mobile/jobs"):
    PromptServer.instance.routes.get("/random_photo_prompt/mobile/jobs")(mobile_session_jobs)
if not _route_exists("POST", "/random_photo_prompt/mobile/remote_runtime/clear"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/remote_runtime/clear")(clear_remote_mobile_runtime_state)
if not _route_exists("GET", "/random_photo_prompt/mobile/runtime_image/{prompt_id}/{filename}"):
    PromptServer.instance.routes.get("/random_photo_prompt/mobile/runtime_image/{prompt_id}/{filename}")(mobile_runtime_image)
if not _route_exists("GET", "/random_photo_prompt/mobile/gallery"):
    PromptServer.instance.routes.get("/random_photo_prompt/mobile/gallery")(mobile_gallery_images)
if not _route_exists("GET", "/random_photo_prompt/mobile/videos"):
    PromptServer.instance.routes.get("/random_photo_prompt/mobile/videos")(mobile_gallery_videos)
if not _route_exists("POST", "/random_photo_prompt/mobile/gallery/delete"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/gallery/delete")(delete_mobile_gallery_images)
if not _route_exists("POST", "/random_photo_prompt/mobile/videos/delete"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/videos/delete")(delete_mobile_gallery_videos)
if not _route_exists("POST", "/random_photo_prompt/remote/delete_output"):
    PromptServer.instance.routes.post("/random_photo_prompt/remote/delete_output")(delete_remote_output_file)
PromptServer.instance.add_on_prompt_handler(_block_remote_asset_save_on_prompt)
	
	
NODE_CLASS_MAPPINGS = {
    "RandomPhotoPrompt": RandomPhotoPrompt,
    "RandomPhotoImageInterrogator": RandomPhotoImageInterrogator,
    "RandomPhotoPromptRemoteUploadImage": RandomPhotoPromptRemoteUploadImage,
    "RandomPhotoPromptRemoteLoadImageFromMac": RandomPhotoPromptRemoteLoadImageFromMac,
    "RandomPhotoPromptRemoteUploadVideo": RandomPhotoPromptRemoteUploadVideo,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RandomPhotoPrompt": "随机写真提示词",
    "RandomPhotoImageInterrogator": "图片反推提示词",
    "RandomPhotoPromptRemoteUploadImage": "远端图片回传到 Mac",
    "RandomPhotoPromptRemoteLoadImageFromMac": "从 Mac 读取视频源图",
    "RandomPhotoPromptRemoteUploadVideo": "远端视频回传到 Mac",
}

WEB_DIRECTORY = "./web"
