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


def _bold_no_outfit_stocking_outfit(shot: str, rng: random.Random) -> str:
    options = BOLD_NO_OUTFIT_STOCKING_OUTFIT_OPTIONS.get(shot, [])  # noqa: F405
    return choose(options, rng) if options else ""


def prompt_parts(scale: str, shot: str, rng: random.Random, aspect: str = "portrait") -> dict[str, str]:
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
        scene_light_options_by_aspect(pool_scale, shot, aspect),
        rng,
        {**director, "keywords": intent_keywords(tuple(director.get("keywords", ())), visual_keywords, focus_keywords)},
        palette,
    )
    filter_grade = choose_filter_grade(pool_scale, director, palette, scene_light, rng)
    context_keywords = intent_keywords(scene_context_keywords(scene_light), visual_keywords, emotion_intent, focus_keywords)
    outfit = ""
    if scale == "bold_no_outfit":
        if shot in {"large_half_body", "full_body"} and rng.random() < 0.5:
            outfit = _bold_no_outfit_stocking_outfit(shot, rng)
    elif not skips_outfit(scale):
        outfit = choose_directed(outfit_options_by_aspect(pool_scale, shot, aspect), rng, director, context_keywords)
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
    cleaned = strengthen_seductive_scene_and_pose(cleaned, scale, shot, aspect)
    cleaned = simplify_pose_language(cleaned)
    cleaned = order_pose_before_expression(cleaned)
    cleaned = polish_photographic_naturalness(cleaned, scale, shot)
    cleaned = clean_global_prompt_text(cleaned, shot, scale)
    cleaned = enforce_prompt_length(cleaned)
    cleaned["feedback_tags"] = ",".join(feedback_tags(cleaned, scale, shot, aspect))
    cleaned["prompt_score"] = str(score_prompt_parts(cleaned, scale, shot, aspect))
    return cleaned


def build_prompt(parts: dict[str, str], enforce_limit: bool = True) -> str:
    source = enforce_prompt_length(parts) if enforce_limit else parts
    ordered = [clean_prompt_text(source.get(name, "")) for name in PROMPT_PART_ORDER]
    return "\n\n".join(ensure_sentence(part) for part in ordered if part)


def generate_candidate_parts(scale: str, shot: str, rng: random.Random, aspect: str, attempts: int = 6) -> dict[str, str]:
    if normalize_scale(scale) == "bold_no_outfit" and normalize_shot(shot) == "full_body":
        attempts = 1
    scene_time = ""
    if normalize_scale(scale) in {"bold", "bold_no_outfit", "nsfw"}:
        scene_time = rng.choice(("morning", "noon", "afternoon", "sunset", "night"))
    best_parts = None
    best_score = -10_000
    for _attempt in range(max(1, attempts)):
        parts = prompt_parts(scale, shot, rng, aspect)
        if scene_time:
            parts = strengthen_seductive_scene_and_pose(parts, scale, shot, aspect, scene_time=scene_time)
            parts = clean_global_prompt_text(parts, shot, scale)
            parts = enforce_prompt_length(parts)
            parts["prompt_score"] = str(score_prompt_parts(parts, scale, shot, aspect))
        score = int(parts.get("prompt_score") or score_prompt_parts(parts, scale, shot, aspect))
        if score > best_score:
            best_parts = parts
            best_score = score
    return best_parts or prompt_parts(scale, shot, rng, aspect)


def generate_prompt_items(count: int, selections: dict[str, str], seed_text: str = "") -> list[dict]:
    rng = random.Random(seed_text or int(time.time() * 1000))
    scale = normalize_scale(selections.get("scale", "bold"))
    shot = normalize_shot(selections.get("shot", ""))
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
        parts = generate_candidate_parts(scale, shot, rng, aspect)
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
