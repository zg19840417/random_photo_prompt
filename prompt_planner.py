from __future__ import annotations
import random
COLOR_PALETTE_TABLE = ({'name': 'coral_lake_gold', 'colors': ('珊瑚粉', '湖蓝', '金色点缀'), 'keywords': ('珊瑚粉', '湖蓝', '海蓝', '金色', '泳池', '海边', '露台', '水光', '阳光'), 'scene_keywords': ('泳池', '海边', '沙滩', '游艇', '露台', '阳伞', '水面'), 'summary': '珊瑚粉、湖蓝和金色点缀'}, {'name': 'lemon_mint_silver', 'colors': ('柠檬黄', '薄荷绿', '银白细闪'), 'keywords': ('柠檬黄', '薄荷绿', '银白', '清爽', '花园', '泳池', '棚拍', '晴日'), 'scene_keywords': ('花园', '泳池', '棚拍', '白墙', '彩色墙面', '更衣间'), 'summary': '柠檬黄、薄荷绿和银白细闪'}, {'name': 'lavender_peach_crystal', 'colors': ('薰衣草紫', '桃橙', '浅粉'), 'keywords': ('薰衣草紫', '浅紫', '桃橙', '蜜桃橙', '浅粉', '窗光', '温柔'), 'scene_keywords': ('阳台', '窗', '室内', '露台', '浅彩墙面'), 'summary': '薰衣草紫、桃橙和浅粉'}, {'name': 'cherry_apple_sky', 'colors': ('樱桃粉', '苹果绿', '晴空蓝'), 'keywords': ('樱桃粉', '苹果绿', '晴空蓝', '糖果色', '甜', '俏皮', '鲜艳', '高饱和'), 'scene_keywords': ('甜品店', '棚拍', '花', '阳台', '彩色', '晴空'), 'summary': '樱桃粉、苹果绿和晴空蓝'}, {'name': 'rose_violet_orange', 'colors': ('玫瑰粉', '紫罗兰', '亮橙'), 'keywords': ('玫瑰粉', '紫罗兰', '亮橙', '热带', '花墙', '艳丽', '性感', '高对比'), 'scene_keywords': ('热带', '花墙', '花园', '露台', '度假', '喷泉'), 'summary': '玫瑰粉、紫罗兰和亮橙'}, {'name': 'tomato_cyan_white', 'colors': ('番茄红', '青蓝', '冷白高光'), 'keywords': ('番茄红', '青蓝', '孔雀蓝', '高对比', '冷白', '亮面', '棚拍', '彩色墙面'), 'scene_keywords': ('棚拍', '画廊', '彩色墙面', '白墙', '室内'), 'summary': '番茄红、青蓝和冷白高光'}, {'name': 'deep_red_gold_black', 'colors': ('暗红', '古铜金', '黑色'), 'keywords': ('暗红', '古铜金', '黑', '暗', '私房', '卧室', '酒店', '烛光', '丝绸', '金色'), 'scene_keywords': ('卧室', '酒店套房', '暗室', '烛光', '壁炉', '丝绒', '深色墙面'), 'summary': '暗红、古铜金和黑色'}, {'name': 'midnight_blue_silver', 'colors': ('午夜蓝', '银白细闪', '冷灰白'), 'keywords': ('午夜蓝', '银白', '冷灰', '月光', '夜晚', '露台', '夜景', '冰凉', '冷静'), 'scene_keywords': ('夜景', '露台', '落地窗', '月光', '泳池夜', '暗色', '城市天际线'), 'summary': '午夜蓝、银白细闪和冷灰白'}, {'name': 'burgundy_ivory_blush', 'colors': ('酒红', '象牙白', '浅粉'), 'keywords': ('酒红', '象牙白', '浅粉', '卧室', '柔软', '私密', '暖', '温柔', '亲密'), 'scene_keywords': ('卧室', '酒店', '窗边', '暗角', '壁灯', '纱帘'), 'summary': '酒红、象牙白和浅粉'}, {'name': 'amber_charcoal_rosegold', 'colors': ('琥珀', '炭灰', '玫瑰金'), 'keywords': ('琥珀', '炭灰', '玫瑰金', '烟雾', '暗调', '浴室', '昏暗', '高温', '暖意'), 'scene_keywords': ('浴室', '蒸汽', '昏暗', '烛台', '壁灯', '琥珀灯光', '深色瓷砖'), 'summary': '琥珀、炭灰和玫瑰金'})
FILTER_GRADE_TABLE = ({'name': 'sunny_clear_high_saturation', 'keywords': ('阳光', '晴天', '泳池', '海边', '露台', '水光', '柠檬黄', '湖蓝', '珊瑚粉'), 'quality': '阳光高饱和调色，清透高光，阴影干净', 'scales': ('normal', 'bold', 'nsfw')}, {'name': 'sweet_vivid_film', 'keywords': ('甜', '俏皮', '樱桃粉', '薄荷绿', '糖果色', '花园', '棚拍', '彩色墙面'), 'quality': '甜艳轻胶片调色，高饱和色块，细腻轻颗粒', 'scales': ('normal', 'bold', 'nsfw')}, {'name': 'glass_bright_contrast', 'keywords': ('窗光', '暖阳', '反射', '湖蓝', '浅紫', '浅粉', '高对比'), 'quality': '亮彩调色，高对比清亮反光，皮肤白但不过曝', 'scales': ('normal', 'bold', 'nsfw')}, {'name': 'warm_vacation_vivid', 'keywords': ('热带', '度假', '沙滩', '甲板', '桃橙', '玫瑰粉', '亮橙', '晴空'), 'quality': '暖阳度假调色，鲜艳背景色，肤色通透自然', 'scales': ('normal', 'bold', 'nsfw')}, {'name': 'dark_film_noir', 'keywords': ('暗红', '午夜蓝', '炭灰', '黑色', '暗调', '私房', '蜡烛', '深色', '低照度'), 'quality': '暗调胶片调色，低照度氛围，暗部细腻有纹理，高光暖金，阴影冷灰', 'scales': ('bold', 'nsfw')}, {'name': 'high_contrast_sensual', 'keywords': ('琥珀', '玫瑰金', '古铜金', '深色', '暗', '高对比', '光影', '性感', '私密'), 'quality': '高对比私房调色，亮部暖金高光，暗部深黑干净，皮肤局部高光强烈', 'scales': ('bold', 'nsfw')}, {'name': 'warm_boudoir_glow', 'keywords': ('酒红', '象牙白', '浅粉', '烛光', '壁灯', '温暖', '亲密', '柔软'), 'quality': '暖色私房辉光调色，暗角自然晕染，皮肤泛暖金色光晕，整体暧昧柔软', 'scales': ('bold', 'nsfw')}, {'name': 'cool_moonlit_drama', 'keywords': ('午夜蓝', '银白', '冷灰', '月光', '夜景', '冰凉', '城市', '露台', '玻璃'), 'quality': '冷月电影调色，蓝色调阴影，银色边缘光，肤色冷白通透，氛围孤冷性感', 'scales': ('bold', 'nsfw')}, {'name': 'erotic_boudoir_glow', 'keywords': ('情欲', '性', '床', '结合', '肌肤泛红', '私密', '湿润', '潮红'), 'quality': '高锐度私房情欲质感，皮肤泛情欲潮红光泽，暧昧幽暗光影氛围，湿润黏腻的体感', 'scales': ('nsfw',)}, {'name': 'wet_sensual_film', 'keywords': ('润滑', '汗珠', '水光', '湿润', '潮红', '黏腻', '纠缠', '深入'), 'quality': '湿润质感高对比，肌肤泛情欲光泽与汗光交织，暗部深黑亮部暖金，氛围氤氲暧昧', 'scales': ('nsfw',)})
DIRECTOR_TABLE = ({'name': 'sunny_multicolor_pool_glamour', 'keywords': ('阳光', '晴天', '泳池', '水光', '多色', '湖蓝', '薄荷绿', '珊瑚粉', '亮色', '高饱和'), 'focus': ('眼', '唇', '锁骨', '胸', '腰', '腿', '脚踝', '水面反光', '皮肤白'), 'scene_groups': ('室外', '野外')}, {'name': 'beach_vivid_glamour', 'keywords': ('海边', '沙滩', '浪花', '海蓝', '天空', '阳伞', '彩色', '珊瑚粉', '柠檬黄', '风', '艳丽'), 'focus': ('全身', '脚', '脚尖', '脚下', '地面', '腿线', '发丝', '回头', '皮肤白'), 'scene_groups': ('野外', '室外')}, {'name': 'garden_waterlight_seduction', 'keywords': ('花园', '花', '喷泉', '绿植', '草地', '暖阳', '多色', '薄荷绿', '玫瑰粉', '浅紫', '柔亮'), 'focus': ('眼', '手', '发丝', '肩颈', '锁骨', '腰', '低头', '抬眼', '甜美', '挑逗'), 'scene_groups': ('野外', '室外')}, {'name': 'color_balcony_light', 'keywords': ('阳台', '露台', '屋顶', '窗光', '反射', '晴空', '彩色', '湖蓝', '浅紫'), 'focus': ('眼', '唇', '手', '锁骨', '胸', '腰', '栏杆', '侧身', '回望', '皮肤白'), 'scene_groups': ('室内', '室外')}, {'name': 'bright_studio_color_fashion', 'keywords': ('棚拍', '工作室', '画廊', '白墙', '彩色墙面', '干净', '高对比', '高饱和', '阳光黄', '苹果绿'), 'focus': ('脸', '眼', '唇', '轮廓', '锁骨', '胸', '腰', '线条', '留白', '造型'), 'scene_groups': ('室内',)}, {'name': 'tropical_terrace_sensuality', 'keywords': ('热带', '度假', '露台', '藤编', '甲板', '彩色花', '天空光', '桃橙', '湖蓝', '芒果黄'), 'focus': ('全身', '腿', '腰', '臀线', '脚下', '地面', '风', '发丝', '皮肤白'), 'scene_groups': ('室外', '野外')}, {'name': 'sweet_vivid_tease', 'keywords': ('甜', '俏皮', '鲜艳', '樱桃粉', '桃橙', '柠檬黄', '浅紫', '亮片', '糖果色', '多色'), 'focus': ('眼', '唇', '手指', '舌尖', '肩', '锁骨', '胸', '撒娇', '挑逗', '坏笑'), 'scene_groups': ('室内', '室外')}, {'name': 'forced_perspective_focus', 'keywords': ('强透视', '近大远小', '前景', '靠近镜头', '低角度', '夸张透视', '视觉路径', '多色', '高对比'), 'focus': ('脚', '脚尖', '脚踝', '腿', '膝', '手', '手指', '唇', '舌尖', '胸', '腰', '臀线'), 'scene_groups': ('室内', '室外', '野外')}, {'name': 'dark_boudoir_intimate', 'keywords': ('暗室', '卧室', '酒店', '烛光', '暗红', '酒红', '古铜', '深色', '私密', '壁灯'), 'focus': ('眼', '唇', '舌尖', '锁骨', '胸', '腰', '髋', '臀线', '全身', '回头', '倚靠', '皮肤白'), 'scene_groups': ('室内',)}, {'name': 'bathroom_steam_lust', 'keywords': ('浴室', '蒸汽', '水汽', '玻璃', '雾面', '水珠', '瓷砖', '镜子', '潮湿', '昏暗'), 'focus': ('全身', '背', '臀线', '腿', '膝', '脚下', '地面', '镜面', '玻璃', '反光', '手指', '胸前'), 'scene_groups': ('室内',)}, {'name': 'midnight_balcony_seduction', 'keywords': ('夜景', '城市', '落地窗', '月光', '露台', '霓虹', '银白', '冷蓝', '风中', '天际线'), 'focus': ('全身', '腿', '腰', '臀', '回头', '风', '发丝', '倚靠', '栏杆', '脚下', '高挑'), 'scene_groups': ('室内', '室外')}, {'name': 'mirror_vanity_desire', 'keywords': ('镜前', '镜面', '梳妆台', '灯光', '倒影', '自我', '反射', '双重', '台面', '凳子'), 'focus': ('手', '手指', '唇', '眼', '脸', '锁骨', '胸', '倒影', '镜内', '镜外', '视觉路径'), 'scene_groups': ('室内',)})
EMOTION_INTENT_TABLE = ({'name': 'sunny_bright_smile', 'keywords': ('阳光', '明亮', '开心', '微笑', '大笑', '灿烂', '清爽', '笑容'), 'scales': ('normal', 'bold', 'nsfw')}, {'name': 'playful_tease', 'keywords': ('俏皮', '玩笑', '逗笑', '坏笑', '挑逗', '调皮', '甜', '笑意'), 'scales': ('normal', 'bold', 'nsfw')}, {'name': 'mock_blame_smile', 'keywords': ('怪罪', '责备', '假装', '嫌弃', '嘲弄', '忍不住笑', '笑着'), 'scales': ('normal', 'bold', 'nsfw')}, {'name': 'proud_showoff', 'keywords': ('得意', '展示', '自信', '挑衅', '明亮', '造型', '主动'), 'scales': ('normal', 'bold', 'nsfw')}, {'name': 'inviting_glamour', 'keywords': ('邀请', '勾人', '主动', '诱惑', '热烈', '直视', '靠近', '坏笑'), 'scales': ('bold', 'nsfw')}, {'name': 'amused_dominance', 'keywords': ('嘲笑', '审视', '轻蔑', '挑衅', '压迫感', '得意', '笑着'), 'scales': ('bold', 'nsfw')}, {'name': 'climax_ecstasy', 'keywords': ('高潮', '失神', '翻白', '痉挛', '战栗', '浪叫', '失控', '快感', '喷涌'), 'scales': ('nsfw',)}, {'name': 'desperate_longing', 'keywords': ('渴望', '乞求', '饥渴', '哀求', '迫不及待', '想要', '等不及', '渴求'), 'scales': ('nsfw',)}, {'name': 'submissive_surrender', 'keywords': ('顺从', '沉沦', '放弃', '完全交给', '闭上眼睛', '等待', '承受'), 'scales': ('nsfw',)}, {'name': 'painful_pleasure', 'keywords': ('痛苦', '快感', '极限', '撑开', '撕裂', '哭泣', '快乐又痛苦'), 'scales': ('nsfw',)})
VISUAL_FOCUS_BY_SHOT = {'head_shot': (('eyes_lips', ('眼', '眼神', '嘴角', '唇', '笑', '脸', '下巴')), ('hand_face', ('手', '手指', '指尖', '脸颊', '下巴', '前景')), ('neck_shoulders', ('肩', '颈', '肩颈', '锁骨', '发丝'))), 'half_body': (('waist_curve', ('腰', '腰线', '身体曲线', '侧身', '手')), ('chest_waist', ('胸', '胸口', '腰', '前倾', '靠近')), ('hand_foreground', ('手', '手指', '前景', '靠近镜头', '视觉路径'))), 'full_body': (('feet_ground', ('脚', '脚尖', '脚下', '地面', '站点', '全身')), ('long_leg_line', ('腿', '长腿', '腿线', '站姿', '迈步', '高挑')), ('whole_silhouette', ('全身', '轮廓', 'S形', '姿态', '身体线条')), ('forced_perspective', ('近大远小', '强透视', '前景', '靠近镜头')))}
POSE_FAMILY_TABLE = {'standing': ('站', '站立', '站姿', '直立', '迈步', '走', '脚下', '脚掌', '重心', '倚靠'), 'sitting': ('坐', '坐姿', '坐在', '边缘', '扶', '腰侧'), 'kneeling': ('跪', '跪姿', '跪坐', '膝', '半蹲', '蹲'), 'lying': ('躺', '侧躺', '仰躺', '横躺', '平躺', '趴', '横向', '沿宽画幅'), 'dynamic': ('跳', '跃起', '转身', '回头', '迈近', '摆动', '甩动', '抓拍'), 'foreground': ('近大远小', '强透视', '前景', '靠近镜头', '视觉路径')}
POSE_FAMILY_WEIGHTS = {'head_shot': {'dynamic': 3, 'foreground': 2, 'standing': 1}, 'half_body': {'dynamic': 3, 'sitting': 2, 'foreground': 2, 'standing': 1}, 'full_body': {'standing': 2, 'sitting': 3, 'kneeling': 3, 'lying': 4, 'dynamic': 3, 'foreground': 0}}

