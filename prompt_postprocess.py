from __future__ import annotations

import copy
import random
import re

from prompt_constants import (
    FEEDBACK_TAG_RULES,
    FORBIDDEN_BY_SHOT,
    MAX_POSITIVE_PROMPT_LENGTH,
    PART_LENGTH_BUDGETS,
    PROMPT_PART_ORDER,
    TRIMMABLE_PARTS,
    VISIBLE_PROMPT_PARTS,
    WHITE_EDGE_REPLACEMENTS,
    QUALITY_BY_SCALE,
)
from prompt_data import QUALITY_SUFFIX
from prompt_planner import VISUAL_FOCUS_BY_SHOT


def enrich_visual_finish(parts: dict[str, str], palette: dict | None, grade: dict | None, scale: str = "bold") -> dict[str, str]:
    enriched = dict(parts)
    palette_summary = palette.get("summary") if palette else ""
    grade_quality = grade.get("quality") if grade else ""
    if palette_summary:
        palette_clause = f"阳光鲜艳配色以{palette_summary}为主"
        for name in ("scene_light",):
            text = str(enriched.get(name) or "")
            text = re.sub(r"阳光鲜艳配色以[^，。]+为主", palette_clause, text)
            enriched[name] = text
        scene_light = str(enriched.get("scene_light") or "")
        if "配色" not in scene_light and palette_summary not in scene_light:
            scene_light = scene_light.rstrip("，。 \n\t")
            enriched["scene_light"] = f"{scene_light}，整体配色以{palette_summary}为主" if scene_light else f"整体配色以{palette_summary}为主"
    if grade_quality:
        base = QUALITY_BY_SCALE.get(scale, QUALITY_BY_SCALE["bold"])
        quality = str(enriched.get("quality") or base)
        if grade_quality not in quality:
            enriched["quality"] = f"{quality}，{grade_quality}"
    elif not enriched.get("quality"):
        enriched["quality"] = QUALITY_BY_SCALE.get(scale, QUALITY_BY_SCALE["bold"])
    return enriched


def clean_sentence(text: str, shot: str, scale: str) -> str:
    text = "，".join(part.strip() for part in str(text).replace("；", "，").split("，") if part.strip())
    for source, replacement in WHITE_EDGE_REPLACEMENTS:
        text = text.replace(source, replacement)
    blockers = FORBIDDEN_BY_SHOT.get(shot, ())
    if blockers:
        parts = [part.strip() for part in text.split("，") if part.strip()]
        parts = [part for part in parts if not any(marker in part for marker in blockers)]
        text = "，".join(parts)
    return text.strip("，。 \n\t")


def ensure_sentence(text: str) -> str:
    text = text.strip("，。 \n\t")
    return f"{text}。" if text else ""


def _clauses(text: str) -> list[str]:
    return [part.strip("，。 \n\t") for part in str(text or "").replace("；", "，").split("，") if part.strip("，。 \n\t")]


def _set_clauses(parts: dict[str, str], name: str, clauses: list[str]) -> None:
    parts[name] = "，".join(clauses)


def _parts_text(parts: dict[str, str]) -> str:
    ordered = [parts.get(name, "") for name in PROMPT_PART_ORDER if name in VISIBLE_PROMPT_PARTS]
    return "\n".join(ensure_sentence(part) for part in ordered if part)


def _parts_length(parts: dict[str, str]) -> int:
    return len(_parts_text({name: value for name, value in parts.items() if name in VISIBLE_PROMPT_PARTS}))


def _trim_part_to(parts: dict[str, str], name: str, target_len: int) -> None:
    clauses = _clauses(parts.get(name, ""))
    # 保留最后2个分句（通常是表情/眼神/笑容等关键语义），从中间开始裁剪
    # 先裁剪场景/手势细节类分句（优先级低）
    low_priority_markers = ("脚下", "地面", "阴影", "反光", "光线", "背景", "材质", "纹理", "色块", "修容", "鼻梁", "下颌", "高光")
    while len(clauses) > 2 and _parts_length(parts) > target_len:
        # 从前往后找第一个低优先级分句裁剪
        cut_idx = -1
        for i, clause in enumerate(clauses[:-2]):  # 不动最后2个
            if any(m in clause for m in low_priority_markers):
                cut_idx = i
                break
        if cut_idx == -1:
            cut_idx = 0  # 没有低优先级分句就裁剪第一个非保留分句
        clauses.pop(cut_idx)
        _set_clauses(parts, name, clauses)


def enforce_part_budgets(parts: dict[str, str], budgets: dict[str, int] | None = None) -> dict[str, str]:
    budgets = budgets or PART_LENGTH_BUDGETS
    compacted = dict(parts)
    for name, budget in budgets.items():
        text = str(compacted.get(name) or "")
        if len(text) <= budget:
            continue
        clauses = _clauses(text)
        while len(clauses) > 2 and len("，".join(clauses)) > budget:
            if name == "character":
                clauses.pop(-1)  # character保留身份词（开头），从末尾裁剪细节
            else:
                clauses.pop(0)  # 其他维度保留最后2个关键分句
        compacted[name] = "，".join(clauses) if clauses else text[:budget]
    return compacted


