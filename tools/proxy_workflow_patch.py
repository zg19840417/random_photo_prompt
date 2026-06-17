#!/usr/bin/env python3
from pathlib import Path

from prompt_resolution import base_resolution_for_workflow, mobile_resolution_for_custom_prompt


def ensure_unique_save_prefix(payload, token=""):
    if not isinstance(payload, dict):
        return 0
    prompt = payload.get("prompt")
    if not isinstance(prompt, dict):
        return 0
    suffix = str(token or "").replace("-", "")[:12]
    changed = 0
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict) or "filename_prefix" not in inputs:
            continue
        prefix = str(inputs.get("filename_prefix") or "").strip()
        if prefix != "ComfyUI":
            continue
        inputs["filename_prefix"] = f"{prefix}_{suffix}"
        changed += 1
    return changed


def workflow_link_consumers(prompt):
    consumers = {}
    if not isinstance(prompt, dict):
        return consumers
    for node_id, node in prompt.items():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict):
            continue
        for value in inputs.values():
            if isinstance(value, list) and value:
                consumers.setdefault(str(value[0]), set()).add(str(node_id))
    return consumers


def ultimate_sd_upscale_node_ids(prompt):
    if not isinstance(prompt, dict):
        return set()
    return {
        str(node_id)
        for node_id, node in prompt.items()
        if isinstance(node, dict) and str(node.get("class_type") or "") == "UltimateSDUpscale"
    }


def prune_non_final_image_outputs(prompt):
    return 0


def replace_save_nodes_with_websocket(payload, use_websocket_output=True):
    if not use_websocket_output or not isinstance(payload, dict):
        return 0, "", []
    prompt = payload.get("prompt")
    if not isinstance(prompt, dict):
        return 0, "", []
    prune_non_final_image_outputs(prompt)
    changed = 0
    output_prefix = ""
    websocket_ids = []
    for node_id, node in list(prompt.items()):
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        images = inputs.get("images")
        if not isinstance(images, list) or not images:
            continue
        class_type = str(node.get("class_type") or "")
        is_save_node = class_type == "SaveImage" or "filename_prefix" in inputs
        if not is_save_node:
            continue
        if not output_prefix:
            output_prefix = Path(str(inputs.get("filename_prefix") or "mobile").replace("\\", "/").strip("/")).name or "mobile"
        node["class_type"] = "SaveImageWebsocket"
        node["inputs"] = {"images": list(images)}
        websocket_ids.append(str(node_id))
        changed += 1
    return changed, output_prefix, websocket_ids


def unpatched_save_node_classes(payload):
    if not isinstance(payload, dict):
        return []
    prompt = payload.get("prompt")
    if not isinstance(prompt, dict):
        return []
    classes = []
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if class_type == "SaveImageWebsocket":
            continue
        if "filename_prefix" in inputs or class_type.startswith("Save") or "Save" in class_type:
            classes.append(class_type or "unknown")
    return classes


def looks_negative_prompt_node(node):
    inputs = node.get("inputs") if isinstance(node, dict) else None
    title = str((node.get("_meta") or {}).get("title") or "").lower() if isinstance(node, dict) else ""
    text = str((inputs or {}).get("text") or "").lower()
    return any(marker in title or marker in text for marker in ("negative", "负向", "反向", "bad quality", "worst quality", "watermark"))


def extract_positive_prompt_text(prompt):
    candidates = []
    for node in prompt.values() if isinstance(prompt, dict) else []:
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        text = inputs.get("text")
        class_type = str(node.get("class_type") or "")
        if not isinstance(text, str) or not text.strip():
            continue
        if "CLIPTextEncode" not in class_type and "TextEncode" not in class_type and "Conditioning" not in class_type:
            continue
        if looks_negative_prompt_node(node):
            continue
        candidates.append(text.strip())
    if not candidates:
        for node in prompt.values() if isinstance(prompt, dict) else []:
            inputs = node.get("inputs") if isinstance(node, dict) else None
            if isinstance(inputs, dict) and isinstance(inputs.get("cached_prompt"), str) and inputs["cached_prompt"].strip():
                candidates.append(inputs["cached_prompt"].strip())
    return max(candidates, key=len) if candidates else ""


def node_has_consumers(prompt, node_id):
    if not isinstance(prompt, dict):
        return False
    node_id = str(node_id)
    for consumer_id, node in prompt.items():
        if str(consumer_id) == node_id or not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for value in inputs.values():
            if isinstance(value, list) and value and str(value[0]) == node_id:
                return True
    return False


def random_photo_auto_resolution_enabled(prompt):
    if not isinstance(prompt, dict):
        return False
    for node_id, node in prompt.items():
        if not isinstance(node, dict) or str(node.get("class_type") or "") != "RandomPhotoPrompt":
            continue
        if not node_has_consumers(prompt, node_id):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        value = inputs.get("auto_resolution", True)
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}
        return bool(value)
    return False


