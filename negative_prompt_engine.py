from __future__ import annotations

from prompt_constants import NEGATIVE_PROMPT_RULES
from prompt_data import NEGATIVE_PROMPT
from prompt_normalize import normalize_aspect, normalize_scale, normalize_shot


def _text_has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers if marker)


def _append_negative_terms(terms: list[str], additions: tuple[str, ...]) -> None:
    existing = {term.strip().lower() for term in terms}
    for item in additions:
        value = str(item or "").strip()
        if value and value.lower() not in existing:
            terms.append(value)
            existing.add(value.lower())


def _drop_negative_terms(terms: list[str], removals: tuple[str, ...]) -> None:
    targets = {item.strip().lower() for item in removals}
    terms[:] = [term for term in terms if term.strip().lower() not in targets]


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
    "full_body_integrity": ("脚部裁切", "缺脚", "头部裁切", "缺头", "腿部截断", "腿短变形", "身体比例压缩", "黑色脚趾甲", "尖长脚趾甲", "长脚趾甲"),
    "legal_safety": ("明确性行为", "暴露生殖器"),
    "nsfw_amateur_tone": ("业余摄影", "家庭录像感", "网络摄像头画质", "医疗光", "平光", "过曝", "发灰"),
    "nsfw_male_face_out": ("男人脸部进入镜头", "男性脸部", "男人的脸", "男人的头部", "第二张脸", "两张脸"),
    "nsfw_face_pair_drop": ("第二张脸", "两张脸"),
    # 正面提示词点名要什么，负面词就不能压什么：双采工作流的 ZIB 阶段（1ST，cfg=4）负面词真正生效，
    # 冲突词条会直接压掉正面内容，所以在拼装末尾按正面文本剔除。
    "toothy_smile_drop": ("大笑露齿",),
    "missing_feet_drop": ("缺脚",),
    "flat_light_drop": ("平光",),
    "nsfw_head_drop": ("缺头", "头部裁切"),
    "nsfw_head_protect_woman": ("女人缺头", "女人头部裁切"),
}


# 英文与中文负面词共用一套拼装逻辑，只是词表不同。
_ENGLISH_EXTRAS = {
    "feet": ("cropped feet", "missing feet", "feet out of frame"),
    "smile": ("flat expression", "blank expression", "emotionless face"),
    "bright_scene": ("dark gloomy lighting", "night scene", "low-key dark room"),
    "normal_scale": ("nudity", "lingerie", "transparent underwear"),
    # 双人姿势按规则必须写两人贴身、交叠、缠绕的互动，所以这里不再压“fused bodies / merged limbs”：
    # 那两条会把写死的姿势压回两人分开。防畸形由“extra arms / duplicated limbs / bad anatomy”承担。
    "duo": ("third person", "extra people", "crowd", "extra arms"),
    # 四档双人是“两个女生 + 男人”：男人是画面里合法的第三个人，只保留人群压制。
    "duo_nsfw": ("crowd",),
}
_CHINESE_EXTRAS = {
    "feet": ("脚部裁切", "缺脚", "脚在画面外"),
    "smile": ("表情呆板", "空洞表情", "面无表情"),
    "bright_scene": ("阴暗光线", "夜景", "低调暗房"),
    "normal_scale": ("裸体", "内衣", "透明内衣"),
    # 双人姿势按规则必须写两人贴身、交叠、缠绕的互动，所以这里不再压“身体粘连 / 肢体融合”：
    # 那两条会把写死的姿势压回两人分开。防畸形由“多余手臂 / 重复肢体 / 解剖错误”承担。
    "duo": ("第三个人", "多余人物", "人群", "多余手臂"),
    "duo_nsfw": ("人群",),
}