def enforce_prompt_length(parts: dict[str, str], max_length: int = MAX_POSITIVE_PROMPT_LENGTH) -> dict[str, str]:
    compacted = enforce_part_budgets(parts)
    if _parts_length(compacted) <= max_length:
        return compacted

    # Remove format-like tails before touching visual content.
    compacted["quality"] = ""
    if _parts_length(compacted) <= max_length:
        return compacted

    for name in TRIMMABLE_PARTS:
        if name == "quality":
            continue
        _trim_part_to(compacted, name, max_length)
        if _parts_length(compacted) <= max_length:
            return compacted

    return compacted


def _text_has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers if marker)


def _remove_clauses_with_markers(text: str, markers: tuple[str, ...]) -> str:
    clauses = _clauses(text)
    kept = [clause for clause in clauses if not _text_has_any(clause, markers)]
    return "，".join(kept or clauses[:1])


def _ground_anchor_from_text(text: str) -> str:
    options = (
        (("沙滩", "海边", "海岸", "沙面", "海浪"), "脚下是浅金沙面和脚印纹理"),
        (("泳池", "池边", "水面", "池水", "水光"), "脚下是湿润湖蓝泳池瓷砖"),
        (("花园", "草地", "庭院", "热带", "花丛", "植物"), "脚下是鲜绿色草地和花影"),
        (("露台", "阳台", "屋顶", "甲板"), "脚下是暖色木质露台地板"),
        (("玻璃", "橱窗", "镜面", "反射"), "脚下是浅彩反光地面"),
        (("棚拍", "影棚", "彩色背景", "彩色棚"), "脚下是高饱和彩色棚拍地面"),
        (("街", "路面", "城市", "霓虹", "雨夜", "停车场"), "脚下是带反光的彩色街道路面"),
        (("房间", "酒店", "套房", "室内", "浴室", "更衣"), "脚下是暖色室内地面"),
    )
    for markers, anchor in options:
        if any(marker in text for marker in markers):
            return anchor
    return "脚下是浅暖色地面纹理"


def _ground_material_from_text(text: str) -> str:
    anchor = _ground_anchor_from_text(text)
    return re.sub(r"^脚下是", "", anchor)


def _move_camera_ground_to_pose(parts: dict[str, str]) -> dict[str, str]:
    moved = dict(parts)
    camera = str(moved.get("camera") or "")
    match = re.search(r"(?:，|,|^)?脚下是([^，。,\n]+)", camera)
    if not match:
        return moved
    material = re.split(r"(?:入镜|清楚|完整|可见)", match.group(1).strip(), maxsplit=1)[0].strip()
    if not material:
        return moved
    camera = re.sub(r"(?:，|,)?脚下是[^，。,\n]+", "", camera).strip("，, ")
    pose = str(moved.get("pose_expression") or "").strip("，, ")
    ground_clause = f"脚踩在{material}上"
    if ground_clause not in pose:
        pose = f"{pose}，{ground_clause}" if pose else ground_clause
    moved["camera"] = camera
    moved["pose_expression"] = pose
    return moved


def _replace_generic_ground_margin(text: str, context: str) -> str:
    anchor = _ground_anchor_from_text(context)
    material = _ground_material_from_text(context)
    drop_phrases = (
        "、脚部落点和脚下地面边距",
        "、长腿、脚部落点和脚下地面边距",
        "、长腿、脚部落点和脚下脚下",
        "、脚部落点和脚下脚下",
    )
    cleaned = str(text or "")
    for source in drop_phrases:
        cleaned = cleaned.replace(source, f"、脚下是{material}")
    cleaned = cleaned.replace("脚下脚下是", "脚下是")
    cleaned = cleaned.replace("和脚下是", "清楚，脚下是")
    replacements = (
        "脚下地面边距清楚",
        "脚下地面边缘作为落脚参照",
        "脚下地面质感和站位边距清楚",
        "脚下站位边距清楚",
        "脚下地面或池边边距",
        "脚下沙面边距清楚",
        "脚下草地或地面边距清楚",
        "脚下地面边距清楚",
        "脚下甲板或地面边距清楚",
        "脚下边距清楚",
        "前景肢体和脚下地面边距清楚",
        "地面边距",
        "站位边距",
        "边距清楚",
    )
    for source in replacements:
        cleaned = cleaned.replace(source, anchor)
    cleaned = cleaned.replace("脚下脚下是", "脚下是")
    cleaned = cleaned.replace("和脚下是", "清楚，脚下是")
    return cleaned


