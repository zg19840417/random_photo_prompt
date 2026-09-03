import re


MOBILE_MAX_IMAGE_EDGE = 1536
MOBILE_RESOLUTION_MULTIPLE = 64
MOBILE_RESOLUTION_DOWNSHIFT = 1.0
MOBILE_STANDING_FULL_BODY_RESOLUTION = {
    "aspect": "portrait",
    "width": 768,
    "height": 1536,
    "framing": "窄长站姿全身构图",
}
MOBILE_CUSTOM_RESOLUTION_PRESETS = {
    "768x1536": {"aspect": "portrait", "width": 768, "height": 1536, "framing": ""},
    "1024x1536": {"aspect": "portrait", "width": 1024, "height": 1536, "framing": ""},
    "1536x1536": {"aspect": "square", "width": 1536, "height": 1536, "framing": ""},
    "1536x1024": {"aspect": "landscape", "width": 1536, "height": 1024, "framing": ""},
}


def round_to_multiple(value, multiple=MOBILE_RESOLUTION_MULTIPLE):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0
    multiple = int(multiple or 1)
    return max(multiple, int(round(value / multiple) * multiple))


def clamp_mobile_resolution(resolution):
    clamped = dict(resolution)
    width = int(clamped.get("width") or 0)
    height = int(clamped.get("height") or 0)
    if width > 0:
        width = round_to_multiple(width * MOBILE_RESOLUTION_DOWNSHIFT)
    if height > 0:
        height = round_to_multiple(height * MOBILE_RESOLUTION_DOWNSHIFT)
    max_edge = max(width, height)
    if max_edge > MOBILE_MAX_IMAGE_EDGE:
        scale = MOBILE_MAX_IMAGE_EDGE / max_edge
        width = round_to_multiple(width * scale) if width > 0 else 0
        height = round_to_multiple(height * scale) if height > 0 else 0
    if width > 0:
        clamped["width"] = width
    if height > 0:
        clamped["height"] = height
    return clamped


def mobile_resolution_for_custom_prompt(prompt_text):
    text = str(prompt_text or "")
    if any(marker in text for marker in ("横向", "横屏", "宽画幅", "横躺", "平躺", "大字型", "四肢展开")):
        return clamp_mobile_resolution({"aspect": "landscape", "width": 1536, "height": 1024, "framing": ""})
    if any(marker in text for marker in ("站立", "站姿", "直立", "站在", "迈步", "行走", "走姿", "倚靠", "靠墙")):
        return clamp_mobile_resolution(MOBILE_STANDING_FULL_BODY_RESOLUTION)
    if any(marker in text for marker in ("全身", "从头到脚", "脚部", "脚掌", "脚尖", "站立", "长腿完整")):
        return clamp_mobile_resolution({"aspect": "portrait", "width": 1024, "height": 1536, "framing": ""})
    if any(marker in text for marker in ("半身", "大腿以上", "大腿以上", "小腿", "膝盖")):
        return clamp_mobile_resolution({"aspect": "portrait", "width": 1024, "height": 1536, "framing": ""})
    if any(marker in text for marker in ("半身", "大腿以上", "腰部", "腰线")):
        return clamp_mobile_resolution({"aspect": "portrait", "width": 1024, "height": 1536, "framing": ""})
    if any(marker in text for marker in ("头部", "肩膀及以上", "肩部以上", "脸部特写", "面部特写")):
        return clamp_mobile_resolution({"aspect": "portrait", "width": 1024, "height": 1536, "framing": ""})
    if any(marker in text for marker in ("半身", "肩部以上", "肩部以上", "胸部")):
        return clamp_mobile_resolution({"aspect": "portrait", "width": 1024, "height": 1536, "framing": ""})
    return clamp_mobile_resolution({"aspect": "portrait", "width": 1024, "height": 1536, "framing": ""})


def mobile_custom_resolution(prompt_text, preset=""):
    key = str(preset or "").strip()
    if key in MOBILE_CUSTOM_RESOLUTION_PRESETS:
        return clamp_mobile_resolution(MOBILE_CUSTOM_RESOLUTION_PRESETS[key])
    match = re.fullmatch(r"\s*(\d{2,5})\s*[xX×]\s*(\d{2,5})\s*", key)
    if match:
        width = int(match.group(1))
        height = int(match.group(2))
        if width > 0 and height > 0:
            return clamp_mobile_resolution({
                "aspect": "landscape" if width > height else "portrait",
                "width": width,
                "height": height,
                "framing": "",
            })
    return mobile_resolution_for_custom_prompt(prompt_text)


def linked_float_value(workflow, value, default=1.0):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    if isinstance(value, list) and value:
        node = workflow.get(str(value[0]))
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if isinstance(inputs, dict) and "value" in inputs:
            return linked_float_value(workflow, inputs.get("value"), default)
    return default


def workflow_output_scale(workflow, include_ultimate=True):
    scale = 1.0
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if class_type == "LatentUpscaleBy" and "scale_by" in inputs:
            scale *= linked_float_value(workflow, inputs.get("scale_by"), 1.0)
        if include_ultimate and class_type == "UltimateSDUpscale" and "upscale_by" in inputs:
            scale *= linked_float_value(workflow, inputs.get("upscale_by"), 1.0)
    return scale if scale > 0 else 1.0


def base_resolution_for_workflow(workflow, width, height):
    scale = workflow_output_scale(workflow)
    return round_to_multiple(width / scale), round_to_multiple(height / scale), scale


def workflow_latent_scale(workflow):
    scale = 1.0
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if class_type == "LatentUpscaleBy" and "scale_by" in inputs:
            scale *= linked_float_value(workflow, inputs.get("scale_by"), 1.0)
    return scale if scale > 0 else 1.0


def base_resolution_for_exact_output(workflow, width, height):
    latent_scale = workflow_latent_scale(workflow)
    target_width = max(1, int(width or 1))
    target_height = max(1, int(height or 1))
    ideal_width = max(MOBILE_RESOLUTION_MULTIPLE, target_width / latent_scale)
    ideal_height = max(MOBILE_RESOLUTION_MULTIPLE, target_height / latent_scale)
    target_ratio = target_width / target_height
    center_width = round_to_multiple(ideal_width)
    center_height = round_to_multiple(ideal_height)
    base_width = center_width
    base_height = center_height
    best_score = None
    for width_step in range(-6, 7):
        candidate_width = max(MOBILE_RESOLUTION_MULTIPLE, center_width + width_step * MOBILE_RESOLUTION_MULTIPLE)
        for height_step in range(-6, 7):
            candidate_height = max(MOBILE_RESOLUTION_MULTIPLE, center_height + height_step * MOBILE_RESOLUTION_MULTIPLE)
            ratio_error = abs((candidate_width / candidate_height) - target_ratio)
            size_error = abs(candidate_width - ideal_width) / max(1, ideal_width) + abs(candidate_height - ideal_height) / max(1, ideal_height)
            score = ratio_error * 10 + size_error
            if best_score is None or score < best_score:
                best_score = score
                base_width = candidate_width
                base_height = candidate_height
    latent_width = max(1, base_width * latent_scale)
    latent_height = max(1, base_height * latent_scale)
    ultimate_scale = min(target_width / latent_width, target_height / latent_height)
    return base_width, base_height, latent_scale * ultimate_scale, ultimate_scale
