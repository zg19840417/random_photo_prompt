from __future__ import annotations

import argparse
import importlib.util
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_PATH = ROOT / "docs" / "reports" / "generated_prompt_audit.md"

SCALES = ("normal", "bold", "nsfw")
SHOTS = ("head_shot", "upper_body", "half_body", "large_half_body", "full_body")
SHOT_INPUTS = {
    "head_shot": "头部",
    "upper_body": "上半身",
    "half_body": "半身",
    "large_half_body": "大半身",
    "full_body": "全身",
}

EXPECTED_DIMENSIONS = {
    "normal": ("camera", "character", "makeup", "outfit", "pose_expression", "scene_light"),
    "bold": ("camera", "character", "makeup", "outfit", "pose_expression", "scene_light"),
    "nsfw": ("camera", "character", "makeup", "pose_expression", "scene_light"),
}

DIMENSION_LABELS = {
    "camera": "镜头",
    "character": "角色容貌和身材",
    "makeup": "妆容",
    "outfit": "穿着",
    "pose_expression": "姿势和神情",
    "scene_light": "场景和光线",
    "quality": "固定提示词",
}

CLAUSE_SPLIT_RE = re.compile(r"[。；;，,、\n]+")
CHINESE_PHRASE_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{4,}")

COMMON_REPEAT_FRAGMENTS = {
    "脸部",
    "镜头",
    "眼睛",
    "嘴唇",
    "黑发",
    "冷白",
    "高光",
    "线条",
    "边缘",
    "形成",
    "完整",
    "清晰",
    "画面",
    "人物",
    "韩国女性",
    "真实写真",
    "电影感光影",
    "bestquality",
    "ultradetailed",
}

POSE_CAMERA_OWNERSHIP_TERMS = (
    "横屏",
    "竖屏",
    "横构图",
    "竖构图",
    "横向构图",
    "竖向构图",
    "镜头拉开",
    "镜头垂直",
    "完整身高",
    "构图留白",
)

LYING_POSE_TERMS = ("仰躺", "侧躺", "横躺", "平躺", "躺在", "床面", "顶视角", "俯拍")
UPRIGHT_CAMERA_TERMS = ("竖构图", "窄长", "站立", "从头顶到脚掌", "小腿、脚踝", "脚下")
PORTRAIT_ORIENTATION_TERMS = ("竖构图", "窄长", "竖屏")
LANDSCAPE_ORIENTATION_TERMS = ("横屏", "横向", "横构图")
HORIZONTAL_BODY_TERMS = (
    "横向", "宽画幅", "横躺", "侧躺", "平躺", "仰躺", "斜向仰躺", "横向靠", "横向坐", "横向趴",
    "横向倚", "横向后", "横跨", "侧躺式", "沿画面宽度", "沿宽画幅", "向一侧延伸", "斜向铺",
)
VERTICAL_BODY_TERMS = (
    "竖向", "站立", "自然站立", "直立", "坐立", "跪坐", "竖向坐", "竖向跪", "从头顶到脚掌",
    "从上到下", "纵向", "挺直", "竖构图",
)

MOBILE_RESOLUTION_RULES = {
    "full_body": (
        (("大字", "四肢展开", "双臂自然向两侧展开", "手脚乱舞", "跳", "跃起", "腾空"), {"aspect": "landscape", "framing": "横向全身动态宽构图，四肢外轮廓完整，四周留白"}),
        (("俯拍", "顶视角", "正上方", "仰躺", "躺", "侧躺", "横躺", "床中央", "睡", "睡着"), {"aspect": "landscape", "framing": "横向全身构图，身体沿宽画幅展开，从头到脚完整入镜"}),
        (("坐", "坐姿", "跪", "跪姿", "膝", "蹲", "蜷", "抱膝", "直立", "站", "站立", "竖向", "纵向"), {"aspect": "portrait", "framing": "竖向全身构图，头部、手臂、腿部、脚部和姿势外轮廓完整"}),
        (("站", "站立", "倚靠", "靠墙", "迈步", "走", "单腿", "重心", "伸直", "脚尖", "脚掌"), {"aspect": "portrait", "framing": "窄长全身构图，从头顶到脚掌完整入镜，脚下留地面边距"}),
    ),
    "half_body": (
        (("横躺", "侧躺", "仰躺", "平躺", "俯拍", "顶视角", "床", "横向", "横跨", "横向靠", "横向坐", "横向趴", "沿宽画幅", "斜向铺"), {"aspect": "landscape", "framing": "横向半身镜头，腰部及以上入镜，头部、肩颈、胸部和腰部完整"}),
        (("坐", "坐姿", "跪", "跪坐", "膝", "直立", "站", "站立", "竖向", "纵向"), {"aspect": "portrait", "framing": "竖向半身镜头，腰部及以上入镜，头部、胸腰和双手完整"}),
    ),
    "large_half_body": (
        (("横躺", "侧躺", "仰躺", "平躺", "俯拍", "顶视角", "床", "横向", "横跨", "横向靠", "横向坐", "横向趴", "沿宽画幅", "斜向铺"), {"aspect": "landscape", "framing": "横向大半身镜头，小腿及以上入镜，身体沿宽画幅展开到小腿"}),
        (("坐", "坐姿", "跪", "跪坐", "膝", "直立", "站", "站立", "竖向", "纵向"), {"aspect": "portrait", "framing": "竖向大半身镜头，小腿及以上入镜，头部到小腿完整"}),
    ),
    "upper_body": (
        (("横向", "侧脸", "躺", "侧躺"), {"aspect": "landscape", "framing": "横向上半身镜头，胸部及以上入镜，头顶完整"}),
    ),
    "head_shot": (
        (("横向", "侧脸", "躺", "侧躺"), {"aspect": "landscape", "framing": "横向头部镜头，肩膀及以上入镜，头顶完整"}),
    ),
}