def _replace_generic_canvas_padding(text: str) -> str:
    cleaned = str(text or "")
    replacements = (
        ("身体转向、手臂和腿部外轮廓完整", "身体转向清楚"),
        ("头部、手臂、腿部、脚部和姿势外轮廓完整", "姿势清楚"),
        ("头部、身体和脚部外轮廓完整", "姿势清楚"),
        ("四肢外轮廓完整", "姿势清楚"),
        ("姿势外轮廓完整", "姿势清楚"),
        ("外轮廓完整", "构图完整"),
        ("完整身形占据主体", "人物占据主体"),
        ("画面利用左右环境空间强化身体线条", "横向场景内容铺满画面并强化身体线条"),
        ("左右环境空间强化身体线条", "横向场景内容铺满画面并强化身体线条"),
        ("左右边距保留外轮廓", "横向场景内容铺满画面并保留外轮廓"),
        ("左右边距", "横向场景内容"),
        ("四周留环境边距", "四周都有真实场景内容"),
        ("四周留床面或地面边距", "四周都有床面或地面内容"),
        ("四周边距", "四周场景内容"),
        ("黑色侧边", "真实场景侧边"),
        ("暗色侧边", "真实场景侧边"),
        ("黑边", "真实场景边缘"),
    )
    for source, replacement in replacements:
        cleaned = cleaned.replace(source, replacement)
    return cleaned


_FLAT_EXPRESSION_REPLACEMENTS = (
    ("嘴角没有明显笑容", "嘴角放松"),
    ("嘴角没有笑容", "嘴角放松"),
    ("没有夸张笑容", "表情克制"),
    ("眼神平静柔和", "眼神柔和"),
    ("眼神平静直接", "眼神明亮直接"),
    ("眼神安静专注", "眼神明亮专注"),
    ("眼神清澈安静", "眼神清澈"),
    ("眼神柔和专注", "眼神柔和专注"),
    ("眼神从容", "眼神自信"),
    ("眼神沉重黏着", "眼神强势黏着"),
    ("嘴唇放松闭合", "薄唇轻轻闭合"),
    ("嘴唇闭合带淡淡微笑", "嘴唇闭合带浅淡微笑"),
    ("嘴角带淡淡笑意", "嘴角带浅淡笑意"),
    ("嘴角带含蓄微笑", "嘴角带浅淡微笑"),
    ("嘴角带安静微笑", "嘴角带浅淡微笑"),
    ("冷淡讥笑", "浅淡微笑"),
    ("危险冷笑", "浅淡微笑"),
    ("冷淡", "明亮挑衅"),
)

_STRONG_EXPRESSION_MARKERS = (
    "微笑",
    "浅淡笑意",
    "嘴角轻微上扬",
    "嘴角放松",
    "嘴角微扬",
)

_EXPRESSION_BOOST_BY_SCALE = {
    "normal": ("嘴角轻微上扬", "嘴角带浅淡微笑", "眼尾轻弯，表情柔和"),
    "bold": ("嘴角轻微上扬，眼神明亮直接", "嘴角带克制微笑", "薄唇轻抿，眼尾轻弯", "嘴角带浅淡微笑"),
    "nsfw": ("嘴角轻微上扬，眼神湿润直接", "嘴角带克制微笑", "薄唇微张，表情克制", "嘴角带浅淡微笑"),
}

_FACE_EXPRESSION_CLAUSE_MARKERS = (
    "头部",
    "下巴",
    "眼",
    "狐眼",
    "抬眸",
    "回望",
    "看镜头",
    "直视",
    "嘴",
    "薄唇",
    "唇",
    "嘴角",
    "表情",
    "神情",
    "笑",
)

_BODY_POSE_CLAUSE_MARKERS = (
    "身体",
    "人物",
    "站",
    "坐",
    "跪",
    "躺",
    "趴",
    "蹲",
    "侧转",
    "后仰",
    "前倾",
    "侧弯",
    "双手",
    "一只手",
    "一手",
    "另一手",
    "手臂",
    "锁骨",
    "胸",
    "腰",
    "臀",
    "大腿",
    "小腿",
    "腿",
    "膝",
    "脚",
)

_POSE_LANGUAGE_REPLACEMENTS = (
    ("大头部", "头部"),
    ("大人物", "人物"),
    ("湿润直盯湿润反光", "直视镜头"),
    ("湿润直盯观众", "直视镜头"),
    ("湿润直勾勾盯住观众", "直视镜头"),
    ("直勾勾盯住观众", "直视镜头"),
    ("狐眼压迫直盯地向上仰望", "抬眼直视镜头"),
    ("狐眼压迫直盯", "直视镜头"),
    ("舌尖轻颤", "薄唇微开"),
    ("嘴唇微开薄唇微开", "嘴唇微开"),
    ("腰部、臀部和大腿线条柔软扭转", "腰线和大腿形成斜向曲线"),
    ("腰部、腰部线条柔软扭转", "胸腰形成斜向曲线"),
    ("线条柔软扭转", "形成斜向曲线"),
    ("锁骨突出胸前线条起伏", "锁骨和胸前线条清楚"),
    ("胸前线条起伏", "胸前线条清楚"),
    ("曲线优美，表情充满诱惑", "曲线清楚"),
    ("曲线诱导集中，表情充满渴望", "曲线清楚"),
    ("肩颈、胸腰、臀腿曲线形成浓烈私房氛围", "肩颈、腰线和大腿形成斜向构图"),
    ("肩颈和胸腰曲线形成浓烈私房氛围", "肩颈和胸腰形成斜向构图"),
    ("表情带得意挑衅", "嘴角带得意挑衅笑"),
    ("神情像在嘲弄镜头", "嘴角带嘲弄坏笑"),
    ("带一点甜美诱惑", "嘴角带甜美坏笑"),
)

