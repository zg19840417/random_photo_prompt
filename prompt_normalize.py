from __future__ import annotations

from prompt_constants import SCALE_ALIASES, SHOT_ALIASES
from prompt_data import SHOT_LABELS


def normalize_scale(value: str) -> str:
    return SCALE_ALIASES.get(value or "", "bold")


def prompt_pool_scale(scale: str) -> str:
    scale = normalize_scale(scale)
    return "bold" if scale in {"bold_no_outfit", "nsfw"} else scale


def skips_outfit(scale: str) -> bool:
    return normalize_scale(scale) in {"bold_no_outfit", "nsfw"}


def normalize_shot(value: str) -> str:
    value = value or ""
    if value in SHOT_ALIASES:
        return SHOT_ALIASES[value]
    if "头部" in value or "肩膀及以上" in value or "肩部以上" in value or "脸" in value or "面部" in value or "特写" in value:
        return "head_shot"
    if "上半身" in value or "胸部以上" in value or "胸部及以上" in value:
        return "upper_body"
    if "大半身" in value or "大腿以上" in value or "小腿" in value:
        return "large_half_body"
    if "半身" in value or "腰" in value:
        return "half_body"
    return "full_body"


def normalize_aspect(value: str = "", width: int | None = None, height: int | None = None) -> str:
    value = (value or "").strip().lower()
    if value in {"landscape", "horizontal", "横屏", "横向", "wide"}:
        return "landscape"
    if value in {"portrait", "vertical", "竖屏", "竖向", "tall"}:
        return "portrait"
    if width and height and width > height:
        return "landscape"
    return "portrait"


def shot_label(shot: str) -> str:
    return SHOT_LABELS[shot]
