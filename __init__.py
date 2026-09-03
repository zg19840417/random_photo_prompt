from __future__ import annotations

import sys
from pathlib import Path

import execution
import folder_paths
from aiohttp import web
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


if not _route_exists("POST", "/random_photo_prompt/generate"):
    PromptServer.instance.routes.post("/random_photo_prompt/generate")(generate_random_photo_prompt)
if not _route_exists("POST", "/random_photo_prompt/resolve_resolution"):
    PromptServer.instance.routes.post("/random_photo_prompt/resolve_resolution")(resolve_random_photo_prompt_resolution)
if not _route_exists("POST", "/random_photo_prompt/interrogate"):
    PromptServer.instance.routes.post("/random_photo_prompt/interrogate")(interrogate_random_photo_prompt)
if not _route_exists("GET", "/"):
    PromptServer.instance.routes.get("/")(mobile_root_redirect)
if not _route_exists("GET", "/random_photo_prompt/mobile"):
    PromptServer.instance.routes.get("/random_photo_prompt/mobile")(mobile_generation_page)
if not _route_exists("GET", "/random_photo_prompt/manual"):
    PromptServer.instance.routes.get("/random_photo_prompt/manual")(manual_generation_page)
if not _route_exists("GET", "/random_photo_prompt/mobile/status"):
    PromptServer.instance.routes.get("/random_photo_prompt/mobile/status")(mobile_generation_status)
if not _route_exists("GET", "/random_photo_prompt/manual/status"):
    PromptServer.instance.routes.get("/random_photo_prompt/manual/status")(mobile_generation_status)
if not _route_exists("GET", "/random_photo_prompt/local/status"):
    PromptServer.instance.routes.get("/random_photo_prompt/local/status")(local_status_page)
if not _route_exists("POST", "/random_photo_prompt/mobile/prompt"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/prompt")(pregenerate_mobile_image_prompt)
if not _route_exists("POST", "/random_photo_prompt/mobile/generate"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/generate")(generate_mobile_image)
if not _route_exists("POST", "/random_photo_prompt/manual/generate"):
    PromptServer.instance.routes.post("/random_photo_prompt/manual/generate")(generate_mobile_image)
if not _route_exists("POST", "/random_photo_prompt/mobile/video/generate"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/video/generate")(generate_mobile_video)
if not _route_exists("POST", "/random_photo_prompt/mobile/video/source/upload"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/video/source/upload")(upload_mobile_video_source)
if not _route_exists("GET", "/random_photo_prompt/remote/video/source_image"):
    PromptServer.instance.routes.get("/random_photo_prompt/remote/video/source_image")(mobile_remote_video_source_image)
if not _route_exists("POST", "/random_photo_prompt/remote/video/upload"):
    PromptServer.instance.routes.post("/random_photo_prompt/remote/video/upload")(receive_remote_video)
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
if not _route_exists("POST", "/random_photo_prompt/mobile/viewed"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/viewed")(mark_mobile_viewed_images)
if not _route_exists("POST", "/random_photo_prompt/mobile/gallery/open-qview"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/gallery/open-qview")(open_mobile_gallery_image_in_qview)
if not _route_exists("GET", "/random_photo_prompt/mobile/videos"):
    PromptServer.instance.routes.get("/random_photo_prompt/mobile/videos")(mobile_gallery_videos)
if not _route_exists("GET", "/random_photo_prompt/mobile/favorites"):
    PromptServer.instance.routes.get("/random_photo_prompt/mobile/favorites")(mobile_favorite_images)
if not _route_exists("GET", "/random_photo_prompt/mobile/favorite/file/{filename}"):
    PromptServer.instance.routes.get("/random_photo_prompt/mobile/favorite/file/{filename}")(mobile_favorite_image_file)
if not _route_exists("POST", "/random_photo_prompt/mobile/favorites/delete"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/favorites/delete")(delete_mobile_favorite_images)
if not _route_exists("POST", "/random_photo_prompt/mobile/favorite/backup"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/favorite/backup")(backup_mobile_favorite_image)
if not _route_exists("POST", "/random_photo_prompt/mobile/video/favorite/backup"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/video/favorite/backup")(backup_mobile_favorite_video)
if not _route_exists("POST", "/random_photo_prompt/mobile/gallery/delete"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/gallery/delete")(delete_mobile_gallery_images)
if not _route_exists("POST", "/random_photo_prompt/mobile/videos/delete"):
    PromptServer.instance.routes.post("/random_photo_prompt/mobile/videos/delete")(delete_mobile_gallery_videos)
if not _route_exists("POST", "/random_photo_prompt/remote/delete_output"):
    PromptServer.instance.routes.post("/random_photo_prompt/remote/delete_output")(delete_remote_output_file)
if not _route_exists("POST", "/random_photo_prompt/remote/submit"):
    PromptServer.instance.routes.post("/random_photo_prompt/remote/submit")(submit_guarded_remote_workflow)
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
