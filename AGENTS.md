# AI Agent Guidelines

## Project Overview

This repository generates adult fashion/glamour portrait prompts for image generation.

## Core Responsibilities

1. **Prompt Generation**: Create detailed, natural-language prompts for adult fashion/glamour portraits
2. **Dimension Assembly**: Combine camera, character, makeup, outfit, pose/expression, scene/light dimensions
3. **Scale Management**: Support three content scales - normal, bold, nsfw

## Scale Definitions

### Normal Scale
- Editorial fashion photography style
- Fully clothed or modest coverage
- Emphasis on styling, lighting, composition
- Suitable for general fashion/editorial use

### Bold Scale
- Glamour photography style
- Revealing but non-explicit (lingerie, swimwear, implied nude)
- Strong sensual atmosphere
- Adult-only but not explicit

### NSFW Scale
- Adult intimate photography style
- Full nudity allowed
- Direct body descriptions including exposed breasts and nude figure
- Explicit sexual descriptions allowed
- No concealment wording required

## Dimension System

All scales use the same six dimensions:
1. **Camera**: Shot type, angle, lens characteristics
2. **Character**: Identity, age, ethnicity, body type, skin, face, hair
3. **Makeup**: Style, intensity, color palette
4. **Outfit**: Clothing, coverage, details (omitted for NSFW)
5. **Pose/Expression**: Body position, gesture, facial expression, mood
6. **Scene/Light**: Location, environment, lighting setup

## Prompt Construction Rules

### General Rules
- Use natural Chinese phrases, not mechanical labels
- One primary pose family per prompt (standing, sitting, kneeling, lying, crawling, walking are mutually exclusive)
- Match pose descriptions to camera scope
- Keep descriptions continuous and flowing, not fragmented

### Camera Scope Constraints（镜头可见范围表）

所有尺度通用，NSFW额外增加男性可见范围：

| 镜头 | 女性可见范围 | NSFW男性可见范围 | 禁止描写 |
|------|-------------|-----------------|---------|
| **head_shot**（头部） | 脸、颈、肩、发丝 | 男人的手、手指、指腹、前臂 | 胸、腰、臀、腿、全身 |
| **upper_body**（上半身） | 头到胸、锁骨、手臂、上背 | 男人的手、手臂、胸膛、下巴、嘴唇 | 腰以下、腿、脚 |
| **half_body**（半身） | 头到腰、上臀边缘 | 男人的手、手臂、腰、大腿上侧 | 膝以下、脚 |
| **large_half_body**（大半身） | 头到膝、臀部、大腿、小腿 | 男人的大腿、手、腰、下腹、阴茎根部 | 脚掌、脚尖细节 |
| **full_body**（全身） | 全身完整 | 全身（含阴茎） | 无 |

注：Normal和Bold尺度不出现男性，女性穿着不可暴露。

### NSFW Specific Rules
- Skip outfit dimension entirely
- Use direct body descriptions without concealment
- Allow explicit sexual descriptions and terminology
- Describe body curves, skin, and sensuality directly and naturally
- Bold and normal scales still require clothed or covered descriptions

### NSFW 姿势维度 → 必须写明男女互动画面
NSFW姿势维度（POSE_EXPRESSION_OPTIONS）写性动作时，必须遵循"画面可执行"原则：

1. **必须用"男人"代替"他"**：AI图像生成模型不理解"他"（代词概念），必须显式写"男人/一个男人/男人的"，例如：
   - ❌ 他双手握住她的腰 → ✅ 男人双手握住女人的腰
   - ❌ 她躺在他身下 → ✅ 女人躺在男人身下
   - ❌ 她双腿缠绕在他腰间 → ✅ 女人双脚缠绕在男人腰间