_SMILE_SOFTEN_REPLACEMENTS = (
    ("自然大笑前一刻的灿烂笑容", "自然微笑"),
    ("开朗大笑后的明亮笑容", "浅淡微笑"),
    ("阳光大方的笑容", "浅淡微笑"),
    ("挑衅又灿烂的笑", "挑衅微笑"),
    ("主动邀请的灿烂笑", "主动微笑"),
    ("灿烂挑逗笑", "挑逗微笑"),
    ("放肆一点的", ""),
    ("放肆", "克制"),
    ("灿烂笑容", "浅淡微笑"),
    ("明亮笑容", "浅淡微笑"),
    ("明亮笑意", "浅淡笑意"),
    ("开朗笑意", "浅淡笑意"),
    ("嘴角展开明显微笑", "嘴角轻微上扬"),
    ("嘴角明显上扬", "嘴角轻微上扬"),
    ("嘴角上扬", "嘴角轻微上扬"),
    ("嘴角扬成清爽微笑", "嘴角带清爽微笑"),
    ("眼睛笑成弯弯的亮线", "眼尾轻微弯起"),
    ("眼睛笑得明亮", "眼神明亮"),
    ("假装认真又忍不住笑", "眼神认真，嘴角带浅淡笑意"),
    ("刚忍不住笑出声", "刚露出浅淡笑意"),
    ("像刚说完一句玩笑", "像刚轻声回应"),
    ("像刚完成一个轻松转身", "像刚完成一个轻松转身"),
    ("露出自然大笑", "带自然微笑"),
    ("露出明亮笑容", "带浅淡微笑"),
    ("大笑", "微笑"),
    ("咧嘴", "微笑"),
    ("露齿", "闭唇"),
    ("坏笑", "微笑"),
    ("冷笑", "浅淡微笑"),
    ("嘲笑", "浅淡微笑"),
    ("讥笑", "浅淡微笑"),
    ("怪罪式笑意", "浅淡笑意"),
    ("挑衅笑", "挑衅微笑"),
    ("挑衅微笑", "克制微笑"),
    ("挑逗笑", "挑逗微笑"),
    ("挑逗微笑", "浅淡微笑"),
    ("俏皮笑", "俏皮微笑"),
    ("俏皮微笑", "浅淡微笑"),
    ("玩味的笑意", "玩味微笑"),
    ("笑着勾人的表情", "浅淡勾人表情"),
    ("笑着挑衅", "眼神挑衅"),
    ("笑着压向镜头", "眼神压向镜头"),
    ("带笑意看向镜头", "带浅淡笑意看向镜头"),
    ("带笑意", "带浅淡笑意"),
    ("带自然笑意", "带浅淡自然笑意"),
    ("带俏皮笑意", "带俏皮微笑"),
    ("明亮微笑", "浅淡微笑"),
    ("自然微笑", "浅淡微笑"),
    ("温和微笑", "浅淡微笑"),
    ("温柔微笑", "浅淡微笑"),
    ("亲近笑意", "浅淡笑意"),
    ("轻松笑意", "浅淡笑意"),
    ("嘴角带笑", "嘴角带浅淡笑意"),
    ("嘴角在笑", "嘴角带浅淡笑意"),
    ("明显在笑", "带浅淡笑意"),
)

_SCENE_GLASS_PROP_REPLACEMENTS = (
    ("透明彩片", "亮色墙面"),
    ("透明亚克力片", "亮色墙面"),
    ("彩色玻璃", "彩色墙面"),
    ("玻璃砖", "浅色瓷砖"),
    ("棱镜窗光", "暖阳窗光"),
    ("棱镜", "暖阳色块"),
    ("橱窗彩色反光", "亮色墙面反光"),
    ("彩色橱窗", "彩色墙面"),
    ("彩色反光片", "亮色衣料边缘"),
    ("浅彩玻璃反射地面", "浅彩反光地面"),
    ("玻璃边缘", "背景边缘"),
    ("镜面边缘", "背景边缘"),
    ("镜面小反光", "浅色墙面反光"),
    ("透明水晶", "浅粉果冻"),
)


def _soften_smile_language(text: str) -> str:
    softened = str(text or "")
    for source, replacement in _SMILE_SOFTEN_REPLACEMENTS:
        softened = softened.replace(source, replacement)
    softened = re.sub(r"嘴角[^，。]{0,10}(?:扩散|展开)[^，。]{0,8}笑", "嘴角带浅淡微笑", softened)
    softened = re.sub(r"嘴巴[^，。]{0,6}张开[^，。]{0,8}(?:笑|笑容)", "嘴唇微开，嘴角带浅淡微笑", softened)
    softened = re.sub(r"嘴角轻微上扬[^，。]{0,8}嘴角轻微上扬", "嘴角轻微上扬", softened)
    softened = re.sub(r"浅淡微笑[^，。]{0,6}浅淡微笑", "浅淡微笑", softened)
    return softened

