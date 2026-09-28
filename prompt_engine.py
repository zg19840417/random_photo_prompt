from __future__ import annotations

import hashlib
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prompt_data import *  # noqa: F403
from negative_prompt_engine import build_negative_prompt
from prompt_composer import COMPOSER_SCALES, compose_parts
from prompt_constants import (
    PROMPT_PART_ORDER,
    RESOLUTIONS,
)
from prompt_normalize import (
    normalize_aspect,
    normalize_scale,
    normalize_shot,
    shot_label,
)
from prompt_postprocess import (
    clean_global_prompt_text,
    clean_prompt_text,
    clean_sentence,
    ensure_sentence,
    feedback_tags,
    naturalize_pose_framing,
    normalize_quality_line,
    simplify_pose_language,
    strengthen_expression,
)


def choose(values, rng: random.Random) -> str:
    return rng.choice(values) if values else ""


def _is_ancient_era(era: str) -> bool:
    return str(era or "").strip() in {"ancient", "古装", "古代"}


_BAR_COUNTER_MIST_SCENE = "环境光设定：夜店吧台后方大团紫色烟雾被冷紫逆光照亮，右后方红色射灯切过暗部，幽蓝霓虹散景包住背景，黑色湿润吧台从左下角斜向延伸，前景酒瓶和玻璃杯虚化反光，淡粉补光落在脸、锁骨和手指上"
_BAR_COUNTER_BOLD_OUTFIT = "夜店吧台半身造型，黑色细带亮钻胸衣配银色身体链，锁骨链、手链、臂环和腰链在紫色灯光下反光，关键部位由黑色布料完整覆盖，肩颈、胸线边缘和细腰成为视觉重点"
_BAR_COUNTER_HALF_BODY_POSE = "人物侧坐在吧台高脚椅上，上身前倾靠近黑色吧台，左前臂压在吧台边缘，右手举着威士忌杯停在肩线外侧，肩膀转向镜头，腰臀向画面右下方延伸，头部回望镜头，眼神直视镜头，嘴角轻轻上扬"


_SCENE_CATEGORY_MARKERS = {
    "nightclub": ("夜店", "吧台", "酒吧", "酒廊", "包厢", "霓虹", "威士忌杯", "酒杯"),
    "bedroom": ("卧室", "床沿", "床边", "床头", "床单", "纱帘"),
    "bathroom": ("浴室", "镜面", "镜台", "水汽", "瓷砖"),
    "pool": ("泳池", "池边", "池水", "水面", "遮阳伞"),
    "garden": ("庭院", "花园", "森林", "木栈道", "植物", "竹林", "树影"),
    "cafe": ("咖啡馆", "甜品店", "书店", "更衣间", "商店", "美术馆"),
    "beach": ("海边", "海岸", "沙滩", "湖边", "湖面"),
    "ancient": ("古代", "宫苑", "画舫", "书房", "屏风", "铜镜", "民国", "苗疆", "敦煌"),
}


def _scene_category(parts: dict[str, str]) -> str:
    text = str(parts.get("scene_light") or "")
    for category, markers in _SCENE_CATEGORY_MARKERS.items():
        if any(marker in text for marker in markers):
            return category
    return "other"


