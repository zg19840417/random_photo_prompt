#!/usr/bin/env python3
"""提示词自检工具（优化版，与 audit_generated_prompts.py v2 保持一致）。

相对旧版移除的误报源：
- 把正常词当禁用词的硬编码黑名单（单字「或/或者/或是」、常见词「焦点/氛围/
  形成层次/维持/用于…」）——这些会误伤几乎所有正常提示词。
- 抽象词密度检查（ABSTRACT_WORDS）与场景物件启发式（SCENE_OBJECT_MARKERS）——
  对「背景/墙面/窗帘/焦点/张力」等常见词频繁误报。
- 段落布局启发式（质量段位置、环境母题混杂、导演段站姿冲突等）——强依赖排版
  约定，误报多。

保留 / 新增的可靠检查：
- 真实拼接残片（重复主语「女孩她/女人她」、字段错位「肩线和肩线下方」等）。
- 精确重复分句 / 重复内容。
- 复用 v2 的文本级检查：非视觉叙述、独立脚主语、远镜头舌头、摄影真实感缺失、超长。
- 档位 / 景别 / 时代 的结构性检查（无衣着档位出现上衣、头部镜头出现胸前、古代混现代衣）。

`main()` 还会对每条生成结果跑 v2 的完整维度审计（audit_item），两路并发，任一
发现问题即判 FAIL。

用法：
    python tools/audit_prompt_self_check.py --target-pass 3 --max-rounds 30
"""
from __future__ import annotations

import argparse
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prompt_engine import generate_prompt_items  # noqa: E402
import audit_generated_prompts as V2  # noqa: E402  v2 可靠检查

SCALES = ("normal", "bold", "bold_no_outfit", "nsfw")
SHOTS = ("head_shot", "half_body", "full_body")
ASPECTS = ("portrait",)
ERAS = ("modern", "ancient")

# 仅保留「真实的拼接残片」：重复主语 / 重复身体部位 / 字段错位 / 真实语法 artifact。
ARTIFACT_PHRASES = (
    "角色脚底及以上她", "角色脚底及以上腰线", "头部从树影下头部",
    "女孩她", "女人她", "双手左手", "肩线和肩线下方", "肩线侧转头部",
    "角色脚底及以上机位", "眼神像刚从旁边收回来", "眼神像刚从侧光暗部收回来",
    "斜斜压在镜头", "裙摆下方保持裸足", "脚下落点完整，左手", "贴合肩颈和胸前上衣",
    "指尖停在肩线下方", "手指停在肩线下方", "手指停在胸前上衣", "胸前的黑亮指甲",
    "身前的台面", "前臂压住身前", "低台台面", "画面重心", "视觉路径",
)

REPEATED_PATTERNS = (
    re.compile(r"([\u4e00-\u9fff]{2,6})\1"),
    re.compile(r"(眼神|嘴角|身体|画面|高光|边缘)[^。]{0,8}\1"),
)

# 古代场景不应出现的现代衣着词（真实检查）
MODERN_OUTFIT_MARKERS = (
    "飞行员夹克", "牛仔", "棒球领", "乐福鞋", "帆布鞋", "运动鞋", "针织背心", "工装", "卫衣",
)


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[。！？\n]+", text) if part.strip()]


def clause_repetition_issue(text: str) -> str:
    clauses = [
        part.strip("，。； \n\t")
        for part in re.split(r"[，。；\n]+", text)
        if part.strip("，。； \n\t")
    ]
    seen: set[str] = set()
    for clause in clauses:
        normalized = re.sub(r"(保持|清楚|微微|轻轻|一点|很|的)", "", clause)[:18]
        if len(normalized) >= 6 and normalized in seen:
            return clause
        seen.add(normalized)
    return ""