_VAGUE_PROMPT_REPLACEMENTS = (
    ("脚下地面清楚", ""),
    ("长腿、脚部落点清楚", ""),
    ("完整长腿和脚部落点清楚", ""),
    ("完整腿部和脚部落点清楚", ""),
    ("完整站姿和脚部落点清楚", ""),
    ("腿线和脚部落点清楚", ""),
    ("腿部轮廓和脚部落点清楚", ""),
    ("脚部落点清楚", ""),
    ("脸部表情明确", ""),
    ("脸部表情清楚", ""),
    ("眼睛笑起来", "眼尾弯起"),
    ("五官危险精致", ""),
    ("轻薄彩色薄纱作局部前景", "轻薄彩色薄纱从画面左下角掠过"),
    ("远处色块来自户外设施", "远处有彩色遮阳伞和湖蓝躺椅"),
    ("远处色块来自自然环境而非室内道具", "远处有花丛、绿植和晴空色块"),
    ("人物脚边环境清楚", "脚边有花影和浅色地面"),
    ("高反差眼妆，", ""),
    ("高反差眼妆", "黑色细眼线贴着睫毛根部并在眼尾上挑，眼尾浅棕灰阴影加深"),
    ("修容轮廓清晰", "鼻梁侧影和下颌阴影清楚，颧骨有细高光"),
    ("修容纤细干净", "鼻梁侧影很淡，下颌阴影收得干净"),
    ("修容让尖下巴和高鼻梁更突出", "鼻梁侧影清楚，下巴下方有轻微阴影"),
    ("修容强调高鼻梁和尖下巴", "鼻梁侧影清楚，下巴下方有轻微阴影"),
    ("鼻梁和下颌修容锋利精致", "鼻梁侧影偏窄，下颌线阴影干净"),
    ("尖下巴和高鼻梁被修容强调", "鼻梁侧影清楚，下巴下方有轻微阴影"),
    ("修容让瓜子脸更纤细", "下颌线阴影收窄瓜子脸"),
    ("修容集中在鼻梁和下巴", "鼻梁两侧有淡阴影，下巴下方有轻微阴影"),
    ("修容强化高鼻梁和尖下巴", "鼻梁侧影清楚，下巴下方有轻微阴影"),
    ("脚下地面有真实材质", "脚下是浅色瓷砖"),
    ("阳光落点跟随地面材质", "阳光落在浅色地面上"),
    ("地面反光自然贴合环境", "浅色地面带柔和反光"),
    ("脚部落点和地面材质", "脚下是浅色瓷砖"),
    ("地面材质", "浅色瓷砖"),
    ("脚尖拉长", "脚背绷直"),
    ("拉长脚尖", "脚背绷直"),
    ("脚尖形成终点", "脚尖指向画面边缘"),
    ("形成暧昧边界", ""),
    ("暧昧边界", ""),
    ("成人 glamour 边界", "glamour写真氛围"),
    ("成人私房边界", "成人私房写真氛围"),
    ("一腿微屈，一腿伸直", "左腿微屈，右腿伸直"),
    ("一腿承重一腿放松", "左腿承重，右腿放松"),
    ("一腿承重一腿侧点地", "左腿承重，右腿向侧前方点地"),
    ("一腿承重一腿向前轻伸", "左腿承重，右腿向前轻伸"),
    ("一腿弯曲一腿伸长", "左腿弯曲，右腿伸长"),
    ("一腿弯曲一腿斜向伸长", "左腿弯曲，右腿斜向伸长"),
    ("一腿伸直一腿弯起", "左腿伸直，右腿弯起"),
    ("一腿前伸一腿弯起", "左腿向前伸，右腿弯起"),
    ("一腿收回一腿斜向伸出", "左腿收回，右腿斜向伸出"),
    ("一腿收回一腿向画面边缘伸展", "左腿收回，右腿向画面边缘伸展"),
    ("一腿垂直承重一腿向前伸直点地", "左腿垂直承重，右腿向前伸直点地"),
    ("一腿垂直承重一腿向下伸直点地", "左腿垂直承重，右腿向下伸直点地"),
    ("一腿弯起一腿向侧前方伸直", "左腿弯起，右腿向侧前方伸直"),
    ("一腿承重一腿向后点地", "左腿承重，右腿向后点地"),
    ("一腿微屈右腿向后点地", "左腿微屈，右腿向后点地"),
    ("一腿弯曲踩在支撑面，一腿自然伸直", "左腿弯曲踩在支撑面，右腿自然伸直"),
    ("一腿弯曲一腿拉长", "左腿弯曲，右腿拉长"),
    ("一腿弯曲一腿向画面侧方伸长", "左腿弯曲，右腿向画面侧方伸长"),
    ("右腿交叉点地另一腿向后拉长", "左腿交叉点地，右腿向后伸直"),
    ("一腿微屈右腿", "左腿微屈，右腿"),
    ("一腿弯曲一腿", "左腿弯曲，右腿"),
    ("一腿弯起一腿", "左腿弯起，右腿"),
    ("一腿承重一腿", "左腿承重，右腿"),
    ("一腿收回一腿", "左腿收回，右腿"),
    ("一腿伸直一腿", "左腿伸直，右腿"),
    ("一腿前伸一腿", "左腿向前伸，右腿"),
    ("另一腿斜向伸出", "右腿斜向伸出"),
    ("另一腿斜向侧前方伸直", "右腿斜向侧前方伸直"),
    ("另一腿向前伸直点地", "右腿向前伸直点地"),
    ("另一腿向后点地", "右腿向后点地"),
    ("一只手抬到头侧一只停在腰侧", "左手抬到头侧，右手停在腰侧"),
    ("一只手穿过发丝，另一只手停在腰侧", "左手穿过发丝，右手停在腰侧"),
    ("一只手停在锁骨旁，一只手按住细腰", "左手停在锁骨旁，右手按住细腰"),
    ("一只手停在唇侧，另一只手停在腰缘", "左手停在唇侧，右手停在腰缘"),
    ("一只手穿进发丝，一只手停在锁骨下方", "左手穿进发丝，右手停在锁骨下方"),
    ("一只手停在头侧，另一只手停在腰侧", "左手停在头侧，右手停在腰侧"),
    ("一只手抬到唇边，另一只手压住腰缘", "左手抬到唇边，右手压住腰缘"),
    ("一只手停在唇边，另一只手托住胸前边缘", "左手停在唇边，右手托住胸前边缘"),
    ("一只手从胸前伸向镜头", "左手从胸前伸向镜头"),
    ("一只手从腰前伸向镜头", "左手从腰前伸向镜头"),
    ("一只手穿过长发一只手按住腰侧", "左手穿过长发，右手按住腰侧"),
    ("一只手穿过长发一只手停在腰侧", "左手穿过长发，右手停在腰侧"),
    ("一只手停在胸部上缘另一只手停在腰侧", "左手停在胸部上缘，右手停在腰侧"),
    ("一只手停在胸前另一只手在腰侧", "左手停在胸前，右手停在腰侧"),
    ("一手抓住长发，一手扶住腰侧", "左手抓住长发，右手扶住腰侧"),
    ("一手抬过头顶，一手按住腰线", "左手抬过头顶，右手按住腰线"),
    ("一手停在肩侧，一手沿腰线滑到腰侧", "左手停在肩侧，右手沿腰线滑到腰侧"),
    ("一手整理发尾，一手扶住腰线", "左手整理发尾，右手扶住腰线"),
    ("一手沿发尾滑到肩侧，一手扶住腰线", "左手沿发尾滑到肩侧，右手扶住腰线"),
    ("一手停胸缘，一手停腰髋", "左手停在胸缘，右手停在腰髋"),
    ("一手撑住头侧一手停在腰髋曲线", "左手撑住头侧，右手停在腰髋曲线"),
    ("一手整理黑发，一手停在腰侧", "左手整理黑发，右手停在腰侧"),
    ("一手自然下垂，一手轻扶腰侧", "左手自然下垂，右手轻扶腰侧"),
    ("一手停在肩侧，一手扶腰", "左手停在肩侧，右手扶腰"),
    ("一手整理耳侧发丝，一手轻搭肩线", "左手整理耳侧发丝，右手轻搭肩线"),
    ("一手停在脸颊边缘，一手沿腰线停住", "左手停在脸颊边缘，右手沿腰线停住"),
    ("一手停在锁骨上方，一手扶住腰部", "左手停在锁骨上方，右手扶住腰部"),
    ("一手停在锁骨旁，一手沿腰线滑到腰侧", "左手停在锁骨旁，右手沿腰线滑到腰侧"),
    ("一手停在唇边，另一只手扣住细腰", "左手停在唇边，右手扣住细腰"),
    ("一手停在唇边，一手停在细腰", "左手停在唇边，右手停在细腰"),
    ("一手靠近脸侧，一手扶住腰缘", "左手靠近脸侧，右手扶住腰缘"),
    ("一手托住下颌，一手扶住腰侧", "左手托住下颌，右手扶住腰侧"),
    ("一手沿发尾滑到肩侧，一手停在腰缘", "左手沿发尾滑到肩侧，右手停在腰缘"),
    ("双手一只撩发一只停在腰线", "左手撩发，右手停在腰线"),
    ("双手一只停在唇边一只停在胸前边缘", "左手停在唇边，右手停在胸前边缘"),
    ("双手一只停在胸部上缘一只停在腰侧", "左手停在胸部上缘，右手停在腰侧"),
    ("双手一只握住胸前另一只手在腰侧", "左手握住胸前，右手停在腰侧"),
    ("双手一只撑地一只沿腰髋曲线停住", "左手撑地，右手沿腰髋曲线停住"),
    ("另一只手停在腰侧", "右手停在腰侧"),
    ("另一只手停在腰缘", "右手停在腰缘"),
    ("另一只手扣住腰侧", "右手扣住腰侧"),
    ("另一只手靠近脸侧", "右手靠近脸侧"),
    ("另一只手扶腰", "右手扶腰"),
    ("另一只手拨开长发", "右手拨开长发"),
    ("另一只手按住腰侧", "右手按住腰侧"),
    ("另一只手停在胸前边缘", "右手停在胸前边缘"),
    ("另一只手停在胸部上缘", "右手停在胸部上缘"),
    ("另左手", "右手"),
    ("另一只手", "右手"),
    ("另一手", "右手"),
    ("一只手", "左手"),
    ("一手", "左手"),
    ("双手一前一后", "左手在前、右手在后"),
    ("双手一高一低", "左手抬高、右手放低"),
)