_MODERN_THEME_BLUEPRINTS = {
    "head_mirror_mist": {
        "scene": {
            "head_shot": "环境光设定：雾面浴室镜前头部近景，镜面水汽和深色瓷砖压成灰蓝暗部，冷白湿光只托住眼尾、唇峰、下颌和镜边水珠，背景不展开",
        },
        "outfit": {
            "head_shot": "浴室湿光近景造型，画面边缘只露出黑色细带、银色锁骨链和少量湿润薄纱边缘",
        },
        "pose": {
            "head_shot": "头部贴近雾面镜边缘，指尖停在镜面水汽旁，眼神越过镜中暗光看向镜头，嘴唇微开",
        },
        "quality": "低曝光湿光头部调色，镜面反光小面积出现，肤色保留灰度和真实纹理",
    },
    "head_bedroom_veil": {
        "scene": {
            "head_shot": "环境光设定：深夜卧室纱帘头部近景，床头灯和半透明纱帘压成淡粉暗部，暖粉窄光只托住脸侧、唇峰和纱帘褶皱，正面不打亮",
        },
        "outfit": {
            "head_shot": "卧室纱帘近景造型，画面边缘只露出蕾丝肩带、细链和薄纱领口，服装不抢脸",
        },
        "pose": {
            "head_shot": "头部靠近半透明纱帘，手指轻轻勾住帘边，眼神从纱影后看向镜头，嘴唇微开",
        },
        "quality": "低曝光暖色头部私房调色，暗角自然晕染，肤色保留灰度",
    },
    "head_fog_lake": {
        "scene": {
            "head_shot": "环境光设定：雾林湖边头部近景，芦苇、湖面和深绿树影压成银蓝背景，冷白窄光只托住眼睛、下颌线和发丝边缘",
        },
        "outfit": {
            "head_shot": "雾林湖边近景造型，画面边缘只露出浅色薄纱领口、细银链和少量花边",
        },
        "pose": {
            "head_shot": "头部靠近树干阴影，手指拨开脸侧枝叶，眼神从叶影缝隙看向镜头，嘴唇微开",
        },
        "quality": "低曝光冷雾头部调色，银蓝暗部有层次，皮肤边缘由窄光托亮",
    },
    "head_jazz_bar": {
        "scene": {
            "head_shot": "环境光设定：深夜爵士酒廊头部近景，暗红墙面、黄铜灯和幽蓝阴影虚化成背景，暖金窄光只托住脸侧、唇峰、颈线和耳侧饰品",
        },
        "outfit": {
            "head_shot": "酒廊近景造型，画面边缘只露出黑色缎面领口、细项链和少量金属扣反光",
        },
        "pose": {
            "head_shot": "头部靠近暗红酒廊背景，一只手轻扶耳侧珍珠耳饰，眼神从黄铜灯暗影下看向镜头，嘴角轻轻上扬",
        },
        "quality": "低曝光酒廊头部胶片调色，暖金反光小面积出现，暗部保留层次",
    },
    "head_garden_dusk": {
        "scene": {
            "head_shot": "环境光设定：黄昏庭院花影头部近景，花枝、石墙和远处薄雾压成暗绿色背景，金橙侧逆光只勾住发丝、脸侧和花枝边缘",
        },
        "outfit": {
            "head_shot": "黄昏庭院近景造型，画面边缘只露出浅色蕾丝领口、薄纱花边和细链",
        },
        "pose": {
            "head_shot": "头部靠近花枝阴影，手指轻轻拨开脸侧叶片，眼神从花影缝隙看向镜头，嘴唇微开",
        },
        "quality": "低曝光黄昏花影头部调色，侧逆光清楚，肤色保留灰度",
    },
    "nightclub_bar": {
        "scene": {
            "head_shot": "环境光设定：深夜夜店吧台近景，背景只有幽蓝霓虹散景、黑色吧台反光和少量酒杯高光，冷紫侧逆光切过脸侧、颈线和黑色手指甲，淡粉补光只落在嘴唇和锁骨边缘",
            "half_body": "环境光设定：深夜夜店吧台半身场景，黑色吧台从画面下缘斜向进入，幽蓝霓虹和暗红射灯在背景虚化，冷紫侧窄光只切过脸侧、锁骨、胸前衣料边缘和手指，酒杯只作为小面积暗亮反光",
            "full_body": "环境光设定：深夜地下夜店舞台全身场景，黑色地面只有局部湿润反光，幽蓝霓虹从后方虚化，冷紫边缘光勾出腰线、长腿和脚下地面，背景不展开成完整房间",
        },
        "outfit": {
            "head_shot": "夜店近景造型，画面边缘只露出黑色细肩带、银色锁骨链和少量亮钻胸衣边缘，服装不抢脸",
            "half_body": "黑色亮钻胸衣搭配银色身体链，细肩带贴住肩颈，胸衣鱼骨线和金属扣清楚，外层黑色薄纱半披在手臂上",
            "full_body": "黑色亮钻胸衣搭配高腰缎面包臀短裙，银色腰链和腿环形成细亮点，黑色薄透吊带丝袜贴住腿线，脚下是黑色细带高跟鞋",
        },
        "pose": {
            "head_shot": "头部靠近吧台侧光，下巴微抬后俯视镜头，右手握住细长酒杯停在肩线外侧，黑色手指甲清楚，嘴唇微开，眼神带挑衅",
            "half_body": "人物侧坐在吧台高脚椅上，上身前倾靠近黑色吧台，左前臂压在吧台边缘，右手举着威士忌杯停在肩线外侧，肩膀转向镜头，头部回望镜头，嘴角轻轻上扬",
            "full_body": "人物站在低机位镜头前方，左腿承重，右腿向侧前方点地，左手扶住腰链，右手停在大腿上，头部微低俯视镜头，嘴唇微开",
        },
        "quality": "夜景私房调色，暗部压低，霓虹只做小面积反光，肤色由窄光托亮",
    },
    "mist_bedroom": {
        "scene": {
            "head_shot": "环境光设定：深夜卧室近景，粉米色床头灯被纱帘柔化，背景只留下浅粉暗部和床头轮廓，暖粉窄光只托住脸侧、唇峰、颈侧和肩线，正面不打亮",
            "half_body": "环境光设定：深夜卧室床沿半身场景，薄纱帘和床头灯在背景虚化，淡粉暖光只落在脸侧、肩颈、胸前衣料边缘和细腰，床面与房间边角保持压暗",
            "full_body": "环境光设定：深夜卧室床沿全身场景，床头灯和纱帘只形成淡粉暗部，暖粉侧后窄光沿腰线、长腿和脚下床边地面滑过，脸和皮肤保留灰度，房间边缘压暗不展开",
        },
        "outfit": {
            "head_shot": "卧室私房近景造型，画面边缘露出浅粉蕾丝肩带、细锁骨链和薄纱领口",
            "half_body": "浅粉蕾丝吊带短上衣搭配半透明薄纱开衫，胸衣鱼骨线、花边肩带和细银扣清楚，腰间有细链",
            "full_body": "浅粉蕾丝吊带短裙搭配半透明薄纱开衫，裙摆一侧微开衩，细腰链和脚踝链贴住皮肤，整体柔软但结构清楚",
        },
        "pose": {
            "head_shot": "头部侧靠在肩线上，左手指尖停在脸旁发丝间，嘴唇微开，舌尖轻轻探出碰到下唇，眼神从睫毛下方看向镜头",
            "half_body": "人物坐在床沿，身体向镜头前倾，左手停在锁骨下方，右手扶住腰侧，肩线一高一低，头部微低，抬眼看向镜头",
            "full_body": "人物坐在床沿前缘，上身后靠，双腿斜向画面下方延展，裸足落在床边地面，左手撑在身后，右手停在大腿上，头部回望镜头",
        },
        "quality": "低曝光暖色私房调色，暗角自然晕染，肤色保留灰度，只带小面积粉金边缘反光",
    },
    "mirror_bathroom": {
        "scene": {
            "head_shot": "环境光设定：玻璃浴室镜前近景，雾面镜子和水汽只在背景形成灰蓝虚化，冷白湿光只托住眼尾、唇峰、下颌和镜边水珠，少量水珠反光贴近脸侧",
            "half_body": "环境光设定：玻璃浴室半身场景，雾面镜和深色瓷砖压暗成背景，幽蓝湿光只落在脸侧、肩颈、胸前衣料边缘和细腰，水汽只保留薄薄一层",
            "full_body": "环境光设定：玻璃浴室全身场景，深色瓷砖和雾面镜反光包住背景，幽蓝湿光沿腰线、长腿和脚下湿地面滑过，湿润地面只有水珠和瓷砖反光",
        },
        "outfit": {
            "head_shot": "浴室湿光近景造型，画面边缘只露出黑色细带和银色锁骨链",
            "half_body": "黑色挂脖连体泳装搭配半透明湿感薄纱罩衫，腰侧弧形镂空和银色小扣清楚，衣料边缘有水光",
            "full_body": "黑色挂脖连体泳装搭配短款半透明湿感罩衫，腰侧弧形镂空清楚，脚踝链贴在裸足上方，整体是浴室湿光造型",
        },
        "pose": {
            "head_shot": "头部贴近雾面镜边缘，下巴微低，一只手扶住镜台边缘，嘴唇微开，眼神直视镜头",
            "half_body": "人物半身靠近镜面，左手停在锁骨旁，右手压在腰侧，肩颈向镜头前倾，头部侧偏直视镜头",
            "full_body": "人物站在湿润瓷砖上，前脚落在画面下缘，后腿拉长，身体向镜面侧转，左手扶住腰侧，右手停在大腿上，头部回望镜头",
        },
        "quality": "低曝光湿光高对比调色，暗部干净，皮肤边缘有小面积冷白水光",
    },
    "pool_noon": {
        "scene": {
            "head_shot": "环境光设定：正午泳池边近景，背景只留下湖蓝水面虚化和白色遮阳棚色块，强天光被压柔后照亮脸、颈侧、锁骨边缘和湿发边缘",
            "half_body": "环境光设定：正午泳池边半身场景，湖蓝水面和白色遮阳棚在背景虚化，水面反光只落在脸、肩颈、胸前衣料边缘和腰线",
            "full_body": "环境光设定：遮阳棚下的泳池边全身场景，背景压暗虚化成湖蓝水面和白色遮阳棚色块，水面反光只在腰线、长腿边缘和脚下瓷砖形成小面积暗亮点，脸和皮肤保留灰度不过白",
        },
        "outfit": {
            "head_shot": "泳池近景造型，画面边缘只露出湖蓝细肩带、透明肩带扣和银色锁骨链",
            "half_body": "湖蓝挂脖连体泳装搭配白色短款薄纱罩衫，腰侧弧形镂空、银色小扣和湿润衣料边缘清楚",
            "full_body": (
                "湖蓝挂脖连体泳装搭配白色开襟短罩衫，腰侧弧形镂空，脚踝链贴在裸足上方，浅色池边瓷砖衬出腿线",
                "白色细带连体泳装搭配湖蓝半透明短罩衫，银色腰链和脚踝链形成小亮点，裸足贴近池边瓷砖",
                "浅青色缎面胸衣搭配白色高腰开衩短裙，外层薄纱短披肩被池边风轻轻带起，脚踝链贴在裸足上方",
            ),
        },
        "pose": {
            "head_shot": "头部微微后仰，左手停在肩线下方衣料边缘，嘴唇微开，眼神从水面反光下直视镜头",
            "half_body": "人物坐在池边，半身向镜头前倾，左手停在肩侧，右手扶住腰侧，头部微低俯视镜头，嘴角轻轻上扬",
            "full_body": "低机位从池边瓷砖向上拍，整只脚自然落在画面下缘，人物一腿弯曲一腿向后伸长，左手停在大腿上，右手扶住腰侧，头部俯视镜头",
        },
        "quality": "低曝光泳池私房调色，水面反光小面积出现，肤色保留灰度和真实纹理",
    },
    "garden_fog": {
        "scene": {
            "head_shot": "环境光设定：雨后庭院近景，背景只有深绿色植物和湿石板反光虚化，冷白窄光照亮脸、发丝、颈侧和黑色手指甲，薄雾停在植物后方",
            "half_body": "环境光设定：雨后庭院半身场景，湿石板、深绿色植物和少量白花虚化成背景，冷白侧光照亮脸、肩颈、胸前衣料边缘和手指，薄雾只停在远处",
            "full_body": "环境光设定：雨后森林木栈道全身场景，湿木板和深绿色植物压暗成背景，银蓝侧后窄光只勾出轮廓、腿线和脚下木栈道边缘，脸和皮肤不被正面照亮，薄雾停在远处树影之间",
        },
        "outfit": {
            "head_shot": "雨后庭院近景造型，画面边缘只露出薄荷绿蕾丝肩带、细银链和浅色薄纱领口",
            "half_body": "薄荷绿蕾丝吊带上衣搭配浅灰薄纱短外搭，花边肩带、细银扣和腰侧细带清楚，材质轻而湿润",
            "full_body": (
                "薄荷绿蕾丝吊带连衣短裙搭配浅灰薄纱外搭，裙摆有细花边，脚踝银链贴住裸足，整体像雨后庭院私房造型",
                "雾白蕾丝胸衣搭配浅青半透明开衩长裙，细银腰链压住腰线，裸足踩在湿木板暗光里",
                "淡灰蓝缎面吊带上衣搭配薄纱不规则短裙，裙摆有细碎蕾丝边，脚踝链和黑色手指甲形成小面积亮点",
            ),
        },
        "pose": {
            "head_shot": "头部从湿发丝间微微侧偏，右手停在肩线下方衣料边缘，嘴唇微开，眼神斜看镜头",
            "half_body": "人物侧身倚在湿石墙边，左手停在胸前衣料边缘，右手扶住腰侧，肩颈向镜头前倾，头部回望镜头",
            "full_body": "人物站在木栈道边缘，左腿承重，右腿向侧前方点地，身体侧转成S形，左手扶住腰侧，右手停在大腿上，头部回望镜头",
        },
        "quality": "低曝光冷雾私房调色，暗部有绿色层次，皮肤边缘由窄光托亮但不过白",
    },
    "cinematic_lounge": {
        "scene": {
            "head_shot": "环境光设定：Art Deco酒廊近景，背景只有暗红丝绒、黄铜灯和幽蓝阴影虚化，暖金窄光只托住脸侧、唇峰、颈线和项链边缘，正面不打亮",
            "half_body": "环境光设定：Art Deco酒廊半身场景，暗红丝绒沙发和黄铜壁灯虚化在背景，暖金侧后窄光只切过脸侧、锁骨、胸前衣料边缘和腰线，幽蓝暗部压住空间边缘",
            "full_body": (
                "环境光设定：深夜极暗酒吧包厢全身场景，无主灯设计，深色沙发、黑灰墙面和地毯几乎沉入暗部，"
                "只有极弱紫色、粉色和幽蓝霓虹在空气薄雾里形成模糊光晕，窄光只擦过脸侧、腰线、腿部轮廓和黑色脚趾甲，背景不展开"
            ),
        },
        "outfit": {
            "head_shot": "酒廊近景造型，画面边缘只露出酒红缎面细肩带、黄铜色细项链和少量蕾丝边",
            "half_body": "酒红缎面胸衣搭配黑色薄纱短外搭，胸衣鱼骨线、黄铜小扣和细腰链清楚，材质柔亮",
            "full_body": "酒红缎面胸衣搭配黑色高腰开衩半裙，黄铜色腰链和腿环形成细亮点，黑色薄透长筒丝袜贴住腿线",
        },
        "pose": {
            "head_shot": "头部靠近暗红背景，下巴微低，抬眼看镜头，左手停在肩头衣料边缘，嘴角轻轻上扬",
            "half_body": "人物坐在丝绒沙发边缘，上身前倾，左手停在胸前衣料边缘，右手扶住腰侧，头部侧偏直视镜头",
            "full_body": "人物坐在深色沙发前缘，一条腿弯曲成不对称M形贴近身体，另一条腿沿地面斜向伸出，整只脚自然侧向落地，脚趾放松不朝向镜头，上身后仰，左手撑住沙发坐垫，右手停在锁骨下方，头部大幅后仰后俯视镜头",
        },
        "quality": "低曝光酒廊胶片调色，暖金反光只做小面积边缘光，暗部保留丝绒层次，禁止正面硬闪",
    },
}