2. **必须写明身体接触点**：每个动作至少2个接触点（男人双手握住女人的腰 + 女人双腿缠绕在男人腰间）
3. **必须按镜头范围控制可见男体**：
   - head_shot：只能出现男人的手、手指、指腹、前臂
   - upper_body：可写男人的手、手臂、胸膛、下巴、嘴唇
   - half_body：可写男人的手、手臂、胸膛、腰部、大腿上侧
   - large_half_body：可写男人的大腿、手、腰部、下腹、阴茎根部
   - full_body：可写全身
4. **禁止虚空动作**：不能用"被贯穿""被进入""被律动"等无主体的被动描述
5. **禁止SM/伤痕词汇**：掐、淤、青紫、淤痕、触目惊心、蹂躏、粗暴、暴力、血丝、破皮、火辣辣、反剪、失去反抗

### 其他维度不需要写男性入镜
- 妆容、发型、场景光线维度不涉及动作/互动，不需要写男性入镜
- 姿势维度以外的维度只描述该维度的内容（妆容描述妆效、发型描述发丝、光线描述灯光）

## Output Format

Final prompts should be:
- Continuous natural Chinese description
- 总长度控制在800字以内，由各维度PART_LENGTH_BUDGETS控制单个维度不膨胀
- Dimension parts tracked separately for debugging
- Positive prompt + negative prompt pair
- **维度顺序（CLIP front-load原则）**：pose_expression → scene_light → quality → camera → character/outfit/makeup/hair
  本地文生图模型越靠前的文字遵守度越高。pose（核心姿势）和scene（场景光线）放最前面，quality（scale专属风格指引）
  放第三位确保进入前2个CLIP块。character身份描述、outfit、makeup等细节信息放后半段。

If a generated prompt would exceed 800 characters, remove repeated or format-like wording first: fixed quality tail, duplicate camera crop labels, repeated body-part lists, repeated skin-whiteness wording, repeated lip constraints, and repeated mood endings. Preserve visible fixed-character identity wording before trimming other dimensions.

Rule 1 character/body text must stay camera-scoped. Preserve the fixed identity phrase `22岁冷白皮K-pop韩国夜店女王`, but do not reinsert full-body clauses such as waist, hips, legs, feet, or toenails into head, upper-body, half-body, or large-half-body shots unless that body part is visible in the active camera scope.

**关键保护规则**：character维度的"22岁冷白皮K-pop韩国夜店女王"身份词**任何情况下不能被裁剪**。提示词完整性优先于长度限制。

**保底描述兜底规则**：
- 用户固定传入的身份描述（FIXED_CHARACTER_ORIGINAL）是**最终的兜底保障**，任何生成逻辑失败时用它填充
- 规则：生成逻辑产生的内容（Excel数据、扩写）**覆盖**保底；生成失败（空字符串）时**回退**到保底
- `prompt_planner.py:choose()` 当数据池为空时返回""而非崩溃，由上层兜底
- `prompt_postprocess.py:enforce_part_budgets()` 对character维度**从末尾裁剪**（pop(-1)），保留开头身份词；其他维度仍从开头裁剪（pop(0)）
- `prompt_constants.py:TRIMMABLE_PARTS` **不包含character**，总长裁剪的第二阶段不会动它

**重复描述规避规则**：
- pose结尾boost随机从多个变体中选择（代码层），同一scale下不应连续出现相同结尾
- 配色（"整体配色以XX为主"）只出现在scene_light维度，不出现在outfit/character
- scene_light数据中不含"明亮glamour写真""背景鲜艳但不抢脸""彩色反光保持小面积"等固定质量尾巴
- camera中的镜头约束分句（入镜/清楚/完整等）不应在pose中重复出现（代码层自动去重）

