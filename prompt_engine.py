from __future__ import annotations

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prompt_data import *  # noqa: F403
from negative_prompt_engine import build_negative_prompt
from prompt_constants import (
    PROMPT_PART_ORDER,
    RESOLUTIONS,
)
from prompt_normalize import normalize_aspect, normalize_scale, normalize_shot, prompt_pool_scale, shot_label, skips_outfit
from prompt_planner import (
    choose,
    choose_color_palette,
    choose_directed,
    choose_director,
    choose_emotion_intent,
    choose_filter_grade,
    choose_pose_family,
    choose_scene_light,
    choose_visual_focus,
    classify_pose_family,
    intent_keywords,
    palette_keywords,
    scene_context_keywords,
)
from prompt_postprocess import (
    apply_conflict_cleaner,
    clean_global_prompt_text,
    clean_prompt_text,
    clean_sentence,
    enforce_prompt_length,
    enrich_visual_finish,
    ensure_sentence,
    feedback_tags,
    order_pose_before_expression,
    polish_photographic_naturalness,
    score_prompt_parts,
    simplify_pose_language,
    strengthen_expression,
    strengthen_seductive_scene_and_pose,
)


def _bold_no_outfit_stocking_outfit(shot: str, rng: random.Random, era: str = "modern") -> str:
    return ""


def _is_ancient_era(era: str) -> bool:
    return str(era or "").strip() in {"ancient", "古装", "古代"}


_MODERN_SCENE_MARKERS_FOR_ANCIENT = (
    "玻璃小桌",
    "藤椅",
    "藤编",
    "露台",
    "阳台",
    "城市",
    "泳池",
    "玻璃栏杆",
    "现代",
    "天台",
    "屋顶",
    "白色栏杆",
    "躺椅",
)

_BAR_COUNTER_MIST_SCENE = "环境光设定：夜店吧台后方大团紫色烟雾被冷紫逆光照亮，右后方红色射灯切过暗部，幽蓝霓虹散景包住背景，黑色湿润吧台从左下角斜向延伸，前景酒瓶和玻璃杯虚化反光，淡粉补光落在脸、锁骨和手指上"
_BAR_COUNTER_BOLD_OUTFIT = "夜店吧台半身造型，黑色细带亮钻胸衣配银色身体链，锁骨链、手链、臂环和腰链在紫色灯光下反光，关键部位由黑色布料完整覆盖，肩颈、胸线边缘和细腰成为视觉重点"
_BAR_COUNTER_HALF_BODY_POSE = "人物侧坐在吧台高脚椅上，上身前倾靠近黑色吧台，左前臂压在吧台边缘，右手举着威士忌杯停在脸侧，肩膀转向镜头，腰臀向画面右下方延伸，头部回望镜头，眼神直视镜头，嘴角轻轻上扬"
_BAR_COUNTER_CAMERA = "竖向夜店吧台半身近景，人物从头到大腿上侧入镜，黑色吧台从左下角斜向延伸，身体沿右下角形成对角线，脸部靠近画面中心"
_DOUBLE_GIRL_CAMERA = "竖向双人贴身半身构图，两名女性从头到大腿上侧入镜，脸部和嘴唇靠近画面中心，肩颈、手部、腰线和身体接触点清楚，背景保持简单"
_DOUBLE_GIRL_SCENE = "环境光设定：灰色墙面和浅色室内地面保持极简背景，左侧大窗柔光照亮两名女性的脸、肩颈、手指和腰腹，身体贴合处保留柔和阴影，整体是安静室内私房半身近景"
_BEACH_CAT_CAMERA = "竖向海边沙滩低机位全身强透视构图，镜头贴近沙地和前景高跟鞋，脚部在画面下方放大，腿部向后延伸，人物从脚到头完整入镜，远处海平线保持水平"
_BEACH_CAT_POSE = "人物背向镜头跪坐在蓝色复古手提箱上，双腿一前一后打开，前脚靠近镜头形成强透视，身体前倾后扭腰回头看向镜头，肩膀微微转开，眼神直视镜头，嘴唇微开，表情带一点挑逗和无辜感"
_BEACH_CAT_OUTFIT = "海边猫系私房全身造型，白色猫耳发箍配白色蕾丝边连体泳装，腰臀边缘露肤明显，白色大腿袜带蕾丝袜口，白色厚底高跟鞋带深蓝蝴蝶结和珍珠装饰，整体是沙滩局部阳光下的清透诱惑造型"
_BEACH_CAT_SCENE = "环境光设定：海边沙滩被镜头压低曝光，远处海面和晴空只保留柔和蓝色虚化，局部阳光从左上方切到人物腿部、腰线和肩颈，沙地只在脚边形成小面积反光，蓝色复古手提箱处在主体附近，背景不展开全景"
_CINEMA_CUP_CAMERA = "竖向电影院座椅半身构图，人物坐在红色影院座椅中，从头到大腿上侧入镜，脸部靠近画面中心，手部和白色纸杯挡在嘴唇前方，后排红色座椅虚化成背景层次"
_CINEMA_CUP_OUTFIT = "电影院日常半身造型，黑色高领修身针织长袖上衣贴合肩颈和上身线条，衣料细密柔软，袖口自然包住手腕，整体干净低调，红色座椅衬出黑色衣料轮廓"
_CINEMA_CUP_POSE = "人物坐在电影院红色座椅里，身体轻轻靠向椅背，右手拿着白色纸杯停在嘴唇前方，左手自然放在大腿上，眼睛越过纸杯直视镜头，嘴唇被纸杯边缘遮住，表情安静专注"
_CINEMA_CUP_SCENE = "电影院红色座椅半身场景，成排红色软椅在背景中虚化，暖色放映光从画面上方和后方落下，照亮头发边缘、眼睛、鼻梁、手指和白色纸杯，暗部保持柔和，整体像安静观影前的生活方式写真"

