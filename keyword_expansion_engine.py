from __future__ import annotations
import random
import re
import time
from typing import Iterable
MAX_KEYWORD_PROMPT_LENGTH = 800
FIXED_CHARACTER_ORIGINAL = '22岁冷白皮K-pop韩国女生，夜店斩男精致妆容，御姐范十足，通透瓷白皮肤，黑色直发，标准瓜子脸，狐狸眼，浅棕色眼影，深棕色美瞳，高鼻梁，尖鼻子，尖下巴，黑色手指甲，性感锁骨，骨架偏瘦但胸部和臀部丰满，小蛮腰，腿细且长'
SUBJECT_KEYWORDS = [FIXED_CHARACTER_ORIGINAL]
CHARACTER_BY_SHOT = {'head_shot': '22岁冷白皮K-pop韩国女生，夜店斩男精致妆容，御姐范十足，通透瓷白皮肤，黑色直发，标准瓜子脸，狐狸眼，浅棕色眼影，深棕色美瞳，高鼻梁，尖鼻子，尖下巴', 'half_body': '22岁冷白皮K-pop韩国女生，夜店斩男精致妆容，御姐范十足，通透瓷白皮肤，黑色直发，标准瓜子脸，狐狸眼，浅棕色眼影，深棕色美瞳，高鼻梁，尖鼻子，尖下巴，黑色手指甲，性感锁骨，骨架偏瘦但胸部丰满，小蛮腰', 'full_body': FIXED_CHARACTER_ORIGINAL}
THEME_KEYWORDS = ['阳光泳池边写真', '夏日海边时尚写真', '彩色棚拍甜辣大片', '露台阳光私房写真', '花园度假风写真', '城市街头高饱和写真', '酒店阳台明亮写真']
THEME_SCENE_PACKAGES = [{'theme': '阳光泳池边写真', 'scenes': ['蓝色泳池、水面反光、彩色泳池砖和阳光伞组成背景', '泳池台阶、湖蓝瓷砖、米白躺椅和水面高光进入背景'], 'poses': [], 'poses_by_shot': {'head_shot': ['头部微仰感受阳光，闭眼嘴角带笑，手指轻拨湿润的发梢'], 'half_body': ['大腿以上半浸在池水中，双手向后撑着池边，水珠从锁骨滑落'], 'full_body': ['趴在泳池边回头看向前方，双腿向后轻轻抬起，水珠顺着腿部线条滴落']}}, {'theme': '夏日海边时尚写真', 'scenes': ['沙滩、米白木质躺椅、海面和鲜艳遮阳伞进入背景', '海边淡金色沙面、蓝色海面、橙黄和湖蓝遮阳伞铺满背景'], 'poses': [], 'poses_by_shot': {'head_shot': ['海风中侧脸面向阳光，碎发被风吹到脸侧，嘴角带着轻松笑意'], 'half_body': ['站在浅水边大腿以上入镜，双手拿着遮阳帽边缘面带微笑，水面上有阳光波光粼粼'], 'full_body': ['脚踩在淡金色沙面上，身体轻轻扭转，长腿线条清楚，海风吹动长发和衣摆']}}, {'theme': '彩色棚拍甜辣大片', 'scenes': ['彩色棚拍墙面、明亮地面和局部高饱和色块铺满背景', '淡粉和湖蓝墙面、湖蓝色地台和柔和棚拍光组成干净背景'], 'poses': [], 'poses_by_shot': {'head_shot': ['正对前方下巴微抬，眼神直接看向前方，手指轻触下颌线'], 'half_body': ['侧身站在彩色背景前，一只手搭在腰侧展现出腰线，头部转向前方'], 'full_body': ['站在彩色墙前转身回望，一只手整理长发，腿线在明亮地面衬托下修长']}}, {'theme': '露台阳光私房写真', 'scenes': ['露台木地板、花盆、远处天空和暖色阳光形成空间层次', '米白露台地板、白色户外桌椅、绿色盆栽和远处蓝天进入背景'], 'poses': [], 'poses_by_shot': {'head_shot': ['靠在白色栏杆旁侧脸看向前方，阳光在面部形成柔和温暖的光晕'], 'half_body': ['坐在露台边缘身体微微前倾，双手自然搭在腰侧，阳光从背后照来形成轮廓光'], 'full_body': ['脚踩在暖色木质露台地板上，身体向前方轻轻转过来，长发在微风中飘动']}}, {'theme': '花园度假风写真', 'scenes': ['花园绿植、鲜艳花朵、米白石板地面和自然阳光', '明亮花园小径、彩色花丛、绿色枝叶和米白地面组成背景'], 'poses': [], 'poses_by_shot': {'head_shot': ['站在花丛中头部微侧，阳光透过花叶在脸上投下斑驳光影'], 'half_body': ['站在花园小径上双手自然垂在身前，身体微侧，花枝在构图边缘形成自然前景'], 'full_body': ['站在花园小径上侧身回望，一只手轻扶发尾，裙摆和长发在微风中有动态']}}, {'theme': '城市街头高饱和写真', 'scenes': ['城市彩色墙面、街边阳光、米白地面和远处店招', '彩色街边立面、阳光斑驳地面、远处店铺招牌形成层次'], 'poses': [], 'poses_by_shot': {'head_shot': ['站在彩色墙前头部转向阳光方向，闭眼享受阳光，睫毛在脸上投下细影'], 'half_body': ['站在彩色街墙前一只手搭在腰侧，头部转向前方，街边阳光从侧面照亮腰线'], 'full_body': ['脚踩在带反光的彩色街道路面上，身体轻轻扭转，长腿线条在阳光中突出']}}, {'theme': '酒店阳台明亮写真', 'scenes': ['酒店阳台栏杆、米白地面、远处天空和暖色阳光形成背景', '明亮酒店阳台、米白地砖、远处城市天际线和局部绿植入镜'], 'poses': [], 'poses_by_shot': {'head_shot': ['靠在阳台栏杆旁头部转向前方，阳光打在脸上形成温暖高光'], 'half_body': ['靠在酒店阳台栏杆旁回头看向前方，一只手扶住栏杆，阳光照亮大腿以上的线条'], 'full_body': ['坐在阳台米白地面上，身体斜向前方，手指轻扶膝盖，远处天际线作为背景']}}]
SHOT_KEYWORDS = ['肩部以上近景写真，头顶完整，脸、锁骨和胸前线条贴近前景', '大腿以半身写真，身体重心和手部动作清楚', '大腿以半身写真，腰臀到大腿线条自然进入构图', '全身写真，人物从头到脚自然入画，身体比例修长完整', '横向构图，人物姿态沿构图展开', '竖向构图，人物身形比例自然']
POSE_KEYWORDS_BY_SHOT = {'head_shot': ['头部微仰感受阳光，闭眼嘴角带笑，手指轻拨湿润的发梢', '正对前方下巴微抬，眼神直接看向前方，手指轻触下颌线', '靠在栏杆旁侧脸看向前方，阳光在面部形成柔和温暖的光晕', '头部微转向前方，闭眼面带放松的表情，睫毛在灯光下投下细影'], 'half_body': ['大腿以上侧身面向前方，一只手搭在腰侧展现出腰线，头部转向前方', '坐在边缘身体微微前倾，双手自然搭在身侧，阳光从背后照来形成轮廓光', '侧身靠在墙边一只手搭在腰侧，腰线和手臂线条在光线下清晰', '身体微微扭转一只手扶墙，展现出腰、胸和背部的线条感'], 'full_body': ['站在明亮地面上身体轻轻扭转，长腿线条清楚，一只手自然垂在身侧', '侧身站在背景前一条腿微曲作为重心，身体呈现出自然的S形曲线', '脚踩在米白地面上身体向前方轻轻转过来，长发和衣摆在微风中飘动', '身体靠在墙边一条腿屈起脚掌贴墙，另一条腿作为重心支撑身体']}
EXPRESSION_KEYWORDS_BY_SCALE = {'normal': ['明媚俏皮笑，眼睛睁大直看前方，眼尾微微上扬', '甜美大笑，像被拍摄者逗笑的一瞬间', '得意挑衅的笑，眼尾上扬直看前方', '阳光活泼的笑容，眼睛睁大，脸颊微微抬起', '带一点怪罪感的笑，像在轻轻责怪拍摄者', '嘴角勾起一抹俏皮笑意，眼睛明亮带着闪光'], 'bold': ['得意挑衅的笑，眼尾上扬直看前方', '慵懒半眯狐眼，嘴角轻轻上扬，嘴唇保持纤薄自然', '妩媚半眯眼，嘴角带坏笑直看前方', '湿润嘴角微张，半眯狐眼直看前方，眼尾上挑', '眼尾上扬，嘴角偏向一侧，露出嘲弄式坏笑'], 'nsfw': ['湿润直视前方，嘴唇微张眼角带红，表情沉浸在被占有的快感中', '半眯狐眼嘴角勾起挑衅的坏笑，嘴唇微张露出舌尖的缝隙', '眼神迷离涣散嘴唇微微张开，表情沉浸在快感之后的慵懒余韵中', '抬眼看向前方，嘴角带着满足又坏笑的表情，嘴唇上沾着湿润的光泽', '闭着眼睛睫毛微颤嘴唇微张，像在高潮的余韵中轻轻喘息']}
OUTFIT_KEYWORDS = ['珊瑚粉和湖蓝色泳装，搭配少量金属小配饰', '柠檬黄短上衣和薄荷绿短裙，颜色明亮清爽', '玫粉色亮面吊带和米白短裤，细小银色配饰点缀', '薰衣草紫轻薄上衣和蜜桃橙短裙，薄纱材质轻透', '天空蓝修身上衣和樱桃粉短裙，局部有湖蓝色边饰', '湖蓝色贴身短裙造型，搭配细链条和透明亮面小配饰']
SHOT_OUTFIT_OPTIONS = {'normal': {'head_shot': ['银色耳饰和湖蓝色发夹靠近脸侧，颈侧有一条细小项链', '薄荷绿发夹固定黑色发丝，耳垂有小颗珍珠耳饰', '珊瑚粉丝巾边缘贴近肩颈，耳饰在阳光下轻微发亮'], 'half_body': ['珊瑚粉短上衣搭配湖蓝色高腰短裤，配一枚细小银色耳饰', '天空蓝运动短上衣搭配白色百褶短裙，手腕有彩色细手链']}, 'bold': {'head_shot': ['细银项链贴近颈侧，湖蓝色耳饰和透明手套指尖靠近脸部', '玫粉色发夹固定黑色发丝，细银耳饰和颈侧小链条贴近脸侧', '湖蓝色指甲停在脸侧，耳饰和发丝高光贴近脸侧'], 'half_body': ['亮黄色轻薄短上衣搭配薄荷绿高腰短裤，透明手套边缘贴近手腕', '玫粉色亮面细吊带搭配天空蓝短裙，腰侧有一条细银链']}}
LIGHT_COLOR_KEYWORDS = ['温暖阳光，高饱和多色协调，皮肤显白但不过曝', '明亮阳光和局部彩色反光，对比度高，颜色鲜艳', '阳光穿过场景形成干净高光和柔和阴影，肤色通透', '清爽夏日调色，主色鲜明，辅助色和点缀色彼此协调', '高对比商业写真调色，背景鲜艳，人物皮肤保持冷白干净']
SUBJECT_DETAIL_OPTIONS = ['脸部、发丝、手指和服装边缘清晰，人物与背景有自然景深', '人物与场景关系清晰，动作像照片瞬间被捕捉下来', '主体气质鲜明，表情、姿态和造型服务同一个画面主题', '人物比例自然，姿势有动态感，视线第一眼落在人物身上']
SCENE_ENVIRONMENT_OPTIONS = ['真实环境铺满背景，背景有可识别的空间层次和生活化细节', '近景有可触摸的材质，中景有主体动作，远景有阳光和颜色层次', '环境不堆砌无关装饰，只保留能强化画面主题的物件', '背景色彩丰富但不抢主体，空间边缘也有真实场景内容']
COMPOSITION_CAMERA_OPTIONS = ['摄影级构图，主体位置稳定，画面重心明确，透视自然', '真实相机视角，人物与环境比例可信，四周没有空白填充感', '镜头从表情带到手部动作和场景细节，构图层次自然展开', '构图边缘保持完整环境信息，避免像竖图硬塞进横向画布']
LIGHTING_COLOR_OPTIONS = ['高对比度高饱和调色，阳光感鲜明，肤色干净透亮', '明亮暖光与局部彩色反光配合，皮肤显白但不过曝', '色彩搭配积极鲜艳，主色、辅助色和点缀色彼此协调', '光线有层次，主体高光干净，阴影保留细节和立体感']
MATERIAL_TEXTURE_OPTIONS = ['布料、皮肤、发丝和地面材质都有真实质感', '服装边缘、金属小配饰和发丝高光清楚可见', '材质细节自然，不出现无意义的透明玻璃块或杂乱反光碎片', '局部反光来自合理材质，例如水面、瓷砖、金属边或亮面布料']
QUALITY_TAIL_OPTIONS_BY_SCALE = {'normal': ['商业写真级清晰度，真实摄影质感，细节干净，画面完成度高', '杂志大片质感，主体清晰，背景自然虚化，颜色通透鲜艳', '真实人像摄影风格，锐度自然，光影立体，色彩饱满', '高质量摄影成片，构图完整，人物比例自然，画面无边框黑边'], 'bold': ['性感私房大片质感，皮肤泛着温润光泽，光影交织氛围感强', '柔光glamour成片，主体清晰，阴影和亮度过渡自然饱满', '高端写真质感，色调温暖鲜艳，人物的每一寸肌肤都质感细腻'], 'nsfw': ['情欲氛围强烈的私房摄影质感，暖黄光影在肌肤上流转，氛围充满张力', '暧昧光影投射在肌肤上，皮肤泛着温润潮湿的光泽，画面沉浸感强', '氛围感强烈的私房情欲镜头，肌肤光感通透，体态曲线被暖光勾勒', '温暖暧昧的光影层次，肌肤光泽和水汽感真实，画面充满私密氛围']}
FINISH_OPTIONS_BY_SCALE = {'normal': ['脸部和发丝锐利，背景自然虚化，柠檬黄和湖蓝色块干净通透。', '高饱和杂志大片调色，阳光高光落在皮肤和发丝上，阴影保留清晰层次。', '服装边缘、手指、金属小配饰和地面反光都清楚可见。', '明亮阳光摄影，主体肤色冷白干净，背景颜色鲜艳但不压过人物。'], 'bold': ['湖蓝色发夹、细银链和发丝高光在阳光下清楚发亮。', '背景保持鲜艳层次，侧边阴影让腰背曲线更立体。', '胸前、锁骨、腰线和腿部高光干净，衣料薄而有真实纹理。', '局部水面或金属反光点亮边缘，色彩饱和但不过曝。'], 'nsfw': ['阴影贴着腰背曲线，色彩浓烈但不脏。', '高光集中在胸腰腿线，背景颜色鲜艳，暗部保留层次。', '发丝、指尖、水光和地面反光清楚，私密距离感鲜明。', '局部反光来自水面、瓷砖或亮面布料，明暗张力清楚。']}
NEGATIVE_PROMPT = 'low quality, blurry, distorted body, bad anatomy, extra fingers, missing fingers, deformed hands, deformed feet, cropped head, cropped body, red lipstick, thick lips, white border, black border, blank side margins, pillarbox, letterbox, padding, vertical-photo-on-wide-canvas, plain empty background, meaningless glass blocks'

