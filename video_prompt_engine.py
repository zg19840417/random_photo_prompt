from __future__ import annotations
import random
import re
import time
VIDEO_SCOPE_ORDER = ('head', 'half_body', 'full_body')
VIDEO_SCOPE_MARKERS = {'head': ('头部', '肩膀及以上', '肩部以上', '脸部特写', '面部特写', '头部近景', '头部肖像'), 'half_body': ('半身', '大腿以上', '大腿以上', '腰线', '腰部'), 'full_body': ('全身', '完整身形', '从头到脚', '头顶到脚', '脚踝', '脚掌', '脚部', '脚尖', '鞋')}
VIDEO_POSE_MARKERS = {'lying': ('躺', '仰躺', '侧躺', '横躺', '平躺', '趴', '床中央', '睡着'), 'sitting': ('坐', '靠坐', '坐姿', '沙发', '椅', '床边', '台边'), 'kneeling': ('跪', '跪姿', '跪坐', '膝'), 'standing': ('站', '站立', '迈步', '走', '直立', '倚靠', '靠墙')}
VIDEO_ACTION_OPTIONS = {'head': {'eye_lip': ('她从当前头肩姿态开始，眼睛先看向画面下方，睫毛投下细小阴影，随后眼神慢慢抬回镜头中心，眼尾微微上扬，嘴唇从轻抿变成微张，嘴角露出带挑逗感的笑，右手指尖靠近脸侧整理发丝，头部轻轻偏向右肩，发丝贴着脸颊滑动，镜头缓慢推近到更贴脸的位置，最后停在半低头抬眼的表情。', '她先把视线从镜头左侧移回镜头中心，眼神由漫不经心变得主动，嘴角从冷淡变成俏皮笑，唇峰出现细小水光，右手从下巴旁边抬到脸侧，指尖轻轻拨开头发，头部慢慢向左偏，肩线跟着轻微下沉，光影从鼻梁滑到嘴唇边缘，最后用上目线直视镜头。'), 'near_camera': ('她从当前近景姿态开始，脸部先保持在画面中央，随后慢慢靠近镜头，眼神由漫不经心变成主动直视，嘴唇微张，呼吸让唇部水光轻微闪动，下巴轻轻抬起，右手从肩侧抬到发尾，发丝被拨到一边，镜头继续向前推进，脸部占据更多画面，最后嘴角露出得意笑并停住。',)}, 'half_body': {'waist_turn': ('她从当前半身姿态开始，头部先转向镜头，眼神锁住画面中心，随后半身明显前倾，右肩向前压近，腰线向左侧扭动，右手从锁骨滑到腰侧，左手扶住右侧腰线，身体重心慢慢向镜头靠近，头发跟着前倾晃动，镜头同步推近，嘴角从冷淡变成挑衅笑，最后贴近镜头停住。', '她先向后仰出胸口和腰部曲线，眼神仍然直盯镜头，随后身体向镜头方向回压，肩膀先转回正面，胸线跟着靠近画面，腰线再向侧面扭出弧度，右手沿腰侧向下移动，左手从发侧滑到肩头，头发在回压时轻轻甩动，光影沿腰线滑过，最后停在轻蔑又勾人的半身姿态。'), 'near_camera': ('她从当前半身姿态开始，先用眼神锁住镜头，随后腰部带动半身靠近，右手向镜头前景伸出形成近大远小，指尖短暂占据画面前方，左手停在腰侧，肩膀跟着向前压近，头发从背后滑到胸前，镜头略微后退再推近，嘴角慢慢上扬，最后身体停在更靠近镜头的位置。',)}, 'full_body': {'step_turn': ('她从当前全身姿态开始，先从侧身慢慢转向镜头，眼神提前锁住画面中心，随后左腿承重，右腿向镜头方向迈近一步，半身跟着前倾，肩线和腰线一起扭动，右手撩开头发，左手扶住腰侧，头发和配饰随着转身晃动，镜头同步向前推进，光影沿腿线和腰侧移动，最后抬起下巴露出挑衅笑容。', '她先用眼神锁定镜头，身体保持完整入画，随后左腿承重，右腿向前点地，腰线慢慢转向镜头，肩膀跟着回到正面，右手从发侧滑到腰侧，左手抬起制造手臂曲线，头发被手臂动作带动，镜头从脚下方向轻轻上推，最后停在更强势的全身展示姿态。'), 'lying_recline': ('她从当前横向全身姿态开始，先侧身抬眼看向镜头，右手撑住支撑面，随后肩背离开支撑面，腰线向镜头方向卷起，右腿轻轻伸展带动身体转动，左腿保持弯曲形成层次，头发铺开后向一侧滑动，镜头沿身体横向轻轻移动，光影从肩背滑到腰侧，最后半身靠近镜头并露出挑逗笑容。',), 'forced_perspective': ('她从当前全身姿态开始，先把右脚向镜头前方伸出形成强透视，脚部和小腿占据画面前景，随后身体重心向后拉开，左腿稳定支撑身体，腰线和肩线转向镜头，右手靠近脸侧整理头发，左手停在腰侧，镜头沿前景腿部向脸部推进，光影从脚背滑到腿线，最后抬眼直视镜头，嘴角带得意笑。',)}}
ACTION_PRIORITY_BY_SCOPE = {'head': ('eye_lip', 'near_camera'), 'half_body': ('waist_turn', 'near_camera'), 'full_body': ('step_turn', 'forced_perspective', 'lying_recline')}
LONG_DURATION_EXTRA_CLAUSES = {'head': ('眼神短暂移开又重新回到镜头中心', '右手指尖轻碰脸侧后慢慢放下', '发丝在脸颊旁轻轻晃动', '镜头停在更贴近眼睛和嘴唇的位置'), 'half_body': ('腰线再次向侧面拧出弧度', '右手从腰侧抬回锁骨旁边', '头发随着身体回压轻轻甩动', '镜头停在胸腰和表情都清楚的位置'), 'full_body': ('脚下重心再次调整，完整身形保持入画', '右手从腰侧抬到发侧，头发和配饰再次晃动', '镜头从腿部线条推到脸部表情', '光影沿肩线、腰线和腿部慢慢滑过')}
FORBIDDEN_BY_SCOPE = {'head': ('全身', '腰', '臀', '腿', '脚', '走', '迈', '胸口'), 'half_body': ('全身', '脚', '脚尖', '脚掌', '走', '迈近一步')}
NO_CHANGE_WORDS = ('保持原图', '延续原图', '保持不变', '不要变形', '不大幅变形', '克制', '轻微动作', '小幅动作')

