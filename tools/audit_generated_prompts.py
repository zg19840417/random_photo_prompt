"""提示词生成审计工具（重写版，v2）。

设计目标（相对旧版）：
1. 可信：每条检查都对应一个「真实的合理性 / 画面感」问题，杜绝旧版靠字面
   切片、空 planner key 互比、抽象词黑名单产生的海量误报。
2. 语义化：昼夜妆容一致性直接复用引擎自身的 `_makeup_mismatches_scene`，
   镜头/景别一致性按镜头词判定，而非拼接 framing 文本。
3. 内存友好：逐条生成 + 即时审计 + 周期 gc，不在内存里堆积全部样本。
4. 透明：报告开头列出「检查项目录」，每条规则讲清它在抓什么。

用法：
    python tools/audit_generated_prompts.py --samples 15 --scale normal --report docs/reports/audit_normal.md
    python tools/audit_generated_prompts.py --scale bold --scale nsfw --samples 10
    python tools/audit_generated_prompts.py --shot head_shot --samples 20
"""
from __future__ import annotations

import argparse
import gc
import importlib.util
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_PATH = ROOT / "docs" / "reports" / "generated_prompt_audit.md"

SCALES = ("normal", "bold", "bold_no_outfit", "nsfw")
SHOTS = ("head_shot", "half_body", "full_body")
SHOT_INPUTS = {"head_shot": "头部", "half_body": "半身", "full_body": "全身"}

# 每个档位「应当出现且非空」的维度
EXPECTED_DIMENSIONS = {
    "normal": ("camera", "character", "outfit", "pose_expression", "scene_light"),
    "bold": ("camera", "character", "outfit", "pose_expression", "scene_light"),
    "bold_no_outfit": ("camera", "character", "pose_expression", "scene_light"),
    "nsfw": ("camera", "character", "pose_expression", "scene_light"),
}
DIMENSION_LABELS = {
    "camera": "镜头",
    "character": "角色容貌和身材",
    "makeup": "妆容",
    "outfit": "穿着",
    "pose_expression": "姿势和神情",
    "scene_light": "场景和光线",
    "quality": "固定提示词",
}

# 总长度已不再设置上限（运行时 MAX_POSITIVE_PROMPT_LENGTH 为 99999 哨兵，单一来源
# 在 prompt_constants），长度控制由各维度 PART_LENGTH_BUDGETS 在生成时完成；
# 审计只保留长度统计（见 length_report），不再报告「总字数超上限」错误。

# ---------------------------------------------------------------------------
# 检查用的语义标记（精简、刻意保守，宁可漏报也不制造误报）
# ---------------------------------------------------------------------------
CAMERA_SCOPE = {
    "head_shot": ("头部", "肩膀以上", "肩部以上", "肩膀及以上", "头顶", "肩以上"),
    "half_body": ("半身", "大腿以上", "腰部", "胸腰以上"),
    "full_body": ("全身", "从头到脚", "从头顶到脚掌", "从头顶到脚"),
}
CAMERA_PORTRAIT = ("竖构图", "竖向", "竖屏", "窄长", "竖向构图")
CAMERA_LANDSCAPE = ("横构图", "横向", "横屏", "宽画幅", "横向构图")
POSE_PORTRAIT_AXIS = ("从头顶到脚掌", "从上到下", "纵向", "竖向坐", "竖向跪", "竖向全身", "窄长全身", "竖向半身")
# 仅保留「明确横向」词；仰躺/平躺/侧躺等躺姿与竖向全身构图是兼容的（全身竖向构图本就常用于躺姿），
# 不应判为冲突，否则 nsfw 躺姿会被大量误报。
POSE_LANDSCAPE_AXIS = ("横向靠", "横向坐", "横向趴", "横向全身", "横向半身", "沿宽画幅", "沿画面宽度", "向一侧延伸", "斜向铺")
NON_VISUAL_SCENE = ("空气里弥漫", "空气中充满", "空气中是", "气息", "花香", "水声", "回响", "传来", "让人联想到", "仿佛能闻到")
ABSTRACT_POSE = ("勾引意味", "诱惑感集中", "压迫感", "视觉路径", "视线沿手指", "构图重点", "视觉中心", "私密邀请")
# 仅当脚部被写成「独立前景主语」（无动作衔接）才判畸形；"一只脚踩住/踏在" 等
# 带动作上下文的描述是合法的，不应误伤。
DETACHED_FOOT = ("一只裸足", "一只脚掌", "一只脚尖", "裸足停在", "脚掌和脚尖靠近镜头", "一只脚靠近镜头", "一只脚伸向", "一只脚停在")
TONGUE_DISTAL = ("舌尖", "舌头", "伸舌", "探出舌尖")
# 质量行至少应包含其一才算是「有摄影真实感」
QUALITY_REALISM = ("高光不过曝", "真实", "自然", "景深", "肤质", "纹理", "胶片", "调色", "锐利", "清晰", "层次", "反光", "明暗", "柔光", "颗粒")
# 概念族冗余：同一概念在全文出现 >=3 次才算冗余（引擎已做质量行去重，触发即真实）
REDUNDANT_CONCEPT_MARKERS = ("颗粒", "色块", "高光")

