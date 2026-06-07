import sys
import time
import traceback
import json
import asyncio
import copy
import platform
import random
import re
import shutil
import subprocess
import uuid
import urllib.parse
from pathlib import Path

import execution
import folder_paths
from aiohttp import web
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
MOBILE_PAGE_PATH = NODE_DIR / "web" / "mobile.html"
MOBILE_WORKFLOW_PATH = NODE_DIR / "mobile_workflow_api.json"
MOBILE_WORKFLOWS = {
    "zit_single": {"label": "ZIT单采", "path": MOBILE_WORKFLOW_PATH, "type": "image"},
    "zitb_double": {"label": "ZITB双采", "path": NODE_DIR / "mobile_workflow_api_2.json", "type": "image"},
    "ltx_video": {"label": "图生视频", "path": NODE_DIR / "mobile_workflow_api_3.json", "type": "video"},
}
MOBILE_DEFAULT_WORKFLOW_KEY = "zit_single"
MOBILE_VIDEO_WORKFLOW_KEY = "ltx_video"
ZIT_MODEL_DIR = Path(folder_paths.models_dir) / "diffusion_models" / "z_image"
ZIT_MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".gguf"}
ZIMAGE_LORA_SUBDIR = "Zimage"
LORA_MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt"}
MOBILE_OUTPUT_SUBFOLDER = "random_photo_prompt_mobile"
MOBILE_VIDEO_OUTPUT_SUBFOLDER = "random_photo_prompt_mobile_video"
MOBILE_VIDEO_INPUT_SUBFOLDER = "random_photo_prompt_mobile_video"
MOBILE_SCOPE_PRESETS = {
    "head_shot": {"shot": "head_shot", "aspect": "portrait", "width": 1024, "height": 1344},
    "upper_body": {"shot": "upper_body", "aspect": "portrait", "width": 1024, "height": 1536},
    "half_body": {"shot": "half_body", "aspect": "portrait", "width": 1024, "height": 1344},
    "large_half_body": {"shot": "large_half_body", "aspect": "portrait", "width": 1037, "height": 1536},
    "full_body": {"shot": "full_body", "aspect": "portrait", "width": 864, "height": 1536},
}
MOBILE_MAX_ACTIVE_JOBS = 100
MOBILE_SESSION_JOBS = []
MOBILE_PROMPT_BY_FILENAME = {}
MOBILE_VIDEO_PROMPT_BY_FILENAME = {}
MOBILE_VIDEO_DIMENSIONS_BY_FILENAME = {}
MOBILE_PROMPT_INDEX_NAME = ".random_photo_prompt_mobile_prompts.json"
MOBILE_GALLERY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MOBILE_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv"}
MOBILE_MAX_IMAGE_HEIGHT = 1536
MOBILE_RESOLUTION_MULTIPLE = 8
MOBILE_RESOLUTION_DOWNSHIFT = 0.875
MAX_POSITIVE_PROMPT_LENGTH = 800
MOBILE_STANDING_FULL_BODY_RESOLUTION = {
    "aspect": "portrait",
    "width": 864,
    "height": 1536,
    "framing": "窄长站姿全身构图",
}
MOBILE_CUSTOM_RESOLUTION_PRESETS = {
    "704x1536": {"aspect": "portrait", "width": 704, "height": 1536, "framing": ""},
    "768x1536": {"aspect": "portrait", "width": 768, "height": 1536, "framing": ""},
    "864x1536": {"aspect": "portrait", "width": 864, "height": 1536, "framing": ""},
    "1037x1536": {"aspect": "portrait", "width": 1037, "height": 1536, "framing": ""},
    "1024x1536": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": ""},
    "1024x1344": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": ""},
    "1366x1024": {"aspect": "landscape", "width": 1366, "height": 1024, "framing": ""},
    "1536x1024": {"aspect": "landscape", "width": 1536, "height": 1024, "framing": ""},
    "1024x1024": {"aspect": "portrait", "width": 1024, "height": 1024, "framing": ""},
}
PROMPT_DISPLAY_PART_ORDER = (
    "camera",
    "character",
    "makeup",
    "outfit",
    "pose_expression",
    "scene_light",
)
PROMPT_LIMIT_PART_ORDER = ("pose_expression", "scene_light", "quality", "camera", "character", "outfit", "makeup", "hair")