_BRIGHT_SEDUCTIVE_SCENE_TIMES = ("morning", "noon", "afternoon")
_DARK_SEDUCTIVE_SCENE_TIMES = ("sunset", "night")


def _choose_seductive_scene_time(rng: random.Random) -> str:
    if rng.choice((True, False)):
        return rng.choice(_BRIGHT_SEDUCTIVE_SCENE_TIMES)
    return rng.choice(_DARK_SEDUCTIVE_SCENE_TIMES)


def _is_valid_ancient_scene(text: str) -> bool:
    scene = str(text or "")
    if any(marker in scene for marker in _MODERN_SCENE_MARKERS_FOR_ANCIENT):
        return False
    return any(marker in scene for marker in ANCIENT_SCENE_MARKERS)  # noqa: F405


def _lock_era_dimensions(
    parts: dict[str, str],
    scale: str,
    shot: str,
    aspect: str,
    era: str,
    rng: random.Random,
) -> dict[str, str]:
    locked = dict(parts)
    pool_scale = prompt_pool_scale(scale)
    if scale == "bold_no_outfit":
        locked["outfit"] = ""
    elif not skips_outfit(scale):
        outfit_options = outfit_options_by_aspect(pool_scale, shot, aspect, era)
        if outfit_options:
            locked["outfit"] = choose(outfit_options, rng)
    scene_options = scene_light_options_by_aspect(scale, shot, aspect, era)
    scene_light = choose_scene_light(scene_options, rng)
    if scene_light:
        locked["scene_light"] = scene_light
    if _is_ancient_era(era) and not _is_valid_ancient_scene(locked.get("scene_light", "")):
        scene_light = choose_scene_light(scene_light_options_by_aspect(scale, shot, aspect, "ancient"), rng)
        if scene_light:
            locked["scene_light"] = scene_light
    bar_context = "，".join(str(locked.get(name) or "") for name in ("camera", "pose_expression", "scene_light"))
    if "吧台" in bar_context or "威士忌杯" in bar_context:
        if shot == "half_body":
            locked["camera"] = (
                "横向夜店吧台半身构图，人物大腿以上入镜，黑色吧台沿画面下缘斜向延伸，脸部靠近画面左侧，手部和威士忌杯在画面中段"
                if aspect == "landscape"
                else _BAR_COUNTER_CAMERA
            )
            locked["pose_expression"] = _BAR_COUNTER_HALF_BODY_POSE
        locked["scene_light"] = _BAR_COUNTER_MIST_SCENE
        locked["quality"] = "高级私房写真调色，肤质细腻但保留真实纹理，光影有层次，高光不过曝，夜景私房调色，暗部压低，肤色由窄光托亮"
        if scale == "bold":
            locked["outfit"] = _BAR_COUNTER_BOLD_OUTFIT
    double_girl_pose = str(locked.get("pose_expression") or "")
    if shot == "half_body" and any(marker in double_girl_pose for marker in ("双女", "两名女性", "接吻")):
        locked["camera"] = _DOUBLE_GIRL_CAMERA
        locked["scene_light"] = _DOUBLE_GIRL_SCENE
        locked["quality"] = "高级私房写真调色，肤质细腻但保留真实纹理，光影有层次，高光不过曝，柔和室内侧光调色，肤色自然明亮，阴影保留层次"
    beach_cat_context = "，".join(str(locked.get(name) or "") for name in ("camera", "pose_expression", "scene_light", "outfit"))
    if shot == "full_body" and any(marker in beach_cat_context for marker in ("蓝色复古手提箱", "猫耳", "前景高跟鞋")):
        locked["camera"] = _BEACH_CAT_CAMERA
        locked["pose_expression"] = _BEACH_CAT_POSE
        locked["scene_light"] = _BEACH_CAT_SCENE
        locked["quality"] = "高级私房写真调色，肤质细腻但保留真实纹理，光影有层次，高光不过曝，白天欠曝背景调色，人物局部受光，环境压暗虚化"
        if scale == "bold":
            locked["outfit"] = _BEACH_CAT_OUTFIT
    cinema_context = "，".join(str(locked.get(name) or "") for name in ("camera", "pose_expression", "scene_light", "outfit"))
    if scale == "normal" and shot == "half_body" and any(marker in cinema_context for marker in ("电影院", "影院座椅", "白色纸杯", "观影")):
        locked["camera"] = _CINEMA_CUP_CAMERA
        locked["outfit"] = _CINEMA_CUP_OUTFIT
        locked["pose_expression"] = _CINEMA_CUP_POSE
        locked["scene_light"] = _CINEMA_CUP_SCENE
        locked["quality"] = "真实镜头质感，主体清晰，脸部焦点锐利，自然皮肤纹理，高光不过曝，暖色电影厅生活方式调色，背景座椅柔和虚化"
    return locked