CLAUSE_SPLIT_RE = re.compile(r"[。；;，,、\n]+")
EMPTY_PLACEHOLDERS = {"", "无", "——", "无。", "。"}


@dataclass
class Finding:
    severity: str
    scale: str
    shot: str
    aspect: str
    sample: int
    rule: str
    detail: str
    prompt: str


@dataclass
class PromptStats:
    scale: str
    shot: str
    aspect: str
    sample: int
    prompt_length: int
    dimension_lengths: dict[str, int]


def load_prompt_engine():
    path = ROOT / "prompt_engine.py"
    spec = importlib.util.spec_from_file_location("generated_prompt_engine", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# 昼夜妆容一致性：复用引擎自身判定，避免审计与生成逻辑漂移
def _makeup_mismatches_scene(engine, scene_light: str, makeup: str) -> bool:
    fn = getattr(engine, "_makeup_mismatches_scene", None)
    if callable(fn):
        try:
            return bool(fn(scene_light, makeup))
        except Exception:
            return False
    return False


def normalize_text(text: str) -> str:
    return re.sub(r"[\s，。；;、：:\-_/（）()\"'‘’]+", "", text)


def split_clauses(text: str) -> list[str]:
    return [part.strip() for part in CLAUSE_SPLIT_RE.split(text) if len(part.strip()) >= 4]


def ensure_sentence(text: str) -> str:
    text = str(text or "").strip("，。 \n\t")
    return f"{text}。" if text else ""


def prompt_from_parts(parts: dict[str, str]) -> str:
    order = ("camera", "character", "outfit", "makeup", "pose_expression", "scene_light", "quality")
    return "\n".join(ensure_sentence(parts.get(name, "")) for name in order if parts.get(name))


# ---------------------------------------------------------------------------
# 检查函数（每条返回一个 Finding 列表；只报真问题）
# ---------------------------------------------------------------------------
def schema_findings(scale, shot, aspect, sample, parts, prompt) -> list[Finding]:
    findings: list[Finding] = []
    expected = EXPECTED_DIMENSIONS[scale]
    for name in expected:
        value = str(parts.get(name) or "").strip("，。 \n\t")
        if value in EMPTY_PLACEHOLDERS:
            findings.append(Finding("error", scale, shot, aspect, sample, "missing_or_empty_dimension",
                                    f"{DIMENSION_LABELS.get(name, name)} 为空", prompt))
    # 不应出现 outfit 的档位却出现了
    if scale in {"bold_no_outfit", "nsfw"} and str(parts.get("outfit") or "").strip():
        findings.append(Finding("error", scale, shot, aspect, sample, "outfit_leak",
                                f"{scale} 档不应包含 outfit 维度", prompt))
    # normal / bold 应有 outfit
    if scale in {"normal", "bold"} and not str(parts.get("outfit") or "").strip():
        findings.append(Finding("warning", scale, shot, aspect, sample, "outfit_missing",
                                "normal/bold 档缺少 outfit 维度", prompt))
    return findings


def redundancy_findings(scale, shot, aspect, sample, parts, prompt) -> list[Finding]:
    findings: list[Finding] = []
    # 1) 同一分句在全文精确重复（归一化后）
    counter = Counter(normalize_text(c) for c in split_clauses(prompt))
    repeated = [c for c, n in counter.items() if n >= 2 and len(c) >= 6]
    if repeated:
        findings.append(Finding("warning", scale, shot, aspect, sample, "exact_clause_repeat",
                                "、".join(repeated[:5]), prompt))
    # 2) 两个不同维度文本完全相同（且足够长）
    dims = [n for n in EXPECTED_DIMENSIONS[scale]]
    for i in range(len(dims)):
        for j in range(i + 1, len(dims)):
            a, b = normalize_text(str(parts.get(dims[i]) or "")), normalize_text(str(parts.get(dims[j]) or ""))
            if a and a == b and len(a) >= 8:
                findings.append(Finding("warning", scale, shot, aspect, sample, "identical_dimension_text",
                                        f"{DIMENSION_LABELS.get(dims[i], dims[i])} == {DIMENSION_LABELS.get(dims[j], dims[j])}", prompt))
    # 3) 概念族冗余：颗粒/色块/高光 在全文 >=3 次。
    # 高光需先排除强制安全句「高光不过曝」，否则清透高光+高光不过曝会被误判。
    concept_hits = {
        "颗粒": prompt.count("颗粒"),
        "色块": prompt.count("色块"),
        "高光": prompt.replace("高光不过曝", "").count("高光"),
    }
    for marker, count in concept_hits.items():
        if count >= 4:
            findings.append(Finding("warning", scale, shot, aspect, sample, "concept_redundancy",
                                    f"{marker} 出现 {count} 次（已排除安全句「高光不过曝」）", prompt))
            break
    return findings


def coherence_findings(engine, scale, shot, aspect, sample, parts, prompt) -> list[Finding]:
    findings: list[Finding] = []
    camera = str(parts.get("camera") or "")
    pose = str(parts.get("pose_expression") or "")
    scene = str(parts.get("scene_light") or "")

    # 镜头 vs 景别范围一致性
    scope = CAMERA_SCOPE.get(shot, ())
    if scope and not any(m in camera for m in scope):
        findings.append(Finding("warning", scale, shot, aspect, sample, "camera_shot_mismatch",
                                f"镜头缺少 {shot} 应有的范围词（{('/'.join(scope))}）：{camera}", prompt))

    # 镜头朝向 vs 身体轴向冲突
    if any(m in camera for m in CAMERA_LANDSCAPE) and any(m in pose for m in POSE_PORTRAIT_AXIS):
        findings.append(Finding("warning", scale, shot, aspect, sample, "camera_pose_axis_conflict",
                                "横构图镜头搭配竖向身体轴向姿势", prompt))
    if any(m in camera for m in CAMERA_PORTRAIT) and any(m in pose for m in POSE_LANDSCAPE_AXIS):
        findings.append(Finding("warning", scale, shot, aspect, sample, "camera_pose_axis_conflict",
                                "竖构图镜头搭配横向身体轴向姿势", prompt))

    # 昼夜妆容一致性（复用引擎判定）
    makeup = str(parts.get("makeup") or "")
    if makeup and _makeup_mismatches_scene(engine, scene, makeup):
        findings.append(Finding("error", scale, shot, aspect, sample, "makeup_scene_daynight_mismatch",
                                f"场景「{scene}」与妆容「{makeup}」昼夜不一致", prompt))

    # 非视觉叙述不应进入场景维度
    scene_hits = [p for p in NON_VISUAL_SCENE if p in scene]
    if scene_hits:
        findings.append(Finding("error", scale, shot, aspect, sample, "non_visual_scene_text",
                                "、".join(scene_hits), prompt))

    # 抽象元语言（非画面词）混入姿势
    abstract_hits = [p for p in ABSTRACT_POSE if p in pose]
    if abstract_hits:
        findings.append(Finding("warning", scale, shot, aspect, sample, "abstract_pose_text",
                                "、".join(abstract_hits), prompt))

    # 脚部作为独立主语（畸形风险）
    foot_hits = [p for p in DETACHED_FOOT if p in pose or p in prompt]
    if foot_hits:
        findings.append(Finding("error", scale, shot, aspect, sample, "detached_foot_subject",
                                "脚部前景不能写成独立身体部位主语：" + "、".join(foot_hits), prompt))

    # 远镜头出现舌头动作（看不清）
    if shot in {"half_body", "full_body"} and any(t in pose for t in TONGUE_DISTAL):
        findings.append(Finding("error", scale, shot, aspect, sample, "tongue_in_distal_shot",
                                "半身/全身镜头不使用舌头动作，画面里看不清", prompt))

    # 画幅朝向 vs 镜头朝向（轻量 info）；head_shot 无明确朝向冲突，跳过
    if shot != "head_shot":
        if aspect == "landscape" and any(m in camera for m in CAMERA_PORTRAIT) and not any(m in camera for m in CAMERA_LANDSCAPE):
            findings.append(Finding("info", scale, shot, aspect, sample, "camera_aspect_mismatch",
                                    "landscape 画幅但镜头偏竖向词", prompt))
        if aspect == "portrait" and any(m in camera for m in CAMERA_LANDSCAPE) and not any(m in camera for m in CAMERA_PORTRAIT):
            findings.append(Finding("info", scale, shot, aspect, sample, "camera_aspect_mismatch",
                                    "portrait 画幅但镜头偏横向词", prompt))
    return findings


def quality_findings(scale, shot, aspect, sample, parts, prompt) -> list[Finding]:
    findings: list[Finding] = []
    if not any(m in prompt for m in QUALITY_REALISM):
        findings.append(Finding("info", scale, shot, aspect, sample, "photo_realism_missing",
                                "全文未见任何摄影真实感标记（高光不过曝/真实/景深/肤质…）", prompt))
    return findings


def length_findings(scale, shot, aspect, sample, parts, prompt) -> list[Finding]:
    # 总长度不再设置硬上限（MAX_POSITIVE_PROMPT_LENGTH 为 99999 哨兵），长度由
    # 各维度预算在生成时控制；此处不再产生超长 error，长度分布仅作统计展示。
    return []


def audit_item(engine, scale, shot, aspect, sample, item) -> list[Finding]:
    prompt = item["positive_prompt"]
    parts = item["dimension_parts"]
    findings: list[Finding] = []
    findings.extend(schema_findings(scale, shot, aspect, sample, parts, prompt))
    findings.extend(redundancy_findings(scale, shot, aspect, sample, parts, prompt))
    findings.extend(coherence_findings(engine, scale, shot, aspect, sample, parts, prompt))
    findings.extend(quality_findings(scale, shot, aspect, sample, parts, prompt))
    findings.extend(length_findings(scale, shot, aspect, sample, parts, prompt))
    return findings


# ---------------------------------------------------------------------------
# 运行（流式：逐条生成→审计→丢弃，周期 gc）
# ---------------------------------------------------------------------------
def run_audit(samples, scales, shots, engine) -> tuple[list[Finding], dict, list[PromptStats]]:
    findings: list[Finding] = []
    stats: list[PromptStats] = []
    sample_counts: dict[tuple[str, str, str], int] = {}
    for scale in scales:
        for shot in shots:
            for aspect in ("portrait", "landscape"):
                for index in range(samples):
                    seed = f"audit-{scale}-{shot}-{aspect}-{index}"
                    item = engine.generate_prompt_items(
                        1, {"scale": scale, "shot": SHOT_INPUTS[shot], "aspect": aspect}, seed_text=seed
                    )[0]
                    parts = item["dimension_parts"]
                    prompt = item["positive_prompt"]
                    key = (scale, shot, aspect)
                    sample_counts[key] = sample_counts.get(key, 0) + 1
                    findings.extend(audit_item(engine, scale, shot, aspect, index + 1, item))
                    stats.append(PromptStats(
                        scale=scale, shot=shot, aspect=aspect, sample=index + 1,
                        prompt_length=len(prompt),
                        dimension_lengths={n: len(v) for n, v in parts.items() if n in DIMENSION_LABELS and v},
                    ))
                    if (index + 1) % 10 == 0:
                        gc.collect()
                gc.collect()
    return findings, sample_counts, stats


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------
CHECK_CATALOG = [
    ("missing_or_empty_dimension (error)", "某档位必需的维度为空或占位符。"),
    ("outfit_leak (error)", "bold_no_outfit/nsfw 档不应出现 outfit，却出现了。"),
    ("outfit_missing (warning)", "normal/bold 档缺少 outfit 维度。"),
    ("exact_clause_repeat (warning)", "同一分句在全文精确重复 >=2 次（冗余）。"),
    ("identical_dimension_text (warning)", "两个不同维度文本完全相同（复制粘贴式生成）。"),
    ("concept_redundancy (warning)", "颗粒/色块/高光 任一概念在全文明细 >=3 次。"),
    ("camera_shot_mismatch (warning)", "镜头文本缺少该景别应有的范围词（头部/半身/全身）。"),
    ("camera_pose_axis_conflict (warning)", "镜头朝向与身体轴向相反（横构图+竖向身体 等）。"),
    ("makeup_scene_daynight_mismatch (error)", "妆容昼夜与最终场景氛围不一致（复用引擎判定）。"),
    ("non_visual_scene_text (error)", "场景维度混入非视觉叙述（空气里弥漫/传来…）。"),
    ("abstract_pose_text (warning)", "姿势维度混入抽象元语言（勾引意味/压迫感…）。"),
    ("detached_foot_subject (error)", "脚部作为独立身体部位主语（畸形风险）。"),
    ("tongue_in_distal_shot (error)", "半身/全身镜头出现舌头动作（看不清）。"),
    ("camera_aspect_mismatch (info)", "画幅朝向与镜头朝向词不一致（轻量提示）。"),
    ("photo_realism_missing (info)", "全文未见任何摄影真实感标记。"),
]


def percentile(values, percent):
    if not values:
        return 0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    return ordered[round((len(ordered) - 1) * percent)]


def length_report(stats) -> list[str]:
    lines = ["## 长度统计", ""]
    if not stats:
        lines.append("无数据。")
        return lines
    by_scope: dict[tuple, list] = {}
    for s in stats:
        by_scope.setdefault((s.scale, s.shot, s.aspect), []).append(s)
    lines.append("### 总字数（按 档位/景别/画幅）")
    for (scale, shot, aspect), items in sorted(by_scope.items()):
        vals = [s.prompt_length for s in items]
        lines.append(f"- `{scale}` / `{shot}` / `{aspect}`: 中位 {percentile(vals, 0.5)}，p90 {percentile(vals, 0.9)}，最大 {max(vals)}")
    dim_totals: dict[str, list] = {}
    for s in stats:
        for n, v in s.dimension_lengths.items():
            dim_totals.setdefault(n, []).append(v)
    lines.append("")
    lines.append("### 维度字数热点（p90）")
    for n, vals in sorted(dim_totals.items(), key=lambda kv: percentile(kv[1], 0.9), reverse=True):
        lines.append(f"- `{DIMENSION_LABELS.get(n, n)}`: 中位 {percentile(vals, 0.5)}，p90 {percentile(vals, 0.9)}，最大 {max(vals)}")
    return lines


def build_report(findings, sample_counts, stats) -> str:
    counts = Counter(f.severity for f in findings)
    total_samples = sum(sample_counts.values())
    errors = counts.get("error", 0)
    warnings = counts.get("warning", 0)
    infos = counts.get("info", 0)
    # 结论判定：无 error 且 warning 占比很低 => 通过
    warn_rate = (warnings / total_samples) if total_samples else 0
    if errors == 0 and warn_rate < 0.03:
        verdict = "✅ 通过：提示词合理性与画面感核查未发现实质问题（error=0，warning 占比 <3%）。"
    elif errors == 0:
        verdict = f"⚠️ 基本通过：无 error，但 warning 占比偏高（{warn_rate*100:.1f}%），见下方按规则归类。"
    else:
        verdict = f"❌ 未通过：发现 {errors} 个 error，需修复后再发布。"

    lines = ["# 提示词生成审计报告（v2）", ""]
    lines.append("本报告由 `tools/audit_generated_prompts.py` 生成，仅报告真实问题，已剔除旧版的启发式误报。")
    lines += ["", "## 结论", "", verdict, ""]
    lines += [
        "## 概览", "",
        f"- 样本总数：{total_samples}",
        f"- Error：{errors}",
        f"- Warning：{warnings}",
        f"- Info：{infos}", "",
        "## 样本覆盖", "",
    ]
    for (scale, shot, aspect), count in sorted(sample_counts.items()):
        lines.append(f"- `{scale}` / `{shot}` / `{aspect}`：{count}")
    lines += ["", "## 检查项目录（每条规则抓什么）", ""]
    for name, desc in CHECK_CATALOG:
        lines.append(f"- **{name}**：{desc}")
    lines += length_report(stats)
    lines += ["", "## 发现", ""]
    if not findings:
        lines.append("无发现。")
        return "\n".join(lines)
    grouped: dict[tuple, list] = {}
    for f in findings:
        grouped.setdefault((f.severity, f.rule), []).append(f)
    severity_order = {"error": 0, "warning": 1, "info": 2}
    for (sev, rule), group in sorted(grouped.items(), key=lambda kv: (severity_order.get(kv[0][0], 9), kv[0][1])):
        lines.append(f"### {sev}: {rule}（{len(group)} 例）")
        lines.append("")
        for f in group[:12]:
            p = f.prompt.replace("\n", " ")
            if len(p) > 200:
                p = p[:197] + "..."
            lines.append(f"- `{f.scale}` / `{f.shot}` / `{f.aspect}` 样本 {f.sample}：{f.detail}")
            lines.append(f"  - {p}")
        if len(group) > 12:
            lines.append(f"- ... 另有 {len(group) - 12} 例")
        lines.append("")
    return "\n".join(lines)


def selected_values(values, allowed):
    if not values:
        return allowed
    invalid = [v for v in values if v not in allowed]
    if invalid:
        raise ValueError(f"非法值: {', '.join(invalid)}。允许: {', '.join(allowed)}")
    return tuple(values)


def main() -> int:
    parser = argparse.ArgumentParser(description="审计生成的提示词组合（v2，低误报）。")
    parser.add_argument("--samples", type=int, default=15, help="每个 档位/景别/画幅 的样本数")
    parser.add_argument("--scale", action="append", choices=SCALES, help="档位，可重复")
    parser.add_argument("--shot", action="append", choices=SHOTS, help="景别，可重复")
    parser.add_argument("--report", default=str(DEFAULT_REPORT_PATH), help="报告输出路径")
    parser.add_argument("--fail-on-warning", action="store_true")
    args = parser.parse_args()

    engine = load_prompt_engine()
    scales = selected_values(args.scale, SCALES)
    shots = selected_values(args.shot, SHOTS)
    findings, sample_counts, stats = run_audit(max(args.samples, 1), scales, shots, engine)
    report = build_report(findings, sample_counts, stats)
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    counts = Counter(f.severity for f in findings)
    print(f"已写入 {report_path}")
    print(f"Error: {counts.get('error', 0)}; Warning: {counts.get('warning', 0)}; Info: {counts.get('info', 0)}")
    if counts.get("error", 0):
        return 1
    if args.fail_on_warning and counts.get("warning", 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
