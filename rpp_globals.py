from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path

import folder_paths

from prompt_resolution import MOBILE_CUSTOM_RESOLUTION_PRESETS

__all__ = sorted(["BLOCK_REMOTE_ASSET_SAVE", "GENERATION_SUBMISSION_LOCK", "KREA2_MODEL_DIR", "LORA_MODEL_EXTENSIONS", "MOBILE_DEFAULT_WORKFLOW_KEY", "MOBILE_FAVORITE_BACKUP_DIR", "MOBILE_FAVORITE_METADATA_NAME", "MOBILE_GALLERY_EXTENSIONS", "MOBILE_MAX_ACTIVE_JOBS", "MOBILE_MAX_LORAS", "MOBILE_PAGE_HTML", "MOBILE_PAGE_PATH", "MOBILE_PREFERRED_KREA2_MODELS", "MOBILE_PREFERRED_ZIB_MODELS", "MOBILE_PREFERRED_ZIT_MODELS", "MOBILE_PROMPT_BY_FILENAME", "MOBILE_PROMPT_INDEX_NAME", "MOBILE_RESULT_RECEIVE_GRACE_SECONDS", "MOBILE_RUNTIME_IMAGES_BY_PROMPT_ID", "MOBILE_SCOPE_PRESETS", "MOBILE_SESSION_JOBS", "MOBILE_SESSION_JOBS_LOADED", "MOBILE_SESSION_JOBS_NAME", "MOBILE_VIDEO_DIMENSIONS_BY_FILENAME", "MOBILE_VIDEO_EXTENSIONS", "MOBILE_VIDEO_FAVORITE_BACKUP_DIR", "MOBILE_VIDEO_INPUT_SUBFOLDER", "MOBILE_VIDEO_OUTPUT_SUBFOLDER", "MOBILE_VIDEO_PROMPT_BY_FILENAME", "MOBILE_VIDEO_TURBO_4STEP_LORA", "MOBILE_VIDEO_TURBO_LORA", "MOBILE_VIDEO_TURBO_MODEL", "MOBILE_VIDEO_WORKFLOW_KEY", "MOBILE_WORKFLOWS", "MOBILE_WORKFLOW_PATH", "MOBILE_WORKFLOW_TEMPLATES", "MOBILE_WORKFLOW_TEMPLATE_ERRORS", "NODE_DIR", "QVIEW_APP_PATH", "REMOTE_COMFYUI_URL", "REMOTE_DELETE_OUTPUT", "REMOTE_HISTORY_TIMEOUT", "REMOTE_MAC_IMAGE_UPLOAD_URL", "REMOTE_MAC_SOURCE_IMAGE_URL", "REMOTE_MAC_VIDEO_UPLOAD_URL", "REMOTE_OUTPUT_DIR", "REMOTE_PROGRESS_BY_PROMPT_ID", "REMOTE_TRANSFER_ALLOWED_IP", "REMOTE_TRANSFER_TOKEN", "REMOTE_WEBSOCKET_OUTPUT", "REMOTE_WS_CLIENT_ID_BY_PROMPT_ID", "REMOTE_WS_IMAGE_INDEX_BY_PROMPT_ID", "REMOTE_WS_OUTPUT_MODE_BY_PROMPT_ID", "REMOTE_WS_OUTPUT_NODES_BY_PROMPT_ID", "REMOTE_WS_OUTPUT_PREFIX_BY_PROMPT_ID", "REMOTE_WS_WATCHERS", "ZIB_DISTILLED_CFG", "ZIB_DISTILLED_STEPS", "ZIMAGE_LORA_SUBDIR", "ZIT_MODEL_DIR", "ZIT_MODEL_EXTENSIONS", "ZIT_SINGLE_TEN_STEP_MODEL", "__all__"])




NODE_DIR = Path(__file__).resolve().parent
PROJECT_VERSION_BASE = "0.1"


def _project_version() -> str:
    """版本号 = 手工维护的主次版本 + git 提交数；工作区有未提交改动时末尾加 “+”。没有 git 的部署副本回落到 0.1.0。"""
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(NODE_DIR), *args], text=True, timeout=5, stderr=subprocess.DEVNULL).strip()

    try:
        count = int(git("rev-list", "--count", "HEAD"))
        dirty = bool(git("status", "--porcelain"))
    except (OSError, ValueError, subprocess.SubprocessError):
        return f"{PROJECT_VERSION_BASE}.0"
    return f"{PROJECT_VERSION_BASE}.{count}{'+' if dirty else ''}"