MOBILE_RESOLUTION_RULES = {
    "full_body": (
        (
            ("大字", "四肢展开", "双臂自然向两侧展开", "手脚乱舞", "跳", "跃起", "腾空"),
            {"aspect": "landscape", "width": 1536, "height": 1024, "framing": "横向全身动态构图"},
        ),
        (
            ("俯拍", "顶视角", "正上方", "仰躺", "侧躺", "横躺", "平躺", "趴", "横向展开", "沿宽画幅", "床中央", "睡", "睡着"),
            {"aspect": "landscape", "width": 1536, "height": 1024, "framing": "横向全身构图，身体沿宽画幅展开，从头到脚完整入镜"},
        ),
        (
            ("近大远小", "强透视", "前景", "靠近镜头", "脚伸到镜头", "手掌和脚尖", "脚尖和脚踝因近大远小"),
            {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向全身强透视构图"},
        ),
        (
            ("站立", "站姿", "直立", "倚靠", "靠墙", "迈步", "行走", "走姿"),
            MOBILE_STANDING_FULL_BODY_RESOLUTION,
        ),
        (
            ("坐", "坐姿", "坐在", "侧坐", "跪", "跪姿", "跪坐", "膝", "蹲", "半蹲", "蜷", "抱膝"),
            {"aspect": "portrait", "width": 1037, "height": 1536, "framing": "竖向全身坐跪构图"},
        ),
        (
            ("扭腰", "回望", "转身", "侧身", "交叉点地", "向后拉长", "双手一上一下"),
            {"aspect": "portrait", "width": 864, "height": 1536, "framing": "竖向全身动态姿势构图"},
        ),
    ),
    "half_body": (
        (
            ("横躺", "侧躺", "仰躺", "平躺", "俯拍", "顶视角", "床", "横向", "横跨", "横向靠", "横向坐", "横向趴", "沿宽画幅", "斜向铺"),
            {"aspect": "landscape", "width": 1366, "height": 1024, "framing": "横向半身镜头，腰部及以上入镜，头部、肩颈、胸部和腰部完整"},
        ),
        (
            ("坐", "坐姿", "跪", "跪坐", "膝", "直立", "站", "站立", "竖向", "纵向"),
            {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "竖向半身镜头，腰部及以上入镜，头部、胸腰和双手完整"},
        ),
    ),
    "large_half_body": (
        (
            ("横躺", "平躺", "俯拍", "顶视角", "横向", "横跨", "横向靠", "横向坐", "横向趴", "沿宽画幅", "斜向铺"),
            {"aspect": "landscape", "width": 1536, "height": 1024, "framing": "大腿以上镜头，横向构图"},
        ),
        (
            ("坐", "坐姿", "跪", "跪坐", "膝", "直立", "站", "站立", "竖向", "纵向", "仰躺", "侧躺"),
            {"aspect": "portrait", "width": 1037, "height": 1536, "framing": "大腿以上镜头，竖向构图"},
        ),
    ),
    "upper_body": (
        (
            ("横向", "侧脸", "躺", "侧躺"),
            {"aspect": "landscape", "width": 1536, "height": 1024, "framing": "横向上半身镜头，胸部及以上入镜，头顶完整"},
        ),
    ),
    "head_shot": (
        (
            ("横向", "侧脸", "躺", "侧躺"),
            {"aspect": "landscape", "width": 1366, "height": 1024, "framing": "横向头部镜头，肩膀及以上入镜，头顶完整"},
        ),
    ),
}
MOBILE_FRAMING_COMPACT_REPLACEMENTS = {
    "横向全身动态宽构图，四肢外轮廓完整，四周留环境边距": "横向全身动态构图",
    "横向全身构图，身体沿宽画幅展开，从头到脚完整入镜": "横向宽构图，身体沿画幅展开",
    "竖向全身非站姿构图，头部、手臂、腿部、脚部和姿势外轮廓完整": "竖向全身非站姿构图",
    "窄长全身构图，从头顶到脚掌完整入镜，脚下留地面边距": "窄长全身构图，脚下留地面边距",
    "横向半身镜头，腰部及以上入镜，头部、肩颈、胸部和腰部完整": "横向半身构图，腰部以上完整",
    "竖向半身镜头，腰部及以上入镜，头部、胸腰和双手完整": "竖向半身构图，胸腰和双手完整",
    "横向大半身镜头，小腿及以上入镜，身体沿宽画幅展开到小腿": "大腿以上镜头，横向构图",
    "竖向大半身镜头，小腿及以上入镜，头部到小腿完整": "大腿以上镜头，竖向构图",
    "横向上半身镜头，胸部及以上入镜，头顶完整": "横向上半身构图，头顶完整",
    "横向头部镜头，肩膀及以上入镜，头顶完整": "横向头部构图，头顶完整",
    "竖向全身构图，从头到脚完整入镜，姿势外轮廓完整": "竖向全身构图",
    "上半身镜头，胸部及以上入镜，头顶完整，画面停在上腰": "竖向上半身构图，头顶完整",
    "头部镜头，肩膀及以上入镜，头顶完整": "竖向头部构图，头顶完整",
}
MOBILE_DEFAULT_RESOLUTIONS = {
    "full_body": {"aspect": "portrait", "width": 864, "height": 1536, "framing": "竖向全身构图"},
    "large_half_body": {"aspect": "portrait", "width": 1037, "height": 1536, "framing": "大腿以上镜头，竖向构图"},
    "half_body": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "竖向半身镜头，腰部及以上入镜，头部、胸腰和双手完整"},
    "upper_body": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "上半身镜头，胸部及以上入镜，头顶完整，画面停在上腰"},
    "head_shot": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "头部镜头，肩膀及以上入镜，头顶完整"},
}
MOBILE_DIRECTOR_RESOLUTION_RULES = {
    "sunny_multicolor_pool_glamour": {
        "full_body": {"aspect": "portrait", "width": 864, "height": 1536, "framing": "竖向全身阳光水光构图，从头到脚完整入镜，脚下留地面或池边边距"},
        "large_half_body": {"aspect": "portrait", "width": 1037, "height": 1536, "framing": "大腿以上镜头，竖向构图"},
        "half_body": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "竖向半身多色反光构图，腰部及以上入镜"},
        "upper_body": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "竖向上半身水光近景，胸部及以上入镜，头顶完整"},
    },
    "beach_vivid_glamour": {
        "full_body": {"aspect": "portrait", "width": 864, "height": 1536, "framing": "竖向全身海边构图，从头到脚完整入镜，脚下沙面边距清楚"},
        "large_half_body": {"aspect": "portrait", "width": 1037, "height": 1536, "framing": "大腿以上镜头，竖向构图"},
        "half_body": {"aspect": "landscape", "width": 1366, "height": 1024, "framing": "横向半身海边构图，腰部及以上入镜，保留海风空间"},
    },
    "garden_waterlight_seduction": {
        "full_body": {"aspect": "portrait", "width": 1037, "height": 1536, "framing": "竖向全身花园构图，从头到脚完整入镜，脚下草地或地面边距清楚"},
        "large_half_body": {"aspect": "portrait", "width": 1037, "height": 1536, "framing": "大腿以上镜头，竖向构图"},
        "half_body": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "竖向半身花园水光构图，腰部及以上入镜"},
        "upper_body": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "竖向上半身暖阳近景，胸部及以上入镜，头顶完整"},
    },
    "glass_balcony_colorlight": {
        "full_body": {"aspect": "portrait", "width": 1037, "height": 1536, "framing": "竖向全身玻璃反射构图，从头到脚完整入镜，脚下地面边距清楚"},
        "large_half_body": {"aspect": "portrait", "width": 1037, "height": 1536, "framing": "大腿以上镜头，竖向构图"},
        "half_body": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "竖向半身玻璃彩光构图，腰部及以上入镜"},
        "upper_body": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "竖向上半身玻璃反光近景，胸部及以上入镜，头顶完整"},
        "head_shot": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "竖向头部玻璃反光近景，肩膀及以上入镜，头顶完整"},
    },
    "bright_studio_color_fashion": {
        "full_body": {"aspect": "portrait", "width": 1037, "height": 1536, "framing": "竖向全身彩色棚拍构图，从头到脚完整入镜，脚下地面边距清楚"},
        "large_half_body": {"aspect": "portrait", "width": 1037, "height": 1536, "framing": "大腿以上镜头，竖向构图"},
        "half_body": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "竖向半身彩色棚拍构图，腰部及以上入镜"},
        "upper_body": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "竖向上半身彩色棚拍近景，胸部及以上入镜，头顶完整"},
        "head_shot": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "竖向头部彩色棚拍近景，肩膀及以上入镜，头顶完整"},
    },
    "tropical_terrace_sensuality": {
        "full_body": {"aspect": "portrait", "width": 864, "height": 1536, "framing": "竖向全身热带露台构图，从头到脚完整入镜，脚下甲板或地面边距清楚"},
        "large_half_body": {"aspect": "portrait", "width": 1037, "height": 1536, "framing": "大腿以上镜头，竖向构图"},
        "half_body": {"aspect": "landscape", "width": 1366, "height": 1024, "framing": "横向半身热带露台构图，腰部及以上入镜"},
    },
    "sweet_vivid_tease": {
        "full_body": {"aspect": "portrait", "width": 1037, "height": 1536, "framing": "竖向全身甜艳构图，从头到脚完整入镜，脚下边距清楚"},
        "large_half_body": {"aspect": "portrait", "width": 1037, "height": 1536, "framing": "大腿以上镜头，竖向构图"},
        "half_body": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "竖向半身甜艳构图，腰部及以上入镜"},
        "upper_body": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "竖向上半身甜艳近景，胸部及以上入镜，头顶完整"},
        "head_shot": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "竖向头部甜艳近景，肩膀及以上入镜，头顶完整"},
    },
    "forced_perspective_focus": {
        "full_body": {"aspect": "portrait", "width": 1037, "height": 1536, "framing": "竖向全身强透视构图，从头到脚完整入镜，前景肢体和脚下地面边距清楚"},
        "large_half_body": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "大腿以上镜头，竖向构图"},
        "half_body": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "竖向半身强透视构图，腰部及以上入镜，前景手部完整"},
        "upper_body": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "竖向上半身强透视近景，胸部及以上入镜，头顶完整"},
        "head_shot": {"aspect": "portrait", "width": 1024, "height": 1344, "framing": "竖向头部强透视近景，肩膀及以上入镜，头顶完整"},
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


