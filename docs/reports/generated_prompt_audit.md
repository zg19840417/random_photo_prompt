# 提示词生成审计报告（v2）

本报告由 `tools/audit_generated_prompts.py` 生成，仅报告真实问题，已剔除旧版的启发式误报。

## 结论

✅ 通过：提示词合理性与画面感核查未发现实质问题（error=0，warning 占比 <3%）。

## 概览

- 样本总数：480
- Error：0
- Warning：0
- Info：0

## 样本覆盖

- `bold` / `full_body` / `landscape`：20
- `bold` / `full_body` / `portrait`：20
- `bold` / `half_body` / `landscape`：20
- `bold` / `half_body` / `portrait`：20
- `bold` / `head_shot` / `landscape`：20
- `bold` / `head_shot` / `portrait`：20
- `bold_no_outfit` / `full_body` / `landscape`：20
- `bold_no_outfit` / `full_body` / `portrait`：20
- `bold_no_outfit` / `half_body` / `landscape`：20
- `bold_no_outfit` / `half_body` / `portrait`：20
- `bold_no_outfit` / `head_shot` / `landscape`：20
- `bold_no_outfit` / `head_shot` / `portrait`：20
- `normal` / `full_body` / `landscape`：20
- `normal` / `full_body` / `portrait`：20
- `normal` / `half_body` / `landscape`：20
- `normal` / `half_body` / `portrait`：20
- `normal` / `head_shot` / `landscape`：20
- `normal` / `head_shot` / `portrait`：20
- `nsfw` / `full_body` / `landscape`：20
- `nsfw` / `full_body` / `portrait`：20
- `nsfw` / `half_body` / `landscape`：20
- `nsfw` / `half_body` / `portrait`：20
- `nsfw` / `head_shot` / `landscape`：20
- `nsfw` / `head_shot` / `portrait`：20

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
- **fluency:* (warning)**：逐行通顺度（prompt_fluency）：冗余表情尾巴、构图词混入姿势、否定式正向词、非视觉场景、服装语法、抽象评价、断句、视线/笑容重复、调色叠加、焦段与镜头不符、超长子句、同一只手两个动作、镜头外部位、场景过短、服装细节堆叠。
## 长度统计

### 总字数（按 档位/景别/画幅）
- `bold` / `full_body` / `landscape`: 中位 560，p90 603，最大 616
- `bold` / `full_body` / `portrait`: 中位 571，p90 590，最大 592
- `bold` / `half_body` / `landscape`: 中位 524，p90 553，最大 565
- `bold` / `half_body` / `portrait`: 中位 527，p90 545，最大 565
- `bold` / `head_shot` / `landscape`: 中位 465，p90 494，最大 506
- `bold` / `head_shot` / `portrait`: 中位 471，p90 488，最大 505
- `bold_no_outfit` / `full_body` / `landscape`: 中位 511，p90 530，最大 551
- `bold_no_outfit` / `full_body` / `portrait`: 中位 517，p90 531，最大 543
- `bold_no_outfit` / `half_body` / `landscape`: 中位 474，p90 482，最大 508
- `bold_no_outfit` / `half_body` / `portrait`: 中位 459，p90 487，最大 501
- `bold_no_outfit` / `head_shot` / `landscape`: 中位 415，p90 432，最大 453
- `bold_no_outfit` / `head_shot` / `portrait`: 中位 412，p90 442，最大 449
- `normal` / `full_body` / `landscape`: 中位 535，p90 551，最大 563
- `normal` / `full_body` / `portrait`: 中位 514，p90 526，最大 555
- `normal` / `half_body` / `landscape`: 中位 468，p90 480，最大 495
- `normal` / `half_body` / `portrait`: 中位 474，p90 487，最大 501
- `normal` / `head_shot` / `landscape`: 中位 406，p90 415，最大 427
- `normal` / `head_shot` / `portrait`: 中位 408，p90 427，最大 442
- `nsfw` / `full_body` / `landscape`: 中位 557，p90 595，最大 595
- `nsfw` / `full_body` / `portrait`: 中位 545，p90 573，最大 579
- `nsfw` / `half_body` / `landscape`: 中位 501，p90 533，最大 552
- `nsfw` / `half_body` / `portrait`: 中位 498，p90 519，最大 529
- `nsfw` / `head_shot` / `landscape`: 中位 442，p90 461，最大 475
- `nsfw` / `head_shot` / `portrait`: 中位 438，p90 480，最大 486

### 维度字数热点（p90）
- `场景和光线`: 中位 93，p90 124，最大 149
- `角色容貌和身材`: 中位 99，p90 99，最大 99
- `姿势和神情`: 中位 55，p90 88，最大 101
- `固定提示词`: 中位 63，p90 68，最大 69
- `妆容`: 中位 44，p90 55，最大 67
- `穿着`: 中位 45，p90 54，最大 66
- `镜头`: 中位 38，p90 50，最大 71

## 发现

无发现。