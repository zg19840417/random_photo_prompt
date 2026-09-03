# MiniMax H3 图生视频加速方案调研（2026-09-02）

## 结论

有可实际接入当前工作流的成熟候选：**ModelTC / LightX2V 发布的 MiniMax-H3 Turbo 蒸馏 LoRA**。它不是普通画风 LoRA，而是为减少采样次数训练的专用 LoRA；作者提供了 ComfyUI 格式权重、I2VA（首帧图生视频）示例工作流和接入说明。

当前项目使用 `MiniMaxH3ImageToVideo` 与 `minimax_h3_fl2va_pruned_int8_convrot.safetensors`，属于 FL2VA 首帧图生视频路径。因此匹配的候选是：

| 方案 | 当前链路兼容性 | 作者推荐采样 | 判断 |
| --- | --- | --- | --- |
| `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` | 是，FL2VA / I2VA；作者提供 ComfyUI I2VA 图 | 8 步（也允许 4 步） | **首选试验项**。相对当前 12 步，理论采样迭代减少约 1/3。 |
| `minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors` | 是，FL2VA / I2VA | 4 步 | 可作为极速档测试；训练规格是 768p / `1344x768`，不应未经画质回归就作为当前竖图默认。 |
| `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors` | 否，当前模板不是 Ref2VA | 4 步 | 不适用。需要改成 Ref2VA 工作流才可用。 |

`8-step v1.0` 是作者在线 Studio 当前采用的版本，且作者的 ComfyUI 示例默认使用它；以目前证据，它是比 4-step 更稳妥的默认加速候选，但并非 MiniMax 官方发布物，接入前仍需在远端 RTX 4090 以真实首帧做速度、首帧一致性、动作稳定性回归。

## 不能混为一谈的概念

| 概念 | 对本项目的含义 | 是否能单独解决当前耗时 |
| --- | --- | --- |
| Turbo 蒸馏 LoRA | 把 FL2VA 的采样轨迹蒸馏为 8 / 4 步；必须接到模型加载后的 LoRA 节点 | 是，主要候选 |
| Lightning / Hyper | 本次一手来源未发现 MiniMax H3 官方或上述作者以这些名称发布、可替代当前 FL2VA I2VA 的独立方案 | 不能据此接入 |
| 采样器与 shift | Turbo 不是只改 `steps`。作者要求 `lora_name`、`steps`、`shift_video`、`shift_audio` 同步匹配，示例采样器为 `euler` | 否；配错会让 Turbo 失效或劣化 |
| 量化 | 当前已经是 `pruned_int8_convrot`。量化主要释放显存/避免卸载，不等于把 12 步变成 4 步 | 不能替代 Turbo |
| 缓存/注意力加速 | 属于运行时优化，和 Turbo 可以叠加，但需要单独核验远端 ComfyUI、显卡与节点兼容性 | 可能，非本次 LoRA 结论 |

## 接入前提与建议

1. 不应直接把 LoRA 放入目录后沿用现有模板。模板须新增/启用该 LoRA，并把 `BasicScheduler.steps`、video/audio shift 与采样器一起改成作者给出的匹配组合。
2. 先只试 `8-step v1.0`，保留现有 12-step 基础模板作为质量档，不删除或覆盖任何现有模型。
3. 对同一首帧、同一提示词、同一秒数和同一分辨率分别跑 12-step 与 8-step，记录端到端耗时、首帧身份保持、运动连续性、闪烁和音画质量；通过后再考虑提供“快速/质量”两种模式。
4. 当前图生视频可到最长边 960；作者的 8-step LoRA 训练为 544p 混合画幅，768p 4-step 版本的训练规格为 `1344x768`。因此竖图 960 长边是否有稳定质量，必须以真实项目样本验证，不能由模型名推断。

## 一手来源

- [ModelTC MiniMax-H3-Turbo 仓库](https://github.com/ModelTC/Minimax-H3-Turbo)：作者说明这是 Turbo LoRA，列出 FL2VA / Ref2VA 各版本、任务、训练分辨率和推荐步数。
- [ModelTC 的 ComfyUI 接入说明](https://github.com/ModelTC/Minimax-H3-Turbo/blob/main/COMFYUI_SETUP_AND_INFERENCE.md)：明确给出 ComfyUI 权重文件、I2VA 示例、以及 LoRA / steps / video shift / audio shift 必须同步设置的要求。
- [Turbo 权重模型卡](https://huggingface.co/lightx2v/Minimax-h3-Turbo)：作者发布的下载位置。
- [ModelTC I2VA ComfyUI 示例工作流](https://github.com/ModelTC/Minimax-H3-Turbo/blob/main/example_workflows/video_minimax_h3_i2v_lightx2v_turbo.json)：首帧图生视频示例。
- [MiniMax 官方 H3 仓库](https://github.com/MiniMax-AI/MiniMax-H3)：基础模型的官方来源。
- [ComfyUI 官方 MiniMax H3 教程](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)：官方 `MiniMaxH3ImageToVideo` 节点与参考图尺寸说明。

## 本项目对应依据

- 当前模板 [minimax_h3_workflow_api.json](../../minimax_h3_workflow_api.json) 使用 `MiniMaxH3ImageToVideo`、12 步 `BasicScheduler`、`res_multistep` 和 FL2VA `pruned_int8_convrot`。
- 当前运行约束见 [AI_CONTEXT.md](../AI_CONTEXT.md)：图生视频最长边 960、24 FPS、默认 4 秒、12 步。

本报告只完成资料核验，不下载模型、不修改远端模型目录或工作流。
