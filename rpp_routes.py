"""两种宿主共用的唯一路由表；本模块不加载 ComfyUI 节点。"""
from rpp_endpoints import *  # noqa: F401,F403
from rpp_remote import receive_remote_video

ROUTES = (
    ('POST', '/random_photo_prompt/generate', generate_random_photo_prompt),
    ('POST', '/random_photo_prompt/resolve_resolution', resolve_random_photo_prompt_resolution),
    ('POST', '/random_photo_prompt/interrogate', interrogate_random_photo_prompt),
    ('GET', '/', mobile_root_redirect),
    ('GET', '/random_photo_prompt/mobile', mobile_generation_page),
    ('GET', '/random_photo_prompt/manual', manual_generation_page),
    ('GET', '/random_photo_prompt/mobile/status', mobile_generation_status),
    ('GET', '/random_photo_prompt/manual/status', mobile_generation_status),
    ('GET', '/random_photo_prompt/local/status', local_status_page),
    ('POST', '/random_photo_prompt/mobile/prompt', pregenerate_mobile_image_prompt),
    ('POST', '/random_photo_prompt/mobile/generate', generate_mobile_image),
    ('POST', '/random_photo_prompt/manual/generate', generate_mobile_image),
    ('POST', '/random_photo_prompt/mobile/video/generate', generate_mobile_video),
    ('POST', '/random_photo_prompt/mobile/video/source/upload', upload_mobile_video_source),
    ('GET', '/random_photo_prompt/remote/video/source_image', mobile_remote_video_source_image),
    ('POST', '/random_photo_prompt/remote/video/upload', receive_remote_video),
    ('POST', '/random_photo_prompt/mobile/video/action', pregenerate_mobile_video_action),
    ('GET', '/random_photo_prompt/mobile/video/action', pregenerate_mobile_video_action),
    ('GET', '/random_photo_prompt/mobile/job/{prompt_id}', mobile_job_detail),
    ('GET', '/random_photo_prompt/mobile/jobs', mobile_session_jobs),
    ('POST', '/random_photo_prompt/mobile/remote_runtime/clear', clear_remote_mobile_runtime_state),
    ('GET', '/random_photo_prompt/mobile/runtime_image/{prompt_id}/{filename}', mobile_runtime_image),
    ('GET', '/random_photo_prompt/mobile/gallery', mobile_gallery_images),
    ('POST', '/random_photo_prompt/mobile/viewed', mark_mobile_viewed_images),
    ('POST', '/random_photo_prompt/mobile/gallery/open-qview', open_mobile_gallery_image_in_qview),
    ('GET', '/random_photo_prompt/mobile/videos', mobile_gallery_videos),
    ('GET', '/random_photo_prompt/mobile/favorites', mobile_favorite_images),
    ('GET', '/random_photo_prompt/mobile/favorite/file/{filename}', mobile_favorite_image_file),
    ('POST', '/random_photo_prompt/mobile/favorites/delete', delete_mobile_favorite_images),
    ('POST', '/random_photo_prompt/mobile/favorite/backup', backup_mobile_favorite_image),
    ('POST', '/random_photo_prompt/mobile/video/favorite/backup', backup_mobile_favorite_video),
    ('POST', '/random_photo_prompt/mobile/gallery/delete', delete_mobile_gallery_images),
    ('POST', '/random_photo_prompt/mobile/videos/delete', delete_mobile_gallery_videos),
    ('POST', '/random_photo_prompt/remote/delete_output', delete_remote_output_file),
    ('POST', '/random_photo_prompt/remote/submit', submit_guarded_remote_workflow),
)


def register_routes(routes, *, comfy_handlers=None):
    """接受 aiohttp RouteTableDef；只由远端宿主注入推理端点。"""
    overrides = comfy_handlers or {}
    existing = {(item.method, item.path) for item in routes}
    for method, path, handler in ROUTES:
        if (method, path) not in existing:
            routes.route(method, path)(overrides.get(handler.__name__, handler))
            existing.add((method, path))