PROJECT_VERSION = _project_version()


MOBILE_PAGE_PATH = NODE_DIR / "web" / "mobile.html"
MOBILE_PAGE_HTML = MOBILE_PAGE_PATH.read_text(encoding="utf-8").replace("{{PROJECT_VERSION}}", PROJECT_VERSION)
MOBILE_WORKFLOW_PATH = NODE_DIR / "mobile_workflow_api.json"
MOBILE_WORKFLOWS = {
    "zit_single": {"label": "单采-ZIT", "path": MOBILE_WORKFLOW_PATH, "type": "image"},
    "zitb_double": {"label": "双采-ZIT+ZIB", "path": NODE_DIR / "mobile_workflow_api_2.json", "type": "image"},
    "redcraft_krea2": {"label": "单采-Krea2", "path": NODE_DIR / "mobile_workflow_api_krea2.json", "type": "image"},
    "krea2_double": {"label": "双采-Krea2", "path": NODE_DIR / "mobile_workflow_api_krea2_double.json", "type": "image"},
    "minimax_h3": {"label": "MiniMax H3 视频", "path": NODE_DIR / "minimax_h3_workflow_api.json", "type": "video"},
}
MOBILE_WORKFLOW_TEMPLATES = {}
MOBILE_WORKFLOW_TEMPLATE_ERRORS = {}
_workflow_template_by_path = {}
_workflow_template_error_by_path = {}
for _workflow_key, _workflow_config in MOBILE_WORKFLOWS.items():
    _workflow_path = _workflow_config["path"]
    if _workflow_path not in _workflow_template_by_path and _workflow_path not in _workflow_template_error_by_path:
        try:
            _workflow_data = json.loads(_workflow_path.read_text(encoding="utf-8"))
            if isinstance(_workflow_data, dict) and isinstance(_workflow_data.get("prompt"), dict):
                _workflow_data = _workflow_data["prompt"]
            if isinstance(_workflow_data, dict) and isinstance(_workflow_data.get("nodes"), list):
                raise ValueError("是普通工作流格式，不是 API 格式。")
            if not isinstance(_workflow_data, dict) or not _workflow_data:
                raise ValueError("不是有效的 ComfyUI API 工作流。")
            _workflow_template_by_path[_workflow_path] = _workflow_data
        except Exception as _workflow_exc:
            _workflow_template_error_by_path[_workflow_path] = str(_workflow_exc)
    if _workflow_path in _workflow_template_by_path:
        MOBILE_WORKFLOW_TEMPLATES[_workflow_key] = _workflow_template_by_path[_workflow_path]
    else:
        MOBILE_WORKFLOW_TEMPLATE_ERRORS[_workflow_key] = _workflow_template_error_by_path[_workflow_path]