_ANCIENT_THEME_BLUEPRINTS = {
    "ancient_rain_corridor": {
        "scene": "环境光设定：古代雨夜回廊场景，青瓦、木柱和湿石阶在背景压暗，纸灯笼暖光从侧后方落下，冷白雨光勾出脸、腰线、长腿和脚下湿石阶，木纹和瓦片细节围住人物",
        "outfit": "月白交领短襦搭配浅青高腰长裙，外层薄纱披帛从肩臂垂下，绣边腰带收住细腰，裸足踩在浅色裙摆下方，衣着是完整古装结构",
        "pose": "人物站在回廊木柱旁，左手扶住木柱，右手停在腰带边缘，左腿承重，右腿向侧前方点地，头部从肩侧回望镜头，嘴唇微开",
        "quality": "雨夜古风私房调色，灯笼暖光和冷白雨光分层，暗部保留木纹和湿石阶反光",
    },
    "ancient_palace_banquet": {
        "scene": "环境光设定：古代宫苑夜宴场景，屏风、低酒案、宫灯和暗色帷幕围住背景，暖金宫灯照亮脸、锁骨、腰线和手指，红木地面只保留局部反光",
        "outfit": "唐制织金短襦搭配高腰曳地长裙，外层薄纱披帛绕过手臂，金色绣边和玉坠压住腰线，裸足从曳地裙摆下方露出，整体是夜宴古装",
        "pose": "人物侧坐在低酒案旁，左手扶住案沿，右手停在腰侧披帛上，身体向镜头微微前倾，头部回望镜头，眼神带挑衅",
        "quality": "暖金宫灯私房调色，红木暗部有层次，肤色由窄光托亮",
    },
    "ancient_study_candle": {
        "scene": "环境光设定：古代书房夜读场景，卷轴、香炉、低案和烛台在背景中虚化，琥珀烛光只照亮脸、手指、锁骨和衣襟边缘，暗部保留纸卷和木纹层次",
        "outfit": "宋制月白交领褙子搭配浅灰高腰裙，领口有细绣边，腰间系窄织带和小玉坠，袖口宽而轻，裸足从浅灰裙摆下方露出",
        "pose": "人物跪坐在低案旁，左手停在卷轴边缘，右手扶住腰侧织带，头部低垂，抬眸看向镜头，嘴角轻轻上扬",
        "quality": "琥珀烛光古风调色，暗部安静，纸面和木纹反光细腻",
    },
    "dunhuang_dancer": {
        "scene": "环境光设定：敦煌壁画风舞台场景，粉金壁画、薄纱帷幕和金色小灯在背景压成柔和色块，暖金侧逆光照亮肩颈、腰线、披帛和脚下地面",
        "outfit": "敦煌舞姬古装，短襦搭配高腰长裙，轻薄披帛绕过双臂，臂钏、流苏和珠片形成小面积金色反光，裸足点在地面上",
        "pose": "人物侧身起舞，左手抬过头顶带起披帛，右手停在腰侧，腰线向外扭转，左腿承重，右脚点地，头部回望镜头",
        "quality": "粉金敦煌胶片调色，暖金边缘光清楚，背景壁画柔和虚化",
    },
    "ancient_hot_spring": {
        "scene": "环境光设定：古代温泉石壁场景，竹帘、湿石壁和水汽围住背景，暖白湿光从侧面照亮脸、肩颈、腰线和脚下湿木地板，水汽保持薄层",
        "outfit": "月白交领薄衫搭配浅杏色高腰裙，外层湿润薄纱披帛贴近肩臂，绣边腰带收住细腰，裸足从浅杏色裙摆下方露出",
        "pose": "人物坐在温泉木台边，左手撑在身侧，右手停在锁骨下方，身体侧转后回望镜头，左腿弯曲，右腿向下伸长点地",
        "quality": "暖白湿光古风调色，水汽柔和，皮肤高光不过曝",
    },
    "ancient_boat_night": {
        "scene": "环境光设定：古代画舫夜雾场景，雕花窗、船舷、湖面灯影和薄纱帘完整属于船舫空间，幽蓝水光从窗外反上来，暖色灯笼只照亮脸、腰线和手指",
        "outfit": "江南交领薄衫搭配浅藕色高腰长裙，内层抹胸边缘被交领遮住，外层薄纱披帛垂在手臂旁，玉坠和绣边腰带清楚，裸足从长裙下方露出",
        "pose": "人物坐在画舫窗边，左手扶住雕花窗框，右手停在腰带上，身体侧身向镜头前倾，头部从肩侧回望镜头，嘴唇微开",
        "quality": "画舫夜雾胶片调色，幽蓝水光和暖灯笼分层，暗部有木纹细节",
    },
    "ancient_bamboo_moon": {
        "scene": "环境光设定：古代竹林月色场景，竹影、石径和远处薄雾形成银蓝背景，月光从侧上方切过脸、肩颈、腰线和脚下石径，竹叶暗影围住人物边缘",
        "outfit": "青绿山水纹交领上衣搭配月白高腰长裙，薄纱披帛从手臂后侧垂下，玉坠和窄绣边腰带压住细腰，裸足从月白裙摆下方露出",
        "pose": "人物站在竹林石径上，左腿承重，右腿向后点地，左手轻扶披帛，右手停在腰侧，头部回望镜头，眼神微眯",
        "quality": "银蓝月色古风调色，竹影暗部有层次，肤色由月光托亮",
    },
    "ancient_theater_backstage": {
        "scene": "环境光设定：古代戏台后台场景，红木妆台、铜镜、戏服架和纸灯笼围住背景，暖红灯光照亮脸、手指、衣襟和腰线，铜镜只保留局部反光",
        "outfit": "花魁风交领短袄搭配织金高腰长裙，盘扣、步摇、披帛和金色绣边清楚，裸足从红色裙摆下方露出，衣着完整古典",
        "pose": "人物坐在红木妆台旁，左手停在铜镜边缘，右手扶住腰侧披帛，身体侧转回望镜头，头部微低，抬眸",
        "quality": "暖红戏台后台调色，铜镜反光小面积出现，暗部保留红木纹理",
    },
    "miao_silver_night": {
        "scene": "环境光设定：苗疆木楼夜色场景，黑蓝木楼、银饰挂帘和幽蓝夜雾在背景压暗，冷白窄光照亮脸、银链、腰线和手腕，木楼栏杆和刺绣布帘围住背景",
        "outfit": "苗疆刺绣短上衣搭配深蓝高腰长裙，银链、银铃和腰间银饰层层垂下，绣边清楚，裸足从深蓝裙摆下方露出，整体是民族古风造型",
        "pose": "人物站在木楼门边，左手抬到银饰耳侧，右手停在腰间银链上，身体侧转成S形，头部回望镜头，嘴角轻轻上扬",
        "quality": "幽蓝银饰夜景调色，银光清楚，暗部保留木楼层次",
    },
    "republic_lace": {
        "scene": "环境光设定：民国老洋房夜窗场景，木窗、台灯、旧墙纸和深色木地板组成复古背景，暖琥珀台灯照亮脸、肩颈、蕾丝领口和手指，窗外只留暗蓝色块",
        "outfit": "民国象牙白蕾丝立领上衣搭配浅金缎面半裙，盘扣、珍珠耳饰和细腰带清楚，衣料复古柔亮，裸足从浅金裙摆下方露出",
        "pose": "人物侧坐在老洋房木窗旁，左手停在窗框上，右手扶住细腰带，身体向镜头微微前倾，头部侧偏直视镜头，嘴唇微开",
        "quality": "民国暖琥珀胶片调色，旧墙纸和木地板暗部有层次，肤色柔亮不过曝",
    },
}