def clean_video_action_text(value: str) -> str:
    text = ' '.join(str(value or '').split())
    for word in NO_CHANGE_WORDS:
        text = text.replace(word, '')
    text = re.sub('\\s+', ' ', text)
    return text.strip(' ，,。；;')

def normalize_video_seconds(value, default: int=8) -> int:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        seconds = default
    return max(6, min(20, seconds))

def infer_video_scope(prompt: str) -> str:
    text = str(prompt or '')
    for scope in VIDEO_SCOPE_ORDER:
        if any((marker in text for marker in VIDEO_SCOPE_MARKERS[scope])):
            return scope
    return ''

def infer_video_pose_family(prompt: str) -> str:
    text = str(prompt or '')
    for family, markers in VIDEO_POSE_MARKERS.items():
        if any((marker in text for marker in markers)):
            return family
    return ''

def _action_keys_for(scope: str, pose_family: str) -> tuple[str, ...]:
    keys = ACTION_PRIORITY_BY_SCOPE.get(scope) or ACTION_PRIORITY_BY_SCOPE['half_body']
    if pose_family == 'lying' and scope == 'full_body':
        return ('lying_recline', 'forced_perspective')
    if pose_family == 'standing' and scope == 'full_body':
        return ('step_turn', 'forced_perspective')
    return keys

def generate_video_action(source_prompt: str='', filename: str='', seed_text: str='', seconds: int | str=8) -> dict[str, str | bool]:
    seconds = normalize_video_seconds(seconds)
    scope = infer_video_scope(source_prompt) or 'half_body'
    pose_family = infer_video_pose_family(source_prompt)
    rng = random.Random(f'{filename}|{source_prompt}|{seed_text or time.time()}')
    action_key = rng.choice(_action_keys_for(scope, pose_family))
    options = VIDEO_ACTION_OPTIONS.get(scope, VIDEO_ACTION_OPTIONS['half_body']).get(action_key)
    if not options:
        options = VIDEO_ACTION_OPTIONS['half_body']['waist_turn']
    action = stage_video_action(rng.choice(options), seconds, scope)
    return {'action': action, 'scope': scope, 'pose_family': pose_family, 'action_key': action_key, 'used_source_prompt': bool(source_prompt)}

def validate_video_action_for_scope(action_text: str, scope: str) -> list[str]:
    text = clean_video_action_text(action_text)
    forbidden = FORBIDDEN_BY_SCOPE.get(scope, ())
    return [word for word in forbidden if word in text]