MOBILE_DEFAULT_RESOLUTIONS = {
    "full_body": {"aspect": "portrait", "framing": "竖向全身构图，从头到脚完整入镜，姿势外轮廓完整"},
    "large_half_body": {"aspect": "portrait", "framing": "竖向大半身镜头，小腿及以上入镜，头部、脸部、肩颈、胸部、腰部、臀部、大腿、膝盖和小腿完整入镜"},
    "half_body": {"aspect": "portrait", "framing": "竖向半身镜头，腰部及以上入镜，头部、胸腰和双手完整"},
    "upper_body": {"aspect": "portrait", "framing": "上半身镜头，胸部及以上入镜，头顶完整，画面停在上腰"},
    "head_shot": {"aspect": "portrait", "framing": "头部镜头，肩膀及以上入镜，头顶完整"},
}


MOBILE_DIRECTOR_RESOLUTION_RULES = {
    "minimal_gallery_bodyline": {
        "full_body": {"aspect": "portrait", "framing": "竖向全身留白构图，从头到脚完整入镜，脚下留地面边距"},
        "large_half_body": {"aspect": "portrait", "framing": "竖向大半身留白构图，小腿及以上入镜，身体线条完整"},
        "half_body": {"aspect": "portrait", "framing": "竖向半身留白构图，腰部及以上入镜，头部和胸腰完整"},
        "upper_body": {"aspect": "portrait", "framing": "竖向上半身极简构图，胸部及以上入镜，头顶完整"},
        "head_shot": {"aspect": "portrait", "framing": "竖向头部极简构图，肩膀及以上入镜，头顶完整"},
    },
    "nightclub_queen": {
        "full_body": {"aspect": "portrait", "framing": "竖向全身舞台构图，从头到脚完整入镜，脚下地面边距清楚"},
        "large_half_body": {"aspect": "portrait", "framing": "竖向大半身压迫构图，小腿及以上入镜，头部到小腿完整"},
        "half_body": {"aspect": "portrait", "framing": "竖向半身压迫构图，腰部及以上入镜，脸部和胸腰清楚"},
        "upper_body": {"aspect": "portrait", "framing": "竖向上半身压迫近景，胸部及以上入镜，头顶完整"},
        "head_shot": {"aspect": "portrait", "framing": "竖向头部压迫近景，肩膀及以上入镜，头顶完整"},
    },
    "soft_private_room": {
        "full_body": {"aspect": "landscape", "framing": "横向全身私房构图，身体沿宽画幅展开，从头到脚完整入镜"},
        "large_half_body": {"aspect": "landscape", "framing": "横向大半身私房构图，小腿及以上入镜，身体沿宽画幅展开"},
        "half_body": {"aspect": "landscape", "framing": "横向半身私房构图，腰部及以上入镜，头部和胸腰完整"},
        "upper_body": {"aspect": "portrait", "framing": "竖向上半身柔光近景，胸部及以上入镜，头顶完整"},
    },
    "mirror_private_space": {
        "full_body": {"aspect": "portrait", "framing": "竖向全身镜面构图，从头到脚完整入镜，脚下留地面边距"},
        "large_half_body": {"aspect": "portrait", "framing": "竖向大半身镜面构图，小腿及以上入镜，反射空间保留"},
        "half_body": {"aspect": "portrait", "framing": "竖向半身镜面构图，腰部及以上入镜，头部和胸腰完整"},
        "upper_body": {"aspect": "portrait", "framing": "竖向上半身镜面近景，胸部及以上入镜，头顶完整"},
    },
    "wet_film_mood": {
        "full_body": {"aspect": "landscape", "framing": "横向全身湿感构图，身体沿宽画幅展开，从头到脚完整入镜"},
        "large_half_body": {"aspect": "landscape", "framing": "横向大半身湿感构图，小腿及以上入镜，留出环境反光"},
        "half_body": {"aspect": "landscape", "framing": "横向半身湿感构图，腰部及以上入镜，留出环境反光"},
        "upper_body": {"aspect": "portrait", "framing": "竖向上半身湿感近景，胸部及以上入镜，头顶完整"},
    },
    "wild_natural_sensuality": {
        "full_body": {"aspect": "landscape", "framing": "横向全身自然环境构图，从头到脚完整入镜，四周留环境空间"},
        "large_half_body": {"aspect": "landscape", "framing": "横向大半身自然环境构图，小腿及以上入镜，四周留环境空间"},
        "half_body": {"aspect": "landscape", "framing": "横向半身自然环境构图，腰部及以上入镜，保留环境空间"},
    },
}
MOBILE_FRAMING_COMPACT_REPLACEMENTS = {
    "妯悜鍏ㄨ韩鍔ㄦ€佸鏋勫浘锛屽洓鑲㈠杞粨瀹屾暣锛屽洓鍛ㄧ暀鐧?": "横向动态宽构图，四周留白",
    "妯悜鍏ㄨ韩鏋勫浘锛岃韩浣撴部瀹界敾骞呭睍寮€锛屼粠澶村埌鑴氬畬鏁村叆闀?": "横向宽构图，身体沿画幅展开",
    "绔栧悜鍏ㄨ韩鏋勫浘锛屽ご閮ㄣ€佹墜鑷傘€佽吙閮ㄣ€佽剼閮ㄥ拰濮垮娍澶栬疆寤撳畬鏁?": "竖向全身构图，外轮廓完整",
    "绐勯暱鍏ㄨ韩鏋勫浘锛屼粠澶撮《鍒拌剼鎺屽畬鏁村叆闀滐紝鑴氫笅鐣欏湴闈㈣竟璺?": "窄长全身构图，脚下留地面边距",
    "妯悜鍗婅韩闀滃ご锛岃叞閮ㄥ強浠ヤ笂鍏ラ暅锛屽ご閮ㄣ€佽偐棰堛€佽兏閮ㄥ拰鑵伴儴瀹屾暣": "横向半身构图，腰部以上完整",
    "绔栧悜鍗婅韩闀滃ご锛岃叞閮ㄥ強浠ヤ笂鍏ラ暅锛屽ご閮ㄣ€佽兏鑵板拰鍙屾墜瀹屾暣": "竖向半身构图，胸腰和双手完整",
    "妯悜澶у崐韬暅澶达紝灏忚吙鍙婁互涓婂叆闀滐紝韬綋娌垮鐢诲箙灞曞紑鍒板皬鑵?": "横向大半身构图，身体沿宽画幅展开",
    "绔栧悜澶у崐韬暅澶达紝灏忚吙鍙婁互涓婂叆闀滐紝澶撮儴鍒板皬鑵垮畬鏁?": "竖向大半身构图，头部到小腿完整",
    "妯悜涓婂崐韬暅澶达紝鑳搁儴鍙婁互涓婂叆闀滐紝澶撮《瀹屾暣": "横向上半身构图，头顶完整",
    "妯悜澶撮儴闀滃ご锛岃偐鑶€鍙婁互涓婂叆闀滐紝澶撮《瀹屾暣": "横向头部构图，头顶完整",
    "绔栧悜鍏ㄨ韩鏋勫浘锛屼粠澶村埌鑴氬畬鏁村叆闀滐紝濮垮娍澶栬疆寤撳畬鏁?": "竖向全身构图，外轮廓完整",
    "涓婂崐韬暅澶达紝鑳搁儴鍙婁互涓婂叆闀滐紝澶撮《瀹屾暣锛岀敾闈㈠仠鍦ㄤ笂鑵?": "竖向上半身构图，头顶完整",
    "澶撮儴闀滃ご锛岃偐鑶€鍙婁互涓婂叆闀滐紝澶撮《瀹屾暣": "竖向头部构图，头顶完整",
}


