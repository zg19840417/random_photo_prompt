from __future__ import annotations

import argparse
from collections import Counter
import difflib
import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPT_DATA_PATH = ROOT / "prompt_data.py"
DEFAULT_REPORT_PATH = ROOT / "docs" / "reports" / "prompt_pool_audit.md"
DEFAULT_DISTRIBUTION_SAMPLES = 20
ACTIVE_SCALES = ("normal", "bold", "bold_no_outfit", "nsfw")
ACTIVE_SHOTS = ("头部", "半身", "全身")

ACTIVE_POOLS = (
    "CAMERA_OPTIONS",
    "CHARACTER_IDENTITY_BY_SHOT",
    "MAKEUP_OPTIONS",
    "OUTFIT_OPTIONS",
    "POSE_EXPRESSION_OPTIONS",
    "SCENE_LIGHT_OPTIONS",
)

ALLOWED_PUBLIC_NAMES = set(ACTIVE_POOLS) | {
    "QUALITY_SUFFIX",
    "NEGATIVE_PROMPT",
    "PROMPT_DATA_SOURCE",
    "SCALES",
    "SHOTS",
    "SHOT_LABELS",
    "_POSE_NORMALIZE_REPLACEMENTS",
}


@dataclass
class Issue:
    severity: str
    pool: str
    index: int
    rule: str
    markers: list[str]
    text: str


def load_prompt_data():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location("audit_prompt_data", PROMPT_DATA_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {PROMPT_DATA_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def iter_entries(value, path=""):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from iter_entries(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value, 1):
            yield from iter_entries(item, f"{path}[{index}]")


def normalized(text: str) -> str:
    return re.sub(r"[\s，。；;、：:\-—.]+", "", text)


def audit_pools(module, max_chars: int) -> list[Issue]:
    issues: list[Issue] = []
    for pool in ACTIVE_POOLS:
        value = getattr(module, pool, None)
        if value is None:
            issues.append(Issue("warning", pool, 0, "active pool missing", [], ""))
            continue
        seen: dict[str, str] = {}
        flat = list(iter_entries(value))
        for index, (path, text) in enumerate(flat, 1):
            if len(text) > max_chars:
                issues.append(Issue("info", pool, index, f"entry longer than {max_chars} chars", [str(len(text))], text))
            key = normalized(text)
            if key in seen:
                issues.append(Issue("warning", pool, index, f"duplicate of {seen[key]}", [], text))
            else:
                seen[key] = path
        values = [text for _path, text in flat]
        for left_index, left in enumerate(values, 1):
            left_key = normalized(left)
            for right_index in range(left_index + 1, len(values) + 1):
                right_key = normalized(values[right_index - 1])
                if left_key and right_key and left_key != right_key:
                    ratio = difflib.SequenceMatcher(None, left_key, right_key).ratio()
                    if ratio >= 0.94:
                        issues.append(Issue("info", pool, right_index, f"near-duplicate of entry {left_index} ({ratio:.2f})", [], values[right_index - 1]))
                        break
    for name, value in vars(module).items():
        if name.isupper() and isinstance(value, (dict, list, str, tuple)) and name not in ALLOWED_PUBLIC_NAMES:
            issues.append(Issue("warning", name, 0, "unknown public prompt-data name; remove or document it", [], name))
    return issues


def generated_distribution_report(sample_count: int) -> list[str]:
    if sample_count <= 0:
        return ["## Generated Prompt Distribution", "", "Distribution sampling disabled.", ""]
    spec = importlib.util.spec_from_file_location("audit_prompt_engine", ROOT / "prompt_engine.py")
    if spec is None or spec.loader is None:
        return ["## Generated Prompt Distribution", "", "Could not load prompt_engine.py", ""]
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    lines = ["## Generated Prompt Distribution", "", f"Samples per scale/shot: {sample_count}", ""]
    for scale in ACTIVE_SCALES:
        lines.append(f"### {scale}")
        for shot in ACTIVE_SHOTS:
            for aspect in ("portrait", "landscape"):
                items = engine.generate_prompt_items(sample_count, {"scale": scale, "shot": shot, "aspect": aspect}, seed_text=f"audit-{scale}-{shot}-{aspect}")
                lengths = [len(item["compact_prompt"]) for item in items]
                part_counts = Counter(tuple(item["dimension_parts"].keys()) for item in items)
                lines.append(f"- `{shot}` / `{aspect}`: {len(items)} samples, min/avg/max chars {min(lengths)}/{sum(lengths)//len(lengths)}/{max(lengths)}, dimension shapes {len(part_counts)}")
        lines.append("")
    return lines


def build_report(module, issues: list[Issue], sample_count: int) -> str:
    counts = Counter(issue.severity for issue in issues)
    lines = [
        "# Prompt Pool Audit Report",
        "",
        "This report is generated by `tools/audit_prompt_pools.py`.",
        "",
        "## Summary",
        "",
        f"- Active pools: {len(ACTIVE_POOLS)}",
        f"- Data source: `{getattr(module, 'PROMPT_DATA_SOURCE', 'prompt_data.py')}`",
        f"- Warnings: {counts.get('warning', 0)}",
        f"- Info: {counts.get('info', 0)}",
        "",
        "## Active Pool Sizes",
        "",
    ]
    for pool in ACTIVE_POOLS:
        lines.append(f"- `{pool}`: {sum(1 for _ in iter_entries(getattr(module, pool, None)))}")
    lines.append("")
    lines.extend(generated_distribution_report(sample_count))
    lines.extend(["## Findings", ""])
    if not issues:
        lines.append("No findings.")
    by_pool: dict[str, list[Issue]] = {}
    for issue in issues:
        by_pool.setdefault(issue.pool, []).append(issue)
    for pool in sorted(by_pool):
        lines.append(f"### {pool}")
        lines.append("")
        for issue in by_pool[pool][:50]:
            markers = f" markers={','.join(issue.markers)}" if issue.markers else ""
            sample = issue.text.replace("\n", " ")
            if len(sample) > 180:
                sample = sample[:177] + "..."
            lines.append(f"- `{issue.severity}` entry {issue.index}: {issue.rule}{markers}")
            if sample:
                lines.append(f"  - {sample}")
        lines.append("")
    return "\n".join(lines)


def audit(max_chars: int, distribution_samples: int) -> tuple[str, list[Issue]]:
    module = load_prompt_data()
    issues = audit_pools(module, max_chars)
    return build_report(module, issues, distribution_samples), issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit current prompt pools and generated scale distribution.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT_PATH), help="Markdown report output path.")
    parser.add_argument("--max-chars", type=int, default=220, help="Warn when one pool entry exceeds this length.")
    parser.add_argument("--distribution-samples", type=int, default=DEFAULT_DISTRIBUTION_SAMPLES)
    parser.add_argument("--fail-on-warning", action="store_true")
    args = parser.parse_args()

    report, issues = audit(args.max_chars, args.distribution_samples)
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    warnings = sum(1 for issue in issues if issue.severity == "warning")
    print(f"Wrote {report_path}")
    print(f"Warnings: {warnings}; total findings: {len(issues)}")
    return 1 if args.fail_on_warning and warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