def _normalize_shot(shot: str) -> str:
    mapping = {'头部': 'head_shot', '半身': 'half_body', '全身': 'full_body', 'head_shot': 'head_shot', 'half_body': 'half_body', 'full_body': 'full_body'}
    return mapping.get(str(shot or '').strip(), 'full_body')

def _shot_key(shot: str) -> str:
    return _normalize_shot(shot)

def _scale_key(scale: str) -> str:
    text = str(scale or '').strip()
    if text in {'一档', '普通', 'normal'}:
        return 'normal'
    if text in {'二档', '大胆', 'bold'}:
        return 'bold'
    if text in {'三档', 'bold_no_outfit', 'no_outfit', 'd', 'D'}:
        return 'bold_no_outfit'
    if text in {'四档', 'NSFW', 'nsfw'}:
        return 'nsfw'
    return 'bold'

def _is_nsfw_scale(scale: str) -> bool:
    return _scale_key(scale) == 'nsfw'

def _keyword_pool_scale(scale: str) -> str:
    key = _scale_key(scale)
    return 'bold' if key == 'bold_no_outfit' else key

def _skip_outfit_scale(scale: str) -> bool:
    return _scale_key(scale) in {'bold_no_outfit', 'nsfw'}
SCALE_KEYWORD_HINTS = {'一档': '高级时尚写真氛围，穿着完整，阳光鲜艳，偏商业大片', '普通': '高级时尚写真氛围，穿着完整，阳光鲜艳，偏商业大片', 'normal': '高级时尚写真氛围，穿着完整，阳光鲜艳，偏商业大片', '二档': '明亮glamour写真氛围，半眯狐眼直看前方，轻薄鲜艳穿着保留衣物结构', '大胆': '明亮glamour写真氛围，半眯狐眼直看前方，轻薄鲜艳穿着保留衣物结构', 'bold': '明亮glamour写真氛围，半眯狐眼直看前方，轻薄鲜艳穿着保留衣物结构', '三档': '明亮glamour写真氛围，半眯狐眼直看前方，不组合衣着维度', 'bold_no_outfit': '明亮glamour写真氛围，半眯狐眼直看前方，不组合衣着维度', 'no_outfit': '明亮glamour写真氛围，半眯狐眼直看前方，不组合衣着维度', '四档': '成人私房写真氛围，镜头距离更近，腰背曲线和肌肤光泽更大胆', 'NSFW': '成人私房写真氛围，镜头距离更近，腰背曲线和肌肤光泽更大胆', 'nsfw': '成人私房写真氛围，镜头距离更近，腰背曲线和肌肤光泽更大胆'}
SCALE_VARIATION_PACKS = {'normal': {'style': ['清爽时尚杂志风格，珊瑚粉和湖蓝色搭配，表情明亮', '阳光生活方式大片，场景明亮丰富，人物状态轻松鲜活', '高级商业人像风格，服装线条整齐，背景留出干净色块', '度假写真风格，海蓝、橙黄和珊瑚粉形成鲜明搭配', '彩色棚拍时尚大片，淡粉背景、湖蓝服装和柠檬黄地台分层'], 'pose': [], 'outfit': ['珊瑚粉短上衣搭配湖蓝色高腰短裤，配一枚细小银色耳饰', '柠檬黄连衣短裙搭配薄荷绿发夹，造型明亮清爽', '天空蓝运动短上衣搭配白色百褶短裙，手腕有彩色细手链', '珍珠耳饰、湖蓝色发夹和细银手链作为小面积点缀'], 'pose_hints': {'head_shot': ['头部微侧靠近前景，右手轻触脸颊，眼神明亮，嘴角露出俏皮笑意'], 'half_body': ['腰部微侧靠向画面，左手扶腰，右手整理发尾，腰背线条向前方伸展'], 'full_body': ['身体轻轻转向前方，左脚向前一步，右手拨发，左手自然垂在腰侧']}}, 'bold': {'style': ['明亮glamour风格，半眯狐眼直看前方，湿润嘴角微张', '缎面胸衣风格，交叉绑带、鱼骨压线和细链结构清楚', '高饱和成人时尚大片，脸部靠近前景，半眯狐眼直看前方', '泳池或露台性感构图，缎面衣料、腰链和吊带丝袜衬托腰背曲线'], 'pose': [], 'outfit': ['珊瑚粉缎面胸衣上衣搭配湖蓝包臀短裙，鱼骨压线和锁骨链作为亮点', '柠檬黄交叉绑带短上衣搭配薄荷绿百褶短裙，透明手套边缘贴近手腕', '玫粉色挂脖胸衣搭配天空蓝缎面短裙，腰侧有一条细银链', '薰衣草紫薄纱叠层吊带搭配浅色短裙，珍珠链和腿环作为小面积点缀'], 'pose_hints': {'head_shot': ['头部贴近前景，右手指尖停在下颌线旁，半眯狐眼直视前方，嘴角带坏笑'], 'half_body': ['腰部向左侧扭转，左手扶住腰侧，右手拨开发丝，胸腰曲线面对前方'], 'full_body': ['脚踩在地面上侧身回望，左腿伸直向前，右腿微曲支撑，右手拨发，左手扶在腰侧']}}, 'nsfw': {'style': ['成人私房风格，半眯狐眼直看前方，肌肤带温润高光', '高强度诱惑人像，肩颈或腰线向前方展开，姿态更靠近前景', '成人glamour光影，肌肤泛着温润高光，阴影贴着腰背曲线', '半眯狐眼直看前方，嘴角带挑衅坏笑或嘲弄笑'], 'pose': [], 'outfit': [''], 'pose_hints': {'head_shot': ['头部贴近前景，半眯狐眼直视，嘴唇微张，表情带挑衅坏笑和喘息感'], 'half_body': ['身体大幅扭转展现胸前和腰线，手部动作可以扶胸、撑地或拉住腰侧'], 'full_body': ['仰躺在构图中，左腿向前方弯起，右腿向侧面伸展，双手撑在身体两侧']}}}
SHOT_KEYWORD_HINTS = {'head_shot': '肩膀及以上近景，头顶完整，脸、颈部和肩线贴近前景', '头部': '肩膀及以上近景，头顶完整，脸、颈部和肩线贴近前景', 'half_body': '大腿以半身写真，脸、胸部、腰线和手部动作进入构图', '半身': '大腿以半身写真，脸、胸部、腰线和手部动作进入构图', 'full_body': '全身写真，人物从头到脚自然入画，身体比例修长完整', '全身': '全身写真，人物从头到脚自然入画，身体比例修长完整'}

