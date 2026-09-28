"""提示词公共数据：固定人物、妆容、质量尾、基础负面词，以及四档专用姿势池的加载。

一至四档的母题、地点、光线、镜头、姿势（四档除外）和服装都在 data/art_direction_pools.json，由 prompt_composer 读取。
此处的内置值只作启动保底，正常内容编辑改 data/prompt_pools.json。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

QUALITY_SUFFIX = '真实写真质感，人物主体清晰，面部锐利，肤质细腻真实，电影感光影high-end editorial portrait, best quality, ultra detailed'
NEGATIVE_PROMPT = 'low quality, blurry, bad anatomy, extra fingers, missing fingers, distorted face, deformed body, duplicated limbs, text, watermark, logo, explicit sexual act, exposed genitals, red lipstick, bright red lips, dark red lips, burgundy lips, wine-red lips, crimson lips, dark lipstick, black lipstick, over-saturated lip color, lip tint, colored lipstick, obvious lipstick, unnatural lip color, plump lips, full lips, thick lips, overlined lips, overfilled lips, swollen lips, lip filler, latex clothing, PVC clothing, rubber clothing, plastic clothing, vinyl clothing, glossy plastic fabric, shiny latex'
SCALES = ('normal', 'bold', 'bold_no_outfit', 'nsfw')
SHOTS = ('head_shot', 'half_body', 'full_body')
SHOT_LABELS = {'head_shot': '头部', 'half_body': '半身', 'full_body': '全身'}
CHARACTER_IDENTITY_BY_SHOT = {'head_shot': ['22岁冷白皮K-pop韩国女生，黑色渐变的手指甲又细又长，夜店斩男精致妆容，御姐范十足，通透瓷白皮肤，黑色直发，标准瓜子脸，狐狸眼，浅棕色眼影，深棕色美瞳，高鼻梁，尖鼻子，尖下巴'],
 'half_body': ['22岁冷白皮K-pop韩国女生，黑色渐变的手指甲又细又长，夜店斩男精致妆容，御姐范十足，通透瓷白皮肤，黑色直发，标准瓜子脸，狐狸眼，浅棕色眼影，深棕色美瞳，高鼻梁，尖鼻子，尖下巴，性感锁骨，骨架偏瘦但胸部丰满，小蛮腰'],
 'full_body': ['22岁冷白皮K-pop韩国女生，黑色渐变的手指甲又细又长，夜店斩男精致妆容，御姐范十足，通透瓷白皮肤，黑色直发，标准瓜子脸，狐狸眼，浅棕色眼影，深棕色美瞳，高鼻梁，尖鼻子，尖下巴，性感锁骨，骨架偏瘦但胸部和臀部丰满，小蛮腰，腿细且长']}
MAKEUP_OPTIONS = {'normal': ['韩系清透妆，冷白水润底妆干净透亮，浅棕眼影压低眼尾，细长眼线拉出狐狸眼形，浅棕美瞳自然放大眼神，原生唇色覆透明无色唇彩让五官显得柔和精致',
            '高级杂志裸妆，底妆薄而通透，鼻梁和颧骨有细腻高光，睫毛根根分明，透明润唇膏让原生唇色更水润，脸部轮廓被修容整理得纤细干净',
            '复古港风柔雾妆，冷白雾面底妆，黑色眼线微微上挑，眼尾浅棕灰阴影轻轻拉长，原生唇色配透明水光唇彩边缘干净，脸部轮廓更冷艳成熟',
            '自然生活感淡妆，底妆保留真实皮肤纹理，眼影很浅，卧蚕微亮，嘴唇保持原生自然粉润水光，整体气质干净亲近',
            '清冷白开水妆，底妆薄透贴肤，眼影只用浅棕压出狐狸眼轮廓，睫毛自然分明，原生唇色覆透明无色水光唇彩，脸部线条干净温柔',
            '日系杂志清透桃花妆，冷白底妆带轻微粉色气色，眼尾浅棕晕染柔和，浅棕美瞳自然发亮，透明润唇膏让原生唇色更粉润水亮，五官显得亲近明亮',
            '高级摄影棚裸妆，底妆保留真实皮肤纹理，鼻梁和颧骨有细腻高光，眼线贴近睫毛根部，唇部保持原生唇色和透明滋润光，整体克制耐看',
            '复古柔雾妆，冷白雾面底妆压住油光，眼尾棕灰阴影轻轻拉长，原生唇色配无色润唇膏质感，脸部轮廓显得成熟安静'],
 'bold': ['冷艳猫眼妆，冷白底妆像瓷面一样干净，眼尾黑色眼线明显上扬，浓密睫毛压出危险感，浅棕瞳孔带细小水光，玻璃唇微微反光，鼻梁和唇峰高光锋利',
          '夜色魅惑妆，底妆冷白且带轻微湿光，柔棕轻烟熏在眼尾轻柔晕染，狐狸眼更狭长，睫毛浓密，纤薄原生唇形覆透明无色唇彩只带轻微水光，脸颊泛出淡淡自然红润',
          '高级私房妆，冷白底妆细腻无瑕，眼下有轻微粉色晕染，眼神显得湿润沉重，唇釉透明发亮，修容让尖下巴和高鼻梁更突出',
          '舞台感亮片猫眼妆，银白细闪集中在眼头和眼尾，黑色眼线锐利，浅棕瞳孔带反光，原生唇色透明玻璃唇微张时显得诱惑且直接',
          '冷艳猫眼妆，冷白底妆像瓷面一样细腻，黑色眼线锋利上挑，睫毛浓密压出侵略感，原生唇色透明玻璃唇反光明显，鼻梁和唇峰高光很锐',
          '湿润夜拍妆，底妆冷白并带轻微潮湿光泽，眼尾轻烟熏向外拉长，浅棕瞳孔直勾勾反光，唇部是原生唇色透明水光，脸颊带淡淡自然红润',
          '舞台私房亮片妆，银灰细闪集中在眼头和眼尾，黑色眼线强化狐狸眼，睫毛厚而卷翘，唇部是原生唇色透明玻璃质地，脸部精致又危险',
          '高压御姐妆，底妆冷白无瑕，修容强调高鼻梁和尖下巴，眼尾深棕上扬，纤薄嘴唇保持原生湿亮，表情空间天然带强烈支配感',
          '暗调胶片妆，冷白底妆被暖光压出柔和阴影，眼下带轻微自然红润，狐狸眼看起来沉重迷离，透明唇釉只让薄唇边界轻微发亮，五官更有成人魅惑感']}
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


def _options_for_aspect(value, aspect: str = 'portrait') -> list[str]:
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return []
    aspect_options = value.get(aspect)
    if isinstance(aspect_options, list):
        return aspect_options
    portrait_options = value.get('portrait')
    if isinstance(portrait_options, list):
        return portrait_options
    for item in value.values():
        if isinstance(item, list):
            return item
        if isinstance(item, dict):
            nested = _options_for_aspect(item, aspect)
            if nested:
                return nested
    return []


def character_identity_options_by_aspect(shot: str, aspect: str) -> list[str]:
    return _options_for_aspect(CHARACTER_IDENTITY_BY_SHOT[shot], aspect)


def makeup_options_by_aspect(scale: str, aspect: str) -> list[str]:
    return _options_for_aspect(MAKEUP_OPTIONS['normal' if scale == 'normal' else 'bold'], aspect)


def _normalize_pose_text(pose_text: str) -> str:
    brow_replacements = (
        ('从眉眼下方抬眸', '低头，抬眸'),
        ('从眉眼下方盯住镜头', '低头，盯住镜头'),
        ('从眉眼下方看向镜头', '低头，看向镜头'),
        ('从眉眼下方', '低头'),
        ('眉心', '眼神'),
        ('眉头', '眼角'),
        ('眉间', '眼神'),
        ('额心', '额头'),
        ('额间', '额头'),
        ('印堂', '额头'),
        ('眉眼下方', '眼睛下方'),
        ('眉峰轻轻上扬', '眼神微微上挑'),
        ('眉峰上扬', '眼神微微上挑'),
        ('眉毛自然舒展', '眼神自然放松'),
        ('眉眼', '眼睛'),
    )
    for source, replacement in brow_replacements:
        pose_text = pose_text.replace(source, replacement)
    pose_text = re.sub(r"(一手[^，。]{1,20}?)一手", r"\1另一手", pose_text)
    for source, replacement in _POSE_NORMALIZE_REPLACEMENTS:
        pose_text = pose_text.replace(source, replacement)
    return pose_text


def pose_expression_options_by_aspect(scale: str, shot: str, aspect: str) -> list[str]:
    """只服务四档：其余档位的姿势由 prompt_composer 从 art_direction_pools.json 组合。"""
    if scale != 'nsfw':
        raise ValueError(f'{scale} 的姿势由构图器生成，不读取旧姿势池')
    return [_normalize_pose_text(text) for text in _options_for_aspect(POSE_EXPRESSION_OPTIONS['nsfw'][shot], aspect)]


def _load_generated_prompt_data() -> None:
    import os
    if os.environ.get('RPP_IGNORE_GENERATED_PROMPT_DATA') == '1':
        return
    path = Path(__file__).resolve().parent / 'data' / 'prompt_pools.json'
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    for name in ('QUALITY_SUFFIX', 'NEGATIVE_PROMPT', 'CHARACTER_IDENTITY_BY_SHOT', 'MAKEUP_OPTIONS'):
        if name in data:
            globals()[name] = data[name]
    globals()['PROMPT_DATA_SOURCE'] = 'data/prompt_pools.json'


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
    required_shots = {'head_shot', 'upper_body', 'half_body', 'large_half_body', 'full_body'}
    if set(data) != required_shots:
        raise RuntimeError('四档姿势规则必须包含 5 种镜头：head_shot、upper_body、half_body、large_half_body、full_body。')
    cleaned = {}
    for shot in required_shots:
        options = data.get(shot)
        if not isinstance(options, list):
            raise RuntimeError(f'四档 {shot} 姿势规则必须是列表。')
        cleaned[shot] = [str(item).strip() for item in options if str(item).strip()]
        if len(cleaned[shot]) != 10:
            raise RuntimeError(f'四档 {shot} 姿势规则必须恰好为 10 条。')
    POSE_EXPRESSION_OPTIONS['nsfw'] = cleaned
    globals()['NSFW_POSE_EXPRESSION_SOURCE'] = 'data/nsfw_pose_expression_options.json'
    globals()['PROMPT_DATA_SOURCE'] = f"{globals()['PROMPT_DATA_SOURCE']} + data/nsfw_pose_expression_options.json"


PROMPT_DATA_SOURCE = 'prompt_data.py'
NSFW_POSE_EXPRESSION_SOURCE = 'prompt_data.py'
_load_generated_prompt_data()
_load_nsfw_pose_expression_json()