def _prompt_signature(scale, shot, aspect="portrait"):
    return f"mobile-logic-v1|{scale or ''}|{shot or ''}"


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


def _build_prompt_item(scale, shot, seed_text="", aspect="portrait", width=None, height=None):
    generate_prompt_items = _load_prompt_generator()
    scale_map = {
        "一档": "normal",
        "二档": "bold",
        "三档": "nsfw",
        "普通": "normal",
        "大胆": "bold",
        "NSFW": "nsfw",
        "normal": "normal",
        "bold": "bold",
        "nsfw": "nsfw",
    }
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


def _build_mobile_prompt_item(scale, shot_config, seed_text):
    shot = shot_config["shot"]
    aspect = shot_config["aspect"]
    width = shot_config["width"]
    height = shot_config["height"]
    return _build_prompt_item(scale, shot, seed_text, aspect, width, height)


FIXED_CHARACTER_IDENTITY = "22岁冷白皮K-pop韩国夜店女王"


def _ensure_scoped_character_prompt(prompt_item):
    item = copy.deepcopy(prompt_item)
    parts = item.get("dimension_parts")
    if isinstance(parts, dict):
        shot_key = item.get("shot_key") or ""
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
    return prompt_item.get("compact_prompt") or prompt_item["positive_prompt"]


def _rebuild_prompt_text_from_parts(parts):
    lines = [
        str(parts.get(name, "")).strip()
        for name in PROMPT_LIMIT_PART_ORDER
        if str(parts.get(name, "")).strip()
    ]
    return "\n\n".join(f"{line.rstrip('，。')}。" for line in lines)


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
    for name in ("scene_light", "outfit", "pose_expression", "makeup", "camera"):
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
        str(parts.get(name, "")).strip()
        for name in PROMPT_DISPLAY_PART_ORDER
        if str(parts.get(name, "")).strip()
    ]
    if lines:
        return "\n\n".join(lines)
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


