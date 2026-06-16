# Random Photo Prompt for ComfyUI

`random_photo_prompt` 是一个 ComfyUI 自定义节点项目，用于生成成人向时尚写真、私房写真和图生视频相关提示词，并提供手机端/网页端生成入口、远端 4090 ComfyUI 代理、本地媒体资产管理等配套能力。

项目目标不是做一个独立应用，而是在 ComfyUI 生态内提供一套可维护的提示词生成、工作流 patch、远程生成和资产回传方案。

## 主要功能

- **随机写真提示词生成**：按镜头、容貌身材、妆容、衣着、姿势表情、场景光线六个维度组合自然中文提示词。
- **四档内容尺度**：
  - 一档 `normal`：时尚编辑写真，强调服装、光线和构图。
  - 二档 `bold`：成人 glamour/私房写真，保留衣着维度，强化性感氛围。
  - 三档 `bold_no_outfit`：沿用二档逻辑，但最终不组合衣着维度。
  - 四档 `nsfw`：仅姿势维度使用专用池，其余沿用三档逻辑，不组合衣着维度。
- **桌面 ComfyUI 节点**：在工作流执行前把生成提示词写入连接的文本编码节点。
- **手机端页面**：支持移动端生成、图库查看、详情页、复制提示词、收藏、删除等操作。
- **18199 统一入口代理**：网页端和手机端都可以通过 Mac 本机 `18199` 访问，并把生成任务转给远端 Windows/4090 ComfyUI。
- **图片直回 Mac**：代理会把保存节点改为 WebSocket 回传，尽量避免资产落在远端 output 文件夹。
- **本地媒体资产管理**：网页端/手机端媒体资产列表读取 Mac 本地输出目录，删除时同步删除本地文件和映射。
- **规则审查工具**：提供提示词池审查、实例化提示词审查和生成报告。

## 目录结构

```text
random_photo_prompt/
├── __init__.py                         # ComfyUI 自定义节点、手机端接口、远端辅助接口
├── prompt_engine.py                    # 提示词生成入口
├── prompt_data.py                      # 提示词池加载和兜底数据
├── prompt_data_generated.py            # 从 Excel 生成的运行时提示词池
├── prompt_postprocess.py               # 提示词清理、长度控制、冲突处理
├── prompt_resolution.py                # 分辨率推断和工作流尺寸 patch
├── negative_prompt_engine.py           # 负面提示词
├── keyword_expansion_engine.py         # 规则2关键词扩写
├── video_prompt_engine.py              # 图生视频动作提示词
├── data/prompt_pools.xlsx              # 提示词池编辑源
├── web/mobile.html                     # 手机端页面
├── tools/
│   ├── build_prompt_data_from_excel.py # Excel -> runtime 数据
│   ├── audit_prompt_pools.py           # 池内容审查
│   ├── audit_generated_prompts.py      # 实例化提示词审查
│   ├── mac_comfyui_remote_proxy.py     # Mac 18199 统一入口代理
│   ├── proxy_local_assets.py           # Mac 本地资产列表/映射/删除
│   ├── proxy_runtime_state.py          # 远端任务进度和运行状态
│   ├── proxy_workflow_patch.py         # 远端工作流提交前 patch
│   ├── run_mac_remote_proxy_daemon.py  # 后台启动 18199 代理
│   ├── restart_windows_remote_comfyui.py
│   └── sync_prompt_runtime_to_remote.py
└── docs/
    ├── AI_CONTEXT.md
    ├── PROMPT_GENERATION_RULES.md
    ├── REMOTE_MOBILE_ACCESS.md
    ├── KEYWORD_EXPANSION_OPTION_GUIDE.md
    └── VIDEO_PROMPT_OPTION_GUIDE.md
```

## 安装

### 1. 放入 ComfyUI custom_nodes

把项目目录放到 ComfyUI 的 `custom_nodes` 下：

```bash
ComfyUI/custom_nodes/random_photo_prompt
```

然后重启 ComfyUI。

### 2. Python 依赖

项目运行在 ComfyUI 自带 Python 环境中。常规节点依赖 ComfyUI 已安装的基础库；工具脚本常用：

- `aiohttp`
- `Pillow`
- `numpy`
- `openpyxl` 或项目现有 Excel 读写依赖