def strengthen_expression(parts: dict[str, str], scale: str, rng: random.Random | None = None) -> dict[str, str]:
    strengthened = dict(parts)
    pose = str(strengthened.get("pose_expression") or "")
    for source, replacement in _FLAT_EXPRESSION_REPLACEMENTS:
        pose = pose.replace(source, replacement)

    full_text = "，".join(str(strengthened.get(name, "")) for name in ("makeup", "pose_expression"))
    if not _text_has_any(full_text, _STRONG_EXPRESSION_MARKERS):
        boosts = _EXPRESSION_BOOST_BY_SCALE.get(scale, _EXPRESSION_BOOST_BY_SCALE.get("bold", ()))
        if boosts:
            if rng:
                boost = rng.choice(boosts)
            else:
                boost = boosts[0]
            pose = f"{pose}，{boost}" if pose else boost

    strengthened["pose_expression"] = pose
    return strengthened


def order_pose_before_expression(parts: dict[str, str]) -> dict[str, str]:
    ordered = dict(parts)
    pose = str(ordered.get("pose_expression") or "")
    clauses = _clauses(pose.replace("；", "，"))
    if len(clauses) < 3:
        return ordered
    body_clauses: list[str] = []
    face_clauses: list[str] = []
    other_clauses: list[str] = []
    for clause in clauses:
        has_body = _text_has_any(clause, _BODY_POSE_CLAUSE_MARKERS)
        has_face = _text_has_any(clause, _FACE_EXPRESSION_CLAUSE_MARKERS)
        if has_body and not has_face:
            body_clauses.append(clause)
        elif has_face and not has_body:
            face_clauses.append(clause)
        else:
            other_clauses.append(clause)
    if body_clauses and face_clauses:
        ordered["pose_expression"] = "，".join(body_clauses + other_clauses + face_clauses)
    return ordered