@dataclass
class Finding:
    severity: str
    scale: str
    shot: str
    aspect: str
    sample: int
    rule: str
    detail: str
    prompt: str


@dataclass
class PromptStats:
    scale: str
    shot: str
    aspect: str
    sample: int
    prompt_length: int
    dimension_lengths: dict[str, int]
    concept_counts: dict[str, int]
    prompt: str


CONCEPT_GROUPS = {
    "skin_whiteness": ("冷白", "白皙", "瓷白", "通透", "白净", "显白", "白皮", "冷瓷", "porcelain"),
    "gaze_pressure": ("直视", "凝视", "看向镜头", "盯", "眼神", "视线", "压迫", "挑衅", "藐视", "审视"),
    "lips": ("嘴唇", "薄唇", "唇", "唇形", "唇面", "嘴角"),
    "chest_focus": ("胸部", "完整胸部", "胸线", "胸腰", "胸前", "胸口", "上胸", "胸"),
    "waist_focus": ("腰线", "细腰", "腰部", "腰", "小蛮腰"),
    "leg_focus": ("长腿", "腿部", "腿线", "大腿", "小腿", "膝盖", "脚部", "脚下", "脚尖", "脚跟"),
    "glamour_tone": ("glamour", "成人", "私房", "情欲", "性感", "诱惑", "撩人", "冷艳", "高级", "张力"),
    "light_highlight": ("高光", "柔光", "光泽", "反光", "提亮", "照亮", "明暗", "暗部", "阴影", "层次"),
    "body_curve": ("曲线", "轮廓", "线条", "身形", "身材", "外轮廓"),
}