如果运行工具脚本时报缺包，在 ComfyUI 虚拟环境中补装对应包即可。

### 3. 构建提示词池

提示词内容的主编辑源是：

```text
data/prompt_pools.xlsx
```

编辑后运行：

```bash
python3 tools/build_prompt_data_from_excel.py
```

生成结果会写入 `prompt_data_generated.py`。不要手改这个生成文件。

例外：四档 `nsfw` 的姿势和表情维度不走 Excel 转表，唯一可编辑源是 `data/nsfw_pose_expression_options.json`。转表脚本会跳过这部分，避免覆盖其他 AI 直接修改的 JSON 内容。

## 基本使用

### 桌面 ComfyUI 节点

1. 重启 ComfyUI。
2. 在节点菜单中添加随机写真提示词节点。
3. 选择尺度、镜头、模型/工作流相关参数。
4. 执行队列时，节点会生成提示词并写入对应文本节点。

### 手机端入口

本机内部服务默认是 ComfyUI `8188`，统一用户入口推荐使用 Mac 代理 `18199`：

```text
http://127.0.0.1:18199/random_photo_prompt/mobile
```

局域网手机访问：

```text
http://Mac局域网IP:18199/random_photo_prompt/mobile
```

状态页：

```text
http://127.0.0.1:18199/random_photo_prompt/proxy/status
```

## 远端 4090 代理

当前推荐链路：

```text
浏览器/手机
  -> Mac 18199 统一入口
  -> Mac 本机 8188 内部接口
  -> Windows 远端 ComfyUI 8188
  -> WebSocket 图片直回 Mac 本地输出目录
```

启动 Mac 代理：

```bash
python3 tools/run_mac_remote_proxy_daemon.py
```

强制重启 Mac 代理：

```bash
RPP_PROXY_RESTART=1 python3 tools/run_mac_remote_proxy_daemon.py
```

常用环境变量：

```bash
RPP_PROXY_REMOTE_URL=http://192.168.123.111:8188
RPP_PROXY_LOCAL_MOBILE_URL=http://127.0.0.1:8188
RPP_PROXY_OUTPUT_DIR="/Users/zouge/Documents/Codex/2026-06-02/macbook-air-80/work/ComfyUI/output/4090 生成"
RPP_PROXY_PORT=18199
RPP_PROXY_DELETE_REMOTE_OUTPUT=1
RPP_PROXY_WEBSOCKET_OUTPUT=1
```

这些默认值集中在 `tools/proxy_config.py` 和 `tools/proxy_env.sh`。

## 规则说明

完整规则以 docs 为准：

- `docs/PROMPT_GENERATION_RULES.md`：文生图提示词生成规则、六维度、镜头范围、尺度逻辑、长度限制。
- `docs/KEYWORD_EXPANSION_OPTION_GUIDE.md`：规则2关键词扩写选项格式。
- `docs/VIDEO_PROMPT_OPTION_GUIDE.md`：图生视频动作提示词格式。
- `docs/REMOTE_MOBILE_ACCESS.md`：手机跨网络访问、18199 统一入口、远端代理说明。
- `docs/AI_CONTEXT.md`：给 AI 协作者看的项目索引和当前上下文。

核心约束摘要：

- 最终正向提示词不超过 800 个中文字符。
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

- 内容池改动优先编辑 `data/prompt_pools.xlsx`，再生成 runtime 数据。
- 逻辑改动集中到对应模块，不把新逻辑继续堆进大文件。
- 不做多余兜底；如果出现多条路径，优先收口成唯一主链路。
- 本地媒体资产删除只删除 Mac 本地输出目录和映射，不依赖远端资产删除。
- 远端生成新资产应尽量通过 WebSocket 直回 Mac，避免先落远端 output 再复制。
- 修改会影响远端网页端的代码后，必须同步到远端并重启远端 ComfyUI。

## 安全边界

本项目面向成年人使用。远端和手机访问入口可以控制生成任务并读取输出资产，不应无保护暴露到公网。

跨网络访问优先使用 Tailscale 等私有网络方案；如果使用 FRP、cpolar、Cloudflare Tunnel 等公网隧道，必须添加访问控制。
