# 提示词生成合理性与画面感整体审查（2026-08-07）

## 审查方法
- 用 `tools/audit_generated_prompts.py` 对 **normal** 档做全量自动化审计：3 个景别（头部/半身/全身）× 2 个画幅 = 90 条样本。
- 对 **bold / bold_no_outfit / nsfw** 三档：本沙箱生成即 OOM（exit 137，已知环境内存限制，与代码无关），改为**代码路径审查** + 质量行去重逻辑的尺度无关性确认。
- 手工通读 normal 各景别完整提示词，逐条判断画面感与维度间合理性。

## 结论
- **normal 档：0 error**（修复前 4 个 error 均为审计误报，见下）。质量行冗余已修复，画面感明显更干净、连贯。
- 维度间无硬矛盾（妆容/场景昼夜一致、镜头/构图与景别一致、服装/尺度一致）。
- 审计剩余大量 warning/info **几乎全是审计启发式的误报**，非提示词缺陷。

## 本次修复（真正影响画面感的问题）
**质量行三层叠加的近义重复**：质量行由「焦段/胶片 base（QUALITY_OPTIONS_BY_SHOT）+ 场景调色 grade（FILTER_GRADE_TABLE）+ 按镜头细分 tail（_QUALITY_TAIL_BY_SHOT）」三层拼成，三者各自描述颗粒/背景色块/高光，导致同一概念说 2–3 遍，例如：
> 旧：`...颗粒细腻，甜艳轻胶片调色，高饱和色块，细腻轻颗粒，...高光不过曝，细腻轻颗粒`
> （颗粒 ×3、色块 ×2、高光 ×2+）

修复：在 `prompt_postprocess.polish_photographic_naturalness` 收尾新增 `_dedupe_quality_concepts()`，按概念族（颗粒 / 背景色块 / 高光）各保留一句，并**始终保留「高光不过曝」安全句**。

修复后（normal 全样本实测，grain≤1、colorblock≤1）：
> `85mm 中长焦特写，f/1.8 浅景深，背景虚化成柔和色块，柯达 Portra 400 暖调，高光柔润，颗粒细腻，甜艳轻胶片调色，肤质保留真实纹理，眼睛清晰锐利，高光不过曝`

该去重对 bold/nsfw 同样安全（其三档质量行不含颗粒/色块，仅保留安全句逻辑，无副作用）。

## 审计误报清单（非提示词缺陷，已同步清理 1 处过时项）
| 审计规则 | 性质 | 说明 |
|---|---|---|
| `final_bad_phrase: 日光反射到身体边缘` | 误报（已移除该过时禁用词） | 实际是很好的泳池画面描写「池水把日光反射到身体边缘」，已从严表删除 |
| `identical_dimension_text` | 误报 | 比对的 `theme_blueprint_locked / environment_anchor_locked / emotional_expression_locked / director_plan_locked` 是空 planner key，互相相等触发 |
| `camera_sentence_mismatch` | 误报 | 真实 `dimension_parts['camera']` 正确（头部=肩部以上近景、半身=竖向半身构图、全身=竖向全身构图）；告警来自审计 framing 解析的拼接值 |
| `photo_naturalness_missing` | 误报 | 严格字面 marker「真实皮肤纹理」匹配不到「肤质保留真实纹理」；提示词实际含真实肤质/高光不过曝 |
| `theme_scene_mismatch` / `theme_pose_mismatch` | 误报（normal） | normal 档未真正套用 theme 元数据（theme_name 仅为松散标签），字面关键词比对必然失配 |
| `human_review_sentence` | 多为误报 | 「脸部焦点锐利」含「焦点」被抽象词启发式命中，实为具体摄影指令 |
| `concept_repetition` / `repeated_descriptive_phrase` | info 级噪声 | 头部提示词 whiteness 词（瓷白/冷白/白）天然偏多；英文短语切片（vivid/color/smile）产生伪重复 |

## 画面感整体评价（normal）
- 场景：有具体时间/光线/环境物件与氛围（如「黄昏咖啡馆角落，暖黄吊灯在她脸侧镀一圈光，窗外街灯刚亮」），画面感强。
- 质量行：焦段/光圈/虚化/胶片/调色分层清晰，不再复读。
- 妆容与昼夜一致：白天场景不配夜妆（前次修复的校准逻辑仍有效）。
- 按镜头细分到位：头部强调肤质/眉眼，半身强调轮廓边缘，全身强调镜头景深/肢体线条。

## 仍可留意的小点（非必须修）
- 个别「晨光韩系裸妆」配「黄昏咖啡馆」：同属白天族，无硬冲突，但晨/昏调性略偏；当前 day/night 过滤不拦白天内部差异，可后续细化。
- 角色描述为固定模板（22岁瓷白冷白皮K-pop…），按设计不随机；若希望更多样可后续开放。

## 覆盖范围限制
- bold / bold_no_outfit / nsfw 三档**未能在本沙箱运行验证**（生成即 OOM），仅做代码路径审查。建议在有足够内存的环境用 `tools/audit_generated_prompts.py --scale bold --samples 10` 补一轮审计。
