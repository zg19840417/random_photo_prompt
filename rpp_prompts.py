from __future__ import annotations

import random
import time

from negative_prompt_engine import build_chinese_negative_prompt, build_negative_prompt
from prompt_constants import SHOT_ALIASES
from prompt_normalize import normalize_aspect, normalize_shot
from rpp_globals import MOBILE_SCOPE_PRESETS
from rpp_utils import _load_prompt_generator
from prompt_resolution import (
    MOBILE_PORTRAIT_RESOLUTION,
    clamp_mobile_resolution,
    mobile_custom_resolution,
    mobile_resolution_for_custom_prompt,
)

__all__ = sorted(["__all__", "_apply_krea2_portrait_orientation_guard", "_build_mobile_prompt_for_scope", "_normalize_mobile_orientation", "_resolve_mobile_orientation", "MOBILE_ORIENTATIONS", "_build_mobile_prompt_item", "_custom_mobile_prompt_item", "_mobile_custom_resolution", "_mobile_resolution_for_custom_prompt", "_mobile_shot_config", "_prompt_text", "_use_chinese_negative_prompt"])


def _build_mobile_prompt_item(scale, shot_config, seed_text, era="modern", cast="solo"):
    generate_prompt_items = _load_prompt_generator()
    return generate_prompt_items(
        1,
        {
            "scale": scale,
            "shot": shot_config["shot"],
            "aspect": normalize_aspect(shot_config["aspect"], shot_config["width"], shot_config["height"]),
            "width": shot_config["width"],
            "height": shot_config["height"],
            "era": era,
            "cast": cast,
        },
        seed_text,
    )[0]


def _prompt_text(prompt_item):
    """提交给模型的正面提示词：原样使用，用户手填的提示词同样不改写。"""
    return str(prompt_item["positive_prompt"])


def _apply_krea2_portrait_orientation_guard(positive_prompt, negative_prompt, prompt_item, width, height):
    if int(height or 0) <= int(width or 0):
        return positive_prompt, negative_prompt
    shot = str(prompt_item.get("shot_key") or "")
    if shot == "head_shot":
        positive_guard = (
            "strict upright vertical portrait, camera level, camera not rotated, subject not sideways, "
            "Krea2竖屏正立头部构图，脸部保持竖直方向，头顶朝向画面上方，下巴朝向画面下方，双眼水平对齐，"
            "肩线接近水平，肩颈在脸部下方自然承接，背景保持正常上下关系，不要横躺脸，不要侧躺，不要横向构图，不要旋转画面"
        )
    else:
        positive_guard = (
            "strict upright vertical portrait, camera level, camera not rotated, subject not sideways, "
            "Krea2竖屏正立构图，人物身体主轴保持竖直方向，头部位于画面上方，躯干在画面中段，膝盖、脚部或身体下缘位于画面下方，"
            "脊柱和颈部保持正立，肩线接近水平，背景墙面和地面保持正常上下关系，不要横躺人物，不要侧躺，不要横向构图，不要旋转画面"
        )
    negative_guard = "sideways, head sideways, body sideways, rotated image, rotated face, rotated 90 degrees, landscape body in portrait canvas, horizontal person, lying sideways, side lying pose, tilted 90 degrees, 横躺人物, 侧躺人物, 横向脸部, 画面旋转, 人物旋转90度"
    positive = f"{positive_guard}\n\n{positive_prompt}" if positive_prompt else positive_guard
    negative = f"{negative_prompt}, {negative_guard}" if negative_prompt else negative_guard
    return positive, negative


def _custom_mobile_prompt_item(prompt_text, seed_text=""):
    text = str(prompt_text or "").strip()
    if not text:
        return None
    resolution = mobile_resolution_for_custom_prompt(text)
    aspect = normalize_aspect(resolution["aspect"], resolution["width"], resolution["height"])
    return {
        "scale": "custom",
        "shot": "自定义",
        "shot_key": "custom",
        "aspect": "portrait",
        "dimension_parts": {"camera": text},
        "positive_prompt": text,
        "negative_prompt": build_negative_prompt(text, {"camera": text}, "custom", normalize_shot(text), aspect, resolution["width"], resolution["height"]),
        "seed": random.Random(str(seed_text or time.time())).randint(1, 2**48 - 1),
    }


def _use_chinese_negative_prompt(prompt_item, scale, shot_config, width, height, aspect):
    prompt_item["negative_prompt"] = build_chinese_negative_prompt(
        _prompt_text(prompt_item),
        prompt_item.get("dimension_parts") or {},
        scale,
        (shot_config or {}).get("shot") or prompt_item.get("shot_key") or "full_body",
        aspect,
        width,
        height,
    )
    return prompt_item


def _mobile_resolution_for_custom_prompt(prompt_text):
    return mobile_resolution_for_custom_prompt(prompt_text)


def _mobile_custom_resolution(prompt_text, preset=""):
    return mobile_custom_resolution(prompt_text, preset)


MOBILE_ORIENTATIONS = ("auto", "landscape", "portrait", "square")
_ORIENTATION_ALIASES = {
    "自动": "auto",
    "横图": "landscape", "横向": "landscape", "横": "landscape",
    "竖图": "portrait", "竖向": "portrait", "竖": "portrait",
    "方图": "square", "方形": "square", "方": "square",
}
_ORIENTATION_RESOLUTIONS = {
    "landscape": {"aspect": "landscape", "width": 1536, "height": 1024, "framing": ""},
    "square": {"aspect": "square", "width": 1536, "height": 1536, "framing": ""},
    "portrait": MOBILE_PORTRAIT_RESOLUTION,
}


def _normalize_mobile_orientation(value):
    text = str(value or "").strip().lower()
    text = _ORIENTATION_ALIASES.get(text, text)
    return text if text in MOBILE_ORIENTATIONS else "auto"


def _resolve_mobile_orientation(orientation, seed_text):
    """自动模式按本张种子在横图、竖图、方图中等权重抽取，同一种子结果可复现。"""
    orientation = _normalize_mobile_orientation(orientation)
    if orientation != "auto":
        return orientation
    return random.Random(f"{seed_text}|orientation").choice(("landscape", "portrait", "square"))


def _build_mobile_prompt_for_scope(scale, shot_config, seed_text, era="modern", orientation="portrait", cast="solo", custom_resolution=""):
    """手填尺寸优先于画幅；提示词按最终画布方向随机生成。"""
    if str(custom_resolution or "").strip():
        resolution = mobile_custom_resolution("", custom_resolution)
        aspect = resolution["aspect"]
        width, height = resolution["width"], resolution["height"]
    else:
        aspect = _resolve_mobile_orientation(orientation, seed_text)
        resolution = clamp_mobile_resolution(_ORIENTATION_RESOLUTIONS[aspect])
        width, height = {"landscape": (1536, 1024), "square": (1536, 1536)}.get(aspect, (1024, 1536))
    item = _build_mobile_prompt_item(scale, {**shot_config, "aspect": aspect, "width": width, "height": height}, seed_text, era, cast)
    return item, resolution


def _mobile_shot_config(value):
    text = str(value or "").strip()
    if text in {"random", "随机", "随机镜头"}:
        return MOBILE_SCOPE_PRESETS[random.choice(("head_shot", "half_body", "full_body"))]
    key = text if text in MOBILE_SCOPE_PRESETS else SHOT_ALIASES.get(text) if text else None
    if key not in MOBILE_SCOPE_PRESETS:
        raise ValueError(f"不支持的镜头：{text}")
    return MOBILE_SCOPE_PRESETS[key]