def clean_keywords(keywords: str) -> str:
    text = re.sub('\\s+', ' ', str(keywords or '')).strip()
    text = text.strip('，,。.;；、 ')
    return text

def _choice(options: Iterable[str], rng: random.Random) -> str:
    values = [value for value in options if value]
    if not values:
        return ''
    return rng.choice(values)

def _trim_prompt(text: str, limit: int=MAX_KEYWORD_PROMPT_LENGTH) -> str:
    prompt = re.sub('\\s+', '', text)
    prompt = re.sub('，{2,}', '，', prompt)
    prompt = re.sub('。{2,}', '。', prompt)
    if len(prompt) <= limit:
        return prompt
    clauses = re.split('(?<=[。；;])', prompt)
    result = ''
    for clause in clauses:
        if len(result) + len(clause) > limit:
            break
        result += clause
    if result:
        return result.rstrip('，,；;') + '。'
    return prompt[:limit].rstrip('，,；;') + '。'

def _scale_hint(scale: str) -> str:
    return SCALE_KEYWORD_HINTS.get(str(scale or '').strip(), '')

def _scale_variation_parts(scale: str, shot: str, rng: random.Random) -> list[str]:
    pack = SCALE_VARIATION_PACKS.get(_keyword_pool_scale(scale), SCALE_VARIATION_PACKS['bold'])
    shot_key = _shot_key(shot)
    pose_hints = pack.get('pose_hints', {})
    shot_pose = pose_hints.get(shot_key) or pose_hints.get('full_body') or []
    return [_choice(pack.get('style', []), rng), _choice(shot_pose, rng), _choice(pack.get('outfit', []), rng)]

