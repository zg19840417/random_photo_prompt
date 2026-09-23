# Z-Image Base → Z-Image Turbo 双采工作流一手资料（截至 2026-09-23）

> 范围：只读公开的一手模型卡、论文、ComfyUI 文档和工作流作者原帖；未运行模型、未测本项目、未核验远端部署。本报告不是项目运行规则。下文的「作者观察」不等于经本项目复现的画质结论。「ZIB」在这里指官方模型 **Tongyi-MAI/Z-Image**（非蒸馏版），「ZIT」指 **Tongyi-MAI/Z-Image-Turbo**。网页未给出准确发布日期时仅记可确认的年月，不伪造日号。

## 1. 模型作者和官方基线

| 日期／来源 | 明确的原始信息 | 对双采的限制 |
| --- | --- | --- |
| 2025-11-27，Z-Image 团队[论文](https://arxiv.org/abs/2511.22699)、[ZIB 模型卡](https://huggingface.co/Tongyi-MAI/Z-Image) | ZIB 非蒸馏，支持 CFG 和负面词；模型卡推荐 **28–50 步、guidance 3–5**，示例 50 步、guidance 4、`cfg_normalization=False`。 | 这是 **ZIB 单模型完整采样** 的推荐，不表示双采的 ZIB 前半程必须跑满 28 步。 |
| 2025-11 起，[ZIT 模型卡](https://huggingface.co/Tongyi-MAI/Z-Image-Turbo) | ZIT 是蒸馏版；官方 Diffusers 示例 `num_inference_steps=9`（作者注释：实际 8 次 DiT forward），`guidance_scale=0.0`；模型卡将 ZIT 标为不支持 CFG、负面词、低多样性。 | 不能把 Diffusers 的 guidance=0.0 与 ComfyUI `cfg=1` 机械等号，也不能声称加大 ZIT CFG 或负面词是官方推荐。 |
| 2026 年可见的 [ComfyUI ZIB 文档](https://docs.comfy.org/tutorials/image/z-image/z-image) 与 [ZIT 文档](https://docs.comfy.org/tutorials/image/z-image/z-image-turbo) | 分别提供原生单模型模板与所需模型文件；未将 ZIB→ZIT 的双模型交接列为官方标准模板。 | 双采的交接参数属于工作流作者实践，不是 ComfyUI 或模型作者的统一最优配置。 |

## 2. 工作流作者公开的两条路线

### A. 先拆同一条 sigma 序列，再由 ZIB 替代 ZIT 的早期步（优先研究的交接方法）

- **2026-01-29**，作者 `a4d2f` 发布原帖 [Z+Z: Z-Image variability + ZIT quality/speed](https://www.reddit.com/r/StableDiffusion/comments/1qqe6lz/zz_zimage_variability_zit_qualityspeed/)，附 [作者 Civitai 原文](https://civitai.com/articles/25490) 与 [工作流文件](https://pastebin.com/5dtVXnFm)。作者说明：先生成相当于 **8 个 ZIT 目标步** 的噪声日程，把前 **1–2 个 ZIT 步** 所覆盖的高噪声区间重新采样成 **1 到约 4 倍数量的 ZIB 步**；余下低噪声区间仍由 ZIT 完成。例如 `8/2/4` 指目标 8、替代前 2、ZIB 实跑 4、ZIT 实跑 6；`9/1/2` 指 ZIB 2 步 + ZIT 8 步。作者使用 RES4LYF 的 **Sigmas Resample**；明说只验证过 **Euler + simple**，改 scheduler 可能破坏交接，其他采样器未验证。
- 作者在 RTX 5060 Ti 16 GB、1024² 示例图中**观察**：较多 ZIB 前期步会增加种子间构图／脸部变化，但 ZIB 步过少、替代 ZIT 步过多时可出现复杂衣纹和背景噪点；`8/2/4` 是作者举的较干净例子。以上仅是作者单提示词／机器的观察，不是跨题材统计，也**不能外推至不同 sampler、scheduler、分辨率、放大链路**。作者还指出双模型轮换可能抵消少步数的时间收益；是否使用 GGUF/BF16 取决于两模型能否常驻显存。[原帖及作者答复](https://www.reddit.com/r/StableDiffusion/comments/1qqe6lz/zz_zimage_variability_zit_qualityspeed/)

### B. 常规 KSampler Advanced 百分比交接，或低分辨率起图后 latent 放大

- **2026-06 前后**，讨论帖 [Two staged workflow: ZIB to ZIT](https://www.reddit.com/r/StableDiffusion/comments/1tgkoag/two_staged_workflow_zib_to_zit/) 的原发帖人报告：完整 ZIB 后再以 ZIT `denoise=0.15–0.4` 精修出现颗粒；这不是证明 ZIT 本身会增加颗粒。
- 该帖的参与者给出 **同 scheduler、同一去噪比例** 的 `KSampler Advanced` 演示：ZIB 总 32 步只跑 `start=0,end=8`（前 25%），ZIT 总 8 步从 `start=2` 跑到结束（后 75%），前段 `add_noise=true,return_with_leftover_noise=true`，后段 `add_noise=false,return_with_leftover_noise=false`。这是参与者建议的配置，不是官方验证；原发帖人随后报告自己按 32/8 与 8/2 操作时仍有静电噪点，故不能把“同百分比”当作充分的 sigma 对齐保证。[讨论与复现反馈](https://www.reddit.com/r/StableDiffusion/comments/1tgkoag/two_staged_workflow_zib_to_zit/)
- 同帖另一参与者建议 ZIB **7 步、shift 7**，放大较低分辨率 latent，再用 ZIT **8 步、denoise 0.60**；原发帖人回复问题被解决。但这仅是个人条件下的反馈，既没有完整工作流参数，也没有统一画质/耗时对照。[具体回复](https://www.reddit.com/r/StableDiffusion/comments/1tgkoag/two_staged_workflow_zib_to_zit/)
- 作者 `jib_reddit` 在该讨论里指向本人 [JIB's Double Turbo ZIB to ZIT](https://civitai.com/models/2365846/jibs-double-turbo-zib-to-zit-workflow)，并建议若要保留变化应把 ZIB 上的 Turbo LoRA 设低或关闭；Civitai 页本轮无法可靠读取，**未核定该工作流各节点数值及更新日期**，不据此提出参数结论。[作者本人留言](https://www.reddit.com/r/StableDiffusion/comments/1tgkoag/two_staged_workflow_zib_to_zit/)

## 3. 截至 2026-09-23 相关新变化，不应误认为官方双采升级

- **2026-02／03 命名的版本**，[Alibaba-PAI Z-Image-Fun-Lora-Distill 模型卡](https://huggingface.co/alibaba-pai/Z-Image-Fun-Lora-Distill) 提供 ZIB 派生 **4/8 步（2602）**、**2/4/8 步（2603）** 蒸馏 LoRA 及 ComfyUI 版本；2603 声称其随机时间步训练改善 `sigma<0.500` 的适配，作者仍推荐 `simple` scheduler。官方明确写出它**不使用 ZIT 权重**，会略降质量、改变构图，目的是加速 ZIB 衍生模型而非替代 ZIT。它是可单独比较的速度路线，不可直接挂入现有 ZIB→ZIT 并假定改善多样性或质量。
- 模型作者论文/模型卡和 ComfyUI 官方均未提供“ZIB→ZIT 必优于单 ZIB 或单 ZIT”的结论；社区也没有可跨分辨率、采样器、负面词和 LoRA 的一致最优数字。所谓“近期流行”仅指存在作者公开案例与讨论，**没有获得全网使用量排序证据**。

## 4. 本项目与上述做法的具体差距（本地静态核查）

**依据及范围**：只读本地 [`mobile_workflow_api_2.json`](../../mobile_workflow_api_2.json)、[`rpp_workflow.py`](../../rpp_workflow.py)、[`prompt_resolution.py`](../../prompt_resolution.py)、[`rpp_globals.py`](../../rpp_globals.py)、[`workflow_cleanup_policy.py`](../../workflow_cleanup_policy.py)；未调用推理、未核验远端实际加载的副本。下表表示本机源码会组装的工作流，非远端出图效果。

| 环节 | 本项目当前双采 `zitb_double` | 与公开方法的差别／问题 |
| --- | --- | --- |
| ZIB 前段 | 本地模板 15 步、CFG 4、`res_multistep/simple`，仅跑 0–12，保留噪声；若用户选择名称含 `distill`/`10step` 的 ZIB，会改为总 10 步、CFG 1、跑 0–7。 | 作者 A 明确只测 Euler/simple 的**同一 sigma 序列拆分**；我们的 `res_multistep` 不在其验证范围。蒸馏模型路径更不能直接套非蒸馏 ZIB 官方 28–50 步。 |
| 阶段切换 | ZIB 输出经强制 `PurgeVRAM`（清模型与缓存），再以 `bislerp` 放大 latent **1.6 倍**，送入 ZIT。 | 清理可避免本项目远端双模型内存争用；与作者双模型常驻内存的耗时不可直接比较。噪声 latent 被插值放大，还需检查质感／颗粒，不是作者 A 的纯 sigma 接力。 |
| ZIT 后段 | 模板 12 步、CFG 1、`sa_solver/beta`，`add_noise=disable`、从第 4 步运行至终点。 | 与前段 `simple` **没有共享的明确 sigma 序列**；`12/4` 对 `15/12` 或 `10/7` 也不能仅凭步号解释为“同一个剩余去噪区间”。公开作者/参与者均提示交接质量依赖该边界，因此这是最值得核对的变量，而非盲目加步数。 |
| 最终修复 | ZIT 解码后走 `UltimateSDUpscale`：3 步、`euler_ancestral/beta`、denoise 0.2；输出经流式回传 Mac。 | 这是**第三次模型采样／瓷砖修复**，尽管产品称“双采”；易引入纹理变化与耗时，应与不做此步的样本对比，不能无测试宣称优劣。 |

**易误读之处**：模板的 `UltimateSDUpscale.upscale_by` 指向常量 **2.5**，但运行组装器会按目标分辨率覆盖它。对目标 `1024×1536`，静态计算 ZIB 初画布为 `640×960`、latent 后为 `1024×1536`，最终 Ultimate 为 **1.0×**；`1536×1536` 和 `1536×1024` 也为 1.0×，`768×1536` 为约 **1.071×**。因此 [`docs/AI_CONTEXT.md`](../AI_CONTEXT.md) 所写“latent 1.6× 后 SD 1.5×、目标 /1.5/1.6”与当前组装代码不符；该处后续实施优化时应同步纠正，而不是拿 1.5× 当现状。以上数值来自 `base_resolution_for_exact_output()` 的本地确定性计算，不代表最终图像的像素边缘一定不裁剪；`_insert_exact_output_scale` 会依目标另补精确缩放。

另有 UI 选项 **“新双采-ZIT+ZIB+Klein”**，但 [`rpp_globals.py`](../../rpp_globals.py) 登记的 `mobile_workflow_api_zimage_double_v2.json` 在当前唯一源码中不存在；它属于**未就绪选项**，不应误当成本项目现有可用新方案，也不能将它与上面的双采参数混为一谈。

### 建议排序（先离线论证，出图需另行授权）

1. **P0，结构核查／最小 A/B 设计**：绘出实际提交图的两段 sigma、噪声／latent 交接；设计“同一 sigma 网格 + 共同 scheduler”的对照组，保持提示词、模型文件、seed、画幅一致，仅改变交接方法。先确认各节点实现及部署支持，再考虑作者 A 的 `Sigmas Resample`；**不能保证**只改 step 数就对齐。可离线做图结构和参数检查，不调用远端。
2. **P1，画面与时间的消融**：当前 `640×960` 起图到 `1024×1536`、随后 1.0× 的 Ultimate 三步；计划分别比较有／无最终瓷砖修复、不同初画布／latent 倍率。记录脸、手、衣料纹理、背景颗粒及耗时／峰值显存；避免把纯像素缩放、采样修复、结构改动同时变更。
3. **P1，模型分组**：官方非蒸馏 ZIB、名称含 10step 的本地蒸馏 ZIB、不同 ZIT 微调模型**分别**做同种参数对照，尤其检查后一种 ZIB 在 0–7/10 与 ZIT 4–12/12 的噪声区间。模型卡的单采参数不当作双采优胜保证。
4. **P2，整理产品入口与文档**：先修复或移除缺失模板的新双采选项，并纠正倍率文档；这是可靠性问题，不需要出图才能判定，但本轮仅调查，未修改运行文件。

**不建议照搬**：直接加大 ZIT 的 CFG／负面词、照抄不同显存配置的双模型常驻方案、盲目把作者 A 的 Euler/simple 参数套到我们 `res_multistep/simple → sa_solver/beta`、把 ZIB 蒸馏 LoRA 当现有双采的无风险加速。没有同 seed 对照前，不将社区示例宣称为本项目画质提升。

## 资料可靠性说明

- 一手证据层级：模型作者模型卡／论文、ComfyUI 官方教程为模型与平台事实；作者自己的原帖仅证实其工作流配置与个人观察。论坛其他参与者的参数是个人实验，不代表模型官方。
- Civitai 原文和 `pastebin` 文件在本轮阅读工具中未可靠展开；A 的具体参数取自作者本人 Reddit 原帖，B 的未读图文件不猜数值。页面“几个月前”的展示不提供精确日期，故以年月近似标注；如要精确发行日需另查可访问的发布记录。
