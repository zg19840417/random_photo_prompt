# 提示词生成审计报告（v2）

本报告由 `tools/audit_generated_prompts.py` 生成，仅报告真实问题，已剔除旧版的启发式误报。

## 结论

✅ 通过：提示词合理性与画面感核查未发现实质问题（error=0，warning 占比 <3%）。

## 概览

- 样本总数：36
- Error：0
- Warning：0
- Info：0

## 样本覆盖

- `nsfw` / `full_body` / `landscape`：6
- `nsfw` / `full_body` / `portrait`：6
- `nsfw` / `half_body` / `landscape`：6
- `nsfw` / `half_body` / `portrait`：6
- `nsfw` / `head_shot` / `landscape`：6
- `nsfw` / `head_shot` / `portrait`：6

## 检查项目录（每条规则抓什么）

- **missing_or_empty_dimension (error)**：某档位必需的维度为空或占位符。
- **outfit_leak (error)**：bold_no_outfit/nsfw 档不应出现 outfit，却出现了。
- **outfit_missing (warning)**：normal/bold 档缺少 outfit 维度。
- **exact_clause_repeat (warning)**：同一分句在全文精确重复 >=2 次（冗余）。
- **identical_dimension_text (warning)**：两个不同维度文本完全相同（复制粘贴式生成）。
- **concept_redundancy (warning)**：颗粒/色块/高光 任一概念在全文明细 >=3 次。
- **camera_shot_mismatch (warning)**：镜头文本缺少该景别应有的范围词（头部/半身/全身）。
- **camera_pose_axis_conflict (warning)**：镜头朝向与身体轴向相反（横构图+竖向身体 等）。
- **makeup_scene_daynight_mismatch (error)**：妆容昼夜与最终场景氛围不一致（复用引擎判定）。
- **non_visual_scene_text (error)**：场景维度混入非视觉叙述（空气里弥漫/传来…）。
- **abstract_pose_text (warning)**：姿势维度混入抽象元语言（勾引意味/压迫感…）。
- **detached_foot_subject (error)**：脚部作为独立身体部位主语（畸形风险）。
- **tongue_in_distal_shot (error)**：半身/全身镜头出现舌头动作（看不清）。
- **camera_aspect_mismatch (info)**：画幅朝向与镜头朝向词不一致（轻量提示）。
- **photo_realism_missing (info)**：全文未见任何摄影真实感标记。
## 长度统计

### 总字数（按 档位/景别/画幅）
- `nsfw` / `full_body` / `landscape`: 中位 414，p90 445，最大 450
- `nsfw` / `full_body` / `portrait`: 中位 420，p90 435，最大 448
- `nsfw` / `half_body` / `landscape`: 中位 414，p90 425，最大 429
- `nsfw` / `half_body` / `portrait`: 中位 418，p90 432，最大 436
- `nsfw` / `head_shot` / `landscape`: 中位 404，p90 404，最大 410
- `nsfw` / `head_shot` / `portrait`: 中位 400，p90 403，最大 417

### 维度字数热点（p90）
- `角色容貌和身材`: 中位 168，p90 176，最大 176
- `姿势和神情`: 中位 73，p90 83，最大 87
- `固定提示词`: 中位 64，p90 68，最大 71
- `妆容`: 中位 58，p90 60，最大 63
- `场景和光线`: 中位 42，p90 51，最大 51
- `镜头`: 中位 8，p90 13，最大 17

## 发现

无发现。