def _assistant_mobile_prompt_item(seed_text="", scale="", shot_config=None):
    shot_key = (shot_config or {}).get("shot", "")
    result = generate_keyword_expansion_prompt(seed_text=seed_text, scale=scale, shot=shot_key)
    text = str(result.get("prompt") or "").strip()
    if shot_config:
        resolution_probe = {"dimension_parts": {"camera": text, "pose_expression": text, "scene_light": text}}
        resolution = _mobile_resolution_for_prompt(resolution_probe, shot_key)
    else:
        resolution = _mobile_resolution_for_custom_prompt(text)
    return {
        "scale": scale or "assistant_rule",
        "shot": shot_key or "规则2",
        "shot_key": shot_key or "assistant_rule",
        "aspect": resolution.get("aspect", "portrait"),
        "width": resolution.get("width"),
        "height": resolution.get("height"),
        "seed": abs(hash(str(seed_text))) % 2147483647,
        "positive_prompt": text,
        "compact_prompt": text,
        "negative_prompt": result.get("negative_prompt", ""),
        "dimension_parts": {"assistant_rule": text},
        "prompt_audit_issues": [],
    }, resolution


def _mobile_resolution_for_custom_prompt(prompt_text):
    text = str(prompt_text or "")
    if any(marker in text for marker in ("横向", "横屏", "宽画幅", "横躺", "平躺", "大字型", "四肢展开")):
        return _clamp_mobile_resolution({"aspect": "landscape", "width": 1536, "height": 1024, "framing": ""})
    if any(marker in text for marker in ("站立", "站姿", "直立", "站在", "迈步", "行走", "走姿", "倚靠", "靠墙")):
        return _clamp_mobile_resolution(MOBILE_STANDING_FULL_BODY_RESOLUTION)
    if any(marker in text for marker in ("全身", "从头到脚", "脚部", "脚掌", "脚尖", "站立", "长腿完整")):
        return _clamp_mobile_resolution({"aspect": "portrait", "width": 864, "height": 1536, "framing": ""})
    if any(marker in text for marker in ("大半身", "大腿以上", "小腿及以上", "小腿", "膝盖")):
        return _clamp_mobile_resolution({"aspect": "portrait", "width": 1037, "height": 1536, "framing": ""})
    if any(marker in text for marker in ("半身", "腰部及以上", "腰部", "腰线")):
        return _clamp_mobile_resolution({"aspect": "portrait", "width": 1024, "height": 1344, "framing": ""})
    if any(marker in text for marker in ("头部", "肩膀及以上", "肩部以上", "脸部特写", "面部特写")):
        return _clamp_mobile_resolution({"aspect": "portrait", "width": 1024, "height": 1344, "framing": ""})
    if any(marker in text for marker in ("上半身", "胸部及以上", "胸部以上", "胸部")):
        return _clamp_mobile_resolution({"aspect": "portrait", "width": 1024, "height": 1536, "framing": ""})
    return _clamp_mobile_resolution({"aspect": "portrait", "width": 1024, "height": 1536, "framing": ""})


def _mobile_custom_resolution(prompt_text, preset=""):
    key = str(preset or "").strip()
    if key in MOBILE_CUSTOM_RESOLUTION_PRESETS:
        return _clamp_mobile_resolution(MOBILE_CUSTOM_RESOLUTION_PRESETS[key])
    return _mobile_resolution_for_custom_prompt(prompt_text)


def _video_motion_text(seed_text="", seconds=10):
    return str(generate_video_action(seed_text=seed_text, seconds=seconds).get("action") or "")


def _infer_frame_scope_from_prompt(prompt):
    return infer_video_scope(prompt)


def _infer_pose_family_from_prompt(prompt):
    return infer_video_pose_family(prompt)


def _pregenerate_video_action_for_image(filename, scale="", seed_text="", seconds=10, previous_action=""):
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
    clamped = dict(resolution)
    width = int(clamped.get("width") or 0)
    height = int(clamped.get("height") or 0)
    if width > 0:
        clamped["width"] = _round_to_multiple(width * MOBILE_RESOLUTION_DOWNSHIFT)
    if height > 0:
        height = _round_to_multiple(height * MOBILE_RESOLUTION_DOWNSHIFT)
    if height > MOBILE_MAX_IMAGE_HEIGHT:
        height = MOBILE_MAX_IMAGE_HEIGHT
    if height > 0:
        clamped["height"] = height
    return clamped


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
    already_covered = (
        framing in camera or
        camera_first == framing_first or
        camera_first in framing or
        framing_first in camera
    )
    if not already_covered:
        parts["camera"] = f"{camera}，{framing}" if camera else framing
    parts = _enforce_prompt_length(parts)
    item["dimension_parts"] = parts
    prompt = _rebuild_prompt_text_from_parts(parts)
    item["compact_prompt"] = prompt
    item["positive_prompt"] = prompt
    return item


def _build_mobile_prompt_for_scope(scale, shot_config, seed_text):
    initial = _build_mobile_prompt_item(scale, shot_config, seed_text)
    initial = _ensure_scoped_character_prompt(initial)
    resolution = _mobile_resolution_for_prompt(initial, shot_config["shot"])
    if resolution["aspect"] != shot_config["aspect"]:
        resolved_config = {
            **shot_config,
            "aspect": resolution["aspect"],
            "width": resolution["width"],
            "height": resolution["height"],
        }
        initial = _build_mobile_prompt_item(scale, resolved_config, f"{seed_text}-{resolution['aspect']}")
        initial = _ensure_scoped_character_prompt(initial)
        resolution = _mobile_resolution_for_prompt(initial, shot_config["shot"])
    return _apply_mobile_framing(initial, resolution), resolution


def _build_prompt_with_mobile_logic(scale, shot, seed_text=""):
    shot_config = _mobile_shot_config(shot)
    item, _resolution = _build_mobile_prompt_for_scope(scale, shot_config, seed_text)
    return _prompt_text(item)


