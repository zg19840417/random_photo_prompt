from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path

from prompt_excel_io import write_workbook


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "prompt_pools.xlsx"
PROMPT_DATA_PATH = ROOT / "prompt_data.py"

CONSTANT_NAMES = ("QUALITY_SUFFIX", "NEGATIVE_PROMPT")
POOL_NAMES = (
    "CAMERA_OPTIONS",
    "CHARACTER_IDENTITY_BY_SHOT",
    "MAKEUP_OPTIONS",
    "OUTFIT_OPTIONS",
    "POSE_EXPRESSION_OPTIONS",
    "SCENE_LIGHT_OPTIONS",
    "landscape_camera_options",
    "landscape_pose_expression_options",
)
SCENE_LIGHT_GROUPS = {"室内", "室外", "野外"}
PROTECTED_SCALE_SHOT_ENTRIES = {
    ("POSE_EXPRESSION_OPTIONS", "nsfw"),
    ("landscape_pose_expression_options", "nsfw"),
}


def load_prompt_data():
    os.environ["RPP_IGNORE_GENERATED_PROMPT_DATA"] = "1"
    spec = importlib.util.spec_from_file_location("prompt_data_for_excel_export", PROMPT_DATA_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {PROMPT_DATA_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def iter_options(pool_name: str, value):
    if isinstance(value, list):
        for order, text in enumerate(value, 1):
            yield [pool_name, "", "", "portrait", order, 1, text, ""]
    elif isinstance(value, dict):
        if pool_name == "MAKEUP_OPTIONS":
            for scale, options in value.items():
                if not isinstance(options, list):
                    continue
                for order, text in enumerate(options, 1):
                    yield [pool_name, scale, "", "portrait", order, 1, text, ""]
            return
        for key, item in value.items():
            if isinstance(item, list):
                aspect = "landscape" if pool_name.startswith("landscape_") else "portrait"
                for order, text in enumerate(item, 1):
                    yield [pool_name, "", key, aspect, order, 1, text, ""]
            elif isinstance(item, dict):
                for shot, options in item.items():
                    if (pool_name, key) in PROTECTED_SCALE_SHOT_ENTRIES:
                        continue
                    aspect = "landscape" if pool_name.startswith("landscape_") else "portrait"
                    if isinstance(options, list):
                        for order, text in enumerate(options, 1):
                            yield [pool_name, key, shot, aspect, order, 1, text, ""]
                    elif pool_name == "SCENE_LIGHT_OPTIONS" and isinstance(options, dict):
                        order = 1
                        for group, group_options in options.items():
                            if group not in SCENE_LIGHT_GROUPS or not isinstance(group_options, list):
                                continue
                            for text in group_options:
                                yield [pool_name, key, shot, aspect, order, 1, text, f"场景包:{group}"]
                                order += 1


def build_sheets(module) -> dict[str, list[list[object]]]:
    constants = [["name", "text"]]
    for name in CONSTANT_NAMES:
        constants.append([name, getattr(module, name, "")])

    options = [["pool", "scale", "shot", "aspect", "order", "enabled", "text", "notes"]]
    for pool_name in POOL_NAMES:
        value = getattr(module, pool_name, None)
        if value is None:
            continue
        options.extend(iter_options(pool_name, value))
    return {"constants": constants, "options": options}


def main() -> int:
    parser = argparse.ArgumentParser(description="Export currently effective prompt pools to an editable Excel workbook.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output .xlsx path.")
    args = parser.parse_args()

    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    module = load_prompt_data()
    write_workbook(output, build_sheets(module))
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