def simplify_pose_language(parts: dict[str, str]) -> dict[str, str]:
    simplified = dict(parts)
    pose = str(simplified.get("pose_expression") or "")
    for source, replacement in _POSE_LANGUAGE_REPLACEMENTS:
        pose = pose.replace(source, replacement)
    for source, replacement in _VAGUE_PROMPT_REPLACEMENTS:
        pose = pose.replace(source, replacement)
    pose = _soften_smile_language(pose)
    pose = re.sub(r"(薄唇微开[，,、]){2,}", "薄唇微开，", pose)
    pose = pose.replace("，。", "。").replace("，，", "，")
    simplified["pose_expression"] = pose.strip("，、 \n\t")
    return simplified


def apply_conflict_cleaner(parts: dict[str, str], scale: str, shot: str, aspect: str) -> dict[str, str]:
    cleaned = dict(parts)
    if shot == "large_half_body":
        cleaned["camera"] = "大腿以上镜头，横向构图" if aspect == "landscape" else "大腿以上镜头，竖向构图"

    context = "，".join(str(cleaned.get(name, "")) for name in ("camera", "pose_expression", "scene_light"))
    for name in ("camera", "pose_expression", "scene_light"):
        cleaned[name] = _replace_generic_ground_margin(cleaned.get(name, ""), context)

    if aspect == "landscape":
        vertical_markers = ("站立", "站姿", "直立", "竖向", "从头顶到脚掌", "脚下站点")
        cleaned["pose_expression"] = _remove_clauses_with_markers(cleaned.get("pose_expression", ""), vertical_markers)
    if aspect == "portrait":
        horizontal_markers = ("横躺", "侧躺", "平躺", "沿宽画幅", "横向展开", "宽画幅展开")
        cleaned["pose_expression"] = _remove_clauses_with_markers(cleaned.get("pose_expression", ""), horizontal_markers)

    if shot in {"head_shot", "upper_body", "half_body", "large_half_body"}:
        for name in ("camera", "pose_expression", "outfit", "scene_light"):
            cleaned[name] = clean_sentence(cleaned.get(name, ""), shot, scale)
        # 去除pose中与camera重复的镜头约束分句（入镜/入画/清楚/完整等）
        camera_text = str(cleaned.get("camera") or "")
        pose_text = str(cleaned.get("pose_expression") or "")
        if camera_text and pose_text:
            constraint_markers = ("入镜", "入画", "入图", "清楚", "完整身形", "占据主体", "边距")
            for marker in constraint_markers:
                # 如果camera含此标记而pose也含，移除pose中的该分句
                if marker in camera_text and marker in pose_text:
                    pose_text = _remove_clauses_with_markers(pose_text, (marker,))
            cleaned["pose_expression"] = pose_text

    if shot == "full_body":
        full_text = "，".join(str(cleaned.get(name, "")) for name in ("camera", "pose_expression", "scene_light"))
        standing_like = _text_has_any(full_text, ("站", "站立", "站姿", "直立", "迈步", "脚掌", "脚尖"))
        has_ground = _text_has_any(full_text, FEEDBACK_TAG_RULES["full_body_foot_anchor"])
        if standing_like and not has_ground:
            camera = str(cleaned.get("camera") or "").rstrip("，。 \n\t")
            anchor = _ground_anchor_from_text(full_text)
            cleaned["camera"] = f"{camera}，{anchor}" if camera else anchor

    if scale == "bold":
        outfit = str(cleaned.get("outfit") or "")
        for marker in ("裸露", "全裸", "完全裸露", "只剩", "最低覆盖", "覆盖面积极少"):
            outfit = outfit.replace(marker, "轻薄贴身")
        cleaned["outfit"] = outfit

    for name in ("makeup", "pose_expression", "scene_light", "quality"):
        text = str(cleaned.get(name) or "")
        for source, replacement in _VAGUE_PROMPT_REPLACEMENTS:
            text = text.replace(source, replacement)
        for marker in ("红唇", "深红", "酒红", "暗红", "浆果色"):
            text = text.replace(marker, "浅粉自然唇色")
        for marker in ("白边", "留白", "空白侧边", "纯白背景"):
            text = text.replace(marker, "环境色边缘")
        text = re.sub(r"，{2,}", "，", text).strip("，、 \n\t")
        cleaned[name] = text
    scene_light = str(cleaned.get("scene_light") or "")
    for source, replacement in _SCENE_GLASS_PROP_REPLACEMENTS:
        scene_light = scene_light.replace(source, replacement)
    cleaned["scene_light"] = scene_light
    cleaned["camera"] = _replace_generic_canvas_padding(cleaned.get("camera", ""))
    cleaned["scene_light"] = _replace_generic_canvas_padding(cleaned.get("scene_light", ""))
    cleaned = _move_camera_ground_to_pose(cleaned)
    cleaned["scene_light"] = re.sub(r"脚下脚下是", "脚下是", str(cleaned.get("scene_light") or ""))
    cleaned["scene_light"] = re.sub(r"脚部落点和脚下是", "脚下是", str(cleaned.get("scene_light") or ""))
    cleaned["scene_light"] = re.sub(
        r"脚部落点和(浅金沙面和脚印纹理|湿润湖蓝泳池瓷砖|鲜绿色草地和花影|暖色木质露台地板|浅彩反光地面|高饱和彩色棚拍地面|带反光的彩色街道路面|暖色室内地面|浅暖色地面纹理)",
        r"脚下是\1",
        str(cleaned.get("scene_light") or ""),
    )
    cleaned["scene_light"] = re.sub(r"脚部落点和脚下地面边距", "地面材质", str(cleaned.get("scene_light") or ""))

    return cleaned