def estimate_video_seconds(action_text: str) -> int:
    text = clean_video_action_text(action_text)
    if not text:
        return 6
    stage_markers = ('先', '随后', '然后', '接着', '最后', '再', '同时', '逐渐', '从', '到')
    intensity_markers = ('大幅', '明显', '快速', '甩', '转身', '旋转', '跳', '走', '靠近', '贴近', '前倾', '后仰', '扭动', '摆动', '波浪', '伸出', '强透视')
    stage_count = sum((text.count(marker) for marker in stage_markers))
    intensity_count = sum((1 for marker in intensity_markers if marker in text))
    punctuation_count = sum((text.count(marker) for marker in ('，', '；', '、', ',', ';')))
    length_score = len(text) // 32
    score = stage_count + intensity_count + punctuation_count // 2 + length_score
    if score <= 3:
        return 4
    if score <= 8:
        return 6
    if score <= 12:
        return 8
    if score <= 17:
        return 10
    return 12

def _split_action_clauses(action_text: str) -> list[str]:
    text = clean_video_action_text(action_text)
    if not text:
        return []
    clauses = [part.strip(' ，,。；;') for part in re.split('[，。；;,]\\s*', text) if part.strip(' ，,。；;')]
    if len(clauses) <= 1:
        clauses = [part.strip(' ，,。；;') for part in re.split('(?:随后|然后|接着|最后|再)', text) if part.strip(' ，,。；;')]
    return clauses or [text]

def _balanced_stage_chunks(clauses: list[str], stage_count: int) -> list[list[str]]:
    chunks = [[] for _ in range(stage_count)]
    if not clauses:
        return chunks
    if len(clauses) >= stage_count:
        for index, clause in enumerate(clauses):
            target = min(stage_count - 1, index * stage_count // len(clauses))
            chunks[target].append(clause)
        last_non_empty = [clauses[-1]]
        for index, chunk in enumerate(chunks):
            if not chunk:
                chunks[index] = last_non_empty
        return chunks
    target_chars = max(18, sum((len(clause) for clause in clauses)) // stage_count)
    stage_index = 0
    current_len = 0
    for clause in clauses:
        if stage_index < stage_count - 1 and chunks[stage_index] and (current_len + len(clause) > target_chars):
            stage_index += 1
            current_len = 0
        chunks[stage_index].append(clause)
        current_len += len(clause)
    last_non_empty = [clause for clause in clauses[-1:]]
    for index, chunk in enumerate(chunks):
        if not chunk:
            chunks[index] = last_non_empty
    return chunks

def stage_video_action(action_text: str, seconds: int | str=8, scope: str='', allow_extras: bool=True) -> str:
    seconds = normalize_video_seconds(seconds)
    stage_count = max(1, (seconds + 1) // 2)
    clauses = _split_action_clauses(action_text)
    if not clauses:
        return ''
    extras = LONG_DURATION_EXTRA_CLAUSES.get(scope, ())
    if not extras:
        for candidate_scope, markers in VIDEO_SCOPE_MARKERS.items():
            if any((marker in action_text for marker in markers)):
                extras = LONG_DURATION_EXTRA_CLAUSES.get(candidate_scope, ())
                break
    while allow_extras and len(clauses) < stage_count and extras:
        clauses.append(extras[(len(clauses) - 1) % len(extras)])
    chunks = _balanced_stage_chunks(clauses, stage_count)
    stages = []
    for index in range(stage_count):
        start = index * 2
        end = min(seconds, (index + 1) * 2)
        if start >= seconds:
            break
        chunk = chunks[index]
        text = '，'.join((part for part in chunk if part))
        if index == stage_count - 1 and '最后' not in text:
            text = f'最后{text}'
        stages.append(f'{start}-{end}秒：{text}。')
    return '\n'.join(stages)

def video_prompt_from_action(action_text: str, source_prompt: str='', filename: str='', seed_text: str='', seconds: int | str | None=None) -> tuple[str, int]:
    resolved_seconds = normalize_video_seconds(seconds) if seconds is not None else None
    raw_text = str(action_text or '').strip()
    if raw_text and re.search('(?:^|\\n)\\s*\\d+\\s*-\\s*\\d+\\s*秒：', raw_text):
        return (raw_text, resolved_seconds or estimate_video_seconds(raw_text))
    text = clean_video_action_text(action_text)
    if not text:
        result = generate_video_action(source_prompt, filename, seed_text, resolved_seconds or 6)
        text = str(result['action'])
    elif resolved_seconds is not None:
        text = stage_video_action(text, resolved_seconds, infer_video_scope(source_prompt), allow_extras=False)
    return (text, resolved_seconds or estimate_video_seconds(text))