def prompt_parts(scale: str, shot: str, rng: random.Random, aspect: str = "portrait", era: str = "modern") -> dict[str, str]:
    scale = normalize_scale(scale)
    pool_scale = prompt_pool_scale(scale)
    director = choose_director(pool_scale, shot, aspect, rng)
    palette = choose_color_palette(director, pool_scale, shot, aspect, rng)
    emotion_intent = choose_emotion_intent(pool_scale, director, rng)
    visual_focus, focus_keywords = choose_visual_focus(shot, director, rng)
    pose_family = choose_pose_family(shot, aspect, visual_focus, rng)
    visual_keywords = palette_keywords(palette)
    coordination_keywords = intent_keywords(visual_keywords, emotion_intent, focus_keywords)
    camera = choose_directed(camera_options_by_aspect(shot, aspect), rng, director, coordination_keywords)
    character = choose(character_identity_options_by_aspect(shot, aspect), rng)
    scene_light = choose_scene_light(
        scene_light_options_by_aspect(scale, shot, aspect, era),
        rng,
        {**director, "keywords": intent_keywords(tuple(director.get("keywords", ())), visual_keywords, focus_keywords)},
        palette,
    )
    filter_grade = choose_filter_grade(pool_scale, director, palette, scene_light, rng)
    context_keywords = intent_keywords(scene_context_keywords(scene_light), visual_keywords, emotion_intent, focus_keywords)
    outfit = ""
    if scale == "bold_no_outfit":
        outfit = ""
    elif not skips_outfit(scale):
        outfit = choose_directed(outfit_options_by_aspect(pool_scale, shot, aspect, era), rng, director, context_keywords)
    pose_pool_scale = "nsfw" if scale == "nsfw" else pool_scale
    pose_expression = choose_directed(
        pose_expression_options_by_aspect(pose_pool_scale, shot, aspect),
        rng,
        director,
        context_keywords,
        required_family=pose_family,
    )
    parts = {
        "camera": camera,
        "character": character,
        "makeup": "",
        "outfit": outfit,
        "pose_expression": pose_expression,
        "scene_light": scene_light,
        "quality": "",
        "director": director["name"],
    }
    parts = enrich_visual_finish(parts, palette, filter_grade, scale)
    cleaned = {
        name: clean_sentence(value, shot, scale)
        for name, value in parts.items()
        if name != "director"
    }
    cleaned["director"] = director["name"]
    cleaned["color_palette"] = palette["name"]
    cleaned["filter_grade"] = filter_grade["name"]
    cleaned["emotion_intent"] = emotion_intent["name"]
    cleaned["visual_focus"] = visual_focus
    cleaned["pose_family"] = classify_pose_family(cleaned.get("pose_expression", ""))
    cleaned = clean_global_prompt_text(cleaned, shot, scale)
    # Camera pool entries and mobile framing already carry the crop boundary.
    # Avoid appending a second full framing sentence here; it bloats prompts and
    # repeats body-part constraints across dimensions.
    cleaned = apply_conflict_cleaner(cleaned, scale, shot, aspect)
    cleaned = simplify_pose_language(cleaned)
    cleaned = strengthen_expression(cleaned, scale, rng)
    cleaned = simplify_pose_language(cleaned)
    cleaned = order_pose_before_expression(cleaned)
    cleaned = polish_photographic_naturalness(cleaned, scale, shot)
    cleaned = _lock_era_dimensions(cleaned, scale, shot, aspect, era, rng)
    cleaned = clean_global_prompt_text(cleaned, shot, scale)
    cleaned = enforce_prompt_length(cleaned)
    cleaned["feedback_tags"] = ",".join(feedback_tags(cleaned, scale, shot, aspect))
    cleaned["prompt_score"] = str(score_prompt_parts(cleaned, scale, shot, aspect))
    return cleaned


