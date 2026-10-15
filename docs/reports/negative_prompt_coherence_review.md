# 双采（ZIT+ZIB）负面词与正面词一致性回归

- 日期：2026-10-14
- 范围：`ZITB双采` 工作流（`mobile_workflow_api_2.json`）在 ZIB 阶段实际吃到的负面词
- 结论：修复 4 类正负冲突，全部规则化 + 测试化

## 1. 只有 ZIB 那一路吃负面词

| 阶段 | 节点 | 模型 | cfg | 负面条件 |
| --- | --- | --- | --- | --- |
| 1ST | `KSamplerAdvanced` 501 | ZIB（483） | **4** | `CLIPTextEncode` 490（真正生效） |
| 2ND | `KSamplerAdvanced` 500 | ZIT（47） | 1 | `ConditioningZeroOut` 42（等于没有负面词） |

- `rpp_endpoints.py:495` 只对 `workflow_key == "zitb_double"` 置 `accepts_negative_prompt`；留空时用 `build_chinese_negative_prompt` 覆盖（中文负面词），手填则原样提交。
- 因此：**双采的负面词只需要对 ZIB 负责**，而 cfg=4 下负面词是强约束，与正面词冲突的词条会直接把正面写死的内容压掉。

## 2. 发现并修复的 4 类冲突

| # | 冲突 | 触发条件 | 处理 |
| --- | --- | --- | --- |
| 1 | `缺脚` 与同一份负面词里的 `脚部/鞋子` 自相矛盾（头部/半身根本拍不到脚） | 竖构图 + head_shot / half_body，每次都命中 | `shot != full_body` 时剔除 `缺脚`（EN `missing feet`）；full_body 保留 |
| 2 | `大笑露齿` 压掉一档表情池里的“笑得露出一点牙齿 / 笑出了声” | 正面含 露齿/牙齿/笑出声/大笑 | 命中时剔除 `大笑露齿`（EN `wide grin / big grin / toothy smile / open mouth smile / teeth showing`） |
| 3 | `平光` 压掉正面明确要求的柔光/散射光 | 正面含 柔光/散射/柔和的光/柔和而均匀/均匀地包住（场景池 16 处） | 命中时剔除 `平光`（EN `flat lighting`） |
| 4 | `身体粘连` / `肢体融合` 把“两人贴身、交叠、缠绕”的姿势压回两人分开 | 双人（文档已强制双人必须写贴身互动，故对双人恒冲突） | 双人负面词不再包含这两条；防畸形改由 `多余手臂` / `重复肢体` / `解剖错误` 承担 |

另外复核确认无需改动的部分：
- nsfw 单人保留 `第二张脸/两张脸`（画面里只该有一张女人脸），nsfw 双人剔除（两个女生两张脸都该在）；
- nsfw 双人剔除 `第三个人/多余人物/多余手臂`（男人是合法第三人），一至三档双人保留；
- `明确性行为/暴露生殖器` 在四档已被剔除，`高光不过曝` 与负面词 `过曝` 同向不冲突；
- 一档妆容/服装池不含烟熏、亮片、红腮红、内衣等比基类内容，`lips_makeup` 与 `normal_scale` 压制不冲突；
- 夜景母题不会触发白天专用的 `夜景/阴暗光线/低调暗房` 压制（含夜景词与白天触发词的母题只有 bold 专用的月光母题）。

## 3. 验证

- `tests/test_negative_prompt_coherence.py`（新增 5 项）：按语言分别断言中/英文负面词；覆盖 4 类冲突的正反两面（命中时剔除、未命中时保留）；并对 4 档 × 3 镜头 × 单双人 × 6 seed 的生成结果做全量不变量检查。
- 全量单元测试 143 项通过。
- 真实提交路径核对：生成 → 中文负面词覆盖 → patch 双采模板 → 检查节点 490 文本，96 条样本无冲突。
- Mac 8188 已重启，线上接口实测：head_shot/half_body 无 `missing feet`、full_body 保留；四档双人无 `third person` / `second face` / `fused bodies`，保留 `crowd`。

## 4. 待办

远端 4090（192.168.123.111）仍不可达，`negative_prompt_engine.py`、`prompt_constants.py` 已列入 `tools/sync_prompt_runtime_to_remote.py` 的同步清单，但本次未能同步；该机开机后需补跑同步并重启远端 8188。

## 5. 风险与回退

双人不再压 `身体粘连/肢体融合`，若实际出图出现两人糊成一团的粘连问题，可在 `negative_prompt_engine.py` 的 `_CHINESE_EXTRAS["duo"]` / `_ENGLISH_EXTRAS["duo"]` 里加回这两条（代价是姿势会被压回两人分开）。