MAX_POSITIVE_PROMPT_LENGTH = 800
PROMPT_LENGTH_BUDGETS = {
    "head_shot": MAX_POSITIVE_PROMPT_LENGTH,
    "upper_body": MAX_POSITIVE_PROMPT_LENGTH,
    "half_body": MAX_POSITIVE_PROMPT_LENGTH,
    "large_half_body": MAX_POSITIVE_PROMPT_LENGTH,
    "full_body": MAX_POSITIVE_PROMPT_LENGTH,
}

DIMENSION_LENGTH_BUDGETS = {
    "camera": 90,
    "character": 130,
    "makeup": 90,
    "outfit": 100,
    "pose_expression": 130,
    "scene_light": 110,
    "quality": 80,
}
PROMPT_PART_ORDER = ("camera", "character", "makeup", "outfit", "pose_expression", "scene_light", "quality")


def load_prompt_engine():
    path = ROOT / "prompt_engine.py"
    spec = importlib.util.spec_from_file_location("generated_prompt_engine", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_runtime_builder():
    path = ROOT / "__init__.py"
    spec = importlib.util.spec_from_file_location("random_photo_prompt_runtime_audit", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    return getattr(module, "_build_mobile_prompt_for_scope", None)


def normalize_text(text: str) -> str:
    return re.sub(r"[\s，。；;、：:\-_/（）()\"'""''']+", "", text)


def split_clauses(text: str) -> list[str]:
    return [part.strip() for part in CLAUSE_SPLIT_RE.split(text) if len(part.strip()) >= 4]


def uncommon_phrases(text: str) -> set[str]:
    phrases: set[str] = set()
    for match in CHINESE_PHRASE_RE.findall(normalize_text(text)):
        if len(match) < 5:
            continue
        if any(common in match for common in COMMON_REPEAT_FRAGMENTS):
            continue
        for size in (5, 6, 7, 8):
            if len(match) >= size:
                phrases.update(match[index:index + size] for index in range(0, len(match) - size + 1))
    return phrases


def percentile(values: list[int], percent: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    return ordered[round((len(ordered) - 1) * percent)]


def concept_counts(text: str) -> dict[str, int]:
    return {
        name: sum(text.count(marker) for marker in markers)
        for name, markers in CONCEPT_GROUPS.items()
    }


def stats_for_item(scale: str, shot: str, aspect: str, sample: int, item: dict) -> PromptStats:
    parts = item["dimension_parts"]
    prompt = item["positive_prompt"]
    return PromptStats(
        scale=scale,
        shot=shot,
        aspect=aspect,
        sample=sample,
        prompt_length=len(prompt),
        dimension_lengths={name: len(value) for name, value in parts.items() if value and name in DIMENSION_LABELS},
        concept_counts=concept_counts(prompt),
        prompt=prompt,
    )


def missing_dimensions(scale: str, parts: dict[str, str]) -> list[str]:
    expected = EXPECTED_DIMENSIONS[scale]
    missing = [name for name in expected if not parts.get(name, "").strip()]
    if scale == "nsfw" and parts.get("outfit", "").strip():
        missing.append("nsfw_outfit_should_be_empty")
    return missing


def mobile_prompt_text_for_resolution(parts: dict[str, str]) -> str:
    return "，".join(
        str(parts.get(name, ""))
        for name in ("camera", "pose_expression", "scene_light")
        if parts.get(name)
    )


def mobile_resolution_for_parts(parts: dict[str, str], shot: str) -> dict[str, str]:
    text = mobile_prompt_text_for_resolution(parts)
    for markers, resolution in MOBILE_RESOLUTION_RULES.get(shot, ()):
        if any(marker in text for marker in markers):
            return resolution
    director = str(parts.get("director") or "")
    director_resolution = MOBILE_DIRECTOR_RESOLUTION_RULES.get(director, {}).get(shot)
    if director_resolution:
        return director_resolution
    return MOBILE_DEFAULT_RESOLUTIONS[shot]


def prompt_from_parts(parts: dict[str, str]) -> str:
    return "\n".join(ensure_sentence(parts.get(name, "")) for name in PROMPT_PART_ORDER if parts.get(name))


def prompt_len_from_parts(parts: dict[str, str]) -> int:
    return len(prompt_from_parts(parts))


def prompt_clauses(text: str) -> list[str]:
    return [part.strip("，。 \n\t") for part in str(text or "").replace("；", "，").split("，") if part.strip("，。 \n\t")]


def enforce_prompt_length(parts: dict[str, str], max_length: int = MAX_POSITIVE_PROMPT_LENGTH) -> dict[str, str]:
    compacted = dict(parts or {})
    if prompt_len_from_parts(compacted) <= max_length:
        return compacted
    compacted["quality"] = ""
    if prompt_len_from_parts(compacted) <= max_length:
        return compacted
    for name in ("scene_light", "outfit", "pose_expression", "makeup", "camera"):
        clauses = prompt_clauses(compacted.get(name, ""))
        while len(clauses) > 1 and prompt_len_from_parts(compacted) > max_length:
            clauses.pop()
            compacted[name] = "，".join(clauses)
        if prompt_len_from_parts(compacted) <= max_length:
            break
    return compacted


def apply_mobile_framing(item: dict, resolution: dict[str, str]) -> dict:
    framing = resolution.get("framing")
    if not framing:
        return item
    parts = dict(item.get("dimension_parts") or {})
    camera = str(parts.get("camera") or "")
    if any(marker in camera for marker in ("入镜", "镜头", "构图", "画面", "头顶", "完整")):
        framing = MOBILE_FRAMING_COMPACT_REPLACEMENTS.get(framing, framing)
    if framing not in camera:
        parts["camera"] = f"{camera}，{framing}" if camera else framing
    parts = enforce_prompt_length(parts)
    rebuilt = dict(item)
    rebuilt["dimension_parts"] = parts
    rebuilt["positive_prompt"] = prompt_from_parts(parts)
    rebuilt["compact_prompt"] = rebuilt["positive_prompt"]
    return rebuilt


def ensure_sentence(text: str) -> str:
    text = str(text or "").strip("，。 \n\t")
    return f"{text}。" if text else ""


def duplicate_findings(scale: str, shot: str, aspect: str, sample: int, prompt: str, parts: dict[str, str]) -> list[Finding]:
    findings: list[Finding] = []
    clause_counter = Counter(normalize_text(clause) for clause in split_clauses(prompt))
    repeated_clauses = [clause for clause, count in clause_counter.items() if count > 1 and len(clause) >= 6]
    if repeated_clauses:
        findings.append(Finding("warning", scale, shot, aspect, sample, "obvious_repeated_clause", "、".join(repeated_clauses[:5]), prompt))

    part_values = [(name, normalize_text(value)) for name, value in parts.items() if value]
    for left_index, (left_name, left_value) in enumerate(part_values):
        for right_name, right_value in part_values[left_index + 1:]:
            if left_value and left_value == right_value:
                detail = f"{DIMENSION_LABELS.get(left_name, left_name)} == {DIMENSION_LABELS.get(right_name, right_name)}"
                findings.append(Finding("warning", scale, shot, aspect, sample, "identical_dimension_text", detail, prompt))

    phrase_owners: dict[str, set[str]] = {}
    for name, value in parts.items():
        if not value:
            continue
        for phrase in uncommon_phrases(value):
            phrase_owners.setdefault(phrase, set()).add(name)
    repeated_phrases = sorted(phrase for phrase, owners in phrase_owners.items() if len(owners) >= 2)
    if repeated_phrases:
        findings.append(Finding("info", scale, shot, aspect, sample, "repeated_descriptive_phrase", "、".join(repeated_phrases[:8]), prompt))
    return findings


def contradiction_findings(scale: str, shot: str, aspect: str, sample: int, prompt: str, parts: dict[str, str]) -> list[Finding]:
    findings: list[Finding] = []

    if scale == "nsfw" and parts.get("outfit", "").strip():
        findings.append(Finding("error", scale, shot, aspect, sample, "nsfw_outfit_leak", "NSFW final prompt should not include outfit dimension", prompt))

    camera = parts.get("camera", "")
    if shot == "head_shot" and not ("头部" in camera or "肩膀及以上" in camera or "肩部以上" in camera):
        findings.append(Finding("warning", scale, shot, aspect, sample, "camera_sentence_mismatch", camera, prompt))
    if shot == "upper_body" and not ("上半身" in camera or "胸部及以上" in camera or "完整胸部" in camera):
        findings.append(Finding("warning", scale, shot, aspect, sample, "camera_sentence_mismatch", camera, prompt))
    if shot == "half_body" and not ("半身" in camera and ("腰部" in camera or "腰线" in camera)):
        findings.append(Finding("warning", scale, shot, aspect, sample, "camera_sentence_mismatch", camera, prompt))
    if shot == "large_half_body" and not ("大半身" in camera or "小腿及以上" in camera or "小腿" in camera):
        findings.append(Finding("warning", scale, shot, aspect, sample, "camera_sentence_mismatch", camera, prompt))
    if shot == "full_body" and "全身" not in camera:
        findings.append(Finding("warning", scale, shot, aspect, sample, "camera_sentence_mismatch", camera, prompt))

    pose = parts.get("pose_expression", "")
    if any(term in pose for term in POSE_CAMERA_OWNERSHIP_TERMS):
        detail = "pose owns camera/resolution wording: " + "、".join(term for term in POSE_CAMERA_OWNERSHIP_TERMS if term in pose)
        findings.append(Finding("warning", scale, shot, aspect, sample, "pose_camera_ownership", detail, prompt))

    if shot == "full_body" and any(term in pose for term in LYING_POSE_TERMS) and any(term in camera for term in UPRIGHT_CAMERA_TERMS):
        detail = "upright full-body camera combined with lying/top-down pose"
        findings.append(Finding("warning", scale, shot, aspect, sample, "camera_pose_direction_conflict", detail, prompt))

    if any(term in camera for term in PORTRAIT_ORIENTATION_TERMS) and any(term in pose for term in LANDSCAPE_ORIENTATION_TERMS):
        detail = "portrait camera wording combined with landscape pose wording"
        findings.append(Finding("warning", scale, shot, aspect, sample, "camera_pose_direction_conflict", detail, prompt))

    if any(term in camera for term in LANDSCAPE_ORIENTATION_TERMS) and any(term in pose for term in PORTRAIT_ORIENTATION_TERMS):
        detail = "landscape camera wording combined with portrait pose wording"
        findings.append(Finding("warning", scale, shot, aspect, sample, "camera_pose_direction_conflict", detail, prompt))
    if shot in {"half_body", "large_half_body", "full_body"} and aspect == "portrait" and any(term in pose for term in HORIZONTAL_BODY_TERMS):
        detail = "portrait frame combined with horizontal body-axis pose"
        findings.append(Finding("warning", scale, shot, aspect, sample, "frame_body_axis_conflict", detail, prompt))
    if shot in {"half_body", "large_half_body", "full_body"} and aspect == "landscape" and any(term in pose for term in VERTICAL_BODY_TERMS) and not any(term in pose for term in HORIZONTAL_BODY_TERMS):
        detail = "landscape frame combined with vertical body-axis pose"
        findings.append(Finding("warning", scale, shot, aspect, sample, "frame_body_axis_conflict", detail, prompt))
    return findings


def audit_item(scale: str, shot: str, aspect: str, sample: int, item: dict) -> list[Finding]:
    prompt = item["positive_prompt"]
    parts = item["dimension_parts"]
    findings: list[Finding] = []

    missing = missing_dimensions(scale, parts)
    if missing:
        labels = [DIMENSION_LABELS.get(name, name) for name in missing]
        findings.append(Finding("error", scale, shot, aspect, sample, "missing_or_unexpected_dimension", "、".join(labels), prompt))

    findings.extend(duplicate_findings(scale, shot, aspect, sample, prompt, parts))
    findings.extend(contradiction_findings(scale, shot, aspect, sample, prompt, parts))
    budget = PROMPT_LENGTH_BUDGETS.get(shot)
    if budget and len(prompt) > budget:
        findings.append(Finding("error", scale, shot, aspect, sample, "prompt_length_over_budget", f"{len(prompt)} > {budget}", prompt))
    for name, value in parts.items():
        if name not in DIMENSION_LABELS:
            continue
        part_budget = DIMENSION_LENGTH_BUDGETS.get(name)
        if value and part_budget and len(value) > part_budget:
            label = DIMENSION_LABELS.get(name, name)
            findings.append(Finding("info", scale, shot, aspect, sample, "dimension_length_over_budget", f"{label}: {len(value)} > {part_budget}", prompt))
    repeated_concepts = [
        f"{name}={count}"
        for name, count in concept_counts(prompt).items()
        if count >= 4
    ]
    if repeated_concepts:
        findings.append(Finding("info", scale, shot, aspect, sample, "concept_repetition", " | ".join(repeated_concepts), prompt))
    return findings


def selected_values(values: list[str] | None, allowed: tuple[str, ...]) -> tuple[str, ...]:
    if not values:
        return allowed
    invalid = [value for value in values if value not in allowed]
    if invalid:
        raise ValueError(f"Invalid value(s): {', '.join(invalid)}. Allowed: {', '.join(allowed)}")
    return tuple(values)


def run_audit(samples: int, scales: tuple[str, ...], shots: tuple[str, ...]) -> tuple[list[Finding], dict[tuple[str, str, str], int], list[PromptStats]]:
    engine = load_prompt_engine()
    findings: list[Finding] = []
    stats: list[PromptStats] = []
    sample_counts: dict[tuple[str, str, str], int] = {}
    for scale in scales:
        for shot in shots:
            for aspect in ("portrait", "landscape"):
                items = []
                for index in range(samples):
                    initial = engine.generate_prompt_items(
                        1,
                        {"scale": scale, "shot": SHOT_INPUTS[shot], "aspect": aspect},
                        seed_text=f"generated-audit-{scale}-{shot}-{aspect}-{samples}-{index}",
                    )[0]
                    resolution = mobile_resolution_for_parts(initial["dimension_parts"], shot)
                    resolved_aspect = resolution["aspect"]
                    if resolved_aspect != aspect and any(
                        term in mobile_prompt_text_for_resolution(initial["dimension_parts"])
                        for term in HORIZONTAL_BODY_TERMS + VERTICAL_BODY_TERMS
                    ):
                        initial = engine.generate_prompt_items(
                            1,
                            {"scale": scale, "shot": SHOT_INPUTS[shot], "aspect": resolved_aspect},
                            seed_text=f"generated-audit-{scale}-{shot}-{aspect}-{samples}-{index}-{resolved_aspect}",
                        )[0]
                        resolution = mobile_resolution_for_parts(initial["dimension_parts"], shot)
                    items.append((resolved_aspect, apply_mobile_framing(initial, resolution)))
                for resolved_aspect, _item in items:
                    sample_counts[(scale, shot, resolved_aspect)] = sample_counts.get((scale, shot, resolved_aspect), 0) + 1
                for index, (resolved_aspect, item) in enumerate(items, 1):
                    findings.extend(audit_item(scale, shot, resolved_aspect, index, item))
                    stats.append(stats_for_item(scale, shot, resolved_aspect, index, item))
    return findings, sample_counts, stats


def length_repetition_report(stats: list[PromptStats]) -> list[str]:
    lines = ["## Length And Repetition", ""]
    if not stats:
        lines.extend(["No prompt stats collected.", ""])
        return lines

    by_scope: dict[tuple[str, str, str], list[PromptStats]] = {}
    for item in stats:
        by_scope.setdefault((item.scale, item.shot, item.aspect), []).append(item)

    lines.extend(["### Prompt Length By Scale / Shot / Aspect", ""])
    for (scale, shot, aspect), items in sorted(by_scope.items()):
        values = [item.prompt_length for item in items]
        lines.append(f"- `{scale}` / `{shot}` / `{aspect}`: median {percentile(values, 0.5)}, p90 {percentile(values, 0.9)}, max {max(values)}")
    lines.append("")

    dimension_totals: dict[str, list[int]] = {}
    for item in stats:
        for name, length in item.dimension_lengths.items():
            dimension_totals.setdefault(name, []).append(length)
    lines.extend(["### Dimension Length Hotspots", ""])
    for name, values in sorted(dimension_totals.items(), key=lambda pair: percentile(pair[1], 0.9), reverse=True):
        label = DIMENSION_LABELS.get(name, name)
        lines.append(f"- `{label}`: median {percentile(values, 0.5)}, p90 {percentile(values, 0.9)}, max {max(values)}")
    lines.append("")

    concept_totals: Counter[str] = Counter()
    concept_repeat_samples: dict[str, list[PromptStats]] = {}
    for item in stats:
        for concept, count in item.concept_counts.items():
            concept_totals[concept] += count
            if count >= 4:
                concept_repeat_samples.setdefault(concept, []).append(item)
    lines.extend(["### Concept Repetition Totals", ""])
    for concept, count in concept_totals.most_common():
        if count:
            lines.append(f"- `{concept}`: {count}")
    lines.append("")

    lines.extend(["### Longest Generated Prompts", ""])
    for item in sorted(stats, key=lambda stat: stat.prompt_length, reverse=True)[:12]:
        prompt = item.prompt.replace("\n", " ")
        if len(prompt) > 300:
            prompt = prompt[:297] + "..."
        longest_dimensions = sorted(item.dimension_lengths.items(), key=lambda pair: pair[1], reverse=True)[:3]
        dimension_text = ", ".join(f"{DIMENSION_LABELS.get(name, name)}={length}" for name, length in longest_dimensions)
        lines.append(f"- `{item.scale}` / `{item.shot}` / `{item.aspect}` sample {item.sample}: {item.prompt_length} chars; {dimension_text}")
        lines.append(f"  - {prompt}")
    lines.append("")

    if concept_repeat_samples:
        lines.extend(["### Repeated Concept Samples", ""])
        for concept, samples in sorted(concept_repeat_samples.items()):
            lines.append(f"- `{concept}`: {len(samples)} samples at 4+ mentions")
            for item in samples[:3]:
                prompt = item.prompt.replace("\n", " ")
                if len(prompt) > 220:
                    prompt = prompt[:217] + "..."
                lines.append(f"  - `{item.scale}` / `{item.shot}` / `{item.aspect}` sample {item.sample}: {prompt}")
        lines.append("")
    return lines


def build_report(findings: list[Finding], sample_counts: dict[tuple[str, str, str], int], stats: list[PromptStats]) -> str:
    counts = Counter(finding.severity for finding in findings)
    lines = [
        "# Generated Prompt Audit Report",
        "",
        "This report is generated by `tools/audit_generated_prompts.py`.",
        "",
        "## Summary",
        "",
        f"- Samples: {sum(sample_counts.values())}",
        f"- Errors: {counts.get('error', 0)}",
        f"- Warnings: {counts.get('warning', 0)}",
        f"- Info: {counts.get('info', 0)}",
        "",
        "## Sample Coverage",
        "",
    ]
    for (scale, shot, aspect), count in sorted(sample_counts.items()):
        lines.append(f"- `{scale}` / `{shot}` / `{aspect}`: {count}")
    lines.extend([""])
    lines.extend(length_repetition_report(stats))
    lines.extend(["## Findings", ""])
    if not findings:
        lines.append("No findings.")
        return "\n".join(lines)

    grouped: dict[tuple[str, str], list[Finding]] = {}
    for finding in findings:
        grouped.setdefault((finding.severity, finding.rule), []).append(finding)

    severity_order = {"error": 0, "warning": 1, "info": 2}
    for (severity, rule), group in sorted(grouped.items(), key=lambda item: (severity_order.get(item[0][0], 9), item[0][1])):
        lines.append(f"### {severity}: {rule}")
        lines.append("")
        for finding in group[:80]:
            prompt = finding.prompt.replace("\n", " ")
            if len(prompt) > 260:
                prompt = prompt[:257] + "..."
            lines.append(f"- `{finding.scale}` / `{finding.shot}` / `{finding.aspect}` sample {finding.sample}: {finding.detail}")
            lines.append(f"  - {prompt}")
        if len(group) > 80:
            lines.append(f"- ... {len(group) - 80} more")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit generated final prompt combinations.")
    parser.add_argument("--samples", type=int, default=30, help="Samples per selected scale/shot.")
    parser.add_argument("--scale", action="append", choices=SCALES, help="Scale to audit; can be repeated.")
    parser.add_argument("--shot", action="append", choices=SHOTS, help="Shot to audit; can be repeated.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT_PATH), help="Markdown report output path.")
    parser.add_argument("--fail-on-warning", action="store_true")
    args = parser.parse_args()

    scales = selected_values(args.scale, SCALES)
    shots = selected_values(args.shot, SHOTS)
    findings, sample_counts, stats = run_audit(max(args.samples, 1), scales, shots)
    report = build_report(findings, sample_counts, stats)

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    counts = Counter(finding.severity for finding in findings)
    print(f"Wrote {report_path}")
    print(f"Errors: {counts.get('error', 0)}; warnings: {counts.get('warning', 0)}; info: {counts.get('info', 0)}")
    if counts.get("error", 0):
        return 1
    if args.fail_on_warning and counts.get("warning", 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