def audit_prompt(text: str, selections: dict[str, str] | None = None) -> list[str]:
    issues: list[str] = []
    selections = selections or {}
    scale = selections.get("scale")
    shot = selections.get("shot")
    era = selections.get("era")

    # 1) 真实拼接残片
    for phrase in ARTIFACT_PHRASES:
        if phrase in text:
            issues.append(f"拼接残片：{phrase}")

    # 2) 重复内容 / 重复分句
    for pattern in REPEATED_PATTERNS:
        match = pattern.search(text)
        if match:
            issues.append(f"重复内容：{match.group(0)[:24]}")
            break
    repeated_clause = clause_repetition_issue(text)
    if repeated_clause:
        issues.append(f"重复分句：{repeated_clause[:40]}")

    # 3) 复用 v2 文本级可靠检查
    if any(m in text for m in V2.NON_VISUAL_SCENE):
        issues.append("非视觉叙述混入场景")
    if any(m in text for m in V2.DETACHED_FOOT):
        issues.append("脚部作为独立主语（畸形风险）")
    if shot in ("half_body", "full_body") and any(t in text for t in V2.TONGUE_DISTAL):
        issues.append("远镜头出现舌头动作（看不清）")
    if not any(m in text for m in V2.QUALITY_REALISM):
        issues.append("缺少摄影真实感标记")
    if len(text) > V2.MAX_POSITIVE_PROMPT_LENGTH:
        issues.append(f"总字数超过 {V2.MAX_POSITIVE_PROMPT_LENGTH}")

    # 4) 档位 / 景别 / 时代 结构性检查
    if scale in {"bold_no_outfit", "nsfw"} and "上衣" in text:
        issues.append("无衣着档位出现上衣描述")
    if scale in {"bold_no_outfit", "nsfw"} and any(m in text for m in ("裙摆", "衣摆", "衣襟", "披帛")):
        issues.append("无衣着档位出现衣着残留")
    if shot == "head_shot" and any(m in text for m in ("胸前上衣", "胸前衣料", "胸前")):
        issues.append("头部镜头出现胸前描述")
    if era == "ancient" and any(m in text for m in MODERN_OUTFIT_MARKERS):
        issues.append("古代场景混入现代衣着")
    return issues


def sample_prompt(rng: random.Random, index: int) -> tuple[dict[str, str], str, dict]:
    selections = {
        "scale": rng.choice(SCALES),
        "shot": rng.choice(SHOTS),
        "aspect": rng.choice(ASPECTS),
        "era": rng.choice(ERAS),
    }
    seed = f"self-check-{int(time.time() * 1000)}-{index}-{rng.randint(1, 10 ** 9)}"
    item = generate_prompt_items(1, selections, seed_text=seed)[0]
    return selections, item["positive_prompt"], item


def main() -> int:
    parser = argparse.ArgumentParser(description="随机自检生成的提示词，直到连续通过（v2，低误报）。")
    parser.add_argument("--target-pass", type=int, default=3)
    parser.add_argument("--max-rounds", type=int, default=30)
    parser.add_argument("--seed", default="")
    args = parser.parse_args()

    engine = V2.load_prompt_engine()
    rng = random.Random(args.seed or int(time.time() * 1000))
    consecutive = 0
    passed_prompts: list[tuple[str, str]] = []
    for round_index in range(1, args.max_rounds + 1):
        selections, prompt, item = sample_prompt(rng, round_index)
        issues = audit_prompt(prompt, selections)
        # 同时跑 v2 完整维度审计
        v2_findings = V2.audit_item(
            engine, selections["scale"], selections["shot"], selections["aspect"], 1, item
        )
        v2_issues = [f"{f.severity}:{f.rule} {f.detail}" for f in v2_findings]
        all_issues = issues + v2_issues
        label = f"{selections['scale']}/{selections['shot']}/{selections['era']}"
        if all_issues:
            consecutive = 0
            passed_prompts.clear()
            print(f"[FAIL] round={round_index} {label}")
            for issue in all_issues:
                print(f"- {issue}")
            print(prompt)
            return 1
        consecutive += 1
        passed_prompts.append((label, prompt))
        print(f"[PASS] round={round_index} {label} consecutive={consecutive}")
        if consecutive >= args.target_pass:
            print(f"OK: consecutive passes reached {args.target_pass}")
            for idx, (passed_label, passed_prompt) in enumerate(passed_prompts[-args.target_pass:], start=1):
                print(f"\n=== PASSED PROMPT {idx}: {passed_label} ===")
                print(passed_prompt)
            return 0
    print(f"FAIL: only {consecutive} consecutive passes after {args.max_rounds} rounds")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