_ANCIENT_HEAD_THEME_BLUEPRINTS = {
    "head_ancient_copper_mirror": {
        "scene": "环境光设定：古代红木妆台头部近景，铜镜、纸灯笼和戏服架在背景虚化，暖红窄光照亮脸、唇峰、下颌、步摇和交领边缘，铜镜只保留小面积反光",
        "outfit": "古代近景造型，画面边缘只露出交领衣襟、盘扣、织金绣边和一段薄纱披帛，步摇在发侧形成小亮点",
        "pose": "头部从铜镜旁侧转回望镜头，一只手轻扶铜镜边缘，嘴唇微开，眼神从眼尾斜看镜头",
        "quality": "暖红铜镜古风调色，脸部窄光清楚，暗部保留红木质感",
    },
    "head_ancient_candle_study": {
        "scene": "环境光设定：古代书房头部近景，卷轴、香炉和烛台在背景虚化，琥珀烛光照亮脸、眼尾、唇峰和书页边缘，暗部保留纸面和木纹",
        "outfit": "宋制近景造型，画面边缘只露出月白交领、细绣边、玉坠和宽袖边缘",
        "pose": "头部低垂，抬眸直视镜头，右手指尖停在书卷旁，嘴角轻轻上扬，发丝贴近脸侧",
        "quality": "琥珀烛光头部调色，暗部安静，肤色由烛光托亮",
    },
    "head_ancient_bamboo_moon": {
        "scene": "环境光设定：古代竹林头部近景，竹影和银蓝月色在背景虚化，月光切过脸侧、颈线和发簪边缘，薄雾只停在远处",
        "outfit": "竹林古风近景造型，画面边缘只露出青绿交领、月白披帛、玉坠和细绣边",
        "pose": "头部从竹影旁回望镜头，一只手停在耳侧发簪旁，嘴唇微开，眼神微眯斜看镜头",
        "quality": "银蓝月色古风头部调色，竹影暗部有层次，脸部高光不过曝",
    },
    "head_ancient_boat_window": {
        "scene": "环境光设定：古代画舫窗边头部近景，雕花窗、湖面灯影和薄纱帘在背景虚化，幽蓝水光照亮脸侧，暖灯笼光落在唇峰和窗框边缘",
        "outfit": "江南画舫近景造型，画面边缘只露出交领薄衫、玉坠、绣边领口和一段薄纱披帛",
        "pose": "头部靠近雕花窗边，右手指尖停在窗框旁，眼神直视镜头，嘴角轻轻上扬",
        "quality": "画舫夜雾头部调色，幽蓝水光和暖灯笼分层",
    },
    "head_republic_lace": {
        "scene": "环境光设定：民国老洋房头部近景，木窗、台灯和旧墙纸在背景虚化，暖琥珀台灯照亮脸、蕾丝领口、珍珠耳饰和发丝边缘",
        "outfit": "民国近景造型，画面边缘只露出象牙白蕾丝立领、盘扣、珍珠耳饰和浅金缎面边缘",
        "pose": "头部贴近木窗侧光，下巴微低，抬眼看镜头，一只手轻扶珍珠耳饰旁，嘴唇微开",
        "quality": "民国暖琥珀头部胶片调色，旧墙纸暗部柔和，脸部清楚",
    },
}


