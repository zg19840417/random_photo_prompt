from __future__ import annotations

import copy
import random
import re
import time

import folder_paths
from k2_sfw_prompt_rule import RULE_KEY as K2_SFW_RULE_KEY
from k2_sfw_prompt_rule import generate_prompt_item as generate_k2_sfw_prompt_item

from rpp_globals import (
    ANCIENT_SHOE_REPLACEMENTS,
    CHARACTER_BY_SHOT,
    FIXED_CHARACTER_IDENTITY,
    K2_SFW_RULE_KEY,
    KREA2_PORTRAIT_HORIZONTAL_MARKERS,
    MAX_POSITIVE_PROMPT_LENGTH,
    MOBILE_CUSTOM_RESOLUTION_PRESETS,
    MOBILE_DEFAULT_RESOLUTIONS,
    MOBILE_DIRECTOR_RESOLUTION_RULES,
    MOBILE_FRAMING_COMPACT_REPLACEMENTS,
    MOBILE_RESOLUTION_RULES,
    MOBILE_SCOPE_PRESETS,
    MOBILE_STANDING_FULL_BODY_RESOLUTION,
    NODE_DIR,
)
from rpp_utils import (
    _clean_mobile_prompt_clause_text,
    _is_ancient_mobile_era,
    _load_prompt_generator,
    _normalize_aspect,
    _prompt_clauses,
    _remove_mobile_clauses_with_markers,
    _round_to_multiple,
    _strip_outfit_palette_clause,
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
from prompt_postprocess import clean_prompt_text

__all__ = sorted(["__all__", "_apply_krea2_portrait_orientation_guard", "_apply_krea2_prompt_item_orientation_guard", "_apply_mobile_framing", "_build_desktop_prompt_with_mobile_logic", "_build_mobile_prompt_for_scope", "_build_mobile_prompt_item", "_build_mobile_prompt_item_for_rule", "_build_prompt", "_build_prompt_item", "_build_prompt_with_mobile_logic", "_clamp_mobile_resolution", "_clean_mobile_prompt_parts", "_custom_mobile_prompt_item", "_display_prompt_text", "_enforce_mobile_ancient_barefoot_parts", "_enforce_mobile_ancient_barefoot_text", "_enforce_prompt_length", "_ensure_scoped_character_prompt", "_krea2_upright_pose_fallback", "_mobile_custom_resolution", "_mobile_ground_anchor", "_mobile_prompt_text_for_resolution", "_mobile_resolution_for_custom_prompt", "_mobile_resolution_for_prompt", "_mobile_shot_config", "_normalize_mobile_prompt_rule", "_prompt_len_from_parts", "_prompt_text", "_rebuild_prompt_text_from_parts", "_resolve_mobile_framing", "_use_chinese_negative_prompt"])

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
    return _build_mobile_prompt_item_for_rule(scale, shot_config, seed_text, era)


def _normalize_mobile_prompt_rule(value):
    rule = str(value or "").strip()
    if not rule or rule == "standard":
        return "standard"
    if rule == K2_SFW_RULE_KEY:
        return rule
    raise ValueError(f"不支持的提示词规则：{rule}")


def _build_mobile_prompt_item_for_rule(scale, shot_config, seed_text, era="modern", prompt_rule="standard"):
    rule = _normalize_mobile_prompt_rule(prompt_rule)
    if rule == K2_SFW_RULE_KEY:
        return generate_k2_sfw_prompt_item(seed_text)
    shot = shot_config["shot"]
    aspect = shot_config["aspect"]
    width = shot_config["width"]
    height = shot_config["height"]
    return _build_prompt_item(scale, shot, seed_text, aspect, width, height, era)


def _ensure_scoped_character_prompt(prompt_item, era="modern"):
    item = copy.deepcopy(prompt_item)
    parts = item.get("dimension_parts")
    if isinstance(parts, dict):
        shot_key = item.get("shot_key") or ""
        parts = _clean_mobile_prompt_parts(parts, shot_key, era)
        character = str(parts.get("character") or "").strip()
        if not character:
            character = CHARACTER_BY_SHOT.get(shot_key) or CHARACTER_BY_SHOT["full_body"]
        elif "K-pop韩国" not in character:
            character = f"{FIXED_CHARACTER_IDENTITY}，{character}"
        parts["character"] = character
        parts["shot_key"] = shot_key
        parts["scale"] = str(item.get("scale") or "")
        item["dimension_parts"] = parts
        prompt = _rebuild_prompt_text_from_parts(parts)
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
    if str(prompt_item.get("prompt_rule") or "") == K2_SFW_RULE_KEY:
        return str(prompt_item.get("compact_prompt") or prompt_item["positive_prompt"]).strip()
    return clean_prompt_text(prompt_item.get("compact_prompt") or prompt_item["positive_prompt"])


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
    return clean_prompt_text(positive), clean_prompt_text(negative)


def _rebuild_prompt_text_from_parts(parts):
    from prompt_engine import build_prompt

    return clean_prompt_text(build_prompt(dict(parts or {}), enforce_limit=False))


def _enforce_mobile_ancient_barefoot_text(text, era):
    cleaned = str(text or "")
    if not _is_ancient_mobile_era(era):
        return cleaned
    for old, new in ANCIENT_SHOE_REPLACEMENTS:
        cleaned = cleaned.replace(old, new)
    cleaned = cleaned.replace("和裸足完整入镜", "，裸足完整入镜")
    cleaned = cleaned.replace("配裸足", "，裸足")
    return cleaned


def _enforce_mobile_ancient_barefoot_parts(parts, era):
    cleaned = dict(parts or {})
    if not _is_ancient_mobile_era(era):
        return cleaned
    for name in ("camera", "outfit", "pose_expression", "scene_light"):
        cleaned[name] = _enforce_mobile_ancient_barefoot_text(cleaned.get(name, ""), era)
    if cleaned.get("outfit") and "裸足" not in str(cleaned["outfit"]):
        cleaned["outfit"] = f'{cleaned["outfit"]}，裙摆下方保持裸足'
    return cleaned


def _clean_mobile_prompt_parts(parts, shot_key, era="modern"):
    cleaned = dict(parts or {})
    cleaned["outfit"] = _strip_outfit_palette_clause(cleaned.get("outfit", ""))
    if shot_key == "head_shot":
        for name in ("pose_expression", "scene_light", "outfit", "camera"):
            text = str(cleaned.get(name) or "")
            text = text.replace("完整胸部和上腰短截", "胸部上缘")
            text = text.replace("完整胸部与一小段腰部", "胸部线条")
            text = text.replace("完整胸部和少量上腰", "胸部线条")
            text = text.replace("和上腰短截", "")
            text = _remove_mobile_clauses_with_markers(text, ("腰线", "细腰", "腰部", "腰侧", "腰缘", "身体曲线"))
            cleaned[name] = _clean_mobile_prompt_clause_text(text)
    if shot_key == "head_shot":
        for name in ("pose_expression", "scene_light", "outfit", "camera"):
            cleaned[name] = _remove_mobile_clauses_with_markers(
                cleaned.get(name, ""),
                ("胸部", "胸前", "乳沟", "腰", "臀", "腿", "脚"),
            )
    cleaned = _enforce_mobile_ancient_barefoot_parts(cleaned, era)
    return cleaned


def _prompt_len_from_parts(parts):
    return len(_rebuild_prompt_text_from_parts(parts))


def _enforce_prompt_length(parts, max_length=MAX_POSITIVE_PROMPT_LENGTH):
    compacted = dict(parts or {})
    if _prompt_len_from_parts(compacted) <= max_length:
        return compacted
    compacted["quality"] = ""
    if _prompt_len_from_parts(compacted) <= max_length:
        return compacted
    for name in ("scene_light", "outfit", "pose_expression", "camera"):
        clauses = _prompt_clauses(compacted.get(name, ""))
        while len(clauses) > 1 and _prompt_len_from_parts(compacted) > max_length:
            clauses.pop()
            compacted[name] = "，".join(clauses)
        if _prompt_len_from_parts(compacted) <= max_length:
            break
    return compacted


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


def _mobile_ground_anchor(parts, era="modern"):
    if str(era or "").strip() in {"ancient", "古装", "古代"}:
        return "暗色木地板或木质甲板"
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


def _resolve_mobile_framing(framing, parts, era="modern"):
    if "{ground_anchor}" in framing:
        return framing.replace("{ground_anchor}", _mobile_ground_anchor(parts, era))
    return framing


def _apply_mobile_framing(prompt_item, resolution, era="modern"):
    framing = resolution.get("framing")
    if not framing:
        return prompt_item
    item = copy.deepcopy(prompt_item)
    parts = item.setdefault("dimension_parts", {})
    framing = _resolve_mobile_framing(framing, parts, era)
    camera = str(parts.get("camera") or "")
    if any(marker in camera for marker in ("入镜", "镜头", "构图", "画面", "头顶", "完整")):
        framing = MOBILE_FRAMING_COMPACT_REPLACEMENTS.get(framing, framing)
    # 去重：如果camera的开头分句与framing的开头分句重复，跳过追加
    camera_first = re.split(r"[，,]", camera)[0].strip() if camera else ""
    framing_first = re.split(r"[，,]", framing)[0].strip()
    scope_markers = ("大腿以上入镜", "肩膀及以上入镜", "从头到脚完整入镜", "头顶完整")
    # 任何含"全身"的相机描述都已表达全身构图意图，无需再追加泛化的"竖向全身构图"
    camera_has_full_body_framing = "全身" in camera
    framing_has_full_body_framing = "全身" in framing and "构图" in framing
    already_covered = (
        framing in camera or
        camera_first == framing_first or
        camera_first in framing or
        framing_first in camera or
        any(marker in camera and marker in framing for marker in scope_markers) or
        (camera_has_full_body_framing and framing_has_full_body_framing)
    )
    if not already_covered:
        parts["camera"] = f"{camera}，{framing}" if camera else framing
    parts = _clean_mobile_prompt_parts(parts, item.get("shot_key") or "", era)
    parts["shot_key"] = str(item.get("shot_key") or "")
    parts["scale"] = str(item.get("scale") or "")
    parts = _enforce_prompt_length(parts)
    item["dimension_parts"] = parts
    prompt = _rebuild_prompt_text_from_parts(parts)
    item["compact_prompt"] = prompt
    item["positive_prompt"] = prompt
    return item


def _build_mobile_prompt_for_scope(scale, shot_config, seed_text, era="modern", prompt_rule="standard"):
    rule = _normalize_mobile_prompt_rule(prompt_rule)
    if rule == K2_SFW_RULE_KEY:
        item = generate_k2_sfw_prompt_item(seed_text)
        return item, {**item["resolution"], "framing": ""}
    initial = _build_mobile_prompt_item_for_rule(scale, shot_config, seed_text, era, rule)
    initial = _ensure_scoped_character_prompt(initial, era)
    resolution = _mobile_resolution_for_prompt(initial, shot_config["shot"])
    if resolution["aspect"] != shot_config["aspect"]:
        resolved_config = {
            **shot_config,
            "aspect": resolution["aspect"],
            "width": resolution["width"],
            "height": resolution["height"],
        }
        initial = _build_mobile_prompt_item_for_rule(scale, resolved_config, f"{seed_text}-{resolution['aspect']}", era, rule)
        initial = _ensure_scoped_character_prompt(initial)
        resolution = _mobile_resolution_for_prompt(initial, shot_config["shot"])
    return _apply_mobile_framing(initial, resolution, era), resolution


def _build_prompt_with_mobile_logic(scale, shot, seed_text="", era="modern"):
    shot_config = _mobile_shot_config(shot)
    item, _resolution = _build_mobile_prompt_for_scope(scale, shot_config, seed_text, era)
    return _prompt_text(item)


def _build_desktop_prompt_with_mobile_logic(scale, shot, seed_text="", era="modern"):
    shot_config = _mobile_shot_config(shot)
    item, resolution = _build_mobile_prompt_for_scope(scale, shot_config, seed_text, era)
    return item, resolution


def _build_prompt(scale, shot, seed_text="", aspect="portrait", width=None, height=None, era="modern"):
    return _build_prompt_with_mobile_logic(scale, shot, seed_text, era)


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



