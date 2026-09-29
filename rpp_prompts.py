from __future__ import annotations

import copy
import random
import re
import time

import folder_paths

from rpp_globals import (
    CHARACTER_BY_SHOT,
    FIXED_CHARACTER_IDENTITY,
    KREA2_PORTRAIT_HORIZONTAL_MARKERS,
    MOBILE_CUSTOM_RESOLUTION_PRESETS,
    MOBILE_DEFAULT_RESOLUTIONS,
    MOBILE_DIRECTOR_RESOLUTION_RULES,
    MOBILE_RESOLUTION_RULES,
    MOBILE_SCOPE_PRESETS,
    MOBILE_STANDING_FULL_BODY_RESOLUTION,
    NODE_DIR,
)
from rpp_utils import (
    _clean_mobile_prompt_clause_text,
    _load_prompt_generator,
    _normalize_aspect,
    _prompt_clauses,
    _remove_mobile_clauses_with_markers,
)
from prompt_resolution import (
    MOBILE_RESOLUTION_MULTIPLE,
    base_resolution_for_workflow,
    clamp_mobile_resolution,
    linked_float_value,
    mobile_custom_resolution,
    mobile_resolution_for_custom_prompt,
    round_to_multiple,
    workflow_output_scale,
)

__all__ = sorted(["__all__", "_apply_krea2_portrait_orientation_guard", "_apply_krea2_prompt_item_orientation_guard", "_build_desktop_prompt_with_mobile_logic", "_build_mobile_prompt_for_scope", "_normalize_mobile_orientation", "_resolve_mobile_orientation", "MOBILE_ORIENTATIONS", "_build_mobile_prompt_item", "_build_prompt_item", "_clamp_mobile_resolution", "_custom_mobile_prompt_item", "_display_prompt_text", "_ensure_scoped_character_prompt", "_krea2_upright_pose_fallback", "_mobile_custom_resolution", "_mobile_prompt_text_for_resolution", "_mobile_resolution_for_custom_prompt", "_mobile_resolution_for_prompt", "_mobile_shot_config", "_prompt_text", "_rebuild_prompt_text_from_parts", "_use_chinese_negative_prompt"])

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


def _build_mobile_prompt_item(scale, shot_config, seed_text, era="modern"):
    shot = shot_config["shot"]
    aspect = shot_config["aspect"]
    width = shot_config["width"]
    height = shot_config["height"]
    return _build_prompt_item(scale, shot, seed_text, aspect, width, height, era)


def _ensure_scoped_character_prompt(prompt_item, era="modern"):
    """保证固定人物身份行在提示词里；其余文字原样保留，不做清理或改写。"""
    item = copy.deepcopy(prompt_item)
    parts = item.get("dimension_parts")
    if isinstance(parts, dict):
        shot_key = item.get("shot_key") or ""
        character = str(parts.get("character") or "").strip()
        if not character:
            character = CHARACTER_BY_SHOT.get(shot_key) or CHARACTER_BY_SHOT["full_body"]
        elif "K-pop韩国" not in character:
            character = f"{FIXED_CHARACTER_IDENTITY}，{character}"
        parts["character"] = character
        parts["shot_key"] = shot_key
        parts["scale"] = str(item.get("scale") or "")
        item["dimension_parts"] = parts
        prompt = _rebuild_prompt_text_from_parts(parts, item.get("aspect"))
        item["positive_prompt"] = prompt
        item["compact_prompt"] = prompt
    else:
        prompt = _prompt_text(item)
        if "K-pop韩国" not in prompt:
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
    """提交给模型的正面提示词：原样使用，用户手填的提示词同样不改写。"""
    return str(prompt_item.get("compact_prompt") or prompt_item["positive_prompt"])


def _krea2_upright_pose_fallback(shot):
    if shot == "head_shot":
        return "脸部保持竖直方向贴近镜头，头顶朝画面上方，肩颈在脸部下方自然承接，眼神从睫毛下方看向镜头，嘴角带轻蔑浅笑"
    if shot == "half_body":
        return "人物上半身保持竖直方向靠近镜头，头部在肩颈正上方，肩线接近水平，一只手停在锁骨旁，眼神俯视镜头，嘴角带轻蔑浅笑"
    return "人物身体主轴保持竖直方向，头部位于画面上方，躯干自然向下承接，肩线接近水平，眼神俯视镜头，嘴角带轻蔑浅笑"