def _shot_hint(shot: str) -> str:
    return SHOT_KEYWORD_HINTS.get(str(shot or '').strip(), '')

def _character_for_shot(shot: str) -> str:
    return CHARACTER_BY_SHOT.get(_shot_key(shot), FIXED_CHARACTER_ORIGINAL)

def _allowed_by_shot(text: str, shot: str) -> bool:
    shot_key = _shot_key(shot)
    forbidden = {'head_shot': ['胸', '腰', '臀', '腿', '膝', '脚', '短裙', '短裤', '泳装', '吊带', '脚链', '脚指甲', '腰背曲线'], 'half_body': ['大腿', '小腿', '膝', '脚', '脚链', '脚指甲']}.get(shot_key, [])
    return not any((word in str(text or '') for word in forbidden))

def _choice_for_shot(options: Iterable[str], rng: random.Random, shot: str) -> str:
    values = [value for value in options if value and _allowed_by_shot(value, shot)]
    return rng.choice(values) if values else ''

def _outfit_for_shot(scale: str, shot: str, rng: random.Random) -> str:
    scale_key = _scale_key(scale)
    if _skip_outfit_scale(scale):
        return ''
    pool_key = _keyword_pool_scale(scale)
    shot_key = _shot_key(shot)
    shot_pool = SHOT_OUTFIT_OPTIONS.get(pool_key, {}).get(shot_key, [])
    if shot_pool:
        return _choice(shot_pool, rng)
    pool = SCALE_VARIATION_PACKS.get(pool_key, {}).get('outfit', [])
    if pool_key == 'normal':
        pool = [*pool, *OUTFIT_KEYWORDS]
    return _choice_for_shot(pool, rng, shot_key)

