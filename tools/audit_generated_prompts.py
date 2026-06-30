from __future__ import annotations
import argparse
import importlib.util
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_PATH = ROOT / 'docs' / 'reports' / 'generated_prompt_audit.md'
SCALES = ('normal', 'bold', 'bold_no_outfit', 'nsfw')
SHOTS = ('head_shot', 'half_body', 'full_body')
SHOT_INPUTS = {'head_shot': '头部', 'half_body': '半身', 'full_body': '全身'}
EXPECTED_DIMENSIONS = {'normal': ('camera', 'character', 'outfit', 'pose_expression', 'scene_light'), 'bold': ('camera', 'character', 'outfit', 'pose_expression', 'scene_light'), 'bold_no_outfit': ('camera', 'character', 'pose_expression', 'scene_light'), 'nsfw': ('camera', 'character', 'pose_expression', 'scene_light')}
DIMENSION_LABELS = {'camera': '镜头', 'character': '角色容貌和身材', 'makeup': '妆容', 'outfit': '穿着', 'pose_expression': '姿势和神情', 'scene_light': '场景和光线', 'quality': '固定提示词'}
CLAUSE_SPLIT_RE = re.compile('[。；;，,、\\n]+')
CHINESE_PHRASE_RE = re.compile('[\\u4e00-\\u9fffA-Za-z0-9]{4,}')
COMMON_REPEAT_FRAGMENTS = {'脸部', '镜头', '眼睛', '嘴唇', '黑发', '冷白', '高光', '线条', '边缘', '形成', '完整', '清晰', '画面', '人物', '韩国女性', '真实写真', '电影感光影', 'bestquality', 'ultradetailed'}
POSE_CAMERA_OWNERSHIP_TERMS = ('横屏', '竖屏', '横构图', '竖构图', '横向构图', '竖向构图', '镜头拉开', '镜头垂直', '完整身高', '构图留白')
LYING_POSE_TERMS = ('仰躺', '侧躺', '横躺', '平躺', '躺在', '床面', '顶视角', '俯拍')
UPRIGHT_CAMERA_TERMS = ('竖构图', '窄长', '站立', '从头顶到脚掌', '小腿、脚踝', '脚下')
PORTRAIT_ORIENTATION_TERMS = ('竖构图', '窄长', '竖屏')
LANDSCAPE_ORIENTATION_TERMS = ('横屏', '横向', '横构图')
HORIZONTAL_BODY_TERMS = ('横向', '宽画幅', '横躺', '侧躺', '平躺', '仰躺', '斜向仰躺', '横向靠', '横向坐', '横向趴', '横向倚', '横向后', '横跨', '侧躺式', '沿画面宽度', '沿宽画幅', '向一侧延伸', '斜向铺')
VERTICAL_BODY_TERMS = ('竖向', '站立', '自然站立', '直立', '坐立', '跪坐', '竖向坐', '竖向跪', '从头顶到脚掌', '从上到下', '纵向', '挺直', '竖构图')
MOBILE_RESOLUTION_RULES = {'full_body': ((('大字', '四肢展开', '双臂自然向两侧展开', '手脚乱舞', '跳', '跃起', '腾空'), {'aspect': 'landscape', 'framing': '横向全身动态宽构图，四肢外轮廓完整，四周留白'}), (('俯拍', '顶视角', '正上方', '仰躺', '躺', '侧躺', '横躺', '床中央', '睡', '睡着'), {'aspect': 'landscape', 'framing': '横向全身构图，身体沿宽画幅展开，从头到脚完整入镜'}), (('坐', '坐姿', '跪', '跪姿', '膝', '蹲', '蜷', '抱膝', '直立', '站', '站立', '竖向', '纵向'), {'aspect': 'portrait', 'framing': '竖向全身构图，头部、手臂、腿部、脚部和姿势外轮廓完整'}), (('站', '站立', '倚靠', '靠墙', '迈步', '走', '单腿', '重心', '伸直', '脚尖', '脚掌'), {'aspect': 'portrait', 'framing': '窄长全身构图，从头顶到脚掌完整入镜，脚下留地面边距'})), 'half_body': ((('横躺', '侧躺', '仰躺', '平躺', '俯拍', '顶视角', '床', '横向', '横跨', '横向靠', '横向坐', '横向趴', '沿宽画幅', '斜向铺'), {'aspect': 'landscape', 'framing': '横向半身镜头，大腿以上入镜，头部、肩颈、胸部和腰部完整'}), (('坐', '坐姿', '跪', '跪坐', '膝', '直立', '站', '站立', '竖向', '纵向'), {'aspect': 'portrait', 'framing': '竖向半身镜头，大腿以上入镜，头部、胸腰和双手入镜'})), 'head_shot': ((('横向', '侧脸', '躺', '侧躺'), {'aspect': 'landscape', 'framing': '横向头部镜头，肩膀及以上入镜，头顶完整'}),)}
MOBILE_DEFAULT_RESOLUTIONS = {'full_body': {'aspect': 'portrait', 'framing': '竖向全身构图，从头到脚完整入镜，姿势外轮廓完整'}, 'half_body': {'aspect': 'portrait', 'framing': '竖向半身镜头，大腿以上入镜，头部、胸腰和双手入镜'}, 'head_shot': {'aspect': 'portrait', 'framing': '头部镜头，肩膀及以上入镜，头顶完整'}}
MOBILE_DIRECTOR_RESOLUTION_RULES = {'minimal_gallery_bodyline': {'full_body': {'aspect': 'portrait', 'framing': '竖向全身留白构图，从头到脚完整入镜，脚下留地面边距'}, 'half_body': {'aspect': 'portrait', 'framing': '竖向半身留白构图，大腿以上入镜，头部和胸腰完整'}, 'head_shot': {'aspect': 'portrait', 'framing': '竖向头部极简构图，肩膀及以上入镜，头顶完整'}}, 'nightclub_queen': {'full_body': {'aspect': 'portrait', 'framing': '竖向全身舞台构图，从头到脚完整入镜，脚下地面边距清楚'}, 'half_body': {'aspect': 'portrait', 'framing': '竖向半身压迫构图，大腿以上入镜，脸部和胸腰清楚'}, 'head_shot': {'aspect': 'portrait', 'framing': '竖向头部压迫近景，肩膀及以上入镜，头顶完整'}}, 'soft_private_room': {'full_body': {'aspect': 'landscape', 'framing': '横向全身私房构图，身体沿宽画幅展开，从头到脚完整入镜'}, 'half_body': {'aspect': 'landscape', 'framing': '横向半身私房构图，大腿以上入镜，头部和胸腰完整'}}, 'mirror_private_space': {'full_body': {'aspect': 'portrait', 'framing': '竖向全身镜面构图，从头到脚完整入镜，脚下留地面边距'}, 'half_body': {'aspect': 'portrait', 'framing': '竖向半身镜面构图，大腿以上入镜，头部和胸腰完整'}}, 'wet_film_mood': {'full_body': {'aspect': 'landscape', 'framing': '横向全身湿感构图，身体沿宽画幅展开，从头到脚完整入镜'}, 'half_body': {'aspect': 'landscape', 'framing': '横向半身湿感构图，大腿以上入镜，留出环境反光'}}, 'wild_natural_sensuality': {'full_body': {'aspect': 'landscape', 'framing': '横向全身自然环境构图，从头到脚完整入镜，四周留环境空间'}, 'half_body': {'aspect': 'landscape', 'framing': '横向半身自然环境构图，大腿以上入镜，保留环境空间'}}}
MOBILE_FRAMING_COMPACT_REPLACEMENTS = {'妯\ue044悜鍏ㄨ韩鍔ㄦ€佸\ue194鏋勫浘锛屽洓鑲㈠\ue63b杞\ue1bc粨瀹屾暣锛屽洓鍛ㄧ暀鐧?': '横向动态宽构图，四周留白', '妯\ue044悜鍏ㄨ韩鏋勫浘锛岃韩浣撴部瀹界敾骞呭睍寮€锛屼粠澶村埌鑴氬畬鏁村叆闀?': '横向宽构图，身体沿画幅展开', '绔栧悜鍏ㄨ韩鏋勫浘锛屽ご閮ㄣ€佹墜鑷傘€佽吙閮ㄣ€佽剼閮ㄥ拰濮垮娍澶栬疆寤撳畬鏁?': '竖向全身构图，外轮廓完整', '绐勯暱鍏ㄨ韩鏋勫浘锛屼粠澶撮《鍒拌剼鎺屽畬鏁村叆闀滐紝鑴氫笅鐣欏湴闈㈣竟璺?': '窄长全身构图，脚下留地面边距', '妯\ue044悜鍗婅韩闀滃ご锛岃叞閮ㄥ強浠ヤ笂鍏ラ暅锛屽ご閮ㄣ€佽偐棰堛€佽兏閮ㄥ拰鑵伴儴瀹屾暣': '横向半身构图，大腿以上完整', '绔栧悜鍗婅韩闀滃ご锛岃叞閮ㄥ強浠ヤ笂鍏ラ暅锛屽ご閮ㄣ€佽兏鑵板拰鍙屾墜瀹屾暣': '竖向半身构图，胸腰和双手入镜', '妯\ue044悜澶у崐韬\ue0a6暅澶达紝灏忚吙鍙婁互涓婂叆闀滐紝韬\ue0a1綋娌垮\ue194鐢诲箙灞曞紑鍒板皬鑵?': '横向半身构图，身体沿宽画幅展开', '绔栧悜澶у崐韬\ue0a6暅澶达紝灏忚吙鍙婁互涓婂叆闀滐紝澶撮儴鍒板皬鑵垮畬鏁?': '竖向半身构图，头部到大腿完整', '妯\ue044悜涓婂崐韬\ue0a6暅澶达紝鑳搁儴鍙婁互涓婂叆闀滐紝澶撮《瀹屾暣': '横向半身构图，头顶完整', '妯\ue044悜澶撮儴闀滃ご锛岃偐鑶€鍙婁互涓婂叆闀滐紝澶撮《瀹屾暣': '横向头部构图，头顶完整', '绔栧悜鍏ㄨ韩鏋勫浘锛屼粠澶村埌鑴氬畬鏁村叆闀滐紝濮垮娍澶栬疆寤撳畬鏁?': '竖向全身构图，外轮廓完整', '涓婂崐韬\ue0a6暅澶达紝鑳搁儴鍙婁互涓婂叆闀滐紝澶撮《瀹屾暣锛岀敾闈㈠仠鍦ㄤ笂鑵?': '竖向半身构图，头顶完整', '澶撮儴闀滃ご锛岃偐鑶€鍙婁互涓婂叆闀滐紝澶撮《瀹屾暣': '竖向头部构图，头顶完整'}

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
CONCEPT_GROUPS = {'skin_whiteness': ('冷白', '白皙', '瓷白', '通透', '白净', '显白', '白皮', '冷瓷', 'porcelain'), 'gaze_pressure': ('直视', '凝视', '看向镜头', '盯', '眼神', '视线', '压迫', '挑衅', '藐视', '审视'), 'lips': ('嘴唇', '薄唇', '唇', '唇形', '唇面', '嘴角'), 'chest_focus': ('胸部', '完整胸部', '胸线', '胸腰', '胸前', '胸口', '上胸', '胸'), 'waist_focus': ('腰线', '细腰', '腰部', '腰', '小蛮腰'), 'leg_focus': ('长腿', '腿部', '腿线', '大腿', '小腿', '膝盖', '脚部', '脚下', '脚尖', '脚跟'), 'glamour_tone': ('glamour', '成人', '私房', '情欲', '性感', '诱惑', '撩人', '冷艳', '高级', '张力'), 'light_highlight': ('高光', '柔光', '光泽', '反光', '提亮', '照亮', '明暗', '暗部', '阴影', '层次'), 'body_curve': ('曲线', '轮廓', '线条', '身形', '身材', '外轮廓')}
MAX_POSITIVE_PROMPT_LENGTH = 800
PROMPT_LENGTH_BUDGETS = {'head_shot': MAX_POSITIVE_PROMPT_LENGTH, 'half_body': MAX_POSITIVE_PROMPT_LENGTH, 'full_body': MAX_POSITIVE_PROMPT_LENGTH}
DIMENSION_LENGTH_BUDGETS = {'camera': 90, 'character': 210, 'makeup': 90, 'outfit': 140, 'pose_expression': 170, 'scene_light': 180, 'quality': 130}
PROMPT_PART_ORDER = ('camera', 'character', 'outfit', 'pose_expression', 'scene_light', 'quality')
PHOTOGRAPHIC_NATURALNESS_MARKERS = ('真实皮肤纹理', '自然皮肤纹理', '真实镜头景深', '清晰镜头景深', '高光不过曝', '暗部有层次', '真实反光', '细颗粒')
CONCRETE_PHOTO_MARKERS = ('高光', '阴影', '暗部', '层次', '边缘光', '轮廓光', '反光', '景深', '胶片', '调色', '颗粒', '肤质', '肤纹')
GENERIC_QUALITY_MARKERS = ('高级', '质感', '氛围', '大片', '真实写真', 'ultra detailed')
SENSUAL_TENSION_MARKERS = ('直视', '凝视', '盯', '眼神', '挑衅', '克制微笑', '嘴角', '锁骨', '胸腰', '腰线', '臀腿', '大腿', '曲线', '贴近', '压向镜头')
SEDUCTIVE_LIGHT_MARKERS = ('清晨', '晨光', '银蓝晨光', '正午', '天光', '下午', '斜光', '黄昏', '落日', '晚霞', '夜景', '深夜', '夜色', '雨后', '雨夜', '床头', '床头灯', '暗光', '暗部', '霓虹', '灯带', '窄光', '侧光', '暖光', '暖粉侧光', '暖金侧光', '黄铜壁灯', '镜面', '湿光', '低位', '窗外城市', '水面反光', '月光', '烛光')
SEDUCTIVE_TIME_MARKERS = ('清晨', '晨光', '正午', '天光', '下午', '黄昏', '落日', '晚霞', '深夜', '夜景', '夜色', '雨后', '雨夜', 'Art Deco酒廊')
TEASING_POSE_MARKERS = ('舌尖', '俯视镜头', '低机位', '贴近镜头', '靠近镜头', '脚尖', '脚掌', '裸足', '足弓', '手指', '黑色指甲', '黑色手指甲', '脸旁', '唇边', '肩膀', '锁骨', '胸前', '腰侧', '大腿', '眼神微眯', '斜看镜头')
THEME_LOCATION_TERMS = ('夜店', '吧台', '卧室', '床边', '浴室', '镜面', '泳池', '玻璃温室', '绿植', '庭院', '植物', '森林', '木栈道', '酒廊', '古代', '雨夜廊下', '青瓦', '木柱', '宫苑夜宴', '屏风', '酒案', '宫灯', '书房夜读', '卷轴', '香炉', '敦煌', '壁画', '温泉', '竹帘', '画舫', '雕花窗', '竹林', '戏台后台', '红木妆台', '铜镜', '苗疆', '银饰', '民国', '老洋房')
THEME_OUTFIT_TERMS = ('黑色', '亮钻', '胸衣', '身体链', '银色', '腰链', '蕾丝', '吊带', '短裙', '网纱', '丝袜', '薄纱', '短上衣', '法式短上衣', '细项圈', '斜肩', '连体泳装', '挂脖', '细带', '脚踝链', '缎面', '金属扣', '深V领', '吊带丝袜', '交领', '披帛', '绣边', '绣鞋', '唐制', '织金', '短襦', '高腰裙', '宋制', '褙子', '月白', '玉坠', '舞姬', '臂钏', '流苏', '江南', '抹胸', '青绿山水', '花魁', '步摇', '盘扣', '苗疆', '银链', '银铃', '刺绣', '民国', '蕾丝立领', '象牙白', '浅金缎面', '珍珠')
THEME_POSE_TERMS = ('坐', '吧台', '酒杯', '前倾', '回望', '手', '床沿', '床边', '侧躺', '斜靠', '后靠', '双腿', '裸足', '跨步', '镜头', '锁骨', '肩颈', '手指', '食指', '指尖', '腰侧', '低机位', '全身', '脚尖', '腿', '俯视', '站', '倚靠', '侧身', '脚下', '吧椅', '大腿', '跪坐', '低坐', '廊下', '手扶', '低案', '舞', '抬手', '扭腰', '手臂', '水边', '船舷', '窗边', '竹林', '妆台', '铜镜', '手腕')
HAND_TO_CAMERA_PATTERNS = (re.compile('(?:左手|右手|一只手|手指|手掌)[^，。]{0,14}(?:伸向|贴近|靠近)镜头'), re.compile('(?:左手|右手|一只手|手指|手掌)[^，。]{0,14}(?:画面前缘|画面前景)'), re.compile('(?:左手|右手|一只手|手指|手掌)[^，。]{0,14}近大远小'))
BOLD_OUTFIT_NUDE_RISK_MARKERS = ('极少覆盖', '最低覆盖', '覆盖面积极少', '极少量半透明必要遮挡', '半透明必要遮挡', '必要遮挡', '近似饰品', '接近饰品', '几乎没有完整衣物轮廓', '几乎没有传统衣物轮廓', '不形成完整上衣或裙装轮廓', '布料存在感降到最低', '轻薄料少到近似饰品', '大片皮肤边距', '只剩几条窄带', '只有极细窄带', '微型布片', '小片不透明布片')
BOLD_OUTFIT_BANNED_MATERIAL_MARKERS = ('乳胶', '乳胶感', '亮面皮革', '皮革', '皮质', '皮裙', 'PVC', 'pvc', 'latex', 'leather')
FINAL_PROMPT_BAD_PHRASES = ('横向竖向', '横向平视腰部及以', '看着向镜头', '斜看观众', '形成近景焦点', '嘴角是眼神', '嘴角是明亮嘲弄笑', '浅淡微笑意', '表情眼神', '画，面', '把，阳光', '大下巴', '大膝盖', '非显式边界', '维持清晰姿态边界', '诱惑焦点', '诱惑感集中', '带着勾引意味', '私密邀请感', '私房张力', '压住镜头', '让手脚更醒目', '完整身体轮廓', '双乳挺立', '甜中带藐视', '表情微笑', '嘴角带浅淡微笑感', '嘴角带一点嘴角', '眼神斜看镜头和', '腰部、腰部', '乳沟深邃', '从上方角度可以看到', '双手手指轻轻按压在自己胸前', '乳尖在衣物下挺立', '双乳在胸前挺立', '宽大的，落地', '午后，光线', '高光把画面推到近处', '高光地画面推到近处', '彩色棚拍近景', '视线沿手指', '抬眼露出嘴角', '抬眼露出甜美又危险', '甜美又危险的挑逗笑', '成为构图重点', '脚部落点', '连续拉开', '非室内道具', '人物轮廓清楚轻盈', '强烈诱惑的竖向构图', '，。', '收出腰线', '贴颈细项圈', '贴锁细项圈', '胸腰和双手完整', '形成斜向对角线', '眼神燃跳', '托亮身体全色阳光镶边', '人物轮廓带出轻盈轮廓', '轻轻侧偏带浅淡', '侧偏带浅淡', '竖向S形曲线', '纵向S曲线', '纵向S形曲线', '完整S线', '被姿态拉开', '双手引导视线经过', '墙角或，', '显得更有冲击力', '成为画面重点', '形成横向张力', '形成竖向曲线', '形成紧张对角线', '紧张对角线', '竖向坐立', '眼神看向镜头', '狐眼眼神放松带', '自然反光托亮人物边缘', '明亮笑弧', '小号刺绣标出现在画面下缘', '性感更直接', '更直接', '眼神眼神', '嘴角嘴角', '身体身体', '彩色光只停在水面边缘', '日光反射到身体边缘', '手指从画面前景靠近唇边，近大远小', '她抬眼', '透明薄唇', '肩线保持干净', '横向展开左手', '肩颈线条眼神', '眼神勾人地看向镜头', '近处手掌贴近镜头，脚尖落在画面下缘，近处手掌贴近镜头', '她抬眼微笑', '抬眼微笑', '让腿部和手指更醒目', '保持优雅S线', '的裤腰', '腰部以半身', '上下呼应', '很浅的浅淡')
NON_VISUAL_SCENE_PHRASES = ('空气里弥漫', '空气中充满', '空气中是', '气息', '花香', '水声', '回响', '传来', '让人联想到')
ABSTRACT_POSE_PHRASES = ('勾引意味', '诱惑感集中', '压迫感', '藐视感', '私密邀请', '勾人弧度', '视觉路径', '视线沿手指', '画面大胆', '姿态边界', '构图重点', '连续拉开')
DETACHED_FOOT_PHRASES = ('一只裸足', '一只脚掌', '一只脚尖', '裸足停在', '脚掌和脚尖靠近镜头')
CONNECTED_FOOT_CHAIN_MARKERS = ('前腿', '小腿', '脚踝', '腿部末端')
HUMAN_REVIEW_ABSTRACT_MARKERS = ('焦点', '重点', '构图重点', '视觉中心', '视觉焦点', '张力', '氛围', '诱惑感', '压迫感', '邀请感', '边界', '层次感')
HUMAN_REVIEW_HIGH_RISK_MARKERS = ('焦点', '视觉焦点', '构图重点', '视觉中心', '诱惑感', '压迫感', '邀请感', '边界', '显得', '可以看到', '而非', '用于', '用来', '收出', '连续拉开')
HUMAN_REVIEW_EXPLANATION_MARKERS = ('可以看到', '来自', '而非', '用于', '用来', '作为', '让人', '显得', '呈现', '形成', '成为', '保持', '维持')
HUMAN_REVIEW_UNNATURAL_MARKERS = ('收出', '完整', '清楚', '明确', '自然垂落', '非常醒目', '轮廓稳定', '入画', '入镜', '短截', '下方重点', '胸腰')
HUMAN_REVIEW_SCOPE_MARKERS = ('全身像', '半身像', '半身像', '半身像', '脸部特写', '头部特写', '横向构图', '竖向构图', '方形头部')
BOLD_OUTFIT_AESTHETIC_CONFLICT_GROUPS = ((('吊带丝袜', '长筒丝袜', '连裤袜', '过膝长袜'), ('工装短裤', '运动短裤', '运动短裙', '牛仔短裤', '直筒短裤', '热裤', '运动风短背心'), '丝袜/袜带不应和工装、运动、牛仔短裤硬混搭'),)
BOLD_OUTFIT_TOO_CASUAL_MARKERS = ('西装马甲', '西装短裤', '针织', '运动风', '运动背心', '阔腿短裤', '普通短裤', '热裤')
ANCIENT_OUTFIT_MARKERS = ('古装', '古典', '汉服', '中式', '盘扣', '斜襟', '敦煌', '胡姬', '花魁', '宫廷')
ANCIENT_OUTFIT_MODERN_CONFLICT_MARKERS = (
    '高跟',
    '细跟',
    '凉鞋',
    'choker',
    'Choker',
    '夜店',
    '亮面',
    '短上衣',
    '微型',
    '细肩带',
    '吊带裙',
    '吊带短裙',
    '连体泳装',
    '连体衣',
    '泳装',
    '短罩衫',
    '吊带丝袜',
    '长筒丝袜',
    '包臀短裙',
    '胸衣',
    '酒红缎面胸衣',
    '亮钻胸衣',
    '现代',
    'glamour',
)
ANCIENT_SCENE_MODERN_CONFLICT_MARKERS = (
    '夜店',
    '吧台',
    '霓虹',
    '灯带',
    '镜面房',
    '地下酒廊',
    '泳池',
    '玻璃浴室',
    '现代',
    '黑色镜面地面',
)
MODERN_THEME_ANCIENT_SCENE_MARKERS = (
    '古代',
    '宫苑',
    '画舫',
    '雕花窗',
    '纱帐寝殿',
    '香炉',
    '屏风',
    '铜镜',
    '竹林月色',
    '雨夜廊下',
)
ANCIENT_OUTFIT_STRUCTURE_MARKERS = (
    '交领',
    '襦',
    '披帛',
    '齐胸',
    '高腰',
    '马面裙',
    '云头绣鞋',
    '绣鞋',
    '软底',
    '盘扣',
    '斜襟',
    '短袄',
    '宽袖',
    '织带',
)
CAMERA_STACK_PATTERNS = (('头部近景', '方形头部镜头'), ('贴近镜头的头部肖像', '肩膀及以上入镜'), ('竖向半身写真构图', '竖向半身构图'))

