from __future__ import annotations

import json
import time
import traceback
import urllib.request
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
import torch
import comfy.utils

from rpp_globals import (
    MOBILE_VIDEO_OUTPUT_SUBFOLDER,
    REMOTE_MAC_IMAGE_UPLOAD_URL,
    REMOTE_MAC_VIDEO_UPLOAD_URL,
    REMOTE_TRANSFER_TOKEN,
    NODE_DIR,
)
from rpp_prompts import (
    _build_desktop_prompt_with_mobile_logic,
    _enforce_mobile_ancient_barefoot_text,
    _prompt_text,
)
from rpp_utils import _normalize_aspect, _prompt_signature
from prompt_postprocess import clean_prompt_text

__all__ = sorted(["RandomPhotoImageInterrogator", "RandomPhotoPrompt", "RandomPhotoPromptRemoteLoadImageFromMac", "RandomPhotoPromptRemoteUploadImage", "RandomPhotoPromptRemoteUploadVideo", "RandomPhotoPromptStreamImage", "__all__"])

class RandomPhotoPromptStreamImage:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"images": ("IMAGE",)}}

    RETURN_TYPES = ()
    FUNCTION = "stream_images"
    OUTPUT_NODE = True
    CATEGORY = "Random Photo"

    def stream_images(self, images):
        progress = comfy.utils.ProgressBar(images.shape[0])
        for index, image in enumerate(images):
            array = 255.0 * image.cpu().numpy()
            pil_image = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))
            progress.update_absolute(index, images.shape[0], ("PNG", pil_image, None))
        return {}

    @classmethod
    def IS_CHANGED(cls, images):
        return time.time()


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
        if not REMOTE_TRANSFER_TOKEN:
            raise RuntimeError("RPP_REMOTE_TRANSFER_TOKEN is not configured.")
        request = urllib.request.Request(
            source_url,
            headers={"X-RPP-Transfer-Token": REMOTE_TRANSFER_TOKEN},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=120) as response:
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
            },
            "optional": {"upload_url": ("STRING", {"default": ""})},
        }

    RETURN_TYPES = ()
    FUNCTION = "upload_video"
    OUTPUT_NODE = True
    CATEGORY = "Random Photo"

    def upload_video(self, video, filename_prefix="remote_video", format="mp4", codec="h264", upload_url=""):
        target_url = str(upload_url or REMOTE_MAC_VIDEO_UPLOAD_URL).strip()
        if not target_url:
            raise RuntimeError("Mac video upload URL is not configured.")
        if not REMOTE_TRANSFER_TOKEN:
            raise RuntimeError("RPP_REMOTE_TRANSFER_TOKEN is not configured.")
        from comfy_api.latest import Types

        safe_prefix = Path(str(filename_prefix or "remote_video").replace("\\", "/").strip("/")).name or "remote_video"
        extension = Types.VideoContainer.get_extension(format)
        # Encode in RAM and immediately POST to the Mac. No video bytes are written on the remote host.
        buffer = BytesIO()
        video.save_to(buffer, format=Types.VideoContainer(format), codec=codec, metadata={})
        request = urllib.request.Request(
            target_url,
            data=buffer.getvalue(),
            headers={
                "Content-Type": f"video/{extension}",
                "X-RPP-Filename-Prefix": safe_prefix,
                "X-RPP-Video-Extension": f".{extension}",
                "X-RPP-Transfer-Token": REMOTE_TRANSFER_TOKEN,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=300) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = {
            "filename": payload.get("filename"),
            "subfolder": payload.get("subfolder", MOBILE_VIDEO_OUTPUT_SUBFOLDER),
            "type": payload.get("type", "output"),
        }
        return {"ui": {"videos": [result]}}


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
                return (clean_prompt_text(_enforce_mobile_ancient_barefoot_text(cached_prompt, era)), cached_negative_prompt)
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

