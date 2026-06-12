from __future__ import annotations

from prompt_constants import NEGATIVE_PROMPT_RULES
from prompt_data import NEGATIVE_PROMPT
from prompt_normalize import normalize_aspect, normalize_scale, normalize_shot
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
    scale = normalize_scale(scale)
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


CHINESE_NEGATIVE_PROMPT = (
    "低质量, 模糊, 解剖错误, 多余手指, 缺失手指, 脸部扭曲, 身体变形, 重复肢体, "
    "文字, 水印, 标志, 明确性行为, 暴露生殖器, 红色口红, 亮红嘴唇, 深红嘴唇, "
    "酒红嘴唇, 暗色口红, 黑色口红, 唇色过饱和, 染唇, 彩色口红, 明显口红, "
    "不自然唇色, 丰满嘴唇, 厚嘴唇, 唇线过度外扩, 过度丰唇, 肿胀嘴唇, 玻尿酸丰唇"
)

CHINESE_NEGATIVE_PROMPT_RULES = {
    "base_quality": (
        "低质量",
        "模糊",
        "解剖错误",
        "多余手指",
        "缺失手指",
        "脸部扭曲",
        "身体变形",
        "重复肢体",
        "文字",
        "水印",
        "标志",
    ),
    "lips_makeup": (
        "红色口红",
        "亮红嘴唇",
        "深红嘴唇",
        "酒红嘴唇",
        "暗色口红",
        "黑色口红",
        "唇色过饱和",
        "染唇",
        "彩色口红",
        "明显口红",
        "不自然唇色",
        "丰满嘴唇",
        "厚嘴唇",
        "唇线过度外扩",
        "过度丰唇",
        "肿胀嘴唇",
        "玻尿酸丰唇",
        "浓重烟熏妆",
        "亮片眼妆",
        "闪粉眼影",
        "金属眼影",
        "眼周水钻",
        "眼周贴钻",
        "眼皮亮片",
        "面部贴钻",
        "大笑露齿",
        "夸张笑容",
        "怪异笑容",
        "不自然笑容",
        "大面积红腮红",
        "脸部泛红过重",
    ),
    "canvas_padding": (
        "白边",
        "黑边",
        "空白侧边",
        "白色侧边条",
        "黑色侧边条",
        "暗色侧边条",
        "上下黑边",
        "左右黑边",
        "空白白色背景",
        "空白黑色背景",
        "白色填充",
        "黑色填充",
        "画布填充",
        "纯白侧边",
        "纯黑侧边",
        "竖图居中放在横向画布",
        "横向画布两侧空白",
    ),
    "landscape_mismatch": (
        "横向画布里的竖向裁切",
        "身体竖直居中但两侧空白",
        "宽画幅中的窄竖图",
        "左右两侧空白",
    ),
    "portrait_mismatch": (
        "竖向画面里的横向身体裁切",
        "竖向画面横构图",
        "缺头",
        "缺脚",
    ),
    "shot_scope_head": ("全身", "半身", "腿部", "脚部", "鞋子", "站姿", "坐姿"),
    "shot_scope_upper": ("腿部", "脚部", "鞋子", "全身", "下半身", "肚脐"),
    "shot_scope_half": ("脚部", "鞋子", "小腿", "全身"),
    "full_body_integrity": ("脚部裁切", "缺脚", "头部裁切", "缺头", "腿部截断", "腿短变形", "身体比例压缩"),
    "legal_safety": ("明确性行为", "暴露生殖器"),
    "nsfw_amateur_tone": ("业余摄影", "家庭录像感", "网络摄像头画质", "医疗光", "平光", "过曝", "发灰"),
}


def build_chinese_negative_prompt(
    positive_prompt: str = "",
    parts: dict[str, str] | None = None,
    scale: str = "bold",
    shot: str = "full_body",
    aspect: str = "portrait",
    width: int | None = None,
    height: int | None = None,
) -> str:
    parts = parts or {}
    scale = normalize_scale(scale)
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
    terms = [item.strip() for item in CHINESE_NEGATIVE_PROMPT.split(",") if item.strip()]
    _append_negative_terms(terms, CHINESE_NEGATIVE_PROMPT_RULES["base_quality"])
    _append_negative_terms(terms, CHINESE_NEGATIVE_PROMPT_RULES["lips_makeup"])
    _append_negative_terms(terms, CHINESE_NEGATIVE_PROMPT_RULES["canvas_padding"])
    _append_negative_terms(terms, CHINESE_NEGATIVE_PROMPT_RULES["legal_safety"])
    if aspect == "landscape" or _text_has_any(source, ("横向", "宽画幅", "沿画幅展开", "横幅")):
        _append_negative_terms(terms, CHINESE_NEGATIVE_PROMPT_RULES["landscape_mismatch"])
    if aspect == "portrait" or _text_has_any(source, ("竖向", "竖构图", "站姿", "站立")):
        _append_negative_terms(terms, CHINESE_NEGATIVE_PROMPT_RULES["portrait_mismatch"])
    if shot == "head_shot":
        _append_negative_terms(terms, CHINESE_NEGATIVE_PROMPT_RULES["shot_scope_head"])
    elif shot == "upper_body":
        _append_negative_terms(terms, CHINESE_NEGATIVE_PROMPT_RULES["shot_scope_upper"])
    elif shot == "half_body":
        _append_negative_terms(terms, CHINESE_NEGATIVE_PROMPT_RULES["shot_scope_half"])
    elif shot == "full_body":
        _append_negative_terms(terms, CHINESE_NEGATIVE_PROMPT_RULES["full_body_integrity"])
    if _text_has_any(source, ("脚下", "脚掌", "脚尖", "从头到脚", "全身")):
        _append_negative_terms(terms, ("脚部裁切", "缺脚", "脚在画面外"))
    if _text_has_any(source, ("笑", "微笑", "大笑", "俏皮", "坏笑")):
        _append_negative_terms(terms, ("表情呆板", "空洞表情", "面无表情"))
    if _text_has_any(source, ("泳池", "沙滩", "海边", "阳光", "晴空")):
        _append_negative_terms(terms, ("阴暗光线", "夜景", "低调暗房"))
    if scale == "normal":
        _append_negative_terms(terms, ("裸体", "内衣", "透明内衣"))
    if scale == "nsfw":
        _append_negative_terms(terms, CHINESE_NEGATIVE_PROMPT_RULES["nsfw_amateur_tone"])
    return ", ".join(terms)
