"""一档、二档、三档构图器（现代与古装）：先定艺术母题，再按约束挑地点、身体动作、神情、配色服装，用固定句式渲染。

数据只读 data/art_direction_pools.json：
- 母题决定光线、空气感、前景、配色、调色和机位，保证一张图只有一个清楚的氛围；
- 地点提供环境文本、可互动道具、室内外与私密属性；三档全部只用私密地点，二档不限地点；
- 姿势只写身体动作并声明所需道具，神情单独成池，两者按动作能量组合；
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

from prompt_data import character_identity_options, makeup_options
from prompt_fluency import fluency_defects

DATA_PATH = Path(__file__).resolve().parent / "data" / "art_direction_pools.json"
COMPOSER_SCALES = ("normal", "bold", "bold_no_outfit")
CASTS = ("solo", "duo")
NIGHT_MAKEUP_MARKERS = ("夜景", "夜色", "暗夜", "夜拍", "暗调", "月光", "夜")
_DAY_MAKEUP_MARKERS = ("晨光", "日系", "晴日", "暖阳", "阳光")
_ATTEMPTS = 8
# 二档、三档一半的画面使用非常规镜头（畸变、低机位、荷兰角、俯拍、动态模糊）。
_WILD_CAMERA_CHANCE = 0.5
_WILD_POSE_CHANCE = 0.55
# 地点有可互动道具时，优先让人物和道具发生动作（拿、摘、拨、泼、抛），而不只是站、坐、靠。
_INTERACTIVE_POSE_CHANCE = 0.75
# 双人妆容拉开差距：一人取清透自然的妆，一人取轮廓更清楚的妆。
# 按妆容名（第一个逗号前）分组，不看描述细节。
_DEFINED_MAKEUP_MARKERS = ("轮廓", "骨相", "高光妆", "港风", "清冷", "清透水光", "唇釉妆", "蜜桃唇", "私房", "冷感")


def _load_pools() -> dict:
    pools = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    for key in ("ART_DIRECTIONS", "PLACES", "EXPRESSIONS", "POSES", "OUTFITS", "OUTFITS_ANCIENT", "COMPOSITION", "LENSES", "WILD_CAMERA", "DUO"):
        if key not in pools:
            raise ValueError(f"{DATA_PATH.name} 缺少 {key}")
    for direction in pools["ART_DIRECTIONS"]:
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


def _pose_table(group: str, shot: str, aspect: str, era: str, cast: str = "solo") -> list[dict]:
    poses = _pool("POSES", cast)[group]
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
    if scale == "bold_no_outfit":
        return bool(place.get("private"))
    return True


def _fitting_poses(group: str, shot: str, aspect: str, era: str, props: list[str], cast: str = "solo") -> list[dict]:
    return [pose for pose in _pose_table(group, shot, aspect, era, cast) if set(pose.get("props", ())) <= set(props)]


def _choose_pose(rng: random.Random, poses: list[dict]) -> dict:
    # 先决定是否和道具互动，再在其中偏向大胆动态的 wild 姿势（二档、三档可用时 55%）。
    interactive = [pose for pose in poses if pose.get("props")]
    if interactive and rng.random() < _INTERACTIVE_POSE_CHANCE:
        poses = interactive
    wild = [pose for pose in poses if pose.get("wild")]
    if wild and rng.random() < _WILD_POSE_CHANCE:
        poses = wild
    return _pick(rng, poses)


def _light_type(group: str, direction: dict) -> dict | None:
    # 二档、三档用光型把光线、身体轮廓和构图绑在一起；一档保持清爽叙事，不加身体光线句。
    if group != "bold" or not direction.get("light_type"):
        return None
    return POOLS["LIGHT_TYPES"][direction["light_type"]]


def _scene_line(group: str, shot: str, direction: dict, place: dict, rng: random.Random, cast: str = "solo") -> str:
    light_type = _light_type(group, direction)
    body_light = [_pick(rng, light_type["body_light"][shot])] if light_type else []
    if shot == "head_shot":
        text = "，".join([place["near"], direction["near_light"], *body_light])
    else:
        clauses = [place["half" if shot == "half_body" else "full"], direction["light"], *body_light, _pick(rng, direction["atmosphere"])]
        if direction["foreground"] and rng.random() < 0.5:
            clauses.append(_pick(rng, direction["foreground"]))
        text = "，".join(clauses)
    return re.sub("她(?!们)", "她们", text) if cast == "duo" else text


def _wild_camera(group: str, shot: str, aspect: str, rng: random.Random, cast: str = "solo") -> dict | None:
    if group != "bold" or rng.random() >= _WILD_CAMERA_CHANCE:
        return None
    options = [bundle for bundle in _pool("WILD_CAMERA", cast)[shot] if aspect in bundle["aspects"]]
    return _pick(rng, options) if options else None


def _camera_line(group: str, shot: str, aspect: str, direction: dict, wild: dict | None, rng: random.Random, cast: str = "solo") -> str:
    # 光型构图按单人写（“人物位于…”），双人改用 DUO 构图池。
    light_type = _light_type(group, direction) if cast == "solo" else None
    if wild:
        angle, composition = wild["angle"], wild["composition"]
    else:
        angle = _pick(rng, direction["camera"])
        composition = _pick(rng, light_type["compositions"][shot] if light_type else _pool("COMPOSITION", cast)[shot])
    orientation = {"landscape": "横向", "square": "方形"}.get(aspect, "竖向")
    who = "两人" if cast == "duo" else ""
    if shot == "head_shot":
        scope = f"{who}肩部以上近景"
    elif shot == "half_body":
        scope = f"{who}腰部以上的{orientation}半身构图"
    else:
        scope = f"{who}从头到脚的{orientation}全身构图"
    return f"{angle}，{scope}，{composition}"


# 固定容貌里“脸部”与“身材”的分界；妆容插在两者之间，原文一个字不改。
_IDENTITY_BODY_MARKER = "，性感锁骨"


def _split_identity(text: str) -> tuple[str, str]:
    index = text.find(_IDENTITY_BODY_MARKER)
    if index < 0:
        return text, ""
    return text[:index], text[index + 1:]


def _outfit_fits_place(option, place: dict) -> bool:
    requires = option.get("requires") if isinstance(option, dict) else None
    if requires == "water":
        return bool(place.get("water"))
    return True


def _outfit_line(group: str, era: str, shot: str, place: dict, palette: list[str], barefoot: bool, rng: random.Random) -> tuple[str, str]:
    main, support, accent = palette
    if era == "ancient":
        # 古装服装风格（汉服、民国、敦煌）必须与地点一致，避免宫殿里穿旗袍。
        styles = place.get("styles", ["hanfu"])
        options = [option for option in POOLS["OUTFITS_ANCIENT"][group][shot] if option["style"] in styles]
    else:
        options = POOLS["OUTFITS"][group][shot]
    options = [option for option in options if _outfit_fits_place(option, place)]
    # 泳装只出现在水边；水边地点一半概率优先挑泳装，内衣类不限地点。
    swim_only = [option for option in options if isinstance(option, dict) and option.get("requires") == "water"]
    if swim_only and rng.random() < 0.5:
        options = swim_only
    option = _pick(rng, options)
    if isinstance(option, dict):
        text = option["text"]
        if not barefoot and option.get("shoes"):
            text = f"{text}，脚上是{option['shoes']}"
    else:
        text = option
    style = option.get("style", "modern") if isinstance(option, dict) else "modern"
    return text.format(main=main, support=support, accent=accent), style


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
    """两人各穿一套：第二套主辅色互换，两套文字不同，分成两句。"""
    main, support, accent = palette
    left, style = _outfit_line(group, era, shot, place, palette, barefoot, rng)
    same_garment = left.replace(main, "\0").replace(support, main).replace("\0", support)
    for _ in range(6):
        right, _style = _outfit_line(group, era, shot, place, [support, main, accent], barefoot, rng)
        if right != same_garment:
            break
    return f"左边的女生穿着{left}。右边的女生穿着{right}", style


def _compose_once(scale: str, shot: str, aspect: str, era: str, rng: random.Random, cast: str = "solo") -> dict[str, str]:
    group = _group(scale)
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
        poses = _fitting_poses(group, shot, aspect, era, place["props"], cast)
        if poses:
            break
    else:
        raise ValueError(f"没有与 {scale}/{era}/{shot}/{aspect} 相容的母题、地点和姿势组合")
    pose = _choose_pose(rng, poses)
    expression = _pick(rng, _pool("EXPRESSIONS", cast)[group][pose["energy"]])
    palette = _pick(rng, direction["palettes"][group])
    wild = _wild_camera(group, shot, aspect, rng, cast)
    lens = wild["lens"] if wild else _pick(rng, POOLS["LENSES"][shot])
    main, support, accent = palette
    camera = _camera_line(group, shot, aspect, direction, wild, rng, cast)
    texture = "肤质细腻并保留真实纹理" if group == "bold" else "肤质保留真实纹理"
    dress = _duo_outfit_line if cast == "duo" else _outfit_line
    outfit, outfit_style = ("", "") if scale == "bold_no_outfit" else dress(group, era, shot, place, palette, bool(pose.get("barefoot")), rng)
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
        # 双人动作用“左边的女生/右边的女生”区分，不再把“一只手”改写成左手、右手。
        "pose_expression": f"{pose['body'] if cast == 'duo' else _name_hands(pose['body'])}。{expression}",
        "scene_light": _scene_line(group, shot, direction, place, rng, cast),
        "quality": f"{direction['grade']}，画面以{main}和{support}为主色，点缀一点{accent}，{texture}，高光不过曝",
        "director": direction["name"],
        "art_direction": direction["name"],
        "art_place": place_name,
        "art_pose": pose["body"],
        "art_wild_camera": wild["angle"] if wild else "",
        "art_outfit_style": outfit_style,
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