def _theme_blueprint_for(theme_name: str, era: str) -> dict[str, object]:
    if _is_ancient_era(era):
        return _ANCIENT_HEAD_THEME_BLUEPRINTS.get(theme_name) or _ANCIENT_THEME_BLUEPRINTS.get(theme_name) or {}
    return _MODERN_THEME_BLUEPRINTS.get(theme_name) or {}


def _theme_blueprint_value(blueprint: dict[str, object], key: str, shot: str, variant_seed: str = "") -> str:
    value = blueprint.get(key)
    if isinstance(value, dict):
        value = value.get(shot) or value.get("default") or ""
    return str(value or "")


def _apply_theme_blueprint(parts: dict[str, str], scale: str, shot: str, aspect: str, era: str) -> dict[str, str]:
    theme_name = str(parts.get("theme_name") or "")
    blueprint = _theme_blueprint_for(theme_name, era)
    if not blueprint:
        return parts
    # 场景一旦选定，旧主题不能把另一地点的动作、衣着和调色盖上去。
    scene = str(parts.get("scene_light") or "")
    blueprint_scene = _theme_blueprint_value(blueprint, "scene", shot)
    if scene and blueprint_scene:
        theme_category = _scene_category({"scene_light": blueprint_scene})
        if theme_category != "other" and theme_category != _scene_category({"scene_light": scene}):
            return parts
    locked = dict(parts)
    variant_seed = str(parts.get("variant_seed") or "")
    # 旧流程只剩四档使用：四档不输出服装，姿势来自四档专用池。
    locked["outfit"] = ""
    locked["theme_blueprint_locked"] = "1"
    return locked