def patch_web_prompt_resolution(payload):
    if not isinstance(payload, dict):
        return {}
    prompt = payload.get("prompt")
    if not isinstance(prompt, dict):
        return {}
    if not random_photo_auto_resolution_enabled(prompt):
        return {}
    positive_text = extract_positive_prompt_text(prompt)
    if not positive_text:
        return {}
    resolution = mobile_resolution_for_custom_prompt(positive_text)
    target_width = int(resolution.get("width") or 0)
    target_height = int(resolution.get("height") or 0)
    if target_width <= 0 or target_height <= 0:
        return {}
    base_width, base_height, output_scale = base_resolution_for_workflow(prompt, target_width, target_height)
    changed_width = 0
    changed_height = 0
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        class_type = str(node.get("class_type") or "")
        title = str((node.get("_meta") or {}).get("title") or "").lower()
        is_size_node = class_type in {"EmptyLatentImage", "CR SDXL Aspect Ratio"} or "aspect ratio" in title or "resolution" in title
        if not is_size_node and not any(key in inputs for key in ("width", "height", "W", "H", "image_width", "image_height", "latent_width", "latent_height")):
            continue
        for key in ("width", "W", "image_width", "latent_width", "empty_latent_width"):
            if key in inputs and isinstance(inputs.get(key), (int, float, str)):
                inputs[key] = int(base_width)
                changed_width += 1
        for key in ("height", "H", "image_height", "latent_height", "empty_latent_height"):
            if key in inputs and isinstance(inputs.get(key), (int, float, str)):
                inputs[key] = int(base_height)
                changed_height += 1
    return {
        "width": changed_width,
        "height": changed_height,
        "target_width": target_width,
        "target_height": target_height,
        "base_width": base_width,
        "base_height": base_height,
        "output_scale": output_scale,
    }


def model_value_is_zib(value):
    text = str(value or "").replace("\\", "/").strip().lower()
    name = Path(text).name
    return name.startswith("zib") and Path(name).suffix.lower() in {".safetensors", ".ckpt", ".gguf"}


def patch_web_zib_single_steps(payload):
    if not isinstance(payload, dict):
        return {}
    prompt = payload.get("prompt")
    if not isinstance(prompt, dict):
        return {}
    has_zib_model = False
    has_zib_native_sampler = False
    ksamplers = []
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if any(model_value_is_zib(value) for value in inputs.values()):
            has_zib_model = True
        if str(node.get("class_type") or "") == "KSamplerAdvanced":
            model_input = inputs.get("model")
            if isinstance(model_input, list) and model_input and str(model_input[0]) == "483":
                has_zib_native_sampler = True
        if str(node.get("class_type") or "") == "KSampler" and isinstance(inputs.get("steps"), (int, float, str)):
            ksamplers.append(inputs)
    if has_zib_native_sampler:
        return {"zib_model": has_zib_model, "zib_native_sampler": True, "ksamplers": len(ksamplers), "steps_changed": 0}
    if not has_zib_model or len(ksamplers) != 1:
        return {"zib_model": has_zib_model, "zib_native_sampler": False, "ksamplers": len(ksamplers), "steps_changed": 0}
    old_steps = ksamplers[0].get("steps")
    ksamplers[0]["steps"] = 35
    return {"zib_model": True, "ksamplers": 1, "steps_changed": int(old_steps != 35), "old_steps": old_steps, "new_steps": 35}


def patch_web_zimage_weight_dtype(payload):
    if not isinstance(payload, dict):
        return {"weight_dtype_changed": 0}
    prompt = payload.get("prompt")
    if not isinstance(prompt, dict):
        return {"weight_dtype_changed": 0}
    changed = 0
    old_values = []
    for node in prompt.values():
        if not isinstance(node, dict) or str(node.get("class_type") or "") != "UNETLoader":
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        raw_unet_name = str(inputs.get("unet_name") or "")
        unet_name = raw_unet_name.replace("\\", "/").lower()
        model_name = Path(unet_name).name.lower()
        if "z_image/" not in unet_name and not model_name.startswith(("zib", "zit")):
            continue
        if inputs.get("weight_dtype") in {"fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2", "bf16"}:
            old_values.append(str(inputs.get("weight_dtype")))
            inputs["weight_dtype"] = "default"
            changed += 1
    return {"weight_dtype_changed": changed, "old_values": old_values}


def patch_web_disable_model_purge(payload):
    if not isinstance(payload, dict):
        return {"purge_models_disabled": 0}
    prompt = payload.get("prompt")
    if not isinstance(prompt, dict):
        return {"purge_models_disabled": 0}
    disabled = 0
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        if str(node.get("class_type") or "") != "LayerUtility: PurgeVRAM V2":
            continue
        inputs = node.get("inputs")
        if isinstance(inputs, dict) and inputs.get("purge_models") is True:
            inputs["purge_models"] = False
            disabled += 1
    return {"purge_models_disabled": disabled}