def choose(values, rng: random.Random) -> str:
    if not values:
        return ''
    return rng.choice(values)

def _score_keywords(text: str, keywords: tuple[str, ...]) -> int:
    source = str(text or '')
    return sum((1 for keyword in keywords if keyword and keyword in source))

def _director_keywords(director: dict | None) -> tuple[str, ...]:
    if not director:
        return ()
    return tuple(director.get('keywords', ())) + tuple(director.get('focus', ()))

def _director_score(text: str, director: dict | None) -> int:
    if not director:
        return 0
    source = str(text or '')
    return sum((1 for keyword in _director_keywords(director) if keyword and keyword in source))

def choose_color_palette(director: dict | None, scale: str, shot: str, aspect: str, rng: random.Random) -> dict:
    source = ' '.join(tuple(director.get('keywords', ())) + tuple(director.get('focus', ())) + tuple(director.get('scene_groups', ())) if director else ())
    weighted = []
    nsfw_palettes = {'deep_red_gold_black', 'midnight_blue_silver', 'burgundy_ivory_blush', 'amber_charcoal_rosegold'}
    for palette in COLOR_PALETTE_TABLE:
        score = _score_keywords(source, tuple(palette.get('keywords', ())) + tuple(palette.get('scene_keywords', ())))
        if scale in {'bold', 'nsfw'} and palette['name'] in {'rose_violet_orange', 'tomato_cyan_white'}:
            score += 1
        if scale == 'nsfw' and palette['name'] in nsfw_palettes:
            score += 3
        if shot == 'head_shot' and palette['name'] in {'lavender_peach_crystal', 'cherry_apple_sky'}:
            score += 1
        weighted.extend([palette] * (1 + min(score, 4)))
    return rng.choice(weighted or list(COLOR_PALETTE_TABLE))

