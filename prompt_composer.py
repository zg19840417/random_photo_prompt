"""一至四档共用构图器（现代与古装）：先定艺术母题，再按约束挑地点、姿势表情、配色服装，用固定句式渲染。

主池只读 data/art_direction_pools.json；四档姿势表情经 prompt_data 读取独立 JSON：
- 母题决定光线、空气感、前景、配色、调色和机位，保证一张图只有一个清楚的氛围；
- 地点提供环境文本、可互动道具、室内外与私密属性；三档全部只用私密地点，二档不限地点；
- 一至三档先选择气质与状态，再选相容的身体动作和完整神情方案；四档完整姿势原样接入；
- 二档姿势不写服装，三档直接复用；服装按母题配色填色，赤脚姿势不写鞋。
渲染后用 prompt_fluency 检查，不合格就重抽，不做字符串修补。固定人物容貌行始终取自原人物池，不在这里改写。
双人（cast="duo"）沿用同一套母题、地点、光线与配色，只把姿势、神情、构图换成 DUO 池，
两人共用固定容貌，妆容一清透一立体，各穿一套同配色的衣服，场景主语改成“她们”。
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Callable

from prompt_data import character_identity_options, makeup_options, pose_expression_options_by_aspect
from prompt_fluency import fluency_defects

DATA_PATH = Path(__file__).resolve().parent / "data" / "art_direction_pools.json"
COMPOSER_SCALES = ("normal", "bold", "bold_no_outfit", "nsfw")
CASTS = ("solo", "duo")
NIGHT_MAKEUP_MARKERS = ("夜景", "夜色", "暗夜", "夜拍", "暗调", "月光", "夜")
_DAY_MAKEUP_MARKERS = ("晨光", "日系", "晴日", "暖阳", "阳光")
_ATTEMPTS = 8
_WILD_POSE_CHANCE = 0.55
# 地点有可互动道具时，优先让人物和道具发生动作（拿、摘、拨、泼、抛），而不只是站、坐、靠。
_INTERACTIVE_POSE_CHANCE = 0.75
# 双人妆容拉开差距：一人取清透自然的妆，一人取轮廓更清楚的妆。
# 按妆容名（第一个逗号前）分组，不看描述细节。
_DEFINED_MAKEUP_MARKERS = ("轮廓", "骨相", "高光妆", "港风", "清冷", "清透水光", "唇釉妆", "蜜桃唇", "私房", "冷感")


def _load_pools() -> dict:
    pools = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    for key in ("ART_DIRECTIONS", "PLACES", "PERSONAS", "POSES", "OUTFITS", "OUTFITS_ANCIENT", "COMPOSITION", "LENSES", "WILD_CAMERA", "DUO"):
        if key not in pools:
            raise ValueError(f"{DATA_PATH.name} 缺少 {key}")
    for direction in pools["ART_DIRECTIONS"]:
        if not all(direction.get(key) for key in ("compact_light", "compact_grade")):
            raise ValueError(f"母题 {direction['name']} 缺少精简光线或调色")
        if direction.get("light_type") and direction["light_type"] not in pools["LIGHT_TYPES"]:
            raise ValueError(f"母题 {direction['name']} 引用了不存在的光型：{direction['light_type']}")
        missing = [
            name for name in direction["places"]
            if name not in pools["PLACES"] or not set(direction["eras"]) & set(pools["PLACES"][name]["eras"])
        ]
        if missing:
            raise ValueError(f"母题 {direction['name']} 引用了不存在的地点：{missing}")
        for group in direction["scales"]:
            if group not in direction["palettes"]:
                raise ValueError(f"母题 {direction['name']} 缺少 {group} 配色")
    profiles = set(pools["PERSONAS"]["pose_profiles"])
    for group in ("normal", "bold"):
        persona = pools["PERSONAS"][group]
        states = persona["states"]
        for state_id, state in states.items():
            if not state["expressions"] or not set(state["pose_profiles"]) <= profiles:
                raise ValueError(f"{group}/{state_id} 状态缺少神情或引用了未知动作类型")
            for frame in state["expressions"]:
                if set(frame) != {"gaze", "brows", "mouth", "detail"} or not all(frame.values()):
                    raise ValueError(f"{group}/{state_id} 神情方案不完整")
        for theme in persona["temperaments"]:
            if not theme["states"] or not set(theme["states"]) <= set(states):
                raise ValueError(f"{group}/{theme['id']} 气质引用了未知状态")
            if not theme["pose_profiles"] or not set(theme["pose_profiles"]) <= profiles:
                raise ValueError(f"{group}/{theme['id']} 气质引用了未知动作类型")
            for state_id in theme["states"]:
                if not set(theme["pose_profiles"]) & set(states[state_id]["pose_profiles"]):
                    raise ValueError(f"{group}/{theme['id']}/{state_id} 没有相容动作类型")
        for root in (pools, pools["DUO"]):
            for table in root["POSES"][group].values():
                for options in table.values():
                    for pose in options:
                        if not pose["persona_profiles"] or not set(pose["persona_profiles"]) <= profiles:
                            raise ValueError(f"{group} 姿势缺少有效人物状态标签：{pose['body']}")
    return pools


POOLS = _load_pools()


def _group(scale: str) -> str:
    return "normal" if scale == "normal" else "bold"


def _era(era: str) -> str:
    return "ancient" if str(era or "").strip() in {"ancient", "古装", "古代"} else "modern"


def _name_hands(body: str) -> str:
    """动作里的“一只手…另一只手”写成明确的左手、右手，图像模型才不会把两只手画成同一侧。"""
    return body.replace("另一只手", "右手").replace("一只手", "左手")


def _pick(rng: random.Random, values):
    return values[rng.randrange(len(values))]


def normalize_cast(cast: str) -> str:
    return "duo" if str(cast or "").strip() in {"duo", "双人", "2"} else "solo"


def _pool(key: str, cast: str):
    return POOLS["DUO"][key] if cast == "duo" else POOLS[key]


def _pose_table(scale: str, shot: str, aspect: str, era: str, cast: str = "solo") -> list[dict]:
    if scale == "nsfw":
        # 独立池已经包含完整姿势表情句，作为不透明文本接入，不拆句或追加神情。
        return [{"body": text, "text": text} for text in pose_expression_options_by_aspect(scale, shot, aspect, cast)]
    poses = _pool("POSES", cast)[_group(scale)]
    if shot == "head_shot":
        # 头部动作与画幅无关，横构图额外加入横向头部动作。
        table = poses["portrait"]["head_shot"] + (poses["landscape"]["head_shot"] if aspect == "landscape" else [])
    elif aspect == "square" and "square" in poses:
        # 方图放斜向身体线条的姿势（慵懒斜靠、斜坐、斜倾）；没有专用方图池的档位沿用竖构图姿势。
        table = poses["square"][shot]
    else:
        table = poses["landscape" if aspect == "landscape" else "portrait"][shot]
    return [pose for pose in table if era in pose.get("eras", ("modern", "ancient"))]


def _place_allowed(place: dict, scale: str, shot: str) -> bool:
    if _group(scale) not in place["scales"]:
        return False
    if scale in {"bold_no_outfit", "nsfw"}:
        return bool(place.get("private"))
    return True


def _fitting_poses(scale: str, shot: str, aspect: str, era: str, props: list[str], cast: str = "solo") -> list[dict]:
    return [pose for pose in _pose_table(scale, shot, aspect, era, cast) if set(pose.get("props", ())) <= set(props)]


def _choose_pose(rng: random.Random, poses: list[dict]) -> dict:
    # 先决定是否和道具互动，再在其中偏向大胆动态的 wild 姿势（二档、三档可用时 55%）。
    interactive = [pose for pose in poses if pose.get("props")]
    if interactive and rng.random() < _INTERACTIVE_POSE_CHANCE:
        poses = interactive
    wild = [pose for pose in poses if pose.get("wild")]
    if wild and rng.random() < _WILD_POSE_CHANCE:
        poses = wild
    return _pick(rng, poses)


def _choose_persona(group: str, rng: random.Random, complete_pose: bool = False) -> tuple[dict, str, dict | None]:
    pool = POOLS["PERSONAS"][group]
    theme = _pick(rng, pool["temperaments"])
    if complete_pose:
        return theme, "", None
    state_id = _pick(rng, theme["states"])
    return theme, state_id, pool["states"][state_id]


def _state_expression(state: dict, cast: str, rng: random.Random) -> str:
    # 一次选定完整神情方案，部位之间不再分别随机。
    frame = _pick(rng, state["expressions"])
    return "，".join(frame[key] for key in ("gaze", "brows", "mouth", "detail")).format(subject="两人" if cast == "duo" else "她")


def _light_type(group: str, direction: dict) -> dict | None:
    if not POOLS["PERSONAS"][group]["light_composition"] or not direction.get("light_type"):
        return None
    return POOLS["LIGHT_TYPES"][direction["light_type"]]


def _scene_line(group: str, shot: str, direction: dict, place: dict, rng: random.Random, cast: str = "solo") -> str:
    location = place[{"head_shot": "near", "half_body": "half"}.get(shot, "full")]
    light = direction["near_light"] if shot == "head_shot" else direction["compact_light"]
    text = f"{location}，{light}"
    return re.sub("她(?!们)", "她们", text) if cast == "duo" else text


def _wild_camera(group: str, shot: str, aspect: str, rng: random.Random, cast: str = "solo") -> dict | None:
    chance = POOLS["PERSONAS"][group]["wild_camera_chance"]
    if chance <= 0 or rng.random() >= chance:
        return None
    options = [bundle for bundle in _pool("WILD_CAMERA", cast)[shot] if aspect in bundle["aspects"]]
    return _pick(rng, options) if options else None


def _camera_line(group: str, shot: str, aspect: str, direction: dict, wild: dict | None, rng: random.Random, cast: str = "solo", temperament: dict | None = None) -> str:
    # 光型构图按单人写（“人物位于…”），双人改用 DUO 构图池。
    light_type = _light_type(group, direction) if cast == "solo" else None
    if wild:
        angle, composition = wild["angle"], wild["composition"]
    else:
        angles = direction["camera"]
        if temperament:
            angles = [angle for angle in angles if angle in temperament["camera"]]
        angle = _pick(rng, angles)
        composition = _pick(rng, light_type["compositions"][shot] if light_type else _pool("COMPOSITION", cast)[shot])
    orientation = {"landscape": "横向", "square": "方形"}.get(aspect, "竖向")
    who = "两人" if cast == "duo" else ""
    if shot == "head_shot":
        scope = f"{who}肩部以上近景"
    elif shot == "half_body":
        scope = f"{who}腰部以上的{orientation}半身构图"
    else:
        scope = f"{who}从头到脚的{orientation}全身构图"
    text = f"{angle}，{scope}，{composition}"
    return f"{text}，人物呈现{temperament['intro']}" if temperament else text


# 固定容貌里“脸部”与“身材”的分界；妆容插在两者之间，原文一个字不改。
_IDENTITY_BODY_MARKER = "，性感锁骨"


def _split_identity(text: str) -> tuple[str, str]:
    index = text.find(_IDENTITY_BODY_MARKER)
    if index < 0:
        return text, ""
    return text[:index], text[index + 1:]


def _pick_outfit(group: str, era: str, shot: str, place: dict, palette: list[str], barefoot: bool, rng: random.Random) -> tuple[str, str, str]:
    """选一套服装，返回 (渲染文本, 风格, 服装模板)：模板是填色前的原文，用来判断两套衣服是否同款。"""
    main, support, accent = palette
    if era == "ancient":
        # 古装服装风格（汉服、民国、敦煌）必须与地点一致，避免宫殿里穿旗袍。
        styles = place.get("styles", ["hanfu"])
        options = [option for option in POOLS["OUTFITS_ANCIENT"][group][shot] if option["style"] in styles]
    else:
        options = POOLS["OUTFITS"][group][shot]
    option = _pick(rng, options)
    if isinstance(option, dict):
        template = option["text"]
        text = template
        if not barefoot and option.get("shoes"):
            text = f"{text}，脚上是{option['shoes']}"
    else:
        template = text = option
    style = option.get("style", "modern") if isinstance(option, dict) else "modern"
    return text.format(main=main, support=support, accent=accent), style, template


def _outfit_line(group: str, era: str, shot: str, place: dict, palette: list[str], barefoot: bool, rng: random.Random) -> tuple[str, str]:
    text, style, _ = _pick_outfit(group, era, shot, place, palette, barefoot, rng)
    return text, style


def _makeup_choices(group: str, direction: dict) -> list[str]:
    options = list(makeup_options(group))
    # 黄昏仍按白天处理：场景没有夜色时不配夜妆。
    if direction["time"] in ("day", "dusk"):
        return [option for option in options if not any(marker in option for marker in NIGHT_MAKEUP_MARKERS)] or options
    return [option for option in options if not any(marker in option for marker in _DAY_MAKEUP_MARKERS)] or options


def _makeup(group: str, direction: dict, place: dict, aspect: str, rng: random.Random) -> str:
    return _pick(rng, _makeup_choices(group, direction))


def _duo_makeup(group: str, direction: dict, rng: random.Random) -> str:
    options = _makeup_choices(group, direction)
    defined = [option for option in options if any(marker in option.split("，")[0] for marker in _DEFINED_MAKEUP_MARKERS)]
    soft = [option for option in options if option not in defined]
    if defined and soft:
        pair = [_pick(rng, soft), _pick(rng, defined)]
        rng.shuffle(pair)
    else:
        pair = rng.sample(options, 2)
    return f"左边的女生化着{pair[0]}。右边的女生化着{pair[1]}"


def _duo_outfit_line(group: str, era: str, shot: str, place: dict, palette: list[str], barefoot: bool, rng: random.Random) -> tuple[str, str]:
    """两人各穿一套：第二套主辅色互换，模板不同才算不同款，分成两句。"""
    main, support, accent = palette
    left, style, left_template = _pick_outfit(group, era, shot, place, palette, barefoot, rng)
    right = left
    for _ in range(6):
        candidate, _, candidate_template = _pick_outfit(group, era, shot, place, [support, main, accent], barefoot, rng)
        right = candidate
        if candidate_template != left_template:
            break
    return f"左边的女生穿着{left}。右边的女生穿着{right}", style


def _compose_once(scale: str, shot: str, aspect: str, era: str, rng: random.Random, cast: str = "solo") -> dict[str, str]:
    group = _group(scale)
    temperament, state_id, state = _choose_persona(group, rng, complete_pose=scale == "nsfw")
    persona_profiles = set(temperament["pose_profiles"]) & set(state["pose_profiles"]) if state else set()
    directions = [
        direction for direction in POOLS["ART_DIRECTIONS"]
        if group in direction["scales"] and era in direction["eras"]
    ]
    for _ in range(len(directions) * 3):
        direction = _pick(rng, directions)
        place_names = [name for name in direction["places"] if _place_allowed(POOLS["PLACES"][name], scale, shot)]
        if not place_names:
            continue
        place_name = _pick(rng, place_names)
        place = POOLS["PLACES"][place_name]
        poses = _fitting_poses(scale, shot, aspect, era, place["props"], cast)
        if state:
            poses = [pose for pose in poses if pose.get("expression_visible", True) and persona_profiles & set(pose["persona_profiles"])]
        if poses:
            break
    else:
        raise ValueError(f"没有与 {scale}/{era}/{shot}/{aspect} 相容的母题、地点和姿势组合")
    pose = _choose_pose(rng, poses)
    pose_expression = pose.get("text")
    if pose_expression is None:
        expression = _state_expression(state, cast, rng)
        pose_expression = f"{pose['body'] if cast == 'duo' else _name_hands(pose['body'])}。{expression}"
    palette = _pick(rng, direction["palettes"][group])
    wild = _wild_camera(group, shot, aspect, rng, cast)
    lens = wild["lens"] if wild else _pick(rng, POOLS["LENSES"][shot])
    main, support, accent = palette
    camera = _camera_line(group, shot, aspect, direction, wild, rng, cast, temperament)
    texture = POOLS["PERSONAS"][group]["texture"]
    grade = direction["compact_grade"]
    dress = _duo_outfit_line if cast == "duo" else _outfit_line
    outfit, outfit_style = ("", "") if scale in {"bold_no_outfit", "nsfw"} else dress(group, era, shot, place, palette, bool(pose.get("barefoot")), rng)
    face, body = _split_identity(_pick(rng, character_identity_options(shot)))
    if cast == "duo":
        # 两人共用固定容貌；妆容各写一句，接在容貌后面。
        face = f"两个女生都是{face}"
    return {
        "camera": camera,
        "camera_line": camera,
        "lens": lens,
        "character": face,
        "body": body,
        "makeup": _duo_makeup(group, direction, rng) if cast == "duo" else _makeup(group, direction, place, aspect, rng),
        "outfit": outfit,
        "pose_expression": pose_expression,
        "scene_light": _scene_line(group, shot, direction, place, rng, cast),
        "quality": f"{grade}，画面以{main}和{support}为主色，点缀一点{accent}，{texture}，高光不过曝",
        "director": direction["name"],
        "art_direction": direction["name"],
        "art_place": place_name,
        "art_pose": pose["body"],
        "art_wild_camera": wild["angle"] if wild else "",
        "art_outfit_style": outfit_style,
        "character_temperament": temperament["id"],
        "character_temperament_label": temperament["label"],
        "character_state": state_id,
        "character_state_label": state["label"] if state else "",
        "color_palette": "、".join(palette),
        "theme_name": "",
        "era": era,
        "cast": cast,
        "variant_seed": str(rng.random()),
    }


def compose_parts(
    scale: str,
    shot: str,
    aspect: str,
    rng: random.Random,
    render_lines: Callable[[dict[str, str]], dict[str, str]],
    era: str = "modern",
    cast: str = "solo",
) -> dict[str, str]:
    """返回维度文本；render_lines 是最终拼装的逐行渲染函数，用于通顺检查。
    """
    if scale not in COMPOSER_SCALES:
        raise ValueError(f"构图器不处理 {scale}")
    best: dict[str, str] | None = None
    best_count = 10_000
    for _ in range(_ATTEMPTS):
        parts = _compose_once(scale, shot, aspect, _era(era), rng, normalize_cast(cast))
        lines = render_lines({**parts, "shot_key": shot, "scale": scale, "aspect": aspect})
        count = len(fluency_defects(lines, scale, shot))
        if count < best_count:
            best, best_count = parts, count
        if count == 0:
            break
    assert best is not None
    return best