# 妆容与场景氛围统一：白天场景排除夜系妆，夜景场景排除晨光/日系等白天妆
_NIGHT_SCENE_MARKERS = ("夜晚", "夜景", "月光", "夜色", "暗室", "烛光", "壁灯", "入夜", "日落后", "深夜", "午夜", "夜")
_NIGHT_MAKEUP_MARKERS = ("夜景", "夜色", "暗夜", "夜拍", "暗调", "月光", "夜")
_DAY_MAKEUP_MARKERS = ("晨光", "日系", "晴日", "暖阳", "阳光", "橘", "蜜桃", "珊瑚", "樱花", "暖")


def _scene_is_night(scene_light: str) -> bool:
    return any(marker in (scene_light or "") for marker in _NIGHT_SCENE_MARKERS)


def _makeup_mismatches_scene(scene_light: str, makeup: str) -> bool:
    """白天场景却配了夜系妆才算失配；夜景配中性/白天妆是可接受的。"""
    if not scene_light or not makeup:
        return False
    s_night = _scene_is_night(scene_light)
    m_night = any(m in makeup for m in _NIGHT_MAKEUP_MARKERS)
    return (not s_night) and m_night


def build_prompt(parts: dict[str, str]) -> str:
    return _build_human_prompt(parts)


def _strip_dimension_labels(text: str) -> str:
    cleaned = str(text or "").strip("，。 \n\t")
    cleaned = re.sub(r"^环境光设定[:：]?", "", cleaned).strip("，。 \n\t")
    return cleaned


_HUMAN_ABSTRACT_MARKERS = (
    "画面重心",
    "视觉路径",
    "构图重点",
    "保持清楚",
    "完整入镜",
    "完整带出",
    "保持完整",
    "材质统一",
    "承担",
    "压迫感",
    "命令感",
    "诱惑感",
    "张力",
)