def choose_filter_grade(scale: str, director: dict | None, palette: dict | None, scene_light: str, rng: random.Random) -> dict:
    source = ' '.join(tuple(director.get('keywords', ())) + tuple(palette.get('keywords', ())) + tuple(palette.get('colors', ())) + (str(scene_light or ''),) if director and palette else (str(scene_light or ''),))
    bright_scene = any((marker in source for marker in ('阳光', '暖阳', '窗光', '晴天', '明亮', '棚拍', '彩色墙面', '泳池', '海边', '露台', '花园', '度假')))
    dark_grades = {'dark_film_noir', 'high_contrast_sensual', 'warm_boudoir_glow', 'cool_moonlit_drama'}
    weighted = []
    eligible = [g for g in FILTER_GRADE_TABLE if scale in g.get('scales', ('normal', 'bold', 'nsfw'))]
    for grade in eligible:
        if bright_scene and grade.get('name') in dark_grades:
            continue
        score = _score_keywords(source, tuple(grade.get('keywords', ())))
        weighted.extend([grade] * (1 + min(score, 4)))
    fallback = [g for g in FILTER_GRADE_TABLE if scale in g.get('scales', ('normal', 'bold', 'nsfw'))]
    return rng.choice(weighted or fallback or list(FILTER_GRADE_TABLE))

