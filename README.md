# Random Photo Prompt for ComfyUI

`random_photo_prompt` 是一个 ComfyUI 自定义节点项目，用于生成成人向时尚写真、私房写真和图生视频相关提示词，并提供手机端/网页端生成入口、远端 4090 ComfyUI 计算和本地媒体资产管理等配套能力。

项目目标不是做一个独立应用，而是在 ComfyUI 生态内提供一套可维护的提示词生成、工作流 patch、远程生成和资产回传方案。

## 源码与运行目录（权威定义）

本机唯一可编辑源码目录是：

```text
/Users/zouge/Project/1-myProject/random_photo_prompt/
```

Mac ComfyUI 的目录：

```text
/Users/zouge/Documents/ComfyUI/custom_nodes/random_photo_prompt
```

是指向上述源码目录的软链接，不是第二份源码，也不是独立的“运行副本”。禁止直接在运行路径维护另一份内容。Windows 远端目录 `D:\ComfyUI\ComfyUI\custom_nodes\random_photo_prompt` 只是部署副本，只能由同步脚本从本机源码更新，禁止把远端或运行目录当作编辑源。

## 主要功能

- **随机写真提示词生成**：按镜头、容貌身材、妆容、衣着、姿势表情、场景光线六个维度组合自然中文提示词。
- **四档内容尺度**：
  - 一档 `normal`：时尚编辑写真，强调服装、光线和构图。
  - 二档 `bold`：成人 glamour/私房写真，保留衣着维度，强化性感氛围。
  - 三档 `bold_no_outfit`：沿用二档逻辑，但最终不组合衣着维度。
  - 四档 `nsfw`：仅姿势维度使用专用池，其余沿用三档逻辑，不组合衣着维度。
- **桌面 ComfyUI 节点**：在工作流执行前把生成提示词写入连接的文本编码节点。
- **手机端页面**：支持移动端生成、图库查看、详情页、复制提示词、收藏、删除等操作；收藏图片会在收藏目录的独立索引中保留提示词和 Seed。
- **远端计算与图片直回 Mac**：手机页由 Mac 本机 `8188` 提供，任务提交到远端 Windows/4090，结果经 WebSocket 直接回到 Mac 本地。
- **本地媒体资产管理**：网页端/手机端媒体资产列表读取 Mac 本地输出目录，删除时同步删除本地文件和映射。
- **规则审查工具**：提供提示词池审查、实例化提示词审查和生成报告。

## 目录结构

```text
random_photo_prompt/
├── __init__.py                         # 聚合入口：命名空间导入、路由注册、节点映射
├── rpp_globals.py                      # 常量与共享运行时状态
├── rpp_utils.py                        # 纯工具函数
├── rpp_prompts.py                      # 提示词构建、清洗、分辨率推断
├── rpp_workflow.py                     # 工作流模板 patch（图片/视频/远端输出改写）
├── rpp_remote.py                       # 远端 ComfyUI 调用、WebSocket 回传、模型解析
├── rpp_mobile.py                       # 移动端文件/图库/收藏/任务状态
├── rpp_nodes.py                        # ComfyUI 节点类
├── rpp_endpoints.py                    # HTTP 端点
├── prompt_engine.py                    # 提示词生成入口
├── prompt_data.py                      # 提示词池加载（JSON + 保底数据）
├── prompt_postprocess.py               # 提示词清理、长度控制、冲突处理
├── prompt_resolution.py                # 分辨率推断和工作流尺寸 patch
├── negative_prompt_engine.py           # 负面提示词
├── video_prompt_engine.py              # 图生视频动作提示词
├── data/prompt_pools.json              # 提示词池（JSON 数据源，运行时加载）
├── data/nsfw_pose_expression_options.json  # 四档 NSFW 姿势池（独立 JSON）
├── web/mobile.html                     # 手机端页面
├── tools/
│   ├── audit_prompt_pools.py           # 池内容审查
│   ├── audit_generated_prompts.py      # 实例化提示词审查
│   ├── restart_windows_remote_comfyui.py
│   └── sync_prompt_runtime_to_remote.py
└── docs/
    ├── AI_CONTEXT.md
    ├── PROMPT_GENERATION_RULES.md
    ├── REMOTE_MOBILE_ACCESS.md
    └── VIDEO_PROMPT_OPTION_GUIDE.md
```

## 安装

### 1. 接入 Mac ComfyUI

保持本项目目录为唯一源码，并让 Mac ComfyUI 的 `custom_nodes/random_photo_prompt` 指向它的软链接。不要复制项目目录到 `custom_nodes`，否则会重新产生两份可编辑代码。完成链接后重启 Mac ComfyUI。

### 2. Python 依赖

项目运行在 ComfyUI 自带 Python 环境中。常规节点依赖 ComfyUI 已安装的基础库；工具脚本常用：

- `aiohttp`
- `Pillow`
- `numpy`

如果运行工具脚本时报缺包，在 ComfyUI 虚拟环境中补装对应包即可。

### 3. 提示词池数据源

提示词池统一存放在 JSON 数据文件中：

```text
data/prompt_pools.json            # 六维度主池（camera/character/makeup/outfit/pose/scene/quality）
data/nsfw_pose_expression_options.json  # 四档 nsfw 姿势与表情池（独立维护）
```

`data/prompt_pools.json` 由 `prompt_data.py` 在运行时直接加载（`_load_generated_prompt_data`），改完 JSON 重启 ComfyUI 即生效，无需转表。四档 `nsfw` 的姿势和表情维度只使用 `data/nsfw_pose_expression_options.json`，不读主池的 pose 数据。