def _theme_pose_for_shot(package: dict, shot: str, rng: random.Random) -> str:
    pose_by_shot = package.get('poses_by_shot', {})
    shot_key = _shot_key(shot)
    pool = pose_by_shot.get(shot_key, [])
    if pool:
        return rng.choice(pool)
    return _choice(package.get('poses', []), rng)

def build_auto_keywords(rng: random.Random, scale: str='', shot: str='') -> str:
    parts = build_auto_keyword_parts(rng, scale=scale, shot=shot)
    return '，'.join(parts)

def _trim_prompt_parts(parts: Iterable[str], limit: int=MAX_KEYWORD_PROMPT_LENGTH) -> str:
    result = ''
    for raw in parts:
        part = re.sub('\\s+', '', str(raw or '')).strip('，。；; ŁŹĄŁ')
        if not part:
            continue
        candidate = part if not result else f'{result}，{part}'
        if len(candidate) <= limit:
            result = candidate
    return result.rstrip('，。；; ŁŹĄŁ') + '。' if result else ''

def _sentence_from_parts(parts: Iterable[str]) -> str:
    cleaned = []
    for raw in parts:
        part = re.sub('\\s+', '', str(raw or '')).strip('，。；; ŁŹĄŁ')
        if part:
            cleaned.append(part)
    return '，'.join(cleaned).rstrip('，。；; ŁŹĄŁ') + '。' if cleaned else ''