def choose_emotion_intent(scale: str, director: dict | None, rng: random.Random) -> dict:
    candidates = [item for item in EMOTION_INTENT_TABLE if scale in item.get('scales', ())]
    director_source = ' '.join(_director_keywords(director))
    weighted = []
    nsfw_emotions = {'climax_ecstasy', 'desperate_longing', 'submissive_surrender', 'painful_pleasure'}
    for item in candidates:
        score = _score_keywords(director_source, tuple(item.get('keywords', ())))
        if scale == 'nsfw' and item['name'] in nsfw_emotions:
            score += 3
        if director and director.get('name') == 'sweet_vivid_tease' and (item['name'] in {'playful_tease', 'mock_blame_smile'}):
            score += 2
        if director and director.get('name') == 'forced_perspective_focus' and (item['name'] in {'proud_showoff', 'inviting_glamour'}):
            score += 1
        weighted.extend([item] * (1 + min(score, 4)))
    return rng.choice(weighted or candidates)

def choose_visual_focus(shot: str, director: dict | None, rng: random.Random) -> tuple[str, tuple[str, ...]]:
    candidates = VISUAL_FOCUS_BY_SHOT.get(shot, VISUAL_FOCUS_BY_SHOT['full_body'])
    director_source = ' '.join(_director_keywords(director))
    weighted = []
    for name, keywords in candidates:
        score = _score_keywords(director_source, keywords)
        if director and director.get('name') == 'forced_perspective_focus' and (name in {'forced_perspective', 'hand_foreground', 'knee_foreground'}):
            score += 1
        weighted.extend([(name, keywords)] * (1 + min(score, 4)))
    return rng.choice(weighted or list(candidates))