**Quality按scale分化规则**：
- 1档(normal)的quality尾巴使用"时尚大片级光影，高级商业摄影调色" → 引导SD往高级时尚摄影方向
- 2档(bold)的quality尾巴使用"高级私房写真质感，杂志封面级光影与氛围" → 引导SD往私房写真方向
- 3档(nsfw)的quality尾巴使用"私房情欲摄影质感，暧昧光影投射在肌肤上，皮肤泛著温润光泽" → 引导SD往情欲摄影方向
- 每档追加filter_grade的调色描述（关键词匹配或scale筛选）
- NSFW负面提示词额外追加"amateur, clinical lighting, flat lighting"等反义

**NSFW男性互动规则**：
- 男人的身体仅性器官入镜（阴茎、龟头），不描述男性身体其他部位（手、手臂、胸膛等）
- 必须使用直白的性器官名词：阴茎、龟头；结合状态下描述阴道、阴蒂、阴唇、精液/白浊
- 互动动作必须为显性性行为：口交（含入、舔弄龟头、吞吐）、手交（套弄、撸动）、性交（插入、进出、结合）
- head_shot：口交/颜射，女生脸部+性器官焦点
- upper_body：手交/口交/乳交，双乳+性器官焦点  
- half_body：手交为主，性器官在画面下缘
- large_half_body：被口交/性交引导/骑乘，性器官结合画面
- full_body：各种性交体位，性器官结合部位在画面焦点

**指甲和裸足规则**：
- `{nail_color}` 占位符不可从character维度中删除。如不额外指定颜色，默认使用"黑色亮面"
- full_body的character描述中的"脚趾甲油"暗示裸足，不可删除或替换为穿鞋
- 场景中的地面描述（脚下是XX）应自然融合到场景光线中，不可删除character中的裸足/脚趾暗示

## Safety Guidelines

- Keep outputs legal and adult-only
- Avoid instructions that force unsafe/illegal imagery
- When testing with external image generators, use a safe editorial-fashion version of the prompt

## Code Modification Rules

1. **Data Changes**: Modify `prompt_data.py` for pool content changes
2. **Logic Changes**: Modify `prompt_engine.py` for generation logic changes
3. **Audit Tools**: `tools/audit_prompt_pools.py` and `tools/audit_generated_prompts.py` for quality checking (no content blocking)
4. **Documentation**: Update `docs/` for rule changes
5. **Temporary Scripts**: Any temporary script generated for one-off analysis, conversion, cleanup, or verification must be deleted immediately after execution. Do not leave scratch `.py`, `.js`, `.ps1`, `.bat`, `.json`, `.csv`, or similar helper artifacts in the project.

## NSFW Content Policy

NSFW scale has **no content restrictions** beyond legal requirements:
- All explicit terminology allowed in NSFW pools
- No filtering or replacement of sensitive words
- Direct descriptions of sexual acts permitted
- No concealment or euphemism required

Implementation:
- `prompt_engine.py`: NSFW skips `safe_values()` filtering
- `sanitize_runtime_text()`: NSFW skips text replacement
- Audit tools: No `EXPLICIT_MARKERS` blocking

### NSFW 妆容禁令
MAKEUP_OPTIONS NSFW维度**禁止**以下内容：
- ❌ 烟熏妆（所有"烟熏"字样）
- ❌ 过浓/厚重的妆容
- ❌ 抓痕、爪痕、指甲印
- ✅ 允许：轻薄自然、潮红、水光、湿润、微晕眼线

## 图生视频提示词规则 (Video Prompt Generation)

### 核心原则

图生视频提示词描述"这张图片在几秒内如何动起来"。与文生图共享6维度结构，但**角色和妆容维度保持静态**，仅描述人物外貌不做时间变化。

### 6维度分类

| 维度 | 类型 | 说明 |
|------|------|------|
| 运镜 | 动态 | 镜头运动方式（推进/环绕/下探等） |
| 角色 | 静态 | 人物外貌特征（不描述时间变化） |
| 妆容 | 静态 | 妆容风格（不描述时间变化） |
| 穿着 | 跳过 | NSFW档位跳过此维度 |
| 姿势表情 | 动态 | 10秒内身体动作和表情变化 |
| 场景光线 | 动态 | 10秒内环境和光线变化 |

