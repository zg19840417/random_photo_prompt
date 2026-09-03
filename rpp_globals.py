from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import folder_paths

from k2_sfw_prompt_rule import RULE_KEY as K2_SFW_RULE_KEY
from prompt_constants import MAX_POSITIVE_PROMPT_LENGTH  # 单一来源：总长度不再限制（99999 哨兵）
from prompt_resolution import MOBILE_CUSTOM_RESOLUTION_PRESETS, MOBILE_STANDING_FULL_BODY_RESOLUTION

__all__ = sorted(["ANCIENT_SHOE_REPLACEMENTS", "BLOCK_REMOTE_ASSET_SAVE", "CHARACTER_BY_SHOT", "FIXED_CHARACTER_IDENTITY", "FIXED_CHARACTER_ORIGINAL", "GENERATION_SUBMISSION_LOCK", "KREA2_MODEL_DIR", "KREA2_PORTRAIT_HORIZONTAL_MARKERS", "LORA_MODEL_EXTENSIONS", "MANUAL_PAGE_HTML", "MANUAL_PAGE_PATH", "MAX_POSITIVE_PROMPT_LENGTH", "MOBILE_DEFAULT_RESOLUTIONS", "MOBILE_DEFAULT_WORKFLOW_KEY", "MOBILE_DIRECTOR_RESOLUTION_RULES", "MOBILE_FAVORITE_BACKUP_DIR", "MOBILE_FAVORITE_METADATA_NAME", "MOBILE_FRAMING_COMPACT_REPLACEMENTS", "MOBILE_GALLERY_EXTENSIONS", "MOBILE_MAX_ACTIVE_JOBS", "MOBILE_MAX_LORAS", "MOBILE_OUTPUT_SUBFOLDER", "MOBILE_PAGE_HTML", "MOBILE_PAGE_PATH", "MOBILE_PREFERRED_KREA2_MODELS", "MOBILE_PREFERRED_ZIB_MODELS", "MOBILE_PREFERRED_ZIT_MODELS", "MOBILE_PROMPT_BY_FILENAME", "MOBILE_PROMPT_INDEX_NAME", "MOBILE_RESOLUTION_RULES", "MOBILE_RESULT_RECEIVE_GRACE_SECONDS", "MOBILE_RUNTIME_IMAGES_BY_PROMPT_ID", "MOBILE_SCOPE_PRESETS", "MOBILE_SESSION_JOBS", "MOBILE_SESSION_JOBS_LOADED", "MOBILE_SESSION_JOBS_NAME", "MOBILE_VIDEO_DIMENSIONS_BY_FILENAME", "MOBILE_VIDEO_EXTENSIONS", "MOBILE_VIDEO_FAVORITE_BACKUP_DIR", "MOBILE_VIDEO_INPUT_SUBFOLDER", "MOBILE_VIDEO_OUTPUT_SUBFOLDER", "MOBILE_VIDEO_PROMPT_BY_FILENAME", "MOBILE_VIDEO_WORKFLOW_KEY", "MOBILE_WORKFLOWS", "MOBILE_WORKFLOW_PATH", "MOBILE_WORKFLOW_TEMPLATES", "MOBILE_WORKFLOW_TEMPLATE_ERRORS", "NODE_DIR", "PROMPT_DISPLAY_PART_ORDER", "PROMPT_LIMIT_PART_ORDER", "QVIEW_APP_PATH", "REMOTE_BLOCKED_ZIT_MODELS", "REMOTE_COMFYUI_URL", "REMOTE_DELETE_OUTPUT", "REMOTE_HISTORY_TIMEOUT", "REMOTE_LORA_DIR", "REMOTE_MAC_IMAGE_UPLOAD_URL", "REMOTE_MAC_SOURCE_IMAGE_URL", "REMOTE_MAC_VIDEO_UPLOAD_URL", "REMOTE_OUTPUT_DIR", "REMOTE_PROGRESS_BY_PROMPT_ID", "REMOTE_TRANSFER_ALLOWED_IP", "REMOTE_TRANSFER_TOKEN", "REMOTE_WEBSOCKET_OUTPUT", "REMOTE_WS_CLIENT_ID_BY_PROMPT_ID", "REMOTE_WS_IMAGE_INDEX_BY_PROMPT_ID", "REMOTE_WS_OUTPUT_MODE_BY_PROMPT_ID", "REMOTE_WS_OUTPUT_NODES_BY_PROMPT_ID", "REMOTE_WS_OUTPUT_PREFIX_BY_PROMPT_ID", "REMOTE_WS_WATCHERS", "ZIB_BASE_CFG", "ZIB_BASE_STEPS", "ZIB_DISTILLED_CFG", "ZIB_DISTILLED_STEPS", "ZIMAGE_LORA_SUBDIR", "ZIT_MODEL_DIR", "ZIT_MODEL_EXTENSIONS", "ZIT_SINGLE_TEN_STEP_MODEL", "__all__"])








