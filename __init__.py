from __future__ import annotations

import sys
from pathlib import Path

from server import PromptServer


NODE_DIR = Path(__file__).resolve().parent
if str(NODE_DIR) not in sys.path:
    sys.path.insert(0, str(NODE_DIR))

# 聚合层：常量/状态、工具、提示词构建、工作流 patch、远端运行时、移动端业务、
# 节点类与 HTTP 端点分别位于 rpp_* 模块，此处仅做命名空间聚合与路由注册。
from rpp_globals import *  # noqa: F401,F403
from rpp_utils import *  # noqa: F401,F403
from rpp_prompts import *  # noqa: F401,F403
from rpp_workflow import *  # noqa: F401,F403
from rpp_remote import *  # noqa: F401,F403
from rpp_mobile import *  # noqa: F401,F403
from rpp_nodes import *  # noqa: F401,F403
from rpp_endpoints import *  # noqa: F401,F403


from rpp_routes import register_routes
from rpp_comfy import COMFY_HANDLERS

register_routes(PromptServer.instance.routes, comfy_handlers=COMFY_HANDLERS)
PromptServer.instance.add_on_prompt_handler(_block_remote_asset_save_on_prompt)


NODE_CLASS_MAPPINGS = {
    "RandomPhotoPrompt": RandomPhotoPrompt,
    "RandomPhotoImageInterrogator": RandomPhotoImageInterrogator,
    "RandomPhotoPromptStreamImage": RandomPhotoPromptStreamImage,
    "RandomPhotoPromptRemoteUploadImage": RandomPhotoPromptRemoteUploadImage,
    "RandomPhotoPromptRemoteLoadImageFromMac": RandomPhotoPromptRemoteLoadImageFromMac,
    "RandomPhotoPromptRemoteUploadVideo": RandomPhotoPromptRemoteUploadVideo,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RandomPhotoPrompt": "随机写真提示词",
    "RandomPhotoImageInterrogator": "图片反推提示词",
    "RandomPhotoPromptStreamImage": "图片流式回传",
    "RandomPhotoPromptRemoteUploadImage": "远端图片回传到 Mac",
    "RandomPhotoPromptRemoteLoadImageFromMac": "从 Mac 读取视频源图",
    "RandomPhotoPromptRemoteUploadVideo": "远端视频回传到 Mac",
}

WEB_DIRECTORY = "./web"