def _build_desktop_prompt_with_mobile_logic(scale, shot, seed_text=""):
    shot_config = _mobile_shot_config(shot)
    item, resolution = _build_mobile_prompt_for_scope(scale, shot_config, seed_text)
    return item, resolution


def _build_prompt(scale, shot, seed_text="", aspect="portrait", width=None, height=None):
    return _build_prompt_with_mobile_logic(scale, shot, seed_text)


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


def _available_zit_models():
    return _available_zimage_models("zit")


def _available_zib_models():
    return _available_zimage_models("zib")


def _available_loras():
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


def _resolve_zit_model(value=None):
    model_name = Path(str(value or "").replace("\\", "/")).name
    if not model_name:
        return ""
    if model_name not in _available_zit_models():
        raise ValueError(f"没有找到 z_image_turbo 模型：{model_name}")
    return model_name


def _resolve_zib_model(value=None):
    model_name = Path(str(value or "").replace("\\", "/")).name
    if not model_name:
        return ""
    if model_name not in _available_zib_models():
        raise ValueError(f"没有找到 ZIB 模型：{model_name}")
    return model_name


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


def _mobile_output_relative_path(path):
    output_dir = Path(folder_paths.get_output_directory()).resolve()
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


def _mobile_output_file_key(filename, subfolder=""):
    safe_name = Path(str(filename or "")).name
    safe_subfolder = str(subfolder or "").replace("\\", "/").strip("/")
    return f"{safe_subfolder}/{safe_name}" if safe_subfolder else safe_name


def _mobile_prompt_index_path():
    return _mobile_output_dir() / MOBILE_PROMPT_INDEX_NAME


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
    output_dir = Path(folder_paths.get_output_directory()).resolve()
    target = (output_dir / MOBILE_VIDEO_OUTPUT_SUBFOLDER).resolve()
    if output_dir not in target.parents and target != output_dir:
        raise ValueError("手机视频输出目录不在 ComfyUI output 目录内。")
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
    output_dir = Path(folder_paths.get_output_directory()).resolve()
    safe_name = str(filename or "").replace("\\", "/").strip("/")
    path = (output_dir / safe_name).resolve()
    if output_dir in path.parents and path.is_file():
        return path
    raise ValueError("文件路径不在手机输出目录内。")


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
            "subfolder": subfolder,
            "type": "output",
        }
    )
    return f"/view?{params}"


def _mobile_video_view_url(filename):
    params = urllib.parse.urlencode(
        {
            "filename": filename,
            "subfolder": MOBILE_VIDEO_OUTPUT_SUBFOLDER,
            "type": "output",
        }
    )
    return f"/view?{params}"


def _mobile_prompt_for_gallery_file(filename):
    filename = str(filename or "").replace("\\", "/").strip("/")
    prompt = MOBILE_PROMPT_BY_FILENAME.get(filename, "")
    if prompt:
        return prompt
    prompt = _load_mobile_prompt_index().get(filename, "")
    if prompt:
        MOBILE_PROMPT_BY_FILENAME[filename] = prompt
        return prompt
    basename = Path(filename).name
    if basename != filename:
        prompt = MOBILE_PROMPT_BY_FILENAME.get(basename, "") or _load_mobile_prompt_index().get(basename, "")
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
    for job in MOBILE_SESSION_JOBS:
        for image in _mobile_image_urls(str(job.get("prompt_id", ""))):
            if image.get("filename"):
                key = _mobile_output_file_key(image.get("filename", ""), image.get("subfolder", ""))
                prompt_by_filename[key] = job.get("prompt", "")
                _remember_mobile_prompt_file(image["filename"], job.get("prompt", ""), image.get("subfolder", ""))
    items = []
    output_dir = Path(folder_paths.get_output_directory()).resolve()
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
    return items


def _mobile_gallery_videos():
    prompt_by_filename = dict(MOBILE_VIDEO_PROMPT_BY_FILENAME)
    for job in MOBILE_SESSION_JOBS:
        for video in _mobile_video_urls(str(job.get("prompt_id", ""))):
            if video.get("subfolder") == MOBILE_VIDEO_OUTPUT_SUBFOLDER and video.get("filename"):
                prompt_by_filename[video["filename"]] = job.get("prompt", "")
                MOBILE_VIDEO_PROMPT_BY_FILENAME[video["filename"]] = job.get("prompt", "")
    items = []
    for path in _mobile_video_output_dir().iterdir():
        if not path.is_file() or path.suffix.lower() not in MOBILE_VIDEO_EXTENSIONS:
            continue
        stat = path.stat()
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
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    if isinstance(value, list) and value:
        node = workflow.get(str(value[0]))
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if isinstance(inputs, dict) and "value" in inputs:
            return _linked_float_value(workflow, inputs.get("value"), default)
    return default


def _mobile_workflow_output_scale(workflow):
    scale = 1.0
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if class_type == "LatentUpscaleBy" and "scale_by" in inputs:
            scale *= _linked_float_value(workflow, inputs.get("scale_by"), 1.0)
        if class_type == "UltimateSDUpscale" and "upscale_by" in inputs:
            scale *= _linked_float_value(workflow, inputs.get("upscale_by"), 1.0)
    return scale if scale > 0 else 1.0


def _mobile_base_resolution_for_workflow(template, width, height):
    scale = _mobile_workflow_output_scale(template)
    return _round_to_multiple(width / scale), _round_to_multiple(height / scale), scale


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