def _trim_prompt_sections(sections: Iterable[Iterable[str]], limit: int=MAX_KEYWORD_PROMPT_LENGTH) -> str:
    result_sections = []
    for section in sections:
        sentence = _sentence_from_parts(section)
        if not sentence:
            continue
        candidate_sections = [*result_sections, sentence]
        candidate = '\n\n'.join(candidate_sections)
        if len(candidate) <= limit:
            result_sections.append(sentence)
    return '\n\n'.join(result_sections)
CONCRETE_REPLACEMENTS = (('姿态主动诱惑', '身体向前景靠近，半眯狐眼直看前方'), ('姿势主动', '身体向前景靠近'), ('视线有挑逗感', '半眯狐眼直看前方，眼尾上挑'), ('诱惑眼神', '半眯狐眼直看前方，眼尾上挑'), ('主动勾引镜头', '半眯狐眼直看前方，嘴角带坏笑'), ('主动邀请镜头', '眼睛睁大直看前方，眼尾微微上扬'), ('主动邀请前方视线', '眼睛睁大直看前方，眼尾微微上扬'), ('勾引前方视线', '半眯狐眼直看前方，眼尾上挑'), ('眼神像在勾引', '半眯狐眼直看前方，眼尾上挑'), ('湖蓝色耳饰', '湖蓝色耳饰'), ('湖蓝色发夹', '湖蓝色发夹'), ('湖蓝色指甲', '湖蓝色指甲'), ('湖蓝色衣料', '玫粉或湖蓝衣料'), ('湖蓝色边饰', '柠檬黄细边饰'), ('米白露台地板', '米白露台地板'), ('米白地砖', '米白地砖'), ('米白地面', '米白地面'), ('米白石板地面', '米白石板地面'), ('米白木质躺椅', '米白木质躺椅'), ('米白短裤', '米白短裤'), ('米白', '米白'), ('湖蓝色', '湖蓝色'))