def build_prompt(parts: dict[str, str], enforce_limit: bool = True) -> str:
    source = enforce_prompt_length(parts) if enforce_limit else parts
    ordered = [clean_prompt_text(source.get(name, "")) for name in PROMPT_PART_ORDER]
    return "\n\n".join(ensure_sentence(part) for part in ordered if part)


def generate_candidate_parts(scale: str, shot: str, rng: random.Random, aspect: str, era: str = "modern", attempts: int = 6) -> dict[str, str]:
    if normalize_scale(scale) == "bold_no_outfit" and normalize_shot(shot) == "full_body":
        attempts = 1
    scene_time = ""
    if normalize_scale(scale) in {"bold", "bold_no_outfit", "nsfw"} and not _is_ancient_era(era):
        scene_time = _choose_seductive_scene_time(rng)
    best_parts = None
    best_score = -10_000
    for _attempt in range(max(1, attempts)):
        parts = prompt_parts(scale, shot, rng, aspect, era)
        if scene_time:
            parts = _lock_era_dimensions(parts, scale, shot, aspect, era, rng)
            parts = strengthen_seductive_scene_and_pose(parts, scale, shot, aspect, scene_time=scene_time)
            parts = clean_global_prompt_text(parts, shot, scale)
            parts = enforce_prompt_length(parts)
            parts["prompt_score"] = str(score_prompt_parts(parts, scale, shot, aspect))
        score = int(parts.get("prompt_score") or score_prompt_parts(parts, scale, shot, aspect))
        if score > best_score:
            best_parts = parts
            best_score = score
    return best_parts or prompt_parts(scale, shot, rng, aspect, era)


def generate_prompt_items(count: int, selections: dict[str, str], seed_text: str = "") -> list[dict]:
    rng = random.Random(seed_text or int(time.time() * 1000))
    scale = normalize_scale(selections.get("scale", "bold"))
    shot = normalize_shot(selections.get("shot", ""))
    era = str(selections.get("era", "modern") or "modern")
    raw_width = selections.get("width")
    raw_height = selections.get("height")
    try:
        detected_width = int(raw_width) if raw_width is not None else None
        detected_height = int(raw_height) if raw_height is not None else None
    except (TypeError, ValueError):
        detected_width = None
        detected_height = None
    aspect = normalize_aspect(selections.get("aspect", ""), detected_width, detected_height)
    width, height = (detected_width, detected_height) if detected_width and detected_height else RESOLUTIONS[shot]
    items = []
    for index in range(count):
        parts = generate_candidate_parts(scale, shot, rng, aspect, era)
        parts = enforce_prompt_length(parts)
        parts = {name: (clean_prompt_text(value) if isinstance(value, str) else value) for name, value in parts.items()}
        prompt = build_prompt(parts)
        negative_prompt = build_negative_prompt(prompt, parts, scale, shot, aspect, width, height)
        item = {
            "scale": scale,
            "shot": shot_label(shot),
            "shot_key": shot,
            "aspect": aspect,
            "dimension_parts": parts,
            "positive_prompt": prompt,
            "compact_prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "seed": rng.randint(1, 2**48 - 1),
            "prompt_audit_issues": [],
        }
        items.append(item)
    return items