def _apply_krea2_prompt_item_orientation_guard(prompt_item, width, height):
    if int(height or 0) <= int(width or 0):
        return prompt_item
    item = copy.deepcopy(prompt_item)
    parts = item.get("dimension_parts") or {}
    if parts:
        parts = dict(parts)
        shot = str(item.get("shot_key") or "")
        camera = str(parts.get("camera") or "")
        upright_camera = "竖屏正立构图，人物头顶朝画面上方，肩线接近水平，画面不旋转"
        if upright_camera not in camera:
            parts["camera"] = f"{upright_camera}，{camera}" if camera else upright_camera

        pose = str(parts.get("pose_expression") or "")
        pose = pose.replace("头部大幅后仰后又用眼尾向下俯视镜头", "头部轻微后仰但脸部保持竖直，眼尾向下俯视镜头")
        pose = pose.replace("头部大幅后仰后俯视镜头", "头部轻微后仰但脸部保持竖直，俯视镜头")
        pose = pose.replace("头部大幅后仰", "头部轻微后仰且脸部保持竖直")
        pose = _remove_mobile_clauses_with_markers(pose, KREA2_PORTRAIT_HORIZONTAL_MARKERS)
        if not pose.strip() or any(marker in pose for marker in KREA2_PORTRAIT_HORIZONTAL_MARKERS):
            pose = _krea2_upright_pose_fallback(shot)
        parts["pose_expression"] = _clean_mobile_prompt_clause_text(pose)
        parts["shot_key"] = shot
        parts["scale"] = str(item.get("scale") or "")
        item["dimension_parts"] = parts
        prompt = _rebuild_prompt_text_from_parts(parts)
        item["positive_prompt"] = prompt
        item["compact_prompt"] = prompt
    return item


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


def _rebuild_prompt_text_from_parts(parts, aspect=None):
    from prompt_engine import build_prompt

    source = dict(parts or {})
    if aspect is not None:
        source["aspect"] = aspect
    return build_prompt(source)


def _display_prompt_text(prompt_item):
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


MOBILE_ORIENTATIONS = ("auto", "landscape", "portrait", "square")

def _normalize_mobile_orientation(value):
    text = str(value or "").strip().lower()
    aliases = {
        "自动": "auto",
        "横图": "landscape", "横向": "landscape", "横": "landscape",
        "竖图": "portrait", "竖向": "portrait", "竖": "portrait",
        "方图": "square", "方形": "square", "方": "square",
    }
    text = aliases.get(text, text)
    return text if text in MOBILE_ORIENTATIONS else "auto"


def _resolve_mobile_orientation(orientation, seed_text):
    """自动模式按本张种子在横图、竖图、方图中等权重抽取，同一种子结果可复现。"""
    orientation = _normalize_mobile_orientation(orientation)
    if orientation != "auto":
        return orientation
    return random.Random(f"{seed_text}|orientation").choice(("landscape", "portrait", "square"))


def _forced_mobile_resolution(prompt_item, shot, aspect):
    if aspect == "square":
        return _clamp_mobile_resolution({"aspect": "square", "width": 1536, "height": 1536, "framing": ""})
    if aspect == "landscape":
        return _clamp_mobile_resolution(
            {"aspect": "landscape", "width": 1536, "height": 1024, "framing": ""}
        )
    inferred = _mobile_resolution_for_prompt(prompt_item, shot)
    if inferred["aspect"] == "portrait":
        return inferred
    return _clamp_mobile_resolution(MOBILE_DEFAULT_RESOLUTIONS[shot])


def _build_mobile_prompt_for_scope(scale, shot_config, seed_text, era="modern", orientation=None):
    if orientation is not None:
        # 用户选定方向（或自动抽定）后，提示词与分辨率都按该方向生成，不再由姿势文本反推。
        aspect = _resolve_mobile_orientation(orientation, seed_text)
        width, height = {"landscape": (1536, 1024), "square": (1536, 1536)}.get(aspect, (1024, 1536))
        oriented_config = {**shot_config, "aspect": aspect, "width": width, "height": height}
        item = _build_mobile_prompt_item(scale, oriented_config, seed_text, era)
        item = _ensure_scoped_character_prompt(item, era)
        resolution = _forced_mobile_resolution(item, shot_config["shot"], aspect)
        return item, resolution
    initial = _build_mobile_prompt_item(scale, shot_config, seed_text, era)
    initial = _ensure_scoped_character_prompt(initial, era)
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
    return initial, resolution




def _build_desktop_prompt_with_mobile_logic(scale, shot, seed_text="", era="modern"):
    shot_config = _mobile_shot_config(shot)
    item, resolution = _build_mobile_prompt_for_scope(scale, shot_config, seed_text, era)
    return item, resolution


def _mobile_shot_config(value):
    text = str(value or "").strip()
    if text in {"random", "随机", "随机镜头"}:
        key = random.choice(("head_shot", "half_body", "full_body"))
        return MOBILE_SCOPE_PRESETS[key]
    shot_map = {
        "full_body": "full_body",
        "full_body_portrait": "full_body",
        "full_body_landscape": "full_body",
        "全身": "full_body",
        "全身像": "full_body",
        "half_body": "half_body",
        "half_body_portrait": "half_body",
        "half_body_landscape": "half_body",
        "半身": "half_body",
        "半身像": "half_body",
        "半身镜头": "half_body",
        "大腿以上": "half_body",
        "大腿以上镜头": "half_body",
        "head_shot": "head_shot",
        "head_shot_portrait": "head_shot",
        "head_shot_landscape": "head_shot",
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


