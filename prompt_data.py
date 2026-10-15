"""提示词公共数据：固定人物、妆容、基础负面词，以及四档专用姿势池的加载。

一至四档的母题、地点、光线、镜头、姿势（四档除外）和服装都在 data/art_direction_pools.json，由 prompt_composer 读取。
固定人物、妆容、基础负面词只在 data/prompt_pools.json，这里没有内置副本：文件缺失或损坏时直接报错，不回退到旧数据。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SCALES = ('normal', 'bold', 'bold_no_outfit', 'nsfw')
SHOTS = ('head_shot', 'half_body', 'full_body')
SHOT_LABELS = {'head_shot': '头部', 'half_body': '半身', 'full_body': '全身'}
_DATA_DIR = Path(__file__).resolve().parent / 'data'


def _load_json_object(name: str) -> dict:
    path = _DATA_DIR / name
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f'提示词数据文件无法读取：{path}') from exc
    if not isinstance(data, dict):
        raise RuntimeError(f'提示词数据文件必须是 JSON 对象：{path}')
    return data


_POOLS = _load_json_object('prompt_pools.json')
NEGATIVE_PROMPT = _POOLS['NEGATIVE_PROMPT']
CHARACTER_IDENTITY_BY_SHOT = _POOLS['CHARACTER_IDENTITY_BY_SHOT']
MAKEUP_OPTIONS = _POOLS['MAKEUP_OPTIONS']
POSE_EXPRESSION_OPTIONS: dict[str, dict[str, list[str]]] = {}
_POSE_NORMALIZE_REPLACEMENTS: list[tuple[str, str]] = [('一腿微屈，一腿伸直', '左腿微屈，右腿伸直'),
 ('一腿承重一腿放松', '左腿承重，右腿放松'),
 ('一腿承重一腿侧点地', '左腿承重，右腿向侧前方点地'),
 ('一腿承重一腿向前轻伸', '左腿承重，右腿向前轻伸'),
 ('一腿弯曲一腿伸长', '左腿弯曲，右腿伸长'),
 ('一腿弯曲一腿斜向伸长', '左腿弯曲，右腿斜向伸长'),
 ('一腿伸直一腿弯起', '左腿伸直，右腿弯起'),
 ('一腿前伸一腿弯起', '左腿向前伸，右腿弯起'),
 ('一腿收回一腿斜向伸出', '左腿收回，右腿斜向伸出'),
 ('一腿收回一腿向画面边缘伸展', '左腿收回，右腿向画面边缘伸展'),
 ('一腿垂直承重一腿向前伸直点地', '左腿垂直承重，右腿向前伸直点地'),
 ('一腿垂直承重一腿向下伸直点地', '左腿垂直承重，右腿向下伸直点地'),
 ('一腿弯起一腿向侧前方伸直', '左腿弯起，右腿向侧前方伸直'),
 ('一腿承重一腿向后点地', '左腿承重，右腿向后点地'),
 ('一腿微屈右腿向后点地', '左腿微屈，右腿向后点地'),
 ('一腿弯曲踩在支撑面，一腿自然伸直', '左腿弯曲踩在支撑面，右腿自然伸直'),
 ('一腿弯曲一腿拉长', '左腿弯曲，右腿拉长'),
 ('一腿弯曲一腿向画面侧方伸长', '左腿弯曲，右腿向画面侧方伸长'),
 ('一腿微屈右腿', '左腿微屈，右腿'),
 ('一腿弯曲一腿', '左腿弯曲，右腿'),
 ('一腿弯起一腿', '左腿弯起，右腿'),
 ('一腿承重一腿', '左腿承重，右腿'),
 ('一腿收回一腿', '左腿收回，右腿'),
 ('一腿伸直一腿', '左腿伸直，右腿'),
 ('一腿前伸一腿', '左腿向前伸，右腿'),
 ('另一腿斜向伸出', '右腿斜向伸出'),
 ('另一腿斜向侧前方伸直', '右腿斜向侧前方伸直'),
 ('另一腿向前伸直点地', '右腿向前伸直点地'),
 ('另一腿向后点地', '右腿向后点地'),
 ('一只手抬到头侧一只停在腰侧', '左手抬到头侧，右手停在腰侧'),
 ('一只手穿过发丝，另一只手停在腰侧', '左手穿过发丝，右手停在腰侧'),
 ('一只手停在锁骨旁，一只手按住细腰', '左手停在锁骨旁，右手按住细腰'),
 ('一只手停在唇侧，另一只手停在腰缘', '左手停在胸前衣料边缘，右手停在腰缘'),
 ('一只手穿进发丝，一只手停在锁骨下方', '左手穿进发丝，右手停在锁骨下方'),
 ('一只手停在头侧，另一只手停在腰侧', '左手停在头侧，右手停在腰侧'),
 ('一只手抬到唇边，另一只手压住腰缘', '左手抬到耳侧发丝旁，右手压住腰缘'),
 ('一只手停在唇边，另一只手托住胸前边缘', '左手停在锁骨旁，右手托住胸前边缘'),
 ('一只手从胸前伸向镜头', '左手停在胸前'),
 ('一只手从腰前伸向镜头', '左手停在腰侧'),
 ('一只手穿过长发一只手按住腰侧', '左手穿过长发，右手按住腰侧'),
 ('一只手穿过长发一只手停在腰侧', '左手穿过长发，右手停在腰侧'),
 ('一只手停在胸部上缘另一只手停在腰侧', '左手停在胸部上缘，右手停在腰侧'),
 ('一只手停在胸前另一只手在腰侧', '左手停在胸前，右手停在腰侧'),
 ('另一只手停在腰侧', '右手停在腰侧'),
 ('另一只手停在腰缘', '右手停在腰缘'),
 ('另一只手扣住腰侧', '右手扣住腰侧'),
 ('另一只手靠近脸侧', '右手靠近脸侧'),
 ('另一只手扶腰', '右手扶腰'),
 ('另一只手拨开长发', '右手拨开长发'),
 ('另一只手按住腰侧', '右手按住腰侧'),
 ('另一只手停在胸前边缘', '右手停在胸前边缘'),
 ('另一只手停在胸部上缘', '右手停在胸部上缘'),
 ('另左手', '右手'),
 ('另一只手', '右手'),
 ('另一手', '右手'),
 ('一只手', '左手'),
 ('一手', '左手'),
 ('双手一前一后', '左手在前、右手在后'),
 ('双手一高一低', '左手抬高、右手放低'),
 ('右腿交叉点地另一腿向后拉长', '左腿交叉点地，右腿向后伸直'),
 ('一条腿', '左腿')]

def character_identity_options(shot: str) -> list[str]:
    return CHARACTER_IDENTITY_BY_SHOT[shot]


def makeup_options(scale: str) -> list[str]:
    return MAKEUP_OPTIONS['normal' if scale == 'normal' else 'bold']


def _normalize_pose_text(pose_text: str) -> str:
    """姿势池只保留左右手可渲染写法；眉眼等替换已随死数据清除。"""
    # 只排除句号：跨逗号的「一手…一手」也要能改写成左手/右手，否则两只手会同时变成左手。
    pose_text = re.sub(r"(一手[^。]{1,20}?)一手", r"\1另一手", pose_text)
    for source, replacement in _POSE_NORMALIZE_REPLACEMENTS:
        pose_text = pose_text.replace(source, replacement)
    return pose_text


def pose_expression_options_by_aspect(scale: str, shot: str, aspect: str, cast: str = 'solo') -> list[str]:
    """只服务四档：其余档位的姿势由 prompt_composer 从 art_direction_pools.json 组合。

    四档只有姿势内容单独隔离在本文件里，单人、双人各一套池；生成规则与一至三档完全一致。
    """
    if scale != 'nsfw':
        raise ValueError(f'{scale} 的姿势由构图器生成，不读取旧姿势池')
    key = 'nsfw_duo' if str(cast or '').strip() in {'duo', '双人', '2'} else 'nsfw'
    return [_normalize_pose_text(text) for text in POSE_EXPRESSION_OPTIONS[key][shot]]


NSFW_POSE_EXPRESSION_SOURCE = 'data/nsfw_pose_expression_options.json'
# 每镜头最少条数：条数太少，随机重抽就没有差异空间。
NSFW_POSE_MIN_OPTIONS = 10

# 各景别画面里看不见的部位。池里写了这些内容，加载时直接报错：
# 运行时静默裁剪会让越界分句被悄悄丢掉，改池的人无从发现，所以不做裁剪，只做校验。
NSFW_POSE_OUT_OF_SCOPE = {
    'head_shot': ('胸部', '胸前', '乳沟', '腰', '臀', '腿', '脚', '身体曲线'),
    'half_body': ('臀部', '小腿', '双脚', '床面'),
}


def _load_nsfw_pose_expression_json() -> None:
    path = Path(__file__).resolve().parent / 'data' / 'nsfw_pose_expression_options.json'
    if not path.is_file():
        raise RuntimeError(f'四档姿势规则文件不存在：{path}')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f'四档姿势规则文件无法读取：{path}') from exc
    if not isinstance(data, dict):
        raise RuntimeError('四档姿势规则必须是 JSON 对象。')
    if set(data) != set(SHOTS) | {'duo'}:
        raise RuntimeError('四档姿势规则必须包含 head_shot、half_body、full_body 和 duo 四组。')
    duo_source = data['duo']
    if not isinstance(duo_source, dict) or set(duo_source) != set(SHOTS):
        raise RuntimeError('四档 duo 姿势规则必须包含 3 种镜头：head_shot、half_body、full_body。')
    for scale_key, source in (('nsfw', data), ('nsfw_duo', duo_source)):
        cleaned = {}
        for shot in SHOTS:
            options = source.get(shot)
            if not isinstance(options, list):
                raise RuntimeError(f'四档 {scale_key} {shot} 姿势规则必须是列表。')
            cleaned[shot] = [str(item).strip() for item in options if str(item).strip()]
            if len(cleaned[shot]) < NSFW_POSE_MIN_OPTIONS:
                raise RuntimeError(f'四档 {scale_key} {shot} 姿势规则至少需要 {NSFW_POSE_MIN_OPTIONS} 条。')
            for index, text in enumerate(cleaned[shot], 1):
                for marker in NSFW_POSE_OUT_OF_SCOPE.get(shot, ()):
                    if marker in text:
                        raise RuntimeError(
                            f'四档 {scale_key} {shot} 第 {index} 条写了画面外的“{marker}”：'
                            f'{shot} 拍不到这个部位，请改写该分句，不要依赖运行时裁剪。'
                        )
        POSE_EXPRESSION_OPTIONS[scale_key] = cleaned


PROMPT_DATA_SOURCE = 'data/prompt_pools.json + data/nsfw_pose_expression_options.json'
NSFW_POSE_EXPRESSION_SOURCE = 'data/nsfw_pose_expression_options.json'
_load_nsfw_pose_expression_json()