def _human_clauses(text: str) -> list[str]:
    clauses = [
        clause.strip("，。 \\n\\t")
        for clause in _strip_dimension_labels(clean_prompt_text(text)).replace("；", "，").split("，")
        if clause.strip("，。 \\n\\t")
    ]
    return [
        clause
        for clause in clauses
        if clause and not any(marker in clause for marker in _HUMAN_ABSTRACT_MARKERS)
    ]


def _human_camera(parts: dict[str, str]) -> str:
    if parts.get("camera_line"):
        return ensure_sentence(str(parts["camera_line"]))
    camera = clean_prompt_text(parts.get("camera", ""))
    shot = str(parts.get("shot_key") or "")
    if not shot:
        if any(marker in camera for marker in ("头部", "肩部以上", "近景")):
            shot = "head_shot"
        elif "全身" in camera or "脚底" in camera:
            shot = "full_body"
        else:
            shot = "half_body"
    if shot == "head_shot":
        scope = "肩部以上近景"
    else:
        direction = "横向" if parts.get("aspect") == "landscape" else "竖向"
        if shot == "full_body":
            scope = f"从头到脚的{direction}全身构图"
        elif shot == "half_body":
            scope = f"腰部以上的{direction}半身构图"
        else:
            scope = f"大腿以上的{direction}半身构图"
    if any(marker in camera for marker in ("低于下巴", "脸部下方", "从下向上", "仰拍")):
        return ensure_sentence(f"镜头位于她的脸部下方，从低处拍摄，{scope}")
    if any(marker in camera for marker in ("低机位", "略低机位")):
        return ensure_sentence(f"低机位，{scope}")
    return ensure_sentence(scope)


def _human_pose(parts: dict[str, str]) -> str:
    raw = str(parts.get("pose_expression", ""))
    if parts.get("scale") == "nsfw":
        return ensure_sentence(_strip_dimension_labels(raw))
    clauses = _human_clauses(raw)
    if not clauses:
        return ""
    chosen = [clause.replace("人物", "她") for clause in clauses]
    text = naturalize_pose_framing("，".join(chosen))
    text = re.sub(r"，{2,}", "，", text).strip("，。 ")
    return ensure_sentence(text)


def _human_outfit(parts: dict[str, str]) -> str:
    text = _strip_dimension_labels(clean_prompt_text(parts.get("outfit", "")))
    if not text:
        return ""
    text = re.sub(r"，?(?:整体配色|阳光鲜艳配色)[^，。]+", "", text).strip("，。 ")
    text = text.replace("的透明袖口靠近肩侧", "，透明袖口落在肩侧")
    text = text.replace("领口出现在画面下缘", "，领口在画面下缘露出一小段")
    replacements = (
        ("深V领口压出利落线条", "深V领露出锁骨下方的皮肤"),
        ("腰侧只有细窄收省线", "腰侧有两条细竖缝"),
        ("弧形杯线和竖向鱼骨压线清楚", "胸前有弧形杯线和细鱼骨线"),
        ("胸衣鱼骨线和金属扣清楚", "胸衣上有细鱼骨线和小金属扣"),
        ("前片是轻薄蕾丝和细鱼骨压线", "前片有轻薄蕾丝和竖向细鱼骨线"),
        ("腰侧细带收紧", "腰侧系着细带"),
        ("流苏腰链和高腰纱裙统一成舞姬造型", "流苏腰链和高腰纱裙搭成舞姬装"),
        ("唐制胡姬半身造型", "唐制胡姬装"),
        ("古典敦煌半身造型", "古典敦煌装"),
        ("玉坠腰链和水纹绣边冷艳清贵", "玉坠腰链垂在腰侧，水纹绣边沿着裙摆"),
        ("臂钏、珠片、流苏腰链和高腰纱裙形成浓烈舞姬层次", "臂钏、珠片、流苏腰链和高腰纱裙搭成舞姬装"),
    )
    for source, replacement in replacements:
        text = text.replace(source, replacement)
    text = re.sub(
        r"(.+)的翻领进入画面下缘，横向压褶露出一小段",
        r"\1，翻领和压褶停在肩侧",
        text,
    )
    if text.startswith("她穿"):
        return ensure_sentence(text)
    return ensure_sentence(f"她穿着{text}")


def _human_scene(parts: dict[str, str]) -> str:
    clauses = [clause for clause in _human_clauses(parts.get("scene_light", "")) if clause != "肩部以上近景"]
    # 旧流程（四档）去掉与人物/服装重复的身体部位描述；构图器的场景句是按镜头写好的，整句保留。
    if not parts.get("art_direction"):
        clauses = [
            clause
            for clause in clauses
            if not any(marker in clause for marker in ("黑发", "皮肤", "锁骨", "肩颈", "衣料", "手指", "嘴唇"))
            or any(marker in clause for marker in ("照亮", "光", "照"))
        ]
    if str(parts.get("shot_key") or "") != "full_body":
        # 脚边、脚下地面只在全身镜头可见。
        clauses = [clause for clause in clauses if not any(marker in clause for marker in ("脚边", "脚下"))]
    if not clauses:
        return ""
    text = "，".join(clauses)
    replacements = (
        ("构成安静背景", "摆在身后"),
        ("在背景里", "在身后"),
        ("在在身后", "在身后"),
        ("后方散焦", "在身后模糊开"),
        ("放在背景里", "在身后"),
    )
    for source, replacement in replacements:
        text = text.replace(source, replacement)
    text = re.sub(r"，{2,}", "，", text).strip("，。 ")
    return ensure_sentence(text)


def _human_makeup(parts: dict[str, str]) -> str:
    text = _strip_dimension_labels(clean_prompt_text(parts.get("makeup", "")))
    if not text:
        return ""
    return ensure_sentence(text)


