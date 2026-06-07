from __future__ import annotations

from prompt_constants import NEGATIVE_PROMPT_RULES
from prompt_data import NEGATIVE_PROMPT
from prompt_normalize import normalize_aspect, normalize_shot
from prompt_postprocess import _text_has_any


def _append_negative_terms(terms: list[str], additions: tuple[str, ...]) -> None:
    existing = {term.strip().lower() for term in terms}
    for item in additions:
        value = str(item or "").strip()
        if value and value.lower() not in existing:
            terms.append(value)
            existing.add(value.lower())


def build_negative_prompt(
    positive_prompt: str = "",
    parts: dict[str, str] | None = None,
    scale: str = "bold",
    shot: str = "full_body",
    aspect: str = "portrait",
    width: int | None = None,
    height: int | None = None,
) -> str:
    parts = parts or {}
    shot = normalize_shot(shot)
    aspect = normalize_aspect(aspect, width, height)
    source = "，".join(
        str(value or "")
        for value in (
            positive_prompt,
            parts.get("camera"),
            parts.get("pose_expression"),
            parts.get("scene_light"),
            parts.get("feedback_tags"),
        )
    )
    terms = [item.strip() for item in str(NEGATIVE_PROMPT or "").split(",") if item.strip()]
    _append_negative_terms(terms, NEGATIVE_PROMPT_RULES["base_quality"])
    _append_negative_terms(terms, NEGATIVE_PROMPT_RULES["lips_makeup"])
    _append_negative_terms(terms, NEGATIVE_PROMPT_RULES["canvas_padding"])
    _append_negative_terms(terms, NEGATIVE_PROMPT_RULES["legal_safety"])
    if aspect == "landscape" or _text_has_any(source, ("横向", "宽画幅", "沿画幅展开", "横幅")):
        _append_negative_terms(terms, NEGATIVE_PROMPT_RULES["landscape_mismatch"])
    if aspect == "portrait" or _text_has_any(source, ("竖向", "竖构图", "站姿", "站立")):
        _append_negative_terms(terms, NEGATIVE_PROMPT_RULES["portrait_mismatch"])
    if shot == "head_shot":
        _append_negative_terms(terms, NEGATIVE_PROMPT_RULES["shot_scope_head"])
    elif shot == "upper_body":
        _append_negative_terms(terms, NEGATIVE_PROMPT_RULES["shot_scope_upper"])
    elif shot == "half_body":
        _append_negative_terms(terms, NEGATIVE_PROMPT_RULES["shot_scope_half"])
    elif shot == "full_body":
        _append_negative_terms(terms, NEGATIVE_PROMPT_RULES["full_body_integrity"])
    if _text_has_any(source, ("脚下", "脚掌", "脚尖", "从头到脚", "全身")):
        _append_negative_terms(terms, ("cropped feet", "missing feet", "feet out of frame"))
    if _text_has_any(source, ("笑", "微笑", "大笑", "俏皮", "坏笑")):
        _append_negative_terms(terms, ("flat expression", "blank expression", "emotionless face"))
    if _text_has_any(source, ("泳池", "沙滩", "海边", "阳光", "晴空")):
        _append_negative_terms(terms, ("dark gloomy lighting", "night scene", "low-key dark room"))
    if scale == "normal":
        _append_negative_terms(terms, ("nudity", "lingerie", "transparent underwear"))
    if scale == "nsfw":
        _append_negative_terms(terms, NEGATIVE_PROMPT_RULES["nsfw_amateur_tone"])
    return ", ".join(terms)