def classify_pose_family(text: str) -> str:
    source = str(text or '')
    scores = {family: sum((1 for marker in markers if marker and marker in source)) for family, markers in POSE_FAMILY_TABLE.items()}
    best_family, best_score = max(scores.items(), key=lambda item: item[1])
    return best_family if best_score else 'dynamic'

def choose_pose_family(shot: str, aspect: str, visual_focus: str, rng: random.Random) -> str:
    weights = dict(POSE_FAMILY_WEIGHTS.get(shot, POSE_FAMILY_WEIGHTS['full_body']))
    if aspect == 'landscape':
        weights['lying'] = weights.get('lying', 1) + 4
        weights['standing'] = max(0, weights.get('standing', 0) - 2)
    elif shot == 'full_body':
        weights['standing'] = weights.get('standing', 1) + 1
    if visual_focus in {'forced_perspective', 'hand_foreground', 'knee_foreground'}:
        weights['foreground'] = weights.get('foreground', 0) + 1
    if visual_focus in {'feet_ground', 'long_leg_line'}:
        weights['standing'] = weights.get('standing', 1) + 2
    pool = [family for family, weight in weights.items() for _ in range(max(0, int(weight)))]
    return rng.choice(pool or ['dynamic'])

def choose_director(scale: str, shot: str, aspect: str, rng: random.Random) -> dict:
    candidates = list(DIRECTOR_TABLE)
    if scale == 'normal':
        candidates = [item for item in candidates if item['name'] in {'beach_vivid_glamour', 'garden_waterlight_seduction', 'color_balcony_light', 'bright_studio_color_fashion', 'tropical_terrace_sensuality', 'sweet_vivid_tease'}]
    elif scale == 'bold':
        candidates = [item for item in candidates if item['name'] in {'sunny_multicolor_pool_glamour', 'beach_vivid_glamour', 'garden_waterlight_seduction', 'color_balcony_light', 'bright_studio_color_fashion', 'tropical_terrace_sensuality', 'sweet_vivid_tease', 'forced_perspective_focus', 'dark_boudoir_intimate', 'bathroom_steam_lust', 'midnight_balcony_seduction', 'mirror_vanity_desire'}]
    if shot == 'head_shot':
        candidates = [item for item in candidates if item['name'] not in {'beach_vivid_glamour', 'tropical_terrace_sensuality'}]
    if aspect == 'landscape':
        candidates = [item for item in candidates if item['name'] not in {'bright_studio_color_fashion'}] or list(DIRECTOR_TABLE)
    return rng.choice(candidates or list(DIRECTOR_TABLE))

