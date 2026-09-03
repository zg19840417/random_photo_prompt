# 项目 Agent 总指南

本文件是 `random_photo_prompt` 的协作入口。先读本文件，再按任务读取下方指定的权威文档；不要根据目录名、历史对话或其他副本猜测实现位置。

## 1. 项目边界

本项目是 ComfyUI 自定义节点：生成成人时尚/写真提示词，提供 Mac 手机网页、远端 Windows 4090 推理、Mac 本地图片/视频图库与收藏。

运行链路固定如下：

```text
手机或 Mac 浏览器
  -> Mac 本机 8188 /random_photo_prompt/mobile
  -> Windows 4090 192.168.123.111:8188（仅计算）
  -> 直连回传
  -> Mac 本机资产目录与图库索引
```

- `18199` 代理已经废弃。禁止启动、恢复、新增代理、隧道或其他网络中间层。
- 不得修改 Mac 网络设置、路由、代理或 DNS 来解决项目问题。
- 远端 `192.168.123.111:8188` 不是手机入口；手机入口始终是 `http://<Mac 当前局域网 IP>:8188/random_photo_prompt/mobile`。
- Mac IP 会变化。需要连接地址时读取当前活动网卡或到远端路由选出的源 IP，绝不把旧 IP 写死。

## 2. 唯一源码与部署副本

- 唯一可编辑源码：`/Users/zouge/Project/1-myProject/random_photo_prompt/`。
- Mac ComfyUI 的 `custom_nodes/random_photo_prompt` 必须是指向上述目录的软链接，只是运行入口，禁止直接编辑或复制成第二份源码。
- Windows `D:\ComfyUI\ComfyUI\custom_nodes\random_photo_prompt` 是部署副本，只能从唯一源码同步，禁止作为改动来源。
- 修改前先确认文件位于唯一源码。发现重复副本时，先识别当前 Mac 服务加载的副本；只保留唯一源码与软链接关系，不保留镜像源码。

## 3. 协作行为

- 面向用户一律使用中文，正常回复不超过 300 字；需要超出时先说明原因。
- 用户的判断可能不正确。用可验证事实指出错误，不要附和错误前提。
- 需求、现象或目标存在会改变实现方向的歧义时，先只问一个问题，并给出建议答案，格式为“问题：…”换行“建议：…”。
- 需求明确时直接实施。不要为了“兼容”保留废弃入口、旧字段、旧数据池或双路径；需要兼容会改变实现思路时先说明。
- 临时分析、转换、验证脚本与文件完成后立即删除；不得在项目留下 scratch 文件。
- 只改纯文档或审计报告时，不重启服务、不同步远端，并在交付中说明原因。

## 4. 文档职责与优先级

| 文档 | 唯一职责 | 何时必读 |
| --- | --- | --- |
| `AGENTS.md` | 工作边界、源码、部署、资产与验证规则 | 每次任务 |
| `docs/AI_CONTEXT.md` | 模块索引、当前运行行为、手机端与视频上下文 | 改节点、手机端、工作流、图库或服务 |
| `docs/PROMPT_GENERATION_RULES.md` | 文生图六维度、镜头、尺度、固定人物、审查规则 | 改提示词数据或提示词逻辑 |
| `docs/VIDEO_PROMPT_OPTION_GUIDE.md` | 图生视频动作提示词的格式与范围 | 改视频提示词池或视频提示词引擎 |
| `docs/REMOTE_MOBILE_ACCESS.md` | 手机入口、回传、资产目录、图库、远端部署 | 改远程调用、媒体文件、视频或网络行为 |
| `docs/ADR_PROMPT_ENGINE_REFACTOR.md` | 提示词模块职责边界 | 调整 `prompt_*.py` 职责时 |

- 玩法、生成规则、工作流、UI 行为、目录语义、资产流向或接口语义有新增、修改、删除时，必须同步更新对应当前策划/运行文档；未同步文档不得视为完成。
- 文档与代码冲突时，先以运行代码复现和定位真实行为，再在同一改动中消除冲突；不要新增平行说明。
- `docs/reports/` 是审计历史，不是当前规则来源。

## 5. 资产与隐私硬规则

- 生成图片、视频、首帧、临时文件、收藏备份、提示词索引和 Seed 只能存在 Mac 本机；远端不得落盘资产，临时存放也不允许。
- 图片由远端 WebSocket 二进制帧直回 Mac，Mac 原子落盘成功时立刻写入本地图库索引的文件名、提示词与 Seed。
- 视频由远端内存编码后直连回传 Mac 本机视频目录；不得等待浏览器轮询后才记录完成状态。
- 图生视频首帧只能存于 Mac ComfyUI `input/random_photo_prompt_mobile_video`，经令牌校验由远端内存读取；禁止复制到远端，也禁止写入 Mac `output` 或任何瀑布流扫描目录。
- 普通图片瀑布流只扫描 Mac `output` 中的生成图片，排除收藏备份和视频输出目录；收藏页只读本机收藏备份。原图被收藏后仍应留在普通瀑布流，除非用户明确删除原图。
- 已查看状态、收藏索引、提示词索引都由 Mac 服务端本地保存；不依赖浏览器缓存、浏览器 IP 或远端。

## 6. 代码所有权