def _patch_mobile_workflow(template, prompt_item, width, height, seed, zit_model="", output_prefix=None, lora_name="", lora_strength=0.8, zib_model=""):
    workflow = copy.deepcopy(template)
    removed_auxiliary_outputs = _remove_mobile_auxiliary_outputs(workflow)
    positive_prompt = _prompt_text(prompt_item)
    negative_prompt = prompt_item.get("negative_prompt", "")
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
        "base_width": base_width,
        "base_height": base_height,
        "output_scale": output_scale,
        "removed_auxiliary_outputs": removed_auxiliary_outputs,
    }
    patched["lora"] = _patch_existing_lora_nodes(workflow, lora_name, lora_strength)
    text_nodes = []
    resolved_zit_model = _resolve_zit_model(zit_model)
    resolved_zib_model = _resolve_zib_model(zib_model)
    model_consumers = _workflow_model_consumers(workflow)
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        class_type = str(node.get("class_type") or "")
        if "text" in inputs and ("CLIPTextEncode" in class_type or "TextEncode" in class_type or "Conditioning" in class_type):
            text_nodes.append(node)
        if resolved_zit_model and "unet_name" in inputs:
            current_unet = str(inputs.get("unet_name") or "")
            if _is_zit_turbo_model_name(current_unet):
                inputs["unet_name"] = f"z_image/{resolved_zit_model}"
                if platform.system() == "Darwin" and inputs.get("weight_dtype") in {"fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"}:
                    inputs["weight_dtype"] = "default"
                patched["zit_model"] += 1
        if resolved_zib_model and "unet_name" in inputs:
            current_unet = str(inputs.get("unet_name") or "")
            normalized_unet = current_unet.replace("/", "\\").lower()
            consumers = model_consumers.get(str(node_id), set())
            is_zib_slot = normalized_unet.startswith("z_image\\zib") or "483" in consumers
            if is_zib_slot:
                inputs["unet_name"] = f"z_image/{resolved_zib_model}"
                if platform.system() == "Darwin" and inputs.get("weight_dtype") in {"fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"}:
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
        if class_type == "KSampler" and "steps" in inputs and isinstance(inputs.get("steps"), (int, float, str)):
            inputs["steps"] = 8
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


def _patch_mobile_video_workflow(template, prompt_item, image_load_name, source_image_path, seed, seconds=10, fps=24, output_prefix=None, positive_prompt=None):
    workflow = copy.deepcopy(template)
    positive_prompt = positive_prompt or _prompt_text(prompt_item)
    negative_prompt = prompt_item.get("negative_prompt", "")
    scale_to_length = max(32, min(640, int(_image_longest_side(source_image_path) or 640)))
    seconds = max(1, min(30, int(seconds or 6)))
    fps = max(1, min(60, int(fps or 24)))
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


async def _queue_mobile_workflow(workflow, client_id=""):
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


def _queue_contains(prompt_id, items):
    return any(len(item) > 1 and item[1] == prompt_id for item in items)


def _mobile_image_urls(prompt_id):
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


def _mobile_video_urls(prompt_id):
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
        if filename and any(filename.startswith(f"{job.get('output_prefix')}_") for job in MOBILE_SESSION_JOBS if job.get("prompt_id") == prompt_id and job.get("output_prefix")):
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


def _mobile_job_status(prompt_id):
    running, pending = PromptServer.instance.prompt_queue.get_current_queue_volatile()
    images = _mobile_image_urls(prompt_id)
    videos = _mobile_video_urls(prompt_id)
    _remember_mobile_prompt_images(prompt_id, images)
    _remember_mobile_prompt_videos(prompt_id, videos)
    if _queue_contains(prompt_id, running):
        status = "running"
    elif _queue_contains(prompt_id, pending):
        status = "pending"
    elif images or videos:
        status = "completed"
    else:
        status = "unknown"
    return {"prompt_id": prompt_id, "status": status, "images": images, "videos": videos}


def _mobile_active_job_count():
    return sum(
        1
        for item in MOBILE_SESSION_JOBS
        if _mobile_job_status(item.get("prompt_id", "")).get("status") in {"running", "pending"}
    )


