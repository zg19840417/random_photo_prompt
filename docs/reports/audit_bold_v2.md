# 提示词生成审计报告（v2）

本报告由 `tools/audit_generated_prompts.py` 生成，仅报告真实问题，已剔除旧版的启发式误报。

## 结论

✅ 通过：提示词合理性与画面感核查未发现实质问题（error=0，warning 占比 <3%）。

## 概览

- 样本总数：90
- Error：0
- Warning：0
- Info：0

## 样本覆盖

- `bold` / `full_body` / `landscape`：15
- `bold` / `full_body` / `portrait`：15
- `bold` / `half_body` / `landscape`：15
- `bold` / `half_body` / `portrait`：15
- `bold` / `head_shot` / `landscape`：15
- `bold` / `head_shot` / `portrait`：15

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
- **prompt_length_over_budget (error)**：总提示词超过 800 字上限。
## 长度统计

### 总字数（按 档位/景别/画幅）
- `bold` / `full_body` / `landscape`: 中位 358，p90 387，最大 387
- `bold` / `full_body` / `portrait`: 中位 347，p90 382，最大 385
- `bold` / `half_body` / `landscape`: 中位 368，p90 389，最大 392
- `bold` / `half_body` / `portrait`: 中位 378，p90 388，最大 392
- `bold` / `head_shot` / `landscape`: 中位 323，p90 343，最大 349
- `bold` / `head_shot` / `portrait`: 中位 325，p90 340，最大 342

### 维度字数热点（p90）
- `姿势和神情`: 中位 76，p90 103，最大 104
- `角色容貌和身材`: 中位 87，p90 95，最大 95
- `妆容`: 中位 65，p90 70，最大 74
- `固定提示词`: 中位 64，p90 68，最大 68
- `场景和光线`: 中位 42，p90 51，最大 88
- `穿着`: 中位 37，p90 47，最大 47
- `镜头`: 中位 8，p90 9，最大 17

## 发现

无发现。