### 尺度档位与NSFW程度

图生视频的NSFW程度必须与尺度档位匹配：

| 尺度 | NSFW程度 | 动作示例 |
|------|----------|----------|
| **normal** | 无/极低 | 优雅转身、头发轻摆、眼神流转、微笑变化 |
| **bold** | 中等 | 锁骨起伏、乳波晃动、腰线扭动、臀部摇摆 |
| **nsfw** | 高/极高 | 全身撞击、乳房震荡、骨盆抽搐、极限开腿、高潮痉挛 |

### 输出格式

每条视频提示词按以下顺序输出，每维度单独一行，维度之间空一行：

```
【运镜】
镜头从镜中倒影平视起镜，缓慢推进穿过镜面，在抵达主体时略微环绕旋转...

【角色】
22岁冷白皮K-pop韩国夜店女王，黑色长发披肩，五官精致立体，身材火辣...

【妆容】
精致崩溃妆容，眼眶微红，嘴唇被*得红肿，头发凌乱湿润...

【姿势表情】
0-2秒直立悬空，下巴微仰，眼神迷离望向镜头...
2-4秒双腿被掰开向两侧，髋部随之打开...
4-6秒双腿完全打开呈M形，臀部向后翘起...
6-8秒双腿在空中甩动，伴随剧烈撞击...
8-10秒撞击达到高峰，全身痉挛抽搐，翻白眼...

【场景光线】
0-2秒镜面反射清晰可见，暖光从镜框溢出...
2-4秒雾气开始出现，模糊了部分倒影边缘...
4-6秒雾气增多，仅主体轮廓在镜中若隐若现...
6-8秒大半覆盖镜面，只剩关键部位闪着湿漉漉的光泽...
8-10秒雾气中手指划出弧线轨迹，光随指尖流动...
```

### 运镜选项池

运镜维度使用专用运镜池，支持以下运动方式：
- 推进（正推进/螺旋推进）
- 拉远（匀速拉远/快速拉远）
- 环绕（360°环绕/半圆环绕）
- 下探（低机位仰拍/高机位俯拍）
- 横移（左侧横移/右侧横移）
- 组合（推进+环绕/下探+横移）

### 姿势表情选项池

姿势表情维度使用 `VIDEO_POSE_OPTIONS` 池，按尺度×镜头范围组织：
- **normal**: 5镜头范围 × 5条/范围 = 25条
- **bold**: 5镜头范围 × 8条/范围 = 40条
- **nsfw**: 5镜头范围 × 15条/范围 = 75条

每条选项格式：
```
【镜头范围】头部/上半身/半身/大半身/全身
【动作目标】眼神靠近/嘴唇表情/手部引导/肩线转动/胸前动作/腰线转动/臀腿重心/腿部前景/脚部强透视/转身靠近
正文动作链（80-180字，至少4个动作变化点）
```

### 场景光线选项

场景光线维度使用时间分段描述（5段时间），每段描述该时间段内的光线和环境变化：
- 镜面反射变化
- 雾气/蒸汽效果
- 湿漉漉的光泽
- 光随动作流动

## File Structure

```
random_photo_prompt/
├── prompt_engine.py          # Main generation logic
├── prompt_data.py            # Dimension pools
├── AGENTS.md                 # This file
├── docs/
│   ├── PROMPT_GENERATION_RULES.md  # Detailed generation rules
│   └── reports/              # Audit reports
└── tools/
    ├── audit_prompt_pools.py       # Pool quality audit
    └── audit_generated_prompts.py  # Output quality audit
```

## Agent Workflow

1. Read task requirements
2. Identify affected dimensions and scales
3. Modify appropriate pool(s) in `prompt_data.py`
4. Update logic in `prompt_engine.py` if needed
5. Run audit tools to verify
6. Update documentation if rules change