def _concretize_prompt(text: str) -> str:
    result = str(text or '')
    for abstract, concrete in CONCRETE_REPLACEMENTS:
        result = result.replace(abstract, concrete)
    return result

def _strip_outfit_language_for_no_outfit_scale(text: str, scale: str) -> str:
    if not _skip_outfit_scale(scale):
        return text
    cleaned_sections = []
    for section in str(text or '').split('\n\n'):
        if any((marker in section for marker in ('上衣', '短裙', '短裤', '连衣裙', '泳装', '吊带', '穿着', '服装', '衣料', '裙摆', '肩带'))):
            continue
        cleaned_sections.append(section)
    return '\n\n'.join((part for part in cleaned_sections if part.strip()))

def build_auto_keyword_parts(rng: random.Random, scale: str='', shot: str='') -> list[str]:
    theme_package = _choice(THEME_SCENE_PACKAGES, rng)
    if not isinstance(theme_package, dict):
        theme_package = {}
    scale_key = _scale_key(scale)
    pool_key = _keyword_pool_scale(scale)
    scale_pack = SCALE_VARIATION_PACKS.get(pool_key, SCALE_VARIATION_PACKS['bold'])
    shot_key = _shot_key(shot)
    pose_hints = scale_pack.get('pose_hints', {})
    shot_pose_hint = _choice(pose_hints.get(shot_key) or pose_hints.get('full_body') or [], rng)
    parts = [_choice(SUBJECT_KEYWORDS, rng), _scale_hint(scale), _choice(scale_pack.get('style', []), rng), shot_pose_hint]
    if not _skip_outfit_scale(scale):
        parts.append(_choice(scale_pack.get('outfit', []), rng))
    parts.extend([theme_package.get('theme') or _choice(THEME_KEYWORDS, rng), _shot_hint(shot) or _choice(SHOT_KEYWORDS, rng), _theme_pose_for_shot(theme_package, shot_key, rng), _choice(EXPRESSION_KEYWORDS_BY_SCALE.get(pool_key, EXPRESSION_KEYWORDS_BY_SCALE['normal']), rng), '' if _skip_outfit_scale(scale) else _choice(OUTFIT_KEYWORDS, rng), _choice(theme_package.get('scenes') or [], rng), _choice(LIGHT_COLOR_KEYWORDS, rng)])
    return [part for part in parts if part]

