"""提示词总入口：选档位、调用构图器生成各维度文本，按固定顺序渲染成最终提示词。

一至四档都由 prompt_composer 一次成句，这里不再对文字做任何改写：每个维度的文字原样进入最终提示词，
只补句末标点和“她穿着”。文字质量靠数据本身和 prompt_fluency 的逐行检查（不合格就重抽）保证。
四档除姿势表情外与三档一致，姿势表情只从四档专用池原样抽取。
"""
from __future__ import annotations

import random
import time

from negative_prompt_engine import build_negative_prompt
from prompt_composer import compose_parts
from prompt_constants import RESOLUTIONS
from prompt_data import pose_expression_options_by_aspect
from prompt_normalize import normalize_aspect, normalize_scale, normalize_shot, shot_label

_NIGHT_SCENE_MARKERS = ("夜晚", "夜景", "月光", "夜色", "暗室", "烛光", "壁灯", "入夜", "日落后", "深夜", "午夜", "夜")
_NIGHT_MAKEUP_MARKERS = ("夜景", "夜色", "暗夜", "夜拍", "暗调", "月光", "夜")


# 四档专用姿势池按整具身体写动作；头部镜头只看得见肩部以上，越界的分句直接丢弃（其余文字原样保留）。
_NSFW_HEAD_SHOT_OUT_OF_SCOPE = ("胸部", "胸前", "乳沟", "腰", "臀", "腿", "脚", "身体曲线")


def _drop_out_of_scope_clauses(text: str, markers: tuple[str, ...]) -> str:
    sentences = []
    for sentence in str(text or "").split("。"):
        clauses = [clause for clause in sentence.split("，") if clause and not any(marker in clause for marker in markers)]
        if clauses:
            sentences.append("，".join(clauses))
    return "。".join(sentences)


def choose(values, rng: random.Random) -> str:
    return rng.choice(values) if values else ""


def _scene_is_night(scene_light: str) -> bool:
    return any(marker in (scene_light or "") for marker in _NIGHT_SCENE_MARKERS)


def _makeup_mismatches_scene(scene_light: str, makeup: str) -> bool:
    """白天场景却配了夜系妆才算失配；夜景配中性/白天妆是可接受的（审查工具复用这个判定）。"""
    if not scene_light or not makeup:
        return False
    return (not _scene_is_night(scene_light)) and any(marker in makeup for marker in _NIGHT_MAKEUP_MARKERS)


def _sentence(text: str) -> str:
    text = str(text or "").strip("，。 \n\t")
    return f"{text}。" if text else ""


def _outfit_line(parts: dict[str, str]) -> str:
    text = str(parts.get("outfit") or "").strip("，。 \n\t")
    if not text:
        return ""
    return _sentence(text if text.startswith("她穿") else f"她穿着{text}")


def render_prompt_lines(parts: dict[str, str]) -> dict[str, str]:
    """按最终输出顺序渲染各维度行；空行保留为空字符串，便于逐行检查。"""
    return {
        "pose": _sentence(parts.get("pose_expression")),
        "scene": _sentence(parts.get("scene_light")),
        "quality": _sentence(parts.get("quality")),
        "camera": _sentence(parts.get("camera_line")),
        "character": _sentence(parts.get("character")),
        "outfit": _outfit_line(parts),
        "makeup": _sentence(parts.get("makeup")),
    }


def build_prompt(parts: dict[str, str]) -> str:
    return "\n\n".join(line for line in render_prompt_lines(parts).values() if line)


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
    for _ in range(count):
        if scale == "nsfw":
            # 四档除姿势表情外与三档完全一致；姿势表情只从四档专用池原样抽取。
            parts = compose_parts("bold_no_outfit", shot, aspect, rng, render_prompt_lines, era)
            pose_expression = choose(pose_expression_options_by_aspect("nsfw", shot, aspect), rng)
            if shot == "head_shot":
                pose_expression = _drop_out_of_scope_clauses(pose_expression, _NSFW_HEAD_SHOT_OUT_OF_SCOPE)
            parts.update(pose_expression=pose_expression, art_pose=pose_expression)
        else:
            parts = compose_parts(scale, shot, aspect, rng, render_prompt_lines, era)
        items.append(_finish_prompt_item(parts, scale, shot, aspect, width, height, rng))
    return items


def _finish_prompt_item(parts: dict[str, str], scale: str, shot: str, aspect: str, width, height, rng: random.Random) -> dict:
    prompt = build_prompt({**parts, "shot_key": shot, "scale": scale, "aspect": aspect})
    return {
        "scale": scale,
        "shot": shot_label(shot),
        "shot_key": shot,
        "aspect": aspect,
        "dimension_parts": parts,
        "positive_prompt": prompt,
        "compact_prompt": prompt,
        "negative_prompt": build_negative_prompt(prompt, parts, scale, shot, aspect, width, height),
        "width": width,
        "height": height,
        "seed": rng.randint(1, 2**48 - 1),
        "prompt_audit_issues": [],
    }