def _mobile_session_job(item):
    status = _mobile_job_status(item.get("prompt_id", ""))
    return {
        **item,
        "status": status.get("status", "unknown"),
        "images": status.get("images", []),
        "videos": status.get("videos", []),
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
                "scale": (["一档", "二档", "三档"], {"default": "二档"}),
                "shot": (
                    [
                        "头部",
                        "上半身",
                        "半身",
                        "大半身",
                        "全身",
                    ],
                    {"default": "全身"},
                ),
                "use_pregenerated_prompt": ("BOOLEAN", {"default": True}),
                "auto_resolution": ("BOOLEAN", {"default": True}),
                "prompt_rule": (["规则1", "规则2"], {"default": "规则1"}),
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

    def generate(self, scale, shot, use_pregenerated_prompt=True, auto_resolution=True, prompt_rule="规则1", cached_prompt="", cached_negative_prompt="", cached_signature="", cached_aspect="portrait", cached_prompt_source=""):
        try:
            aspect = _normalize_aspect(cached_aspect)
            signature = _prompt_signature(scale, shot, aspect)
            if cached_prompt:
                return (cached_prompt, cached_negative_prompt)
            if str(prompt_rule or "").strip() in {"规则2", "rule2"}:
                result = generate_keyword_expansion_prompt(seed_text=str(time.time()), scale=scale, shot=shot)
                return (result.get("prompt", ""), result.get("negative_prompt", ""))
            item, _resolution = _build_desktop_prompt_with_mobile_logic(scale, shot, str(time.time()))
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
        return (cached_prompt or "请在节点上选择图片并点击反推提示词。",)


async def generate_random_photo_prompt(request):
    try:
        data = await request.json()
        scale = data.get("scale", "澶ц儐")
        shot = data.get("shot", "榛樿")
        seed_text = data.get("seed", "")
        prompt_item, resolution = _build_desktop_prompt_with_mobile_logic(scale, shot, seed_text)
        prompt = _prompt_text(prompt_item)
        width = int(resolution["width"])
        height = int(resolution["height"])
        normalized_aspect = resolution["aspect"]
        return web.json_response(
            {
                "prompt": prompt,
                "negative_prompt": prompt_item.get("negative_prompt", ""),
                "signature": _prompt_signature(scale, shot, normalized_aspect),
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
                "prompt": result["prompt"],
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


async def mobile_generation_page(request):
    try:
        return web.FileResponse(MOBILE_PAGE_PATH)
    except Exception:
        return web.Response(text=traceback.format_exc(), status=500)


async def mobile_generation_status(request):
    workflow_key, config = _mobile_workflow_config(request.query.get("workflow"))
    workflow_path = config["path"]
    template_ready = workflow_path.exists()
    video_config = MOBILE_WORKFLOWS[MOBILE_VIDEO_WORKFLOW_KEY]
    image_workflows = _mobile_image_workflows()
    zit_models = _available_zit_models()
    zib_models = _available_zib_models()
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
                    "template_ready": item["path"].exists(),
                }
                for key, item in image_workflows.items()
            ],
            "video_workflow": {
                "key": MOBILE_VIDEO_WORKFLOW_KEY,
                "label": video_config["label"],
                "template_name": video_config["path"].name,
                "template_ready": video_config["path"].exists(),
            },
            "zit_models": zit_models,
            "zib_models": zib_models,
            "zit_model_dir_ready": ZIT_MODEL_DIR.exists(),
            "loras": loras,
            "lora_dir": str((Path(folder_paths.models_dir) / "loras" / ZIMAGE_LORA_SUBDIR).resolve()),
            "connected": True,
            "message": "" if template_ready else f"请先保存 {workflow_path.name} 后再生成。",
        }
    )


def _mobile_shot_config(value):
    text = str(value or "").strip()
    legacy_map = {
        "random": "full_body",
        "随机": "full_body",
        "full_body": "full_body",
        "全身": "full_body",
        "全身像": "full_body",
        "full_body_portrait": "full_body",
        "full_body_landscape": "full_body",
        "full_body_portrait_standing": "full_body",
        "full_body_portrait_nonstanding": "full_body",
        "全身-竖屏": "full_body",
        "全身-横屏": "full_body",
        "全身-竖屏-站姿": "full_body",
        "全身-竖屏-非站姿": "full_body",
        "half_body": "half_body",
        "半身": "half_body",
        "半身像": "half_body",
        "半身镜头": "half_body",
        "腰部及以上": "half_body",
        "腰部及以上镜头": "half_body",
        "large_half_body": "large_half_body",
        "大半身": "large_half_body",
        "大半身镜头": "large_half_body",
        "大腿以上": "large_half_body",
        "大腿以上镜头": "large_half_body",
        "小腿及以上": "large_half_body",
        "小腿及以上镜头": "large_half_body",
        "half_body_portrait": "half_body",
        "half_body_landscape": "half_body",
        "半身-竖屏": "half_body",
        "半身-横屏": "half_body",
        "upper_body": "upper_body",
        "face": "upper_body",
        "face_closeup": "upper_body",
        "特写": "upper_body",
        "面部特写": "upper_body",
        "胸部以上": "upper_body",
        "胸部以上镜头": "upper_body",
        "胸部以上特写": "upper_body",
        "胸部及以上": "upper_body",
        "胸部及以上镜头": "upper_body",
        "上半身": "upper_body",
        "上半身镜头": "upper_body",
        "上半身中近景": "upper_body",
        "head_shot": "head_shot",
        "头部": "head_shot",
        "头部镜头": "head_shot",
        "肩膀及以上": "head_shot",
        "肩膀及以上镜头": "head_shot",
        "肩部以上": "head_shot",
        "肩部以上镜头": "head_shot",
        "肩部以上特写": "head_shot",
    }
    key = text if text in MOBILE_SCOPE_PRESETS else legacy_map.get(text, "full_body")
    return MOBILE_SCOPE_PRESETS[key]