def choose_directed(values, rng: random.Random, director: dict | None=None, extra_keywords: tuple[str, ...]=(), required_family: str | None=None) -> str:
    if not values:
        raise ValueError('Prompt pool is empty')
    if not director and (not extra_keywords) and (not required_family):
        return rng.choice(values)
    if director and director.get('name') == 'forced_perspective_focus' and (rng.random() < 0.35):
        perspective_values = [value for value in values if any((marker in str(value or '') for marker in ('近大远小', '强透视', '前景', '靠近镜头', '视觉路径')))]
        if perspective_values:
            values = perspective_values
    if required_family:
        family_values = [value for value in values if classify_pose_family(value) == required_family]
        if family_values:
            values = family_values
    weighted = []
    for value in values:
        score = _director_score(value, director)
        score += sum((1 for keyword in extra_keywords if keyword and keyword in str(value or '')))
        if required_family and classify_pose_family(value) == required_family:
            score += 3
        weighted.extend([value] * (1 + min(score, 4)))
    return rng.choice(weighted or values)

def choose_scene_light(values, rng: random.Random, director: dict | None=None, palette: dict | None=None) -> str:
    if isinstance(values, dict):
        groups = {group: options for group, options in values.items() if options}
        if not groups:
            raise ValueError('Prompt pool is empty')
        preferred_groups = tuple(director.get('scene_groups', ())) if director else ()
        palette_scene_keywords = tuple(palette.get('scene_keywords', ())) if palette else ()
        group_pool = []
        for group, options in groups.items():
            weight = 3 if group in preferred_groups else 1
            group_text = ' '.join((str(option or '') for option in options))
            if any((keyword in group_text for keyword in palette_scene_keywords)):
                weight += 2
            group_pool.extend([group] * weight)
        group = rng.choice(group_pool or list(groups))
        return choose_directed(groups[group], rng, director, palette_keywords(palette))
    return choose_directed(values, rng, director, palette_keywords(palette))