del _workflow_template_by_path, _workflow_template_error_by_path
del _workflow_key, _workflow_config, _workflow_path
MOBILE_DEFAULT_WORKFLOW_KEY = "zit_single"
MOBILE_VIDEO_WORKFLOW_KEY = "minimax_h3"
MOBILE_MAX_LORAS = 4
ZIT_SINGLE_TEN_STEP_MODEL = "ZIT-beyondREALITY_V30.safetensors"
ZIT_MODEL_DIR = Path(folder_paths.models_dir) / "diffusion_models" / "z_image"
KREA2_MODEL_DIR = Path(folder_paths.models_dir) / "diffusion_models" / "Krea2"
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
ZIB_DISTILLED_STEPS = 10
ZIB_DISTILLED_CFG = 1
MOBILE_PREFERRED_KREA2_MODELS = (
    "moodyKrea2Mix_v50.safetensors",
)
ZIMAGE_LORA_SUBDIR = "Zimage"
LORA_MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt"}
MOBILE_VIDEO_OUTPUT_SUBFOLDER = "random_photo_prompt_mobile_video"
MOBILE_VIDEO_INPUT_SUBFOLDER = "random_photo_prompt_mobile_video"
MOBILE_VIDEO_TURBO_MODEL = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
MOBILE_VIDEO_TURBO_LORA = "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
MOBILE_VIDEO_TURBO_4STEP_LORA = "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors"
MOBILE_FAVORITE_BACKUP_DIR = Path(
    os.environ.get("RPP_MOBILE_FAVORITE_BACKUP_DIR")
    or (Path(folder_paths.get_output_directory()) / "random_photo_prompt_favorites")
).expanduser()
MOBILE_FAVORITE_METADATA_NAME = ".random_photo_prompt_favorites.json"
MOBILE_VIEWED_INDEX_NAME = ".random_photo_prompt_mobile_viewed.json"
MOBILE_VIDEO_FAVORITE_BACKUP_DIR = Path(
    os.environ.get("RPP_MOBILE_VIDEO_FAVORITE_BACKUP_DIR")
    or (Path(folder_paths.get_output_directory()) / "random_photo_prompt_favorites" / "videos")
).expanduser()
QVIEW_APP_PATH = Path("/Applications/qView.app")
MOBILE_ENTRY_URL = os.environ.get("RPP_MOBILE_ENTRY_URL", "").strip().rstrip("/")
REMOTE_COMFYUI_URL = os.environ.get("RPP_REMOTE_COMFYUI_URL", "").rstrip("/")
REMOTE_OUTPUT_DIR = Path(os.environ.get("RPP_REMOTE_OUTPUT_DIR", "")).expanduser() if os.environ.get("RPP_REMOTE_OUTPUT_DIR") else None
REMOTE_HISTORY_TIMEOUT = float(os.environ.get("RPP_REMOTE_HISTORY_TIMEOUT", "600") or 600)
REMOTE_DELETE_OUTPUT = os.environ.get("RPP_REMOTE_DELETE_OUTPUT", "1").strip().lower() not in {"0", "false", "no", "off"}
REMOTE_WEBSOCKET_OUTPUT = os.environ.get("RPP_REMOTE_WEBSOCKET_OUTPUT", "1").strip().lower() not in {"0", "false", "no", "off"}
BLOCK_REMOTE_ASSET_SAVE = os.environ.get("RPP_BLOCK_REMOTE_ASSET_SAVE", "0").strip().lower() in {"1", "true", "yes", "on"}
REMOTE_MAC_IMAGE_UPLOAD_URL = os.environ.get("RPP_MAC_IMAGE_UPLOAD_URL", "").strip()
REMOTE_MAC_VIDEO_UPLOAD_URL = os.environ.get("RPP_MAC_VIDEO_UPLOAD_URL", "").strip() or REMOTE_MAC_IMAGE_UPLOAD_URL.replace("/upload_image", "/upload_video")
REMOTE_MAC_SOURCE_IMAGE_URL = os.environ.get("RPP_MAC_SOURCE_IMAGE_URL", "").strip() or REMOTE_MAC_IMAGE_UPLOAD_URL.replace("/upload_image", "/source_image")
REMOTE_TRANSFER_TOKEN = os.environ.get("RPP_REMOTE_TRANSFER_TOKEN", "").strip()
REMOTE_TRANSFER_ALLOWED_IP = os.environ.get("RPP_REMOTE_TRANSFER_ALLOWED_IP", "").strip()
MOBILE_SCOPE_PRESETS = {
    "head_shot": {"shot": "head_shot", "aspect": "portrait", "width": 864, "height": 1536},
    "half_body": {"shot": "half_body", "aspect": "portrait", "width": 864, "height": 1536},
    "full_body": {"shot": "full_body", "aspect": "portrait", "width": 864, "height": 1536},
}
MOBILE_MAX_ACTIVE_JOBS = 100
MOBILE_RESULT_RECEIVE_GRACE_SECONDS = float(os.environ.get("RPP_MOBILE_RESULT_RECEIVE_GRACE_SECONDS", "45") or 45)
# 视频在远端编码完成后才开始回传，文件传输通常比图片帧晚得多，不能复用图片的短等待窗口。
MOBILE_VIDEO_RESULT_RECEIVE_GRACE_SECONDS = float(os.environ.get("RPP_MOBILE_VIDEO_RESULT_RECEIVE_GRACE_SECONDS", "300") or 300)
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
REMOTE_FINISHED_AT_BY_PROMPT_ID = {}
REMOTE_WS_IMAGE_RECEIVED_BY_PROMPT_ID = {}
GENERATION_SUBMISSION_LOCK = asyncio.Lock()
MOBILE_RUNTIME_IMAGES_BY_PROMPT_ID = {}
MOBILE_PROMPT_INDEX_NAME = ".random_photo_prompt_mobile_prompts.json"
MOBILE_SESSION_JOBS_NAME = ".random_photo_prompt_mobile_jobs.json"
MOBILE_GALLERY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MOBILE_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv"}