async def generate_mobile_image(request):
    try:
        data = await request.json()
        workflow_key, workflow_config = _mobile_workflow_config(data.get("workflow"))
        if workflow_config.get("type", "image") != "image":
            workflow_key, workflow_config = _mobile_workflow_config(MOBILE_DEFAULT_WORKFLOW_KEY)
        template = _load_mobile_workflow(workflow_key)
        zit_model = _resolve_zit_model(data.get("zit_model"))
        zib_model = _resolve_zib_model(data.get("zib_model")) if workflow_key == "zitb_double" else ""
        lora_name = _resolve_lora_name(data.get("lora_name"))
        lora_strength = _resolve_lora_strength(data.get("lora_strength"))
        scale = data.get("scale", "bold")
        shot_config = _mobile_shot_config(data.get("shot", "full_body_portrait"))
        custom_prompt = str(data.get("custom_prompt") or "").strip()
        prompt_rule = str(data.get("prompt_rule") or "rule1").strip().lower()
        client_id = str(data.get("client_id") or "").strip()
        requested_count = max(1, min(int(data.get("count", 1) or 1), 64))
        remaining_slots = max(0, MOBILE_MAX_ACTIVE_JOBS - _mobile_active_job_count())
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
            elif prompt_rule in {"rule2", "assistant", "assistant_rule", "小助手式"}:
                prompt_item, resolution = _assistant_mobile_prompt_item(seed_text, scale, shot_config)
            else:
                prompt_item, resolution = _build_mobile_prompt_for_scope(scale, shot_config, seed_text)
            width = int(resolution["width"])
            height = int(resolution["height"])
            aspect = resolution["aspect"]
            seed = int(data.get("seed") or prompt_item.get("seed") or int(time.time() * 1000))
            if count > 1 and not data.get("seed"):
                seed = int(prompt_item.get("seed") or seed)
            output_prefix = f"mobile_{uuid.uuid4().hex[:12]}"
            workflow, patched = _patch_mobile_workflow(template, prompt_item, width, height, seed, zit_model, output_prefix, lora_name, lora_strength, zib_model)
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
                "lora_name": lora_name,
                "lora_strength": lora_strength,
                "scale": prompt_item.get("scale", scale),
                "shot": prompt_item.get("shot_key", shot_config["shot"]),
                "custom_prompt": bool(custom_prompt),
                "custom_resolution": data.get("custom_resolution") if custom_prompt else "",
                "prompt_rule": "rule2" if prompt_rule in {"rule2", "assistant", "assistant_rule", "小助手式"} else "rule1",
                "aspect": aspect,
                "width": width,
                "height": height,
                "seed": seed,
                "output_prefix": output_prefix,
                "patched": patched,
                "created_at": int(time.time() * 1000),
            }
            jobs.append(job)
            MOBILE_SESSION_JOBS.append(job)
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
        remaining_slots = max(0, MOBILE_MAX_ACTIVE_JOBS - _mobile_active_job_count())
        if remaining_slots <= 0:
            return web.json_response({"error": f"当前任务数已达到 {MOBILE_MAX_ACTIVE_JOBS}，请等待完成后再添加。"}, status=429)
        count = min(requested_count, remaining_slots)
        source_filename = str(data.get("source_filename") or "")
        source_path, image_load_name = _copy_mobile_gallery_image_to_input(source_filename)
        action_text = data.get("action_text", "")
        fps = data.get("fps", 24)
        requested_seconds = normalize_video_seconds(data.get("seconds", 10))
        source_prompt = _mobile_prompt_for_gallery_file(Path(source_filename).name)
        jobs = []
        errors = []
        for index in range(count):
            seed_text = f"video-{time.time()}-{uuid.uuid4()}-{index}"
            prompt_item, resolution = _build_mobile_prompt_for_scope(scale, shot_config, seed_text)
            video_prompt, seconds = _video_prompt_from_action(
                action_text,
                seed_text,
                requested_seconds,
                source_prompt,
                Path(source_filename).name,
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
            data.get("seconds", 10),
            data.get("previous_action", ""),
        )
        seconds = normalize_video_seconds(data.get("seconds", 10))
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
        return web.json_response(_mobile_job_status(prompt_id))
    except Exception:
        return web.json_response({"error": traceback.format_exc()}, status=500)


async def mobile_session_jobs(request):
    try:
        return web.json_response({"jobs": [_mobile_session_job(item) for item in MOBILE_SESSION_JOBS]})
    except Exception:
        return web.json_response({"error": traceback.format_exc()}, status=500)


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
        for raw in raw_items:
            filename = str(raw.get("filename") or "")
            if not filename:
                continue
            path = _mobile_output_file(filename)
            if not path.is_file() or path.suffix.lower() not in MOBILE_GALLERY_EXTENSIONS:
                continue
            path.unlink()
            deleted += 1
        return web.json_response({"deleted": deleted, "images": _mobile_gallery_images()})
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


if not _route_exists("POST", "/random_photo_prompt/generate"):
    PromptServer.instance.routes.post("/random_photo_prompt/generate")(generate_random_photo_prompt)
if not _route_exists("POST", "/random_photo_prompt/keyword_expand"):
    PromptServer.instance.routes.post("/random_photo_prompt/keyword_expand")(expand_keyword_photo_prompt)
if not _route_exists("POST", "/random_photo_prompt/resolve_resolution"):
    PromptServer.instance.routes.post("/random_photo_prompt/resolve_resolution")(resolve_random_photo_prompt_resolution)
if not _route_exists("POST", "/random_photo_prompt/interrogate"):
    PromptServer.instance.routes.post("/random_photo_prompt/interrogate")(interrogate_random_photo_prompt)
if not _route_exists("GET", "/random_photo_prompt/mobile"):
    PromptServer.instance.routes.get("/random_photo_prompt/mobile")(mobile_generation_page)
if not _route_exists("GET", "/random_photo_prompt/mobile/status"):
    PromptServer.instance.routes.get("/random_photo_prompt/mobile/status")(mobile_generation_status)
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
if not _route_exists("GET", "/random_photo_prompt/mobile/gallery"):
    PromptServer.instance.routes.get("/random_photo_prompt/mobile/gallery")(mobile_gallery_images)
if not _route_exists("GET", "/random_photo_prompt/mobile/videos"):
    PromptServer.instance.routes.get("/random_photo_prompt/mobile/videos")(mobile_gallery_videos)
if not _route_exists("POST", "/random_photo_prompt/mobile/gallery/delete"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/gallery/delete")(delete_mobile_gallery_images)
if not _route_exists("POST", "/random_photo_prompt/mobile/videos/delete"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/videos/delete")(delete_mobile_gallery_videos)


NODE_CLASS_MAPPINGS = {
    "RandomPhotoPrompt": RandomPhotoPrompt,
    "RandomPhotoImageInterrogator": RandomPhotoImageInterrogator,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RandomPhotoPrompt": "随机写真提示词",
    "RandomPhotoImageInterrogator": "图片反推提示词",
}

WEB_DIRECTORY = "./web"
