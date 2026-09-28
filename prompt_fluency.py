"""最终提示词逐行通顺度检查。

输入是按维度渲染好的最终行（见 prompt_engine.render_prompt_lines），输出缺陷列表。
审查工具用它做统计回归，生成流程用它做“不合格重抽”。四档（nsfw）的姿势与质量行不在检查范围。
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FluencyDefect:
    rule: str
    line: str
    detail: str


# (规则名, 适用行, 正则)。行名为 "*" 时检查全部行。
_PATTERN_RULES = (
    ("redundant_expression_tail", "pose", r"眉梢(放松|上挑)、(唇角|视线)|唇角保持"),
    ("frame_words_in_pose", "pose", r"画面下缘|稳定落点|画面前缘|镜头前缘|强透视|构图|节奏|呼吸感|镜头只看见"),
    ("negated_positive_wording", "*", r"不过度|不朝向|避开正对|不抢|不展开|不打亮|不过白|避免|禁止"),
    ("non_visual_scene", "scene", r"声音|嗡嗡|滴答|鸟叫|交响|气息|香气|香味|散发着|充满[^，。]*(感|氛围)|营造出|格调"),
    ("garment_edge_grammar", "outfit", r"穿着[^，。]*(进入画面|出现在画面|的翻领)"),
    ("abstract_verdict", "*", r"危险感|侵略感|迷离感|克制高级|高级感|奢华感|烟火气|有镜头感|支配感"),
    ("makeup_overreach", "makeup", r"眼神|表情|气质|神情"),
    ("broken_comma", "*", r"(?<![柔温饱平])[的与和把被]，"),
    ("duplicate_gaze", "pose", r"(看向镜头|直视镜头|看镜头|回看镜头|回望镜头|盯住镜头|锁住镜头)[^。]*，(眼神|视线|目光)[^，]*(看向镜头|直视镜头|看镜头|盯住镜头|锁住镜头|转回镜头)"),
    ("duplicate_smile", "pose", r"(嘴角|唇角)[^，]*(笑|扬|挑)[^。]*，(嘴角|唇角)[^，]*(笑|扬|挑)"),
)

_LENS_SCOPE_CONFLICTS = {
    "full_body": r"半身人像|特写",
    "half_body": r"全身|特写",
    "head_shot": r"全身|半身",
}
_OUT_OF_SCOPE = {
    "head_shot": r"腰|腿|(?<!针)脚|胸前",
    "half_body": r"(?<!针)脚|腿|臀|膝",
}
_QUALITY_SINGLE_CONCEPTS = ("颗粒", "不过曝", "肤质", "层次")


def fluency_defects(lines: dict[str, str], scale: str, shot: str) -> list[FluencyDefect]:
    """lines: {pose, scene, quality, camera, character, outfit, makeup} -> 缺陷列表。"""
    if scale == "nsfw":
        return []
    defects: list[FluencyDefect] = []
    for rule, line_name, pattern in _PATTERN_RULES:
        targets = lines.items() if line_name == "*" else ((line_name, lines.get(line_name, "")),)
        for name, text in targets:
            match = re.search(pattern, text or "")
            if match:
                defects.append(FluencyDefect(rule, name, match.group(0)))
                break
    quality = lines.get("quality", "")
    tones = re.findall(r"[^，。]*调色", quality)
    if len(tones) >= 2:
        defects.append(FluencyDefect("stacked_color_grade", "quality", "|".join(tones)))
    for concept in _QUALITY_SINGLE_CONCEPTS:
        if quality.count(concept) >= 2:
            defects.append(FluencyDefect("repeated_quality_concept", "quality", concept))
            break
    conflict = _LENS_SCOPE_CONFLICTS.get(shot)
    if conflict and re.search(conflict, quality):
        defects.append(FluencyDefect("lens_scope_mismatch", "quality", re.search(conflict, quality).group(0)))
    for name, text in lines.items():
        for clause in re.split(r"[，。；、]", text or ""):
            if len(clause) > 40:
                defects.append(FluencyDefect("run_on_clause", name, clause[:40]))
                break
    for hand in ("左手", "右手"):
        if (lines.get("pose") or "").count(hand) >= 2:
            defects.append(FluencyDefect("same_hand_twice", "pose", hand))
            break
    scope = _OUT_OF_SCOPE.get(shot)
    if scope:
        for name, text in lines.items():
            if name == "character":
                continue
            match = re.search(rf"[^，。]*({scope})[^，。]*", text or "")
            if match:
                defects.append(FluencyDefect("out_of_scope_body_part", name, match.group(0)))
                break
    pose = lines.get("pose", "")
    if pose and not (re.search(r"镜头|看向|直视|望", pose) and re.search(r"笑|唇|嘴|神情|眉", pose)):
        defects.append(FluencyDefect("pose_missing_gaze_or_expression", "pose", pose[:30]))
    scene = lines.get("scene", "")
    if scene and len(scene) < 22:
        defects.append(FluencyDefect("thin_scene", "scene", scene))
    outfit = lines.get("outfit", "")
    if outfit and len(outfit.split("，")) >= 7:
        defects.append(FluencyDefect("stacked_outfit_details", "outfit", str(len(outfit.split("，")))))
    return defects