## 基本使用

### 供其他项目调用远端 4090

统一脚本每次同步生成一张图片，图片经 WebSocket 直接写入调用方指定目录，标准输出只返回 JSON。远端地址默认是 `http://192.168.123.111:8188`，可通过 `RPP_REMOTE_URL` 覆盖。脚本会原样传入正向提示词，不追加手机端的镜头类型或 Krea2 人物构图保护词。

```bash
COMFYUI_PYTHON=/path/to/ComfyUI/.venv/bin/python
$COMFYUI_PYTHON tools/generate_remote_image.py --workflow zit --prompt "完整正向提示词" --output ./images
$COMFYUI_PYTHON tools/generate_remote_image.py --workflow krea2 --prompt "完整正向提示词" --output ./images
$COMFYUI_PYTHON tools/generate_remote_image.py --workflow double --prompt "完整正向提示词" --negative-prompt "可选负向提示词" --output ./images
```

脚本使用已安装 `aiohttp` 和 Pillow 的 ComfyUI Python 环境，不自动安装依赖或切换解释器。默认分辨率为 `1024x1312`，使用 `--width`、`--height` 修改；工作流末端会按这两个值输出精确尺寸。`zit` 默认使用 `ZIT-beyondREALITY_V30.safetensors` 并固定 10 步，指定其他 ZIT 模型时固定 8 步；`krea2` 默认使用 `KREA2-darkBeast.safetensors`；`double` 默认使用 BeyondReality ZIT 和 `ZIB-redcraft22INT8INT4_zibDistilled.safetensors`。单采只接受正向提示词，只有双采支持可选负向提示词。

### 桌面 ComfyUI 节点

1. 重启 ComfyUI。
2. 在节点菜单中添加随机写真提示词节点。
3. 选择尺度、镜头、模型/工作流相关参数。
4. 执行队列时，节点会生成提示词并写入对应文本节点。

### 手机端入口

手机和 Mac 浏览器直接访问 Mac 本机 ComfyUI `8188`，禁止使用已废弃的 `18199` 代理：

手机端选择双采工作流后，可在“填入提示词”弹窗中同时填写正面和负面提示词；填写负面提示词会覆盖自动负面提示词，留空则继续自动生成中文负面提示词。单采弹窗只显示正面提示词且不接受负面提示词。

```text
http://127.0.0.1:8188/random_photo_prompt/mobile
```

局域网手机访问：

```text
http://Mac局域网IP:8188/random_photo_prompt/mobile
```

## 远端 4090 计算

当前推荐链路：

```text
浏览器/手机
  -> Mac 本机 8188 手机页
  -> Windows 远端 ComfyUI 8188
  -> WebSocket 图片直回 Mac 本地输出目录
```

远端地址仅用于计算和模型列表读取：`http://192.168.123.111:8188`。远端不保存生成资产，也不是手机入口。

## 规则说明

完整规则以 docs 为准：

- `docs/PROMPT_GENERATION_RULES.md`：文生图提示词生成规则、六维度、镜头范围、尺度逻辑、长度限制。
- `docs/VIDEO_PROMPT_OPTION_GUIDE.md`：图生视频动作提示词格式。
- `docs/REMOTE_MOBILE_ACCESS.md`：Mac 8188 手机入口、远端计算和本地资产回传说明。
- `docs/AI_CONTEXT.md`：给 AI 协作者看的项目索引和当前上下文。

核心约束摘要：

- 最终正向提示词不再设置总长度上限，由各维度预算（`PART_LENGTH_BUDGETS`）控制单个维度不膨胀。
- 提示词按镜头可见范围裁剪，不写画面中看不到的身体部位。
- 一档服务时尚、多样性和艺术感。
- 二档服务性感、诱惑和成人 glamour，但仍保留衣着维度。
- 三档不组合衣着维度，其余沿用二档逻辑。
- 四档只有姿势维度走专用池，其余沿用三档/二档逻辑。
- 手机端和网页端应共用同一套提示词、分辨率和工作流 patch 规则。
- 改动提示词规则、节点代码、前端或远端相关逻辑后，需要按远端同步规则同步并重启远端 ComfyUI。

## 审查和维护

提示词池审查：

```bash
python3 tools/audit_prompt_pools.py
```

实例化提示词审查：

```bash
python3 tools/audit_generated_prompts.py
```

同步提示词运行规则到远端并重启：

```bash
python3 tools/sync_prompt_runtime_to_remote.py
```

远端重启：

```bash
python3 tools/restart_windows_remote_comfyui.py
```

## 开发原则

- 内容池改动优先编辑 `data/prompt_pools.json`（或 `data/nsfw_pose_expression_options.json`），运行时直接生效。
- 逻辑改动集中到对应模块，不把新逻辑继续堆进大文件。
- 不做多余兜底；如果出现多条路径，优先收口成唯一主链路。
- 本地媒体资产删除只删除 Mac 本地输出目录和映射，不依赖远端资产删除。
- 远端生成新资产应尽量通过 WebSocket 直回 Mac，避免先落远端 output 再复制。
- 修改会影响远端网页端的代码后，必须同步到远端并重启远端 ComfyUI。

## 安全边界

本项目面向成年人使用。远端和手机访问入口可以控制生成任务并读取输出资产，不应无保护暴露到公网。

跨网络访问优先使用 Tailscale 等私有网络方案；如果使用 FRP、cpolar、Cloudflare Tunnel 等公网隧道，必须添加访问控制。