def scene_context_keywords(scene_light: str) -> tuple[str, ...]:
    text = str(scene_light or '')
    contexts = ((('海', '沙滩', '浪', ' shoreline'), ('海', '沙', '脚', '脚尖', '脚踝', '腿', '风', '阳伞', '珊瑚粉', '湖蓝')), (('泳池', '池边', '水面', 'pool'), ('泳池', '水', '脚', '脚踝', '腿', '湿', '躺椅', '湖蓝', '薄荷绿')), (('花园', '花', '喷泉', '草地', '绿植'), ('花', '喷泉', '手', '发丝', '回头', '低头', '甜', '玫瑰粉', '浅紫')), (('露台', '阳台', '屋顶', '天台', '甲板'), ('露台', '阳台', '栏杆', '扶', '侧身', '回望', '脚下', '晴空', '桃橙', '柠檬黄')), (('窗', '反射', '浅彩墙面'), ('手', '锁骨', '胸', '腰', '反射', '浅紫', '亮粉')), (('棚拍', '工作室', '画廊', '白墙', '投影'), ('棚拍', '造型', '线条', '前景', '强透视', '彩色', '阳光黄', '苹果绿')))
    keywords: list[str] = []
    for markers, values in contexts:
        if any((marker in text for marker in markers)):
            keywords.extend(values)
    return tuple(dict.fromkeys(keywords))

def palette_keywords(palette: dict | None) -> tuple[str, ...]:
    if not palette:
        return ()
    return tuple(palette.get('keywords', ())) + tuple(palette.get('colors', ())) + tuple(palette.get('scene_keywords', ()))

def intent_keywords(*items) -> tuple[str, ...]:
    keywords: list[str] = []
    for item in items:
        if isinstance(item, dict):
            keywords.extend((str(keyword) for keyword in item.get('keywords', ()) if keyword))
        elif isinstance(item, (tuple, list, set)):
            keywords.extend((str(keyword) for keyword in item if keyword))
        elif item:
            keywords.append(str(item))
    return tuple(dict.fromkeys(keywords))