def build_auto_keyword_sections(rng: random.Random, scale: str='', shot: str='') -> list[list[str]]:
    theme_package = _choice(THEME_SCENE_PACKAGES, rng)
    if not isinstance(theme_package, dict):
        theme_package = {}
    scale_key = _scale_key(scale)
    pool_key = _keyword_pool_scale(scale)
    scale_pack = SCALE_VARIATION_PACKS.get(pool_key, SCALE_VARIATION_PACKS['bold'])
    shot_key = _shot_key(shot)
    pose_hints = scale_pack.get('pose_hints', {})
    shot_pose_hint = _choice(pose_hints.get(shot_key) or pose_hints.get('full_body') or [], rng)
    scale_outfit = _outfit_for_shot(scale, shot_key, rng)
    return [[_shot_hint(shot) or _choice(SHOT_KEYWORDS, rng), _choice_for_shot(scale_pack.get('style', []), rng, shot_key)], [_character_for_shot(shot_key)], [scale_outfit], [_theme_pose_for_shot(theme_package, shot_key, rng), _choice(EXPRESSION_KEYWORDS_BY_SCALE.get(pool_key, EXPRESSION_KEYWORDS_BY_SCALE['normal']), rng)], [theme_package.get('theme') or _choice(THEME_KEYWORDS, rng), _choice(theme_package.get('scenes') or [], rng), _choice(LIGHT_COLOR_KEYWORDS, rng)], [_choice_for_shot(FINISH_OPTIONS_BY_SCALE.get(pool_key, FINISH_OPTIONS_BY_SCALE['normal']), rng, shot_key)]]

def generate_keyword_expansion_prompt(seed_text: str='', scale: str='', shot: str='') -> dict:
    seed = str(seed_text or time.time_ns())
    rng = random.Random(seed)
    sections = build_auto_keyword_sections(rng, scale=scale, shot=shot)
    clean_parts = [part for section in sections for part in section if part]
    clean = '，'.join(clean_parts)
    prompt = _strip_outfit_language_for_no_outfit_scale(_concretize_prompt(_trim_prompt_sections(sections)), scale)
    clean = _strip_outfit_language_for_no_outfit_scale(clean, scale)
    return {'prompt': prompt, 'keywords': clean, 'negative_prompt': NEGATIVE_PROMPT, 'signature': f"keyword_expansion|{abs(hash(f'{seed}|{scale}|{shot}'))}", 'source': 'keyword_expansion', 'scale': scale, 'shot': shot}