def _human_quality(parts: dict[str, str]) -> str:
    raw_quality = str(parts.get("quality") or "").strip("。， ")
    if raw_quality:
        if str(parts.get("scale") or "") != "nsfw":
            raw_quality = normalize_quality_line(raw_quality)
        return ensure_sentence(raw_quality)
    if str(parts.get("scale") or "") == "normal":
        return "时尚人像摄影，肤色自然，光线干净，带轻微胶片颗粒。"
    return "高级人像写真，肤质细腻，曝光自然，带轻微胶片颗粒。"


def render_prompt_lines(parts: dict[str, str]) -> dict[str, str]:
    """按最终输出顺序渲染各维度行；空行保留为空字符串，便于逐行检查。"""
    return {
        "pose": _human_pose(parts),
        "scene": _human_scene(parts),
        "quality": _human_quality(parts),
        "camera": _human_camera(parts),
        "character": ensure_sentence(clean_prompt_text(parts.get("character", ""))),
        "outfit": _human_outfit(parts),
        "makeup": _human_makeup(parts),
    }


def _build_human_prompt(parts: dict[str, str]) -> str:
    return "\n\n".join(line for line in render_prompt_lines(parts).values() if line)


def _purge_forbidden_clauses(text: str) -> tuple[str, list[str]]:
    """把正面提示词里的否定指令（禁止/不能/避免…）剥离，转存为负向术语。

    绘画模型对 positive 中的否定语义支持很差，应归入 negative_prompt，
    否则会削弱主体信号（例如“禁止正面硬闪”本应进 negative）。
    """
    forbidden: list[str] = []
    pattern = re.compile(r"(?:禁止|不能|避免|不可|勿用|不要)([^，。；\s]{1,10})")

    def _repl(match: re.Match) -> str:
        term = match.group(1)
        if term and term not in forbidden:
            forbidden.append(term)
        return ""

    cleaned = pattern.sub(_repl, text or "")
    cleaned = re.sub(r"[，。；]{2,}", lambda m: m.group(0)[-1], cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned, forbidden


def generate_prompt_items(count: int, selections: dict[str, str], seed_text: str = "") -> list[dict]:
    rng = random.Random(seed_text or int(time.time() * 1000))
    scale = normalize_scale(selections.get("scale", "bold"))
    shot = normalize_shot(selections.get("shot", ""))
    era = str(selections.get("era", "modern") or "modern")
    raw_width = selections.get("width")
    raw_height = selections.get("height")
    try:
        detected_width = int(raw_width) if raw_width is not None else None
        detected_height = int(raw_height) if raw_height is not None else None
    except (TypeError, ValueError):
        detected_width = None
        detected_height = None
    aspect = normalize_aspect(selections.get("aspect", ""), detected_width, detected_height)
    width, height = (detected_width, detected_height) if detected_width and detected_height else RESOLUTIONS[shot]
    items = []
    for index in range(count):
        if scale == "nsfw":
            # 四档除姿势表情外与三档完全一致；姿势表情只从四档专用池原样抽取。
            parts = compose_parts("bold_no_outfit", shot, aspect, rng, render_prompt_lines, era)
            pose_expression = choose(pose_expression_options_by_aspect("nsfw", shot, aspect), rng)
            parts.update(pose_expression=pose_expression, art_pose=pose_expression)
        else:
            parts = compose_parts(scale, shot, aspect, rng, render_prompt_lines, era)
        items.append(_finish_prompt_item(parts, scale, shot, aspect, width, height, rng))
    return items


def _finish_prompt_item(parts: dict[str, str], scale: str, shot: str, aspect: str, width, height, rng: random.Random) -> dict:
    prompt = build_prompt({**parts, "shot_key": shot, "scale": scale, "aspect": aspect})
    if scale in {"bold_no_outfit", "nsfw"}:
        prompt = clean_prompt_text(prompt)
        prompt = prompt.replace("胸前上衣", "胸前")
        prompt = prompt.replace("肩头上衣", "肩头")
        prompt = prompt.replace("肩线下方的上衣", "肩线下方")
        prompt = prompt.replace("上衣纹理", "皮肤和发丝")
        prompt = prompt.replace("上衣", "身体")
        prompt = prompt.replace("衣料", "皮肤")
    if shot == "head_shot":
        prompt = prompt.replace("胸前上衣", "肩线下方")
        prompt = prompt.replace("胸前衣料边缘", "肩线下方")
        prompt = prompt.replace("胸前", "肩线下方")
        prompt = prompt.replace("肩线和肩线下方", "肩线下方")
        prompt = prompt.replace("鼻梁、肩线和肩线下方", "鼻梁和肩线下方")
    # 正负语义分离：positive 中的“禁止/不能/避免…”否定片段剥离并转存 negative，
    # 避免否定语义留在正面削弱主体信号（如“禁止正面硬闪”）。
    prompt, forbidden_terms = _purge_forbidden_clauses(prompt)
    negative_prompt = build_negative_prompt(prompt, parts, scale, shot, aspect, width, height)
    if forbidden_terms:
        _existing = {t.strip() for t in negative_prompt.split("，")}
        _extra = "，".join(t for t in forbidden_terms if t.strip() and t.strip() not in _existing)
        if _extra:
            negative_prompt = f"{negative_prompt}，{_extra}"
    item = {
        "scale": scale,
        "shot": shot_label(shot),
        "shot_key": shot,
        "aspect": aspect,
        "dimension_parts": parts,
        "positive_prompt": prompt,
        "compact_prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "seed": rng.randint(1, 2**48 - 1),
        "prompt_audit_issues": [],
    }
    return item