FIXED_CHARACTER_ORIGINAL = '22岁瓷白冷白皮K-pop韩国美女，黑色渐变的手指甲又细又长，瓷器般细腻冷白皮肤，细长瓜子脸，非常尖的下巴，高挺精致鼻梁，鼻尖尖翘。黑色直发散落在脸部两侧，魅惑狐狸眼，精致夜店斩男妆，锋利黑色眼线，冷调眼妆，卷翘的长睫毛，纯蓝色美瞳，棕色眼影，眼角和脸颊点缀闪烁银粉与淡淡美人痣，湿润闪亮的粉红唇彩，性感锁骨，骨架偏瘦但胸部和臀部丰满，小蛮腰，腿细且长'
CHARACTER_BY_SHOT = {'head_shot': '22岁瓷白冷白皮K-pop韩国美女，黑色渐变的手指甲又细又长，瓷器般细腻冷白皮肤，细长瓜子脸，非常尖的下巴，高挺精致鼻梁，鼻尖尖翘。黑色直发散落在脸部两侧，魅惑狐狸眼，精致夜店斩男妆，锋利黑色眼线，冷调眼妆，卷翘的长睫毛，纯蓝色美瞳，棕色眼影，眼角和脸颊点缀闪烁银粉与淡淡美人痣，湿润闪亮的粉红唇彩', 'half_body': '22岁瓷白冷白皮K-pop韩国美女，黑色渐变的手指甲又细又长，瓷器般细腻冷白皮肤，细长瓜子脸，非常尖的下巴，高挺精致鼻梁，鼻尖尖翘。黑色直发散落在脸部两侧，魅惑狐狸眼，精致夜店斩男妆，锋利黑色眼线，冷调眼妆，卷翘的长睫毛，纯蓝色美瞳，棕色眼影，眼角和脸颊点缀闪烁银粉与淡淡美人痣，湿润闪亮的粉红唇彩，性感锁骨，骨架偏瘦但胸部丰满，小蛮腰', 'full_body': FIXED_CHARACTER_ORIGINAL}


NODE_DIR = Path(__file__).resolve().parent


