"""提示词总入口：选档位、调用构图器生成各维度文本，按固定顺序渲染成最终提示词。

一至四档都由 prompt_composer 一次成句，这里不再对文字做任何改写：每个维度的文字原样进入最终提示词，
只补句末标点和“她穿着”。文字质量靠数据本身和 prompt_fluency 的逐行检查（不合格就重抽）保证。
四档只有姿势表情的内容单独隔离在四档专用池；姿势行与其余维度一起过同一套通顺门，规则与一至三档相同。
双人（cast="duo"）一至四档都支持：四档双人是“两个女生 + 男人”，姿势表情取四档专用双人池。
"""
from __future__ import annotations

import random
import time

from negative_prompt_engine import build_negative_prompt
from prompt_composer import NIGHT_MAKEUP_MARKERS, compose_parts, normalize_cast
from prompt_constants import RESOLUTIONS
from prompt_normalize import normalize_aspect, normalize_scale, normalize_shot, shot_label

_NIGHT_SCENE_MARKERS = ("夜晚", "夜景", "月光", "夜色", "暗室", "烛光", "壁灯", "入夜", "日落后", "深夜", "午夜", "夜")


def _scene_is_night(scene_light: str) -> bool:
    return any(marker in (scene_light or "") for marker in _NIGHT_SCENE_MARKERS)


def _makeup_mismatches_scene(scene_light: str, makeup: str) -> bool:
    """白天场景却配了夜系妆才算失配；夜景配中性/白天妆是可接受的（审查工具复用这个判定）。"""
    if not scene_light or not makeup:
        return False
    return (not _scene_is_night(scene_light)) and any(marker in makeup for marker in NIGHT_MAKEUP_MARKERS)


def _sentence(text: str) -> str:
    text = str(text or "").strip("，。 \n\t")
    return f"{text}。" if text else ""


def _outfit_line(parts: dict[str, str]) -> str:
    text = str(parts.get("outfit") or "").strip("，。 \n\t")
    if not text:
        return ""
    # 双人服装已写成“左边的女生穿着…。右边的女生穿着…”，不再补主语。
    return _sentence(text if text.startswith("她穿") or "女生穿着" in text else f"她穿着{text}")


def _character_line(parts: dict[str, str]) -> str:
    """脸部固定容貌 → 妆容 → 身材固定容貌，合成一句：妆容紧跟脸，身材接在最后。
    双人共用容貌写一句，两人各自的妆容（“左边的女生化着…。右边的女生化着…”）接在后面。"""
    pieces = [str(parts.get("character") or "").strip("，。 \n\t")]
    makeup = str(parts.get("makeup") or "").strip("，。 \n\t")
    if parts.get("cast") == "duo":
        pieces.append(str(parts.get("body") or "").strip("，。 \n\t"))
        return _sentence("，".join(piece for piece in pieces if piece)) + _sentence(makeup)
    if makeup:
        pieces.append(f"化着{makeup}")
    pieces.append(str(parts.get("body") or "").strip("，。 \n\t"))
    return _sentence("，".join(piece for piece in pieces if piece))


def _camera_line(parts: dict[str, str]) -> str:
    """焦段光圈与机位构图合成一行，镜头信息集中在提示词最前面。"""
    pieces = [str(parts.get(key) or "").strip("，。 \n\t") for key in ("lens", "camera_line")]
    return _sentence("，".join(piece for piece in pieces if piece))


def render_prompt_lines(parts: dict[str, str]) -> dict[str, str]:
    """按最终输出顺序渲染各维度行；空行保留为空字符串，便于逐行检查。"""
    return {
        "camera": _camera_line(parts),
        "character": _character_line(parts),
        "outfit": _outfit_line(parts),
        "pose": _sentence(parts.get("pose_expression")),
        "scene": _sentence(parts.get("scene_light")),
        "quality": _sentence(parts.get("quality")),
    }


def build_prompt(parts: dict[str, str]) -> str:
    """镜头 → 人物与妆容 → 衣着 → 姿势表情 → 场景光线与调色；场景和调色同属一段。"""
    lines = render_prompt_lines(parts)
    paragraphs = [lines["camera"], lines["character"], lines["outfit"], lines["pose"], lines["scene"] + lines["quality"]]
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


def generate_prompt_items(count: int, selections: dict[str, str], seed_text: str = "") -> list[dict]:
    rng = random.Random(seed_text or int(time.time() * 1000))
    scale = normalize_scale(selections.get("scale", "bold"))
    shot = normalize_shot(selections.get("shot", ""))
    era = str(selections.get("era", "modern") or "modern")
    cast = normalize_cast(selections.get("cast", "solo"))
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
        parts = compose_parts(scale, shot, aspect, rng, render_prompt_lines, era, cast)
        items.append(_finish_prompt_item(parts, scale, shot, aspect, width, height, rng))
    return items


def _finish_prompt_item(parts: dict[str, str], scale: str, shot: str, aspect: str, width, height, rng: random.Random) -> dict:
    prompt = build_prompt({**parts, "shot_key": shot, "scale": scale, "aspect": aspect})
    return {
        "scale": scale,
        "cast": parts.get("cast", "solo"),
        "shot": shot_label(shot),
        "shot_key": shot,
        "aspect": aspect,
        "dimension_parts": parts,
        "positive_prompt": prompt,
        "negative_prompt": build_negative_prompt(prompt, parts, scale, shot, aspect, width, height),
        "width": width,
        "height": height,
        "seed": rng.randint(1, 2**48 - 1),
    }