def load_prompt_engine():
    path = ROOT / 'prompt_engine.py'
    spec = importlib.util.spec_from_file_location('generated_prompt_engine', path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def load_runtime_builder():
    path = ROOT / '__init__.py'
    spec = importlib.util.spec_from_file_location('random_photo_prompt_runtime_audit', path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    return getattr(module, '_build_mobile_prompt_for_scope', None)

def normalize_text(text: str) -> str:
    return re.sub('[\\s，。；;、：:\\-_/（）()\\"\'\'\'\']+', '', text)

def split_clauses(text: str) -> list[str]:
    return [part.strip() for part in CLAUSE_SPLIT_RE.split(text) if len(part.strip()) >= 4]

def uncommon_phrases(text: str) -> set[str]:
    phrases: set[str] = set()
    for match in CHINESE_PHRASE_RE.findall(normalize_text(text)):
        if len(match) < 5:
            continue
        if any((common in match for common in COMMON_REPEAT_FRAGMENTS)):
            continue
        for size in (5, 6, 7, 8):
            if len(match) >= size:
                phrases.update((match[index:index + size] for index in range(0, len(match) - size + 1)))
    return phrases

def percentile(values: list[int], percent: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    return ordered[round((len(ordered) - 1) * percent)]

def concept_counts(text: str) -> dict[str, int]:
    return {name: sum((text.count(marker) for marker in markers)) for name, markers in CONCEPT_GROUPS.items()}

def stats_for_item(scale: str, shot: str, aspect: str, sample: int, item: dict) -> PromptStats:
    parts = item['dimension_parts']
    prompt = item['positive_prompt']
    return PromptStats(scale=scale, shot=shot, aspect=aspect, sample=sample, prompt_length=len(prompt), dimension_lengths={name: len(value) for name, value in parts.items() if value and name in DIMENSION_LABELS}, concept_counts=concept_counts(prompt), prompt=prompt)

def missing_dimensions(scale: str, parts: dict[str, str]) -> list[str]:
    expected = EXPECTED_DIMENSIONS[scale]
    missing = [name for name in expected if not parts.get(name, '').strip()]
    if scale in {'bold_no_outfit', 'nsfw'} and parts.get('outfit', '').strip():
        missing.append(f'{scale}_outfit_should_be_empty')
    return missing

def mobile_prompt_text_for_resolution(parts: dict[str, str]) -> str:
    return '，'.join((str(parts.get(name, '')) for name in ('camera', 'pose_expression', 'scene_light') if parts.get(name)))

def mobile_resolution_for_parts(parts: dict[str, str], shot: str) -> dict[str, str]:
    text = mobile_prompt_text_for_resolution(parts)
    for markers, resolution in MOBILE_RESOLUTION_RULES.get(shot, ()):
        if any((marker in text for marker in markers)):
            return resolution
    director = str(parts.get('director') or '')
    director_resolution = MOBILE_DIRECTOR_RESOLUTION_RULES.get(director, {}).get(shot)
    if director_resolution:
        return director_resolution
    return MOBILE_DEFAULT_RESOLUTIONS[shot]

def prompt_from_parts(parts: dict[str, str]) -> str:
    return '\n'.join((ensure_sentence(parts.get(name, '')) for name in PROMPT_PART_ORDER if parts.get(name)))

def prompt_len_from_parts(parts: dict[str, str]) -> int:
    return len(prompt_from_parts(parts))

def prompt_clauses(text: str) -> list[str]:
    return [part.strip('，。 \n\t') for part in str(text or '').replace('；', '，').split('，') if part.strip('，。 \n\t')]

def enforce_prompt_length(parts: dict[str, str], max_length: int=MAX_POSITIVE_PROMPT_LENGTH) -> dict[str, str]:
    compacted = dict(parts or {})
    if prompt_len_from_parts(compacted) <= max_length:
        return compacted
    compacted['quality'] = ''
    if prompt_len_from_parts(compacted) <= max_length:
        return compacted
    for name in ('scene_light', 'outfit', 'pose_expression', 'makeup', 'camera'):
        clauses = prompt_clauses(compacted.get(name, ''))
        while len(clauses) > 1 and prompt_len_from_parts(compacted) > max_length:
            clauses.pop()
            compacted[name] = '，'.join(clauses)
        if prompt_len_from_parts(compacted) <= max_length:
            break
    return compacted

def apply_mobile_framing(item: dict, resolution: dict[str, str], enabled: bool=False) -> dict:
    if not enabled:
        return item
    framing = resolution.get('framing')
    if not framing:
        return item
    parts = dict(item.get('dimension_parts') or {})
    camera = str(parts.get('camera') or '')
    if any((marker in camera for marker in ('入镜', '镜头', '构图', '画面', '头顶', '完整'))):
        framing = MOBILE_FRAMING_COMPACT_REPLACEMENTS.get(framing, framing)
    camera_first = re.split('[，,]', camera)[0].strip() if camera else ''
    framing_first = re.split('[，,]', framing)[0].strip()
    scope_markers = ('肩部以上入镜', '大腿以上入镜', '肩膀及以上入镜', '从头到脚完整入镜', '大腿以上镜头', '头顶完整')
    already_covered = framing in camera or camera_first == framing_first or (camera_first and camera_first in framing) or (framing_first and framing_first in camera) or any((marker in camera and marker in framing for marker in scope_markers))
    if not already_covered:
        parts['camera'] = f'{camera}，{framing}' if camera else framing
    parts = enforce_prompt_length(parts)
    rebuilt = dict(item)
    rebuilt['dimension_parts'] = parts
    rebuilt['positive_prompt'] = prompt_from_parts(parts)
    rebuilt['compact_prompt'] = rebuilt['positive_prompt']
    return rebuilt

def ensure_sentence(text: str) -> str:
    text = str(text or '').strip('，。 \n\t')
    return f'{text}。' if text else ''

def duplicate_findings(scale: str, shot: str, aspect: str, sample: int, prompt: str, parts: dict[str, str]) -> list[Finding]:
    findings: list[Finding] = []
    clause_counter = Counter((normalize_text(clause) for clause in split_clauses(prompt)))
    repeated_clauses = [clause for clause, count in clause_counter.items() if count > 1 and len(clause) >= 6]
    if repeated_clauses:
        findings.append(Finding('warning', scale, shot, aspect, sample, 'obvious_repeated_clause', '、'.join(repeated_clauses[:5]), prompt))
    part_values = [(name, normalize_text(value)) for name, value in parts.items() if value]
    for left_index, (left_name, left_value) in enumerate(part_values):
        for right_name, right_value in part_values[left_index + 1:]:
            if left_value and left_value == right_value:
                detail = f'{DIMENSION_LABELS.get(left_name, left_name)} == {DIMENSION_LABELS.get(right_name, right_name)}'
                findings.append(Finding('warning', scale, shot, aspect, sample, 'identical_dimension_text', detail, prompt))
    phrase_owners: dict[str, set[str]] = {}
    for name, value in parts.items():
        if not value:
            continue
        for phrase in uncommon_phrases(value):
            phrase_owners.setdefault(phrase, set()).add(name)
    repeated_phrases = sorted((phrase for phrase, owners in phrase_owners.items() if len(owners) >= 2))
    if repeated_phrases:
        findings.append(Finding('info', scale, shot, aspect, sample, 'repeated_descriptive_phrase', '、'.join(repeated_phrases[:8]), prompt))
    return findings

def contradiction_findings(scale: str, shot: str, aspect: str, sample: int, prompt: str, parts: dict[str, str]) -> list[Finding]:
    findings: list[Finding] = []
    if scale in {'bold_no_outfit', 'nsfw'} and parts.get('outfit', '').strip():
        findings.append(Finding('error', scale, shot, aspect, sample, 'outfit_leak', 'This scale should not include outfit dimension', prompt))
    if scale == 'bold':
        outfit = parts.get('outfit', '')
        hits = [marker for marker in BOLD_OUTFIT_NUDE_RISK_MARKERS if marker in outfit]
        if hits:
            findings.append(Finding('error', scale, shot, aspect, sample, 'bold_outfit_nude_risk', '、'.join(hits), prompt))
        material_hits = [marker for marker in BOLD_OUTFIT_BANNED_MATERIAL_MARKERS if marker in outfit]
        if material_hits:
            findings.append(Finding('error', scale, shot, aspect, sample, 'bold_outfit_banned_material', '、'.join(material_hits), prompt))
    camera = parts.get('camera', '')
    if shot == 'head_shot' and (not ('头部' in camera or '肩膀以上' in camera or '肩膀及以上' in camera or ('肩部以上' in camera))):
        findings.append(Finding('warning', scale, shot, aspect, sample, 'camera_sentence_mismatch', camera, prompt))
    if shot == 'half_body' and (not ('半身' in camera or '大腿以上' in camera)):
        findings.append(Finding('warning', scale, shot, aspect, sample, 'camera_sentence_mismatch', camera, prompt))
    if shot == 'full_body' and '全身' not in camera:
        findings.append(Finding('warning', scale, shot, aspect, sample, 'camera_sentence_mismatch', camera, prompt))
    pose = parts.get('pose_expression', '')
    if any((term in pose for term in POSE_CAMERA_OWNERSHIP_TERMS)):
        detail = 'pose owns camera/resolution wording: ' + '、'.join((term for term in POSE_CAMERA_OWNERSHIP_TERMS if term in pose))
        findings.append(Finding('warning', scale, shot, aspect, sample, 'pose_camera_ownership', detail, prompt))
    if shot == 'full_body' and any((term in pose for term in LYING_POSE_TERMS)) and any((term in camera for term in UPRIGHT_CAMERA_TERMS)):
        detail = 'upright full-body camera combined with lying/top-down pose'
        findings.append(Finding('warning', scale, shot, aspect, sample, 'camera_pose_direction_conflict', detail, prompt))
    if any((term in camera for term in PORTRAIT_ORIENTATION_TERMS)) and any((term in pose for term in LANDSCAPE_ORIENTATION_TERMS)):
        detail = 'portrait camera wording combined with landscape pose wording'
        findings.append(Finding('warning', scale, shot, aspect, sample, 'camera_pose_direction_conflict', detail, prompt))
    if any((term in camera for term in LANDSCAPE_ORIENTATION_TERMS)) and any((term in pose for term in PORTRAIT_ORIENTATION_TERMS)):
        detail = 'landscape camera wording combined with portrait pose wording'
        findings.append(Finding('warning', scale, shot, aspect, sample, 'camera_pose_direction_conflict', detail, prompt))
    if shot in {'half_body', 'full_body'} and aspect == 'portrait' and any((term in pose for term in HORIZONTAL_BODY_TERMS)):
        detail = 'portrait frame combined with horizontal body-axis pose'
        findings.append(Finding('warning', scale, shot, aspect, sample, 'frame_body_axis_conflict', detail, prompt))
    if shot in {'half_body', 'full_body'} and aspect == 'landscape' and any((term in pose for term in VERTICAL_BODY_TERMS)) and (not any((term in pose for term in HORIZONTAL_BODY_TERMS))):
        detail = 'landscape frame combined with vertical body-axis pose'
        findings.append(Finding('warning', scale, shot, aspect, sample, 'frame_body_axis_conflict', detail, prompt))
    if shot in {'full_body'} and any((term in pose for term in ('舌尖', '舌头', '伸舌', '探出'))):
        findings.append(Finding('error', scale, shot, aspect, sample, 'distant_tongue_expression', '半身/全身镜头不使用舌头动作，画面里看不清', prompt))
    hand_to_camera_hits = [pattern.pattern for pattern in HAND_TO_CAMERA_PATTERNS if pattern.search(pose)]
    if scale in {'bold', 'bold_no_outfit', 'nsfw'} and hand_to_camera_hits:
        findings.append(Finding('error', scale, shot, aspect, sample, 'hand_to_camera_pose', '手部展示应放在脸旁、肩膀、胸前、腰侧或大腿上，不伸向镜头', prompt))
    return findings

def quality_findings(scale: str, shot: str, aspect: str, sample: int, prompt: str, parts: dict[str, str]) -> list[Finding]:
    findings: list[Finding] = []
    scene_quality = '，'.join((str(parts.get(name, '')) for name in ('scene_light', 'quality')))
    concrete_hits = [marker for marker in CONCRETE_PHOTO_MARKERS if marker in scene_quality]
    natural_hits = [marker for marker in PHOTOGRAPHIC_NATURALNESS_MARKERS if marker in prompt]
    generic_count = sum((prompt.count(marker) for marker in GENERIC_QUALITY_MARKERS))
    if generic_count >= 4 and len(concrete_hits) < 2:
        findings.append(Finding('info', scale, shot, aspect, sample, 'generic_quality_stack', f'generic={generic_count}, concrete={len(concrete_hits)}', prompt))
    if len(natural_hits) < 2:
        findings.append(Finding('info', scale, shot, aspect, sample, 'photo_naturalness_missing', 'missing enough real skin / exposure / depth markers', prompt))
    if scale in {'bold', 'bold_no_outfit', 'nsfw'}:
        pose = str(parts.get('pose_expression') or '')
        tension_hits = [marker for marker in SENSUAL_TENSION_MARKERS if marker in pose]
        if len(tension_hits) < 2:
            findings.append(Finding('info', scale, shot, aspect, sample, 'low_sensual_tension', 'missing gaze / expression / body-line tension anchors', prompt))
    if scale in {'bold', 'bold_no_outfit'}:
        scene = str(parts.get('scene_light') or '')
        pose = str(parts.get('pose_expression') or '')
        seductive_light_hits = [marker for marker in SEDUCTIVE_LIGHT_MARKERS if marker in scene]
        time_hits = [marker for marker in SEDUCTIVE_TIME_MARKERS if marker in scene]
        teasing_pose_hits = [marker for marker in TEASING_POSE_MARKERS if marker in pose]
        if len(seductive_light_hits) < 2 or not time_hits:
            findings.append(Finding('warning', scale, shot, aspect, sample, 'weak_seductive_light', '二/三档场景光线需要明确时间段，并用日光/黄昏/夜景的光线细节支撑诱惑氛围', prompt))
        if len(teasing_pose_hits) < 2:
            findings.append(Finding('warning', scale, shot, aspect, sample, 'weak_teasing_pose', '二/三档姿势缺少按镜头范围可见的手足前景/俯视/低机位/表情挑逗动作', prompt))
    return findings

def _split_theme_terms(value: str) -> tuple[str, ...]:
    return tuple(term.strip() for term in str(value or '').split('，') if term.strip())

def _theme_terms_for_lane(parts: dict[str, str], lane_name: str, allowed_terms: tuple[str, ...]) -> tuple[str, ...]:
    lane_terms = _split_theme_terms(str(parts.get(lane_name) or ''))
    return tuple(term for term in lane_terms if term in allowed_terms)

def theme_coherence_findings(scale: str, shot: str, aspect: str, sample: int, prompt: str, parts: dict[str, str]) -> list[Finding]:
    findings: list[Finding] = []
    theme_name = str(parts.get('theme_name') or '')
    if not theme_name:
        return findings
    scene_terms = _theme_terms_for_lane(parts, 'theme_scene_keywords', THEME_LOCATION_TERMS)
    outfit_terms = _theme_terms_for_lane(parts, 'theme_outfit_keywords', THEME_OUTFIT_TERMS)
    pose_terms = _theme_terms_for_lane(parts, 'theme_pose_keywords', THEME_POSE_TERMS)
    scene = str(parts.get('scene_light') or '')
    outfit = str(parts.get('outfit') or '')
    pose = str(parts.get('pose_expression') or '')
    all_theme_terms = _split_theme_terms(str(parts.get('theme_keywords') or ''))
    is_ancient_theme = any(term in all_theme_terms or term in theme_name for term in ('古代', 'ancient', 'dunhuang', 'miao', 'republic', '民国', '苗疆'))
    if scene_terms and not any(term in scene for term in scene_terms):
        findings.append(Finding('warning', scale, shot, aspect, sample, 'theme_scene_mismatch', f'{theme_name}: scene misses {"、".join(scene_terms[:6])}', prompt))
    if scale == 'bold' and outfit_terms and outfit and not any(term in outfit for term in outfit_terms):
        findings.append(Finding('warning', scale, shot, aspect, sample, 'theme_outfit_mismatch', f'{theme_name}: outfit misses {"、".join(outfit_terms[:6])}', prompt))
    if pose_terms and not any(term in pose for term in pose_terms):
        findings.append(Finding('warning', scale, shot, aspect, sample, 'theme_pose_mismatch', f'{theme_name}: pose misses {"、".join(pose_terms[:6])}', prompt))
    if is_ancient_theme:
        scene_conflicts = [marker for marker in ANCIENT_SCENE_MODERN_CONFLICT_MARKERS if marker in scene]
        outfit_conflicts = [marker for marker in ANCIENT_OUTFIT_MODERN_CONFLICT_MARKERS if marker in outfit]
        if scene_conflicts:
            findings.append(Finding('error', scale, shot, aspect, sample, 'ancient_theme_modern_scene_conflict', '、'.join(scene_conflicts), prompt))
        if outfit_conflicts:
            findings.append(Finding('error', scale, shot, aspect, sample, 'ancient_theme_modern_outfit_conflict', '、'.join(outfit_conflicts), prompt))
    elif theme_name:
        ancient_scene_hits = [marker for marker in MODERN_THEME_ANCIENT_SCENE_MARKERS if marker in scene]
        if ancient_scene_hits:
            findings.append(Finding('error', scale, shot, aspect, sample, 'modern_theme_ancient_scene_conflict', '、'.join(ancient_scene_hits), prompt))
    return findings

def final_semantic_findings(scale: str, shot: str, aspect: str, sample: int, prompt: str, parts: dict[str, str]) -> list[Finding]:
    findings: list[Finding] = []
    bad_hits = [phrase for phrase in FINAL_PROMPT_BAD_PHRASES if phrase in prompt]
    if bad_hits:
        findings.append(Finding('error', scale, shot, aspect, sample, 'final_bad_phrase', '、'.join(bad_hits[:8]), prompt))
    scene = str(parts.get('scene_light') or '')
    scene_hits = [phrase for phrase in NON_VISUAL_SCENE_PHRASES if phrase in scene]
    if scene_hits:
        findings.append(Finding('error', scale, shot, aspect, sample, 'non_visual_scene_text', '、'.join(scene_hits), prompt))
    pose = str(parts.get('pose_expression') or '')
    abstract_hits = [phrase for phrase in ABSTRACT_POSE_PHRASES if phrase in pose]
    if abstract_hits:
        findings.append(Finding('warning', scale, shot, aspect, sample, 'abstract_pose_text', '、'.join(abstract_hits), prompt))
    detached_foot_hits = [phrase for phrase in DETACHED_FOOT_PHRASES if phrase in pose or phrase in prompt]
    if detached_foot_hits:
        findings.append(Finding('error', scale, shot, aspect, sample, 'detached_foot_subject', '脚部前景不能写成独立身体部位主语：' + '、'.join(detached_foot_hits), prompt))
    if '脚掌和脚尖' in pose and not any(marker in pose for marker in CONNECTED_FOOT_CHAIN_MARKERS):
        findings.append(Finding('error', scale, shot, aspect, sample, 'foot_foreground_without_leg_chain', '脚掌/脚尖前景必须写明前腿、小腿、脚踝或腿部末端连接关系', prompt))
    if shot == 'head_shot' and re.match('^(头部近景|贴近镜头的头部肖像|竖向头部写真构图|方形头部)', pose):
        findings.append(Finding('warning', scale, shot, aspect, sample, 'pose_repeats_camera_scope', pose.split('，', 1)[0], prompt))
    camera = str(parts.get('camera') or '')
    camera_clause_count = len([clause for clause in re.split('[，。]', camera) if clause.strip()])
    if camera_clause_count > 2:
        findings.append(Finding('warning', scale, shot, aspect, sample, 'camera_over_stacked', f'{camera_clause_count} clauses: {camera}', prompt))
    for left, right in CAMERA_STACK_PATTERNS:
        if left in camera and right in camera:
            findings.append(Finding('warning', scale, shot, aspect, sample, 'camera_duplicate_scope', f'{left} + {right}: {camera}', prompt))
            break
    if scale in {'bold', 'bold_no_outfit'} and any((marker in prompt for marker in ('露点', '乳头', '私处', '全裸', '裸露'))):
        findings.append(Finding('error', scale, shot, aspect, sample, 'bold_explicit_leak', '二档/三档不应出现露点/裸体直白词', prompt))
    if scale == 'bold':
        outfit = str(parts.get('outfit') or '')
        casual_hits = [marker for marker in BOLD_OUTFIT_TOO_CASUAL_MARKERS if marker in outfit]
        if casual_hits:
            findings.append(Finding('warning', scale, shot, aspect, sample, 'bold_outfit_too_casual', '、'.join(casual_hits), prompt))
        if any((marker in outfit for marker in ANCIENT_OUTFIT_MARKERS)):
            modern_hits = [marker for marker in ANCIENT_OUTFIT_MODERN_CONFLICT_MARKERS if marker in outfit]
            structure_hits = [marker for marker in ANCIENT_OUTFIT_STRUCTURE_MARKERS if marker in outfit]
            if modern_hits:
                findings.append(Finding('warning', scale, shot, aspect, sample, 'ancient_outfit_modern_conflict', '、'.join(modern_hits), prompt))
            if len(structure_hits) < 2:
                findings.append(Finding('warning', scale, shot, aspect, sample, 'ancient_outfit_weak_structure', '古装衣着缺少交领/襦裙/披帛/绣鞋/盘扣等时代结构', prompt))
        for left_markers, right_markers, detail in BOLD_OUTFIT_AESTHETIC_CONFLICT_GROUPS:
            if any((marker in outfit for marker in left_markers)) and any((marker in outfit for marker in right_markers)):
                findings.append(Finding('warning', scale, shot, aspect, sample, 'bold_outfit_aesthetic_conflict', detail, prompt))
                break
    if scale == 'normal' and any((marker in pose for marker in ('挑逗', '诱惑', '勾引', '私房'))):
        findings.append(Finding('warning', scale, shot, aspect, sample, 'normal_sensual_drift', '一档姿势不应服务性感诱惑', prompt))
    if re.search('嘴角(?:带|是|有)?[^，。]{0,10}(?:微笑|笑意)[，。][^。]{0,40}嘴角(?:带|是|有)?[^，。]{0,10}(?:微笑|笑意)', prompt):
        findings.append(Finding('warning', scale, shot, aspect, sample, 'duplicated_expression_semantics', '嘴角/笑意重复堆叠', prompt))
    return findings

def human_review_findings(scale: str, shot: str, aspect: str, sample: int, prompt: str, parts: dict[str, str]) -> list[Finding]:
    findings: list[Finding] = []
    review_parts = ('camera', 'outfit', 'pose_expression', 'scene_light', 'quality')
    for name in review_parts:
        text = str(parts.get(name) or '')
        if not text:
            continue
        label = DIMENSION_LABELS.get(name, name)
        for clause in split_clauses(text):
            if '形成背景层次' in clause:
                continue
            reasons: list[str] = []
            high_risk_hits = [marker for marker in HUMAN_REVIEW_HIGH_RISK_MARKERS if marker in clause]
            abstract_hits = [marker for marker in HUMAN_REVIEW_ABSTRACT_MARKERS if marker in clause]
            explanation_hits = [marker for marker in HUMAN_REVIEW_EXPLANATION_MARKERS if marker in clause]
            unnatural_hits = [marker for marker in HUMAN_REVIEW_UNNATURAL_MARKERS if marker in clause]
            scope_hits = [marker for marker in HUMAN_REVIEW_SCOPE_MARKERS if marker in clause]
            if abstract_hits and (high_risk_hits or len(abstract_hits) >= 2):
                reasons.append(f"抽象目的词: {'、'.join(abstract_hits[:3])}")
            if explanation_hits and (high_risk_hits or (name == 'pose_expression' and abstract_hits)):
                reasons.append(f"解释型语言: {'、'.join(explanation_hits[:3])}")
            if unnatural_hits and name != 'camera' and (high_risk_hits or len(unnatural_hits) >= 2):
                reasons.append(f"泛词/别扭搭配: {'、'.join(unnatural_hits[:4])}")
            if name != 'camera' and scope_hits:
                reasons.append(f"镜头词混入{label}: {'、'.join(scope_hits[:3])}")
            if not reasons:
                continue
            detail = f"{label}句子可疑：{clause}（{'; '.join(reasons)}）"
            findings.append(Finding('warning', scale, shot, aspect, sample, 'human_review_sentence', detail, prompt))
            break
    return findings

def audit_item(scale: str, shot: str, aspect: str, sample: int, item: dict) -> list[Finding]:
    prompt = item['positive_prompt']
    parts = item['dimension_parts']
    findings: list[Finding] = []
    missing = missing_dimensions(scale, parts)
    if missing:
        labels = [DIMENSION_LABELS.get(name, name) for name in missing]
        findings.append(Finding('error', scale, shot, aspect, sample, 'missing_or_unexpected_dimension', '、'.join(labels), prompt))
    findings.extend(duplicate_findings(scale, shot, aspect, sample, prompt, parts))
    findings.extend(contradiction_findings(scale, shot, aspect, sample, prompt, parts))
    findings.extend(quality_findings(scale, shot, aspect, sample, prompt, parts))
    findings.extend(theme_coherence_findings(scale, shot, aspect, sample, prompt, parts))
    findings.extend(final_semantic_findings(scale, shot, aspect, sample, prompt, parts))
    findings.extend(human_review_findings(scale, shot, aspect, sample, prompt, parts))
    budget = PROMPT_LENGTH_BUDGETS.get(shot)
    if budget and len(prompt) > budget:
        findings.append(Finding('error', scale, shot, aspect, sample, 'prompt_length_over_budget', f'{len(prompt)} > {budget}', prompt))
    for name, value in parts.items():
        if name not in DIMENSION_LABELS:
            continue
        part_budget = DIMENSION_LENGTH_BUDGETS.get(name)
        if value and part_budget and (len(value) > part_budget):
            label = DIMENSION_LABELS.get(name, name)
            findings.append(Finding('info', scale, shot, aspect, sample, 'dimension_length_over_budget', f'{label}: {len(value)} > {part_budget}', prompt))
    repeated_concepts = [f'{name}={count}' for name, count in concept_counts(prompt).items() if count >= 4]
    if repeated_concepts:
        findings.append(Finding('info', scale, shot, aspect, sample, 'concept_repetition', ' | '.join(repeated_concepts), prompt))
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
            for aspect in ('portrait', 'landscape'):
                items = []
                for index in range(samples):
                    initial = engine.generate_prompt_items(1, {'scale': scale, 'shot': SHOT_INPUTS[shot], 'aspect': aspect}, seed_text=f'generated-audit-{scale}-{shot}-{aspect}-{samples}-{index}')[0]
                    resolution = mobile_resolution_for_parts(initial['dimension_parts'], shot)
                    resolved_aspect = resolution['aspect']
                    if resolved_aspect != aspect and any((term in mobile_prompt_text_for_resolution(initial['dimension_parts']) for term in HORIZONTAL_BODY_TERMS + VERTICAL_BODY_TERMS)):
                        initial = engine.generate_prompt_items(1, {'scale': scale, 'shot': SHOT_INPUTS[shot], 'aspect': resolved_aspect}, seed_text=f'generated-audit-{scale}-{shot}-{aspect}-{samples}-{index}-{resolved_aspect}')[0]
                        resolution = mobile_resolution_for_parts(initial['dimension_parts'], shot)
                    items.append((resolved_aspect, apply_mobile_framing(initial, resolution)))
                for resolved_aspect, _item in items:
                    sample_counts[scale, shot, resolved_aspect] = sample_counts.get((scale, shot, resolved_aspect), 0) + 1
                for index, (resolved_aspect, item) in enumerate(items, 1):
                    findings.extend(audit_item(scale, shot, resolved_aspect, index, item))
                    stats.append(stats_for_item(scale, shot, resolved_aspect, index, item))
    return (findings, sample_counts, stats)

def length_repetition_report(stats: list[PromptStats]) -> list[str]:
    lines = ['## Length And Repetition', '']
    if not stats:
        lines.extend(['No prompt stats collected.', ''])
        return lines
    by_scope: dict[tuple[str, str, str], list[PromptStats]] = {}
    for item in stats:
        by_scope.setdefault((item.scale, item.shot, item.aspect), []).append(item)
    lines.extend(['### Prompt Length By Scale / Shot / Aspect', ''])
    for (scale, shot, aspect), items in sorted(by_scope.items()):
        values = [item.prompt_length for item in items]
        lines.append(f'- `{scale}` / `{shot}` / `{aspect}`: median {percentile(values, 0.5)}, p90 {percentile(values, 0.9)}, max {max(values)}')
    lines.append('')
    dimension_totals: dict[str, list[int]] = {}
    for item in stats:
        for name, length in item.dimension_lengths.items():
            dimension_totals.setdefault(name, []).append(length)
    lines.extend(['### Dimension Length Hotspots', ''])
    for name, values in sorted(dimension_totals.items(), key=lambda pair: percentile(pair[1], 0.9), reverse=True):
        label = DIMENSION_LABELS.get(name, name)
        lines.append(f'- `{label}`: median {percentile(values, 0.5)}, p90 {percentile(values, 0.9)}, max {max(values)}')
    lines.append('')
    concept_totals: Counter[str] = Counter()
    concept_repeat_samples: dict[str, list[PromptStats]] = {}
    for item in stats:
        for concept, count in item.concept_counts.items():
            concept_totals[concept] += count
            if count >= 4:
                concept_repeat_samples.setdefault(concept, []).append(item)
    lines.extend(['### Concept Repetition Totals', ''])
    for concept, count in concept_totals.most_common():
        if count:
            lines.append(f'- `{concept}`: {count}')
    lines.append('')
    lines.extend(['### Longest Generated Prompts', ''])
    for item in sorted(stats, key=lambda stat: stat.prompt_length, reverse=True)[:12]:
        prompt = item.prompt.replace('\n', ' ')
        if len(prompt) > 300:
            prompt = prompt[:297] + '...'
        longest_dimensions = sorted(item.dimension_lengths.items(), key=lambda pair: pair[1], reverse=True)[:3]
        dimension_text = ', '.join((f'{DIMENSION_LABELS.get(name, name)}={length}' for name, length in longest_dimensions))
        lines.append(f'- `{item.scale}` / `{item.shot}` / `{item.aspect}` sample {item.sample}: {item.prompt_length} chars; {dimension_text}')
        lines.append(f'  - {prompt}')
    lines.append('')
    if concept_repeat_samples:
        lines.extend(['### Repeated Concept Samples', ''])
        for concept, samples in sorted(concept_repeat_samples.items()):
            lines.append(f'- `{concept}`: {len(samples)} samples at 4+ mentions')
            for item in samples[:3]:
                prompt = item.prompt.replace('\n', ' ')
                if len(prompt) > 220:
                    prompt = prompt[:217] + '...'
                lines.append(f'  - `{item.scale}` / `{item.shot}` / `{item.aspect}` sample {item.sample}: {prompt}')
        lines.append('')
    return lines

def build_report(findings: list[Finding], sample_counts: dict[tuple[str, str, str], int], stats: list[PromptStats]) -> str:
    counts = Counter((finding.severity for finding in findings))
    lines = ['# Generated Prompt Audit Report', '', 'This report is generated by `tools/audit_generated_prompts.py`.', '', '## Summary', '', f'- Samples: {sum(sample_counts.values())}', f"- Errors: {counts.get('error', 0)}", f"- Warnings: {counts.get('warning', 0)}", f"- Info: {counts.get('info', 0)}", '', '## Sample Coverage', '']
    for (scale, shot, aspect), count in sorted(sample_counts.items()):
        lines.append(f'- `{scale}` / `{shot}` / `{aspect}`: {count}')
    lines.extend([''])
    lines.extend(length_repetition_report(stats))
    lines.extend(['## Findings', ''])
    if not findings:
        lines.append('No findings.')
        return '\n'.join(lines)
    grouped: dict[tuple[str, str], list[Finding]] = {}
    for finding in findings:
        grouped.setdefault((finding.severity, finding.rule), []).append(finding)
    severity_order = {'error': 0, 'warning': 1, 'info': 2}
    for (severity, rule), group in sorted(grouped.items(), key=lambda item: (severity_order.get(item[0][0], 9), item[0][1])):
        lines.append(f'### {severity}: {rule}')
        lines.append('')
        for finding in group[:80]:
            prompt = finding.prompt.replace('\n', ' ')
            if len(prompt) > 260:
                prompt = prompt[:257] + '...'
            lines.append(f'- `{finding.scale}` / `{finding.shot}` / `{finding.aspect}` sample {finding.sample}: {finding.detail}')
            lines.append(f'  - {prompt}')
        if len(group) > 80:
            lines.append(f'- ... {len(group) - 80} more')
        lines.append('')
    return '\n'.join(lines)

def main() -> int:
    parser = argparse.ArgumentParser(description='Audit generated final prompt combinations.')
    parser.add_argument('--samples', type=int, default=30, help='Samples per selected scale/shot.')
    parser.add_argument('--scale', action='append', choices=SCALES, help='Scale to audit; can be repeated.')
    parser.add_argument('--shot', action='append', choices=SHOTS, help='Shot to audit; can be repeated.')
    parser.add_argument('--report', default=str(DEFAULT_REPORT_PATH), help='Markdown report output path.')
    parser.add_argument('--fail-on-warning', action='store_true')
    args = parser.parse_args()
    scales = selected_values(args.scale, SCALES)
    shots = selected_values(args.shot, SHOTS)
    findings, sample_counts, stats = run_audit(max(args.samples, 1), scales, shots)
    report = build_report(findings, sample_counts, stats)
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding='utf-8')
    counts = Counter((finding.severity for finding in findings))
    print(f'Wrote {report_path}')
    print(f"Errors: {counts.get('error', 0)}; warnings: {counts.get('warning', 0)}; info: {counts.get('info', 0)}")
    if counts.get('error', 0):
        return 1
    if args.fail_on_warning and counts.get('warning', 0):
        return 1
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