MOBILE_PAGE_PATH = NODE_DIR / "web" / "mobile.html"
MANUAL_PAGE_PATH = NODE_DIR / "web" / "manual_generate.html"
MOBILE_PAGE_HTML = MOBILE_PAGE_PATH.read_text(encoding="utf-8")
MANUAL_PAGE_HTML = MANUAL_PAGE_PATH.read_text(encoding="utf-8")
MOBILE_WORKFLOW_PATH = NODE_DIR / "mobile_workflow_api.json"
MOBILE_WORKFLOWS = {
    "zit_single": {"label": "单采-ZIT", "path": MOBILE_WORKFLOW_PATH, "type": "image"},
    "zib_single": {"label": "单采-ZIB", "path": NODE_DIR / "mobile_workflow_api_2.json", "type": "image"},
    "zitb_double": {"label": "双采-ZIT+ZIB", "path": NODE_DIR / "mobile_workflow_api_2.json", "type": "image"},
    "zimage_double_v2": {"label": "新双采-ZIT+ZIB+Klein", "path": NODE_DIR / "mobile_workflow_api_zimage_double_v2.json", "type": "image"},
    "redcraft_krea2": {"label": "单采-Krea2", "path": NODE_DIR / "mobile_workflow_api_krea2.json", "type": "image"},
    "krea2_cc": {"label": "单采-Krea2+CC", "path": NODE_DIR / "mobile_workflow_api_krea2_cc.json", "type": "image"},
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
ZIB_BASE_STEPS = 40
ZIB_BASE_CFG = 4
MOBILE_PREFERRED_KREA2_MODELS = (
    "KREA2-darkBeast.safetensors",
    "redcraftKREA2RedMix_krea2Edition.safetensors",
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
    "head_shot": {"shot": "head_shot", "aspect": "portrait", "width": 1024, "height": 1536},
    "half_body": {"shot": "half_body", "aspect": "portrait", "width": 1024, "height": 1536},
    "full_body": {"shot": "full_body", "aspect": "portrait", "width": 1024, "height": 1536},
}
MOBILE_MAX_ACTIVE_JOBS = 99
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
# MAX_POSITIVE_PROMPT_LENGTH 单一来源见 prompt_constants（99999 哨兵，不再限制总长度，
# 各维度由 PART_LENGTH_BUDGETS 控制不膨胀）。
PROMPT_DISPLAY_PART_ORDER = (
    "director_plan",
    "camera",
    "character",
    "outfit",
    "pose_expression",
    "scene_light",
    "quality",
)
PROMPT_LIMIT_PART_ORDER = ("director_plan", "camera", "character", "outfit", "pose_expression", "scene_light", "quality")

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
            ("低机位", "自然纵深", "前景肢体"),
            {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向全身低机位构图"},
        ),
        (
            ("站立", "站姿", "直立", "倚靠", "靠墙", "迈步", "行走", "走姿"),
            MOBILE_STANDING_FULL_BODY_RESOLUTION,
        ),
        (
            ("坐", "坐姿", "坐在", "侧坐", "跪", "跪姿", "跪坐", "膝", "蹲", "半蹲", "蜷", "抱膝"),
            {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向全身坐跪构图"},
        ),
        (
            ("扭腰", "回望", "转身", "侧身", "交叉点地", "向后拉长", "双手一上一下"),
            {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向全身动态姿势构图"},
        ),
    ),
    "half_body": (
        (
            ("横躺", "侧躺", "仰躺", "平躺", "俯拍", "顶视角", "床", "横向", "横跨", "横向靠", "横向坐", "横向趴", "沿宽画幅", "斜向铺"),
            {"aspect": "landscape", "width": 1536, "height": 1024, "framing": "横向半身镜头，大腿以上入镜"},
        ),
        (
            ("坐", "坐姿", "跪", "跪坐", "膝", "直立", "站", "站立", "竖向", "纵向"),
            {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向半身镜头，大腿以上入镜"},
        ),
    ),
    "head_shot": (
        (
            ("横向", "侧脸", "躺", "侧躺"),
            {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向头部镜头，肩膀及以上入镜，头顶完整"},
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
    "full_body": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向全身构图"},
    "half_body": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向半身镜头，大腿以上入镜"},
    "head_shot": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向头部镜头，肩膀及以上入镜，头顶完整"},
}
MOBILE_DIRECTOR_RESOLUTION_RULES = {
    "sunny_multicolor_pool_glamour": {
        "full_body": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向全身阳光水光构图，从头到脚完整入镜，脚下留地面或池边边距"},
        "half_body": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向半身多色反光构图，大腿以上入镜"},
    },
    "beach_vivid_glamour": {
        "full_body": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向全身海边构图，从头到脚完整入镜，脚下沙面边距清楚"},
        "half_body": {"aspect": "landscape", "width": 1536, "height": 1024, "framing": "横向半身海边构图，大腿以上入镜，保留海风空间"},
    },
    "garden_waterlight_seduction": {
        "full_body": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向全身花园构图，从头到脚完整入镜，脚下草地或地面边距清楚"},
        "half_body": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向半身花园水光构图，大腿以上入镜"},
    },
    "glass_balcony_colorlight": {
        "full_body": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向全身玻璃反射构图，从头到脚完整入镜，脚下地面边距清楚"},
        "half_body": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向半身玻璃彩光构图，大腿以上入镜"},
        "head_shot": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向头部玻璃反光近景，肩膀及以上入镜，头顶完整"},
    },
    "bright_studio_color_fashion": {
        "full_body": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向全身彩色棚拍构图，从头到脚完整入镜，脚下地面边距清楚"},
        "half_body": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向半身彩色棚拍构图，大腿以上入镜"},
        "head_shot": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向头部彩色棚拍近景，肩膀及以上入镜，头顶完整"},
    },
    "tropical_terrace_sensuality": {
        "full_body": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向全身热带露台构图，从头到脚完整入镜，脚下甲板或地面边距清楚"},
        "half_body": {"aspect": "landscape", "width": 1536, "height": 1024, "framing": "横向半身热带露台构图，大腿以上入镜"},
    },
    "sweet_vivid_tease": {
        "full_body": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向全身甜艳构图，从头到脚完整入镜，脚下边距清楚"},
        "half_body": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向半身甜艳构图，大腿以上入镜"},
        "head_shot": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向头部甜艳近景，肩膀及以上入镜，头顶完整"},
    },
    "forced_perspective_focus": {
        "full_body": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向全身低机位构图，从头到脚完整入镜，脚下地面边距清楚"},
        "half_body": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向半身强透视构图，大腿以上入镜，手部动作清楚"},
        "head_shot": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": "竖向头部近景，肩膀及以上入镜，头顶完整"},
    },
}


FIXED_CHARACTER_IDENTITY = "22岁瓷白冷白皮K-pop韩国美女"


KREA2_PORTRAIT_HORIZONTAL_MARKERS = (
    "横躺",
    "横向展开",
    "身体横向",
    "侧躺",
    "平躺",
    "沿宽画幅",
    "宽画幅",
    "左手枕在头侧",
    "头发铺散在脸侧和头下",
)


ANCIENT_SHOE_REPLACEMENTS = (
    ("脚下是浅色云头绣鞋", "裸足踩在浅色裙摆下方"),
    ("脚下是红色软底绣鞋", "裸足从红色裙摆下方露出"),
    ("脚下是浅色软底绣鞋", "裸足从浅色裙摆下方露出"),
    ("脚下是软底绣鞋", "裸足从裙摆下方露出"),
    ("脚下是软底舞鞋", "裸足点在地面上"),
    ("脚下是浅色绣鞋", "裸足从浅色裙摆下方露出"),
    ("脚下是软底鞋", "裸足从裙摆下方露出"),
    ("脚下是浅色软底鞋", "裸足从浅色裙摆下方露出"),
    ("云头绣鞋", "裸足"),
    ("云头鞋", "裸足"),
    ("软底绣鞋", "裸足"),
    ("软底舞鞋", "裸足"),
    ("浅色绣鞋", "裸足"),
    ("红色软底绣鞋", "裸足"),
    ("浅色软底绣鞋", "裸足"),
    ("细跟绣鞋", "裸足"),
    ("浅金绣鞋", "裸足"),
    ("绣鞋", "裸足"),
    ("软底鞋", "裸足"),
)