def feedback_tags(parts: dict[str, str], scale: str, shot: str, aspect: str) -> list[str]:
    text = _parts_text(parts)
    tags = []
    for tag, markers in FEEDBACK_TAG_RULES.items():
        matched = _text_has_any(text, markers)
        if tag in {"red_lip_risk", "white_padding_risk", "avoid_flat_face"}:
            if matched:
                tags.append(tag)
        elif matched:
            tags.append(tag)
    if shot == "full_body" and "full_body_foot_anchor" not in tags:
        tags.append("missing_full_body_foot_anchor")
    if aspect == "landscape" and _text_has_any(text, ("站立", "站姿", "直立")):
        tags.append("landscape_vertical_pose_risk")
    if aspect == "portrait" and _text_has_any(text, ("横躺", "侧躺", "沿宽画幅")):
        tags.append("portrait_horizontal_pose_risk")
    if len(text) > MAX_POSITIVE_PROMPT_LENGTH:
        tags.append("over_length")
    return tags


def score_prompt_parts(parts: dict[str, str], scale: str, shot: str, aspect: str) -> int:
    tags = feedback_tags(parts, scale, shot, aspect)
    text = _parts_text(parts)
    score = 100
    score += 8 if "active_smile" in tags else -8
    score += 5 if "vivid_color" in tags else -4
    visual_focus_names = {name for name, _keywords in VISUAL_FOCUS_BY_SHOT.get(shot, ())}
    score += 5 if str(parts.get("visual_focus") or "") in visual_focus_names else 0
    if shot == "full_body":
        score += 10 if "full_body_foot_anchor" in tags else -18
    if "forced_perspective" in tags:
        score += 4
    for bad_tag in ("red_lip_risk", "white_padding_risk", "avoid_flat_face", "landscape_vertical_pose_risk", "portrait_horizontal_pose_risk", "over_length"):
        if bad_tag in tags:
            score -= 14
    score -= max(0, len(text) - MAX_POSITIVE_PROMPT_LENGTH) // 8
    return score