| 改动目标 | 首选位置 |
| --- | --- |
| ComfyUI 导入、节点映射、HTTP 路由 | `__init__.py`、`rpp_nodes.py`、`rpp_endpoints.py` |
| 手机任务、图库、收藏、任务状态、视频输入 | `rpp_mobile.py` |
| 远端提交、WebSocket/视频回传、模型列表 | `rpp_remote.py` |
| 图片/视频工作流 patch、清理节点、LoRA | `rpp_workflow.py`、`workflow_cleanup_policy.py` |
| 共享常量、目录和运行时状态 | `rpp_globals.py`、`rpp_utils.py` |
| 提示词总入口与拼装 | `prompt_engine.py`、`rpp_prompts.py` |
| 提示词数据池 | `data/prompt_pools.json` |
| 四档姿势池 | `data/nsfw_pose_expression_options.json` |
| 提示词规划、标准化、裁剪、负面词、尺寸 | 对应的 `prompt_*.py`、`negative_prompt_engine.py`、`video_resolution.py` |
| 手机页面 | `web/mobile.html` |

- 内容池文字改动直接改 JSON，不再使用 Excel 转 JSON。
- `prompt_data.py` 的内置数据只作启动保底；不得把正常内容编辑写回那里。
- 四档姿势只读 `data/nsfw_pose_expression_options.json`；未被用户明确要求时，不要改该文件。
- 已删除的 `keyword_expansion_engine.py` 与 `/random_photo_prompt/keyword_expand` 不得恢复。

## 7. 生成规则摘要

- 项目默认规则有六个最终维度：镜头、人物、妆容、衣着、姿势表情、场景光线；不要重新拆成旧的碎片维度或保留旧池兼容层。
- 四档映射：一档 `normal`，二档 `bold`，三档 `bold_no_outfit`，四档 `nsfw`。三、四档不组合衣着；四档仅姿势使用专用池。
- 具体镜头可见范围、固定人物、妆容、衣着、姿势、场景、负面词、质量尾和自查要求，以 `docs/PROMPT_GENERATION_RULES.md` 为准，改动前必须全文阅读相关章节。
- 提示词最终顺序遵循：姿势表情 -> 场景光线 -> 质量 -> 镜头 -> 人物/衣着/妆容；固定人物身份文本不可因长度裁剪丢失。
- 提示词优化应由一致的画面母题驱动，优先保证最终画面差异与主题互斥，不把不同主题压成同一套固定夜店色光。
- 截图反馈视为共性缺陷：从数据池、规划、后处理、最终生成文本、`display_prompt` 与运行进程逐层定位，不能只改当前样例。

## 8. 图生视频规则摘要

- 图生视频提示词只写画面如何运动，不重述静态人物、衣着、场景或文生图六维度；具体写法遵循 `docs/VIDEO_PROMPT_OPTION_GUIDE.md`。
- 视频提交只读取视频动作输入框；不得继承图片页残留的手动提示词或其他跨模式状态。
- 视频固定 24 FPS；文生视频为 `540x960`。
- 图生视频按首帧比例缩放，宽高对齐 32 像素，最长边不超过 960，总像素不超过 620,000；实际尺寸由 `video_resolution.py` 写入 `MiniMaxH3ImageToVideo`。
- 视频详情打开后延迟 1 秒静音自动播放；状态展示的是实际视频尺寸与真实队列状态，不能伪造采样步骤。

## 9. 远端内存与队列

- 工作流结束清理节点不得被 WebSocket 输出改写删除。`LayerUtility: PurgeVRAM V2` 必须保持 `purge_models=true`、`purge_cache=true`。
- 切换 ZIT、ZIB、Krea2 或视频模型前，以及任务失败/中断后，先确认远端 `queue_running=0`、`queue_pending=0`，再调用 `/free` 释放模型与显存。
- 只收到中断响应不能视为清理成功；需确认队列为空且显存回到无模型基线。

## 10. 修改、部署与验证

1. 先确认任务入口与影响面，读取本文件及对应权威文档。
2. 只在唯一源码做最小改动，并同步更新对应文档。
3. 对代码做必要的静态检查、目标单元测试或真实接口回归；不要把无关的全量验证当作完成条件。
4. 改动手机端、提示词、分辨率、工作流、图库、视频、回传、`rpp_*.py`、`prompt_*.py`、`data/*.json`、`__init__.py` 或 `web/mobile.html` 时：重启 Mac 本机 `8188`，确认旧进程退出、新进程已加载。
5. 远端会读取的 custom node、工作流模板、模型/LoRA 列表或前端文件发生改动时：运行 `tools/sync_prompt_runtime_to_remote.py`，它会同步并重启远端；随后用远端 `8188` 的实际接口验证。
6. 验证必须匹配用户入口：手机端、图库与资产问题验证 Mac `8188` 的真实接口和本地文件；远端节点/工作流问题验证远端 `8188`。一端成功不能代替另一端验证。

常用命令使用 ComfyUI 的 Python：

```text
/Users/zouge/Documents/ComfyUI/.venv/bin/python tools/run_mac_local_comfyui_daemon.py
/Users/zouge/Documents/ComfyUI/.venv/bin/python tools/sync_prompt_runtime_to_remote.py
/Users/zouge/Documents/ComfyUI/.venv/bin/python tools/restart_windows_remote_comfyui.py
```

仅文档或审计报告变更不运行上述重启/同步命令。