def _compose_negative_prompt(base_text, rules, extras, positive_prompt, parts, scale, shot, aspect, width, height) -> str:
    parts = parts or {}
    scale = normalize_scale(scale)
    shot = normalize_shot(shot)
    aspect = normalize_aspect(aspect, width, height)
    source = "，".join(str(value or "") for value in (positive_prompt, parts.get("camera"), parts.get("pose_expression"), parts.get("scene_light")))
    terms = [item.strip() for item in str(base_text or "").split(",") if item.strip()]
    if scale == "nsfw":
        legal_terms = {item.strip().lower() for item in rules["legal_safety"]}
        terms = [item for item in terms if item.lower() not in legal_terms]
    for key in ("base_quality", "lips_makeup", "canvas_padding"):
        _append_negative_terms(terms, rules[key])
    if scale != "nsfw":
        _append_negative_terms(terms, rules["legal_safety"])
    if aspect == "landscape" or _text_has_any(source, ("横向", "宽画幅", "沿画幅展开", "横幅")):
        _append_negative_terms(terms, rules["landscape_mismatch"])
    if aspect == "portrait" or _text_has_any(source, ("竖向", "竖构图", "站姿", "站立")):
        _append_negative_terms(terms, rules["portrait_mismatch"])
    if shot == "head_shot":
        _append_negative_terms(terms, rules["shot_scope_head"])
    elif shot == "half_body":
        _append_negative_terms(terms, rules["shot_scope_half"])
    elif shot == "full_body":
        _append_negative_terms(terms, rules["full_body_integrity"])
    if _text_has_any(source, ("脚下", "脚掌", "脚尖", "从头到脚", "全身")):
        _append_negative_terms(terms, extras["feet"])
    if _text_has_any(source, ("笑", "微笑", "大笑", "俏皮", "坏笑")):
        _append_negative_terms(terms, extras["smile"])
    if scale == "normal" and _text_has_any(source, ("泳池", "沙滩", "海边", "阳光", "晴空")):
        _append_negative_terms(terms, extras["bright_scene"])
    if scale == "normal":
        _append_negative_terms(terms, extras["normal_scale"])
    duo = parts.get("cast") == "duo"
    if duo:
        # 四档双人画面里男人是合法存在的，用不含“第三人/多余人物/多余手臂”的一组负面词。
        _append_negative_terms(terms, extras["duo_nsfw"] if scale == "nsfw" else extras["duo"])
    if scale == "nsfw":
        _append_negative_terms(terms, rules["nsfw_amateur_tone"])
        _append_negative_terms(terms, rules["nsfw_male_face_out"])
        if duo:
            # 四档双人有两个女生，两张脸都该入镜，剔除会连第二个女生一起压掉的写法。
            _drop_negative_terms(terms, rules["nsfw_face_pair_drop"])
        # 四档里男人的头部本来就该在画外，通用的“缺头/头部裁切”会反过来压制这一点，
        # 所以换成只保护女人头部的定向写法，避免两条规则互相抵消。
        _drop_negative_terms(terms, rules["nsfw_head_drop"])
        _append_negative_terms(terms, rules["nsfw_head_protect_woman"])
    # 正面与负面不能互相打架：双采工作流的 ZIB 阶段（1ST，cfg=4）负面词真正生效，
    # 下面几组词条会直接压掉正面明确要求的内容，按正面文本剔除。
    if _text_has_any(source, ("露齿", "牙齿", "门牙", "笑出声", "大笑")):
        # 正面要露齿的笑，就不能同时压“大笑露齿/露齿微笑”。
        _drop_negative_terms(terms, rules["toothy_smile_drop"])
    if shot != "full_body":
        # 头部/半身镜头里没有脚，“缺脚”会和同一条负面词里的“脚部/鞋子”自相矛盾。
        _drop_negative_terms(terms, rules["missing_feet_drop"])
    if _text_has_any(source, ("柔光", "散射", "柔和的光", "柔和而均匀", "均匀地包住")):
        # 正面要柔光/散射光，就不能同时压“平光”。
        _drop_negative_terms(terms, rules["flat_light_drop"])
    return ", ".join(terms)


def build_negative_prompt(positive_prompt="", parts=None, scale="bold", shot="full_body", aspect="portrait", width=None, height=None) -> str:
    return _compose_negative_prompt(NEGATIVE_PROMPT, NEGATIVE_PROMPT_RULES, _ENGLISH_EXTRAS, positive_prompt, parts, scale, shot, aspect, width, height)


def build_chinese_negative_prompt(positive_prompt="", parts=None, scale="bold", shot="full_body", aspect="portrait", width=None, height=None) -> str:
    return _compose_negative_prompt(CHINESE_NEGATIVE_PROMPT, CHINESE_NEGATIVE_PROMPT_RULES, _CHINESE_EXTRAS, positive_prompt, parts, scale, shot, aspect, width, height)
