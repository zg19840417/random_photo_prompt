from __future__ import annotations

import copy
import os
from pathlib import Path

import folder_paths

from rpp_globals import (
    BLOCK_REMOTE_ASSET_SAVE,
    K2_SFW_RULE_KEY,
    LORA_MODEL_EXTENSIONS,
    MOBILE_DEFAULT_WORKFLOW_KEY,
    MOBILE_MAX_LORAS,
    MOBILE_VIDEO_OUTPUT_SUBFOLDER,
    MOBILE_WORKFLOWS,
    MOBILE_WORKFLOW_TEMPLATES,
    MOBILE_WORKFLOW_TEMPLATE_ERRORS,
    NODE_DIR,
    REMOTE_COMFYUI_URL,
    REMOTE_MAC_IMAGE_UPLOAD_URL,
    REMOTE_MAC_VIDEO_UPLOAD_URL,
    REMOTE_WEBSOCKET_OUTPUT,
    ZIB_DISTILLED_CFG,
    ZIB_DISTILLED_STEPS,
    ZIT_SINGLE_TEN_STEP_MODEL,
    ZIMAGE_LORA_SUBDIR,
)
from rpp_utils import (
    _looks_negative_text,
    _node_meta,
    _node_title,
)
from rpp_prompts import _apply_krea2_portrait_orientation_guard, _prompt_text
from workflow_cleanup_policy import ensure_model_cleanup, remove_mobile_auxiliary_outputs
from prompt_resolution import (
    base_resolution_for_exact_output,
    base_resolution_for_workflow,
    linked_float_value,
    workflow_output_scale,
)
from prompt_postprocess import clean_prompt_text
from video_resolution import image_to_video_resolution

__all__ = sorted(["__all__", "_append_mobile_lora_nodes", "_available_loras", "_block_remote_asset_save_on_prompt", "_bypass_lora_nodes", "_bypass_mobile_upscale_outputs", "_force_websocket_only_image_outputs", "_insert_exact_output_scale", "_is_krea2_workflow", "_is_mobile_lora_node", "_is_zib_distilled_model_name", "_is_zit_turbo_model_name", "_krea2_unet_value", "_linked_float_value", "_load_mobile_workflow", "_mobile_base_resolution_for_workflow", "_mobile_image_workflows", "_mobile_lora_nodes", "_mobile_workflow_config", "_mobile_workflow_output_scale", "_mobile_workflow_statuses", "_next_workflow_node_id", "_node_depends_on_any", "_patch_existing_lora_nodes", "_patch_krea2_negative_text_node", "_patch_mobile_video_workflow", "_patch_mobile_workflow", "_patch_remote_websocket_outputs", "_patch_zib_single_sampler_settings", "_patch_zitb_double_sampler_settings", "_prune_non_final_image_outputs", "_remove_mobile_auxiliary_outputs", "_remove_unreferenced_mobile_prompt_nodes", "_remove_unreferenced_workflow_nodes", "_reroute_lora_model_consumers", "_resolve_lora_name", "_resolve_lora_strength", "_resolve_mobile_loras", "_route_zib_single_outputs", "_set_lora_inputs", "_set_mobile_ultimate_upscale_by", "_ultimate_sd_upscale_node_ids", "_unpatched_remote_save_node_classes", "_workflow_has_mobile_upscale", "_workflow_link_consumers", "_workflow_model_consumers", "_workflow_status_item", "_zimage_unet_value"])

def _patch_krea2_negative_text_node(workflow, negative_prompt):
    if not isinstance(workflow, dict):
        return 0
    clip_link = None
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if str(node.get("class_type") or "") != "CLIPTextEncode":
            continue
        inputs = node.get("inputs")
        if isinstance(inputs, dict) and isinstance(inputs.get("clip"), list):
            clip_link = list(inputs["clip"])
            break
    if not clip_link:
        return 0
    changed = 0
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if str(node.get("class_type") or "") != "ConditioningZeroOut":
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict) or "conditioning" not in inputs:
            continue
        node["class_type"] = "CLIPTextEncode"
        node["_meta"] = {"title": "Negative Prompt"}
        node["inputs"] = {"clip": clip_link, "text": negative_prompt}
        changed += 1
    return changed


def _mobile_workflow_config(value=None):
    key = str(value or MOBILE_DEFAULT_WORKFLOW_KEY).strip()
    return key, MOBILE_WORKFLOWS.get(key) or MOBILE_WORKFLOWS[MOBILE_DEFAULT_WORKFLOW_KEY]


def _mobile_image_workflows():
    return {
        key: item
        for key, item in MOBILE_WORKFLOWS.items()
        if item.get("type", "image") == "image"
    }


def _zimage_unet_value(model_name):
    model_name = Path(str(model_name or "").replace("\\", "/")).name
    if not model_name:
        return ""
    if REMOTE_COMFYUI_URL:
        return f"z_image\\{model_name}"
    return os.path.join("z_image", model_name)


def _krea2_unet_value(model_name):
    model_name = Path(str(model_name or "").replace("\\", "/")).name
    if not model_name:
        return ""
    if REMOTE_COMFYUI_URL:
        return f"Krea2\\{model_name}"
    return os.path.join("Krea2", model_name)


def _is_krea2_workflow(workflow_key):
    return str(workflow_key or "") in {"redcraft_krea2", "krea2_cc"}


def _is_mobile_lora_node(node):
    if not isinstance(node, dict):
        return False
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        return False
    class_type = str(node.get("class_type") or "").lower()
    title = _node_title(node)
    return "lora" in class_type or "lora" in title or any("lora" in str(key).lower() for key in inputs)


def _mobile_lora_nodes(workflow, include_preserved=False):
    nodes = []
    for node_id, node in workflow.items():
        if not _is_mobile_lora_node(node):
            continue
        if not include_preserved and _node_meta(node).get("preserve_mobile_lora") is True:
            continue
        inputs = node.get("inputs")
        if isinstance(inputs.get("model"), list) and len(inputs["model"]) >= 2:
            nodes.append((str(node_id), node))
    return nodes


def _resolve_mobile_loras(value, available_loras=None):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("LoRA 参数格式无效。")
    if len(value) > MOBILE_MAX_LORAS:
        raise ValueError(f"一次最多添加 {MOBILE_MAX_LORAS} 个 LoRA。")
    resolved = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("LoRA 参数格式无效。")
        lora_name = _resolve_lora_name(item.get("name"), available_loras)
        if not lora_name:
            continue
        resolved.append({"name": lora_name, "strength": _resolve_lora_strength(item.get("strength"))})
    return resolved


def _set_lora_inputs(node, lora_name, strength):
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("工作流模板里的 LoRA 节点缺少输入配置。")
    name_patched = False
    for key in list(inputs):
        lower_key = str(key).lower()
        key_text = str(key)
        if lower_key in {"lora_name", "lora", "lora_name_1"} or ("lora" in lower_key and "name" in lower_key) or key_text in {"LoRA名称", "Lora名称", "lora名称", "名称"}:
            inputs[key] = lora_name
            name_patched = True
    if not name_patched:
        raise ValueError("工作流模板里的 LoRA 节点缺少 LoRA 名称输入。")
    for key in list(inputs):
        lower_key = str(key).lower()
        key_text = str(key)
        if lower_key in {"strength_model", "strength_clip", "model_strength", "clip_strength", "strength"} or (
            "strength" in lower_key and isinstance(inputs.get(key), (int, float, str))
        ) or (
            key_text in {"模型强度", "强度", "CLIP强度", "clip强度"} and isinstance(inputs.get(key), (int, float, str))
        ):
            inputs[key] = strength


def _next_workflow_node_id(workflow):
    numeric_ids = [int(node_id) for node_id in workflow if str(node_id).isdigit()]
    return str(max(numeric_ids, default=0) + 1)


def _reroute_lora_model_consumers(workflow, source_node_id, target_node_id, excluded_node_ids=()):
    excluded = {str(node_id) for node_id in excluded_node_ids}
    patched = 0
    for node_id, node in workflow.items():
        if str(node_id) in excluded or not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        model_input = inputs.get("model") if isinstance(inputs, dict) else None
        if isinstance(model_input, list) and model_input and str(model_input[0]) == str(source_node_id):
            inputs["model"] = [str(target_node_id), *model_input[1:]]
            patched += 1
    return patched


def _append_mobile_lora_nodes(workflow, source_node_id, template_node, loras):
    added_node_ids = []
    previous_node_id = str(source_node_id)
    for lora in loras:
        node_id = _next_workflow_node_id(workflow)
        node = copy.deepcopy(template_node)
        inputs = node["inputs"]
        inputs["model"] = [previous_node_id, 0]
        _set_lora_inputs(node, lora["name"], lora["strength"])
        workflow[node_id] = node
        added_node_ids.append(node_id)
        previous_node_id = node_id
    _reroute_lora_model_consumers(workflow, source_node_id, previous_node_id, added_node_ids)
    return len(added_node_ids)


def _patch_existing_lora_nodes(workflow, loras, workflow_key=""):
    if workflow_key == "krea2_cc":
        if not loras:
            return 0
        lora_nodes = _mobile_lora_nodes(workflow, include_preserved=True)
        upstream_lora_ids = {
            str(node.get("inputs", {}).get("model", [""])[0])
            for _, node in lora_nodes
            if isinstance(node.get("inputs", {}).get("model"), list)
        }
        terminal_nodes = [(node_id, node) for node_id, node in lora_nodes if node_id not in upstream_lora_ids]
        if len(terminal_nodes) != 1:
            raise ValueError("Krea2+CC 工作流里没有找到唯一的 LoRA 链末端。")
        terminal_node_id, terminal_node = terminal_nodes[0]
        return _append_mobile_lora_nodes(workflow, terminal_node_id, terminal_node, loras)

    if not loras:
        return _bypass_lora_nodes(workflow)
    lora_nodes = _mobile_lora_nodes(workflow)
    if len(lora_nodes) != 1:
        raise ValueError("工作流模板里需要保留一个可复用的 LoRA 节点。")
    node_id, node = lora_nodes[0]
    template_node = copy.deepcopy(node)
    _set_lora_inputs(node, loras[0]["name"], loras[0]["strength"])
    return 1 + _append_mobile_lora_nodes(workflow, node_id, template_node, loras[1:])


def _bypass_lora_nodes(workflow):
    bypasses = {}
    for node_id, node in list(workflow.items()):
        if not _is_mobile_lora_node(node) or _node_meta(node).get("preserve_mobile_lora") is True:
            continue
        inputs = node.get("inputs")
        model_input = inputs.get("model")
        if isinstance(model_input, list) and len(model_input) >= 2:
            bypasses[str(node_id)] = list(model_input)
            workflow.pop(str(node_id), None)
    if not bypasses:
        return 0
    for node in workflow.values():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict):
            continue
        for key, value in list(inputs.items()):
            if isinstance(value, list) and value and str(value[0]) in bypasses:
                inputs[key] = list(bypasses[str(value[0])])
    return len(bypasses)


def _is_zit_turbo_model_name(value):
    name = Path(str(value or "").replace("\\", "/")).name.lower()
    return name.startswith(("zit-", "zit_", "z_image"))


def _is_zib_distilled_model_name(value):
    name = Path(str(value or "").replace("\\", "/")).name.lower()
    return name.startswith(("zib-", "zib_")) and ("distill" in name or "10step" in name)


def _workflow_model_consumers(workflow):
    consumers = {}
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for value in inputs.values():
            if isinstance(value, list) and value:
                consumers.setdefault(str(value[0]), set()).add(str(node_id))
    return consumers


def _load_mobile_workflow(workflow_key=None):
    key, config = _mobile_workflow_config(workflow_key)
    template = MOBILE_WORKFLOW_TEMPLATES.get(key)
    if template is None:
        detail = MOBILE_WORKFLOW_TEMPLATE_ERRORS.get(key) or "启动时未载入工作流模板。"
        raise ValueError(f"{config['path'].name} 启动加载失败：{detail}")
    return copy.deepcopy(template)


def _workflow_status_item(key, config):
    path = config["path"]
    template = MOBILE_WORKFLOW_TEMPLATES.get(key)
    cached_error = MOBILE_WORKFLOW_TEMPLATE_ERRORS.get(key, "")
    status = {
        "key": key,
        "label": config["label"],
        "type": config.get("type", "image"),
        "template_name": path.name,
        "path": str(path),
        "template_ready": template is not None,
        "format": "missing",
        "message": "",
        "guidance": "",
    }
    if template is None:
        status["format"] = "startup_load_failed"
        status["message"] = f"{path.name} 启动加载失败：{cached_error or '未知错误'}"
        status["guidance"] = "修复工作流文件后重启 ComfyUI，使模板重新载入内存。"
        return status
    status["format"] = "api"
    status["message"] = "API 工作流已载入内存。"
    return status


def _mobile_workflow_statuses():
    return {key: _workflow_status_item(key, config) for key, config in MOBILE_WORKFLOWS.items()}


def _linked_float_value(workflow, value, default=1.0):
    return linked_float_value(workflow, value, default)


def _mobile_workflow_output_scale(workflow, include_ultimate=True):
    return workflow_output_scale(workflow, include_ultimate)


def _workflow_has_mobile_upscale(workflow):
    return any(
        isinstance(node, dict) and str(node.get("class_type") or "") == "UltimateSDUpscale"
        for node in workflow.values()
    )


def _mobile_base_resolution_for_workflow(template, width, height):
    return base_resolution_for_workflow(template, width, height)


def _set_mobile_ultimate_upscale_by(workflow, scale):
    if not isinstance(workflow, dict):
        return 0
    changed = 0
    for node in workflow.values():
        if not isinstance(node, dict) or str(node.get("class_type") or "") != "UltimateSDUpscale":
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        upscale_by = inputs.get("upscale_by")
        if isinstance(upscale_by, list) and upscale_by:
            linked_node = workflow.get(str(upscale_by[0]))
            linked_inputs = linked_node.get("inputs") if isinstance(linked_node, dict) else None
            if isinstance(linked_inputs, dict) and "value" in linked_inputs:
                linked_inputs["value"] = float(scale)
                changed += 1
                continue
        inputs["upscale_by"] = float(scale)
        changed += 1
    return changed


def _remove_mobile_auxiliary_outputs(workflow):
    return remove_mobile_auxiliary_outputs(workflow)


def _remove_unreferenced_mobile_prompt_nodes(workflow):
    referenced = set()
    for node in workflow.values():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict):
            continue
        for value in inputs.values():
            if isinstance(value, list) and value:
                referenced.add(str(value[0]))
    removed = 0
    for node_id, node in list(workflow.items()):
        if str(node_id) in referenced:
            continue
        if isinstance(node, dict) and str(node.get("class_type") or "") == "RandomPhotoPrompt":
            workflow.pop(str(node_id), None)
            removed += 1
    return removed


def _remove_unreferenced_workflow_nodes(workflow):
    referenced = set()
    for node in workflow.values():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict):
            continue
        for value in inputs.values():
            if isinstance(value, list) and value:
                referenced.add(str(value[0]))
    removed = 0
    changed = True
    while changed:
        changed = False
        for node_id, node in list(workflow.items()):
            if str(node_id) in referenced:
                continue
            if not isinstance(node, dict):
                continue
            class_type = str(node.get("class_type") or "")
            inputs = node.get("inputs") if isinstance(node, dict) else None
            is_output = class_type in {"SaveImage", "PreviewImage", "SaveImageWebsocket"} or "filename_prefix" in (inputs or {})
            if is_output:
                continue
            workflow.pop(str(node_id), None)
            removed += 1
            changed = True
            referenced = set()
            for other in workflow.values():
                other_inputs = other.get("inputs") if isinstance(other, dict) else None
                if not isinstance(other_inputs, dict):
                    continue
                for value in other_inputs.values():
                    if isinstance(value, list) and value:
                        referenced.add(str(value[0]))
            break
    return removed


def _bypass_mobile_upscale_outputs(workflow):
    if not isinstance(workflow, dict):
        return 0
    upscale_image_inputs = {}
    for node_id, node in workflow.items():
        if not isinstance(node, dict) or str(node.get("class_type") or "") != "UltimateSDUpscale":
            continue
        image_input = (node.get("inputs") or {}).get("image")
        if isinstance(image_input, list) and image_input:
            upscale_image_inputs[str(node_id)] = [str(image_input[0]), int(image_input[1] if len(image_input) > 1 else 0)]
    if not upscale_image_inputs:
        return 0
    changed = 0
    for node in workflow.values():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict):
            continue
        images = inputs.get("images")
        if isinstance(images, list) and images and str(images[0]) in upscale_image_inputs:
            inputs["images"] = upscale_image_inputs[str(images[0])]
            changed += 1
    changed += _remove_unreferenced_workflow_nodes(workflow)
    return changed


def _route_zib_single_outputs(workflow):
    if not isinstance(workflow, dict) or ("170" not in workflow and "129" not in workflow):
        return 0
    output_node_id = "170" if "170" in workflow else "129"
    changed = 0
    for node in workflow.values():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict):
            continue
        images = inputs.get("images")
        if isinstance(images, list) and images:
            inputs["images"] = [output_node_id, 0]
            changed += 1
    changed += _remove_unreferenced_workflow_nodes(workflow)
    return changed


def _patch_zib_single_sampler_settings(workflow, model_name):
    if not isinstance(workflow, dict):
        return 0
    changed = 0
    first_sampler = workflow.get("501")
    latent_upscale = workflow.get("502")
    second_sampler = workflow.get("500")
    upscale_output = workflow.get("129")
    final_upscale = workflow.get("170")
    if isinstance(first_sampler, dict) and str(first_sampler.get("class_type") or "") == "KSamplerAdvanced":
        inputs = first_sampler.setdefault("inputs", {})
        if isinstance(inputs, dict):
            updates = {
                "add_noise": "enable",
                "steps": 30,
                "cfg": 4,
                "sampler_name": "euler",
                "scheduler": "simple",
                "start_at_step": 0,
                "end_at_step": 25,
                "return_with_leftover_noise": "enable",
            }
            for key, value in updates.items():
                if inputs.get(key) != value:
                    inputs[key] = value
                    changed += 1
    if isinstance(latent_upscale, dict) and str(latent_upscale.get("class_type") or "") == "LatentUpscaleBy":
        inputs = latent_upscale.setdefault("inputs", {})
        if isinstance(inputs, dict):
            updates = {"upscale_method": "bislerp", "scale_by": 1.7, "samples": ["501", 0]}
            for key, value in updates.items():
                if inputs.get(key) != value:
                    inputs[key] = value
                    changed += 1
    if isinstance(second_sampler, dict) and str(second_sampler.get("class_type") or "") == "KSamplerAdvanced":
        inputs = second_sampler.setdefault("inputs", {})
        if isinstance(inputs, dict):
            updates = {
                "add_noise": "enable",
                "steps": 30,
                "cfg": 4,
                "sampler_name": "dpmpp_2m_sde",
                "scheduler": "sgm_uniform",
                "start_at_step": 17,
                "end_at_step": 999,
                "return_with_leftover_noise": "disable",
                "model": ["483", 0],
                "positive": ["45", 0],
                "negative": ["490", 0],
                "latent_image": ["502", 0],
            }
            for key, value in updates.items():
                if inputs.get(key) != value:
                    inputs[key] = value
                    changed += 1
    if isinstance(upscale_output, dict) and str(upscale_output.get("class_type") or "") == "VAEDecode":
        inputs = upscale_output.setdefault("inputs", {})
        if isinstance(inputs, dict) and inputs.get("samples") != ["500", 0]:
            inputs["samples"] = ["500", 0]
            changed += 1
    if isinstance(final_upscale, dict) and str(final_upscale.get("class_type") or "") == "UltimateSDUpscale":
        inputs = final_upscale.setdefault("inputs", {})
        if isinstance(inputs, dict):
            updates = {
                "steps": 30,
                "cfg": 4,
                "sampler_name": "dpmpp_2m_sde",
                "scheduler": "sgm_uniform",
                "denoise": 0.2,
                "model": ["483", 0],
                "positive": ["45", 0],
                "negative": ["490", 0],
                "image": ["129", 0],
            }
            for key, value in updates.items():
                if inputs.get(key) != value:
                    inputs[key] = value
                    changed += 1
    return changed


def _patch_zitb_double_sampler_settings(workflow, model_name):
    if not isinstance(workflow, dict) or not _is_zib_distilled_model_name(model_name):
        return 0
    first_sampler = workflow.get("501")
    if not isinstance(first_sampler, dict) or str(first_sampler.get("class_type") or "") != "KSamplerAdvanced":
        return 0
    inputs = first_sampler.setdefault("inputs", {})
    updates = {
        "add_noise": "enable",
        "steps": ZIB_DISTILLED_STEPS,
        "cfg": ZIB_DISTILLED_CFG,
        "sampler_name": "res_multistep",
        "scheduler": "simple",
        "start_at_step": 0,
        "end_at_step": 7,
        "return_with_leftover_noise": "enable",
    }
    changed = 0
    for key, value in updates.items():
        if inputs.get(key) != value:
            inputs[key] = value
            changed += 1
    return changed


def _workflow_link_consumers(workflow):
    consumers = {}
    if not isinstance(workflow, dict):
        return consumers
    for node_id, node in workflow.items():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict):
            continue
        for value in inputs.values():
            if isinstance(value, list) and value:
                consumers.setdefault(str(value[0]), set()).add(str(node_id))
    return consumers


def _ultimate_sd_upscale_node_ids(workflow):
    if not isinstance(workflow, dict):
        return set()
    return {
        str(node_id)
        for node_id, node in workflow.items()
        if isinstance(node, dict) and str(node.get("class_type") or "") == "UltimateSDUpscale"
    }


def _node_depends_on_any(workflow, node_id, target_ids, visited=None):
    node_id = str(node_id)
    if node_id in target_ids:
        return True
    visited = set(visited or ())
    if node_id in visited:
        return False
    visited.add(node_id)
    node = workflow.get(node_id)
    inputs = node.get("inputs") if isinstance(node, dict) else None
    if not isinstance(inputs, dict):
        return False
    for value in inputs.values():
        if isinstance(value, list) and value and _node_depends_on_any(workflow, value[0], target_ids, visited):
            return True
    return False


def _prune_non_final_image_outputs(workflow):
    upscale_ids = _ultimate_sd_upscale_node_ids(workflow)
    if not upscale_ids:
        return 0
    removed = 0
    for node_id, node in list(workflow.items()):
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        images = inputs.get("images")
        if not isinstance(images, list) or not images:
            continue
        class_type = str(node.get("class_type") or "")
        is_output = (
            class_type in {
                "SaveImage",
                "PreviewImage",
                "SaveImageWebsocket",
                "RandomPhotoPromptRemoteUploadImage",
            }
            or "filename_prefix" in inputs
            or class_type.startswith("Save")
            or "Save" in class_type
        )
        if not is_output:
            continue
        if _node_depends_on_any(workflow, images[0], upscale_ids):
            continue
        workflow.pop(str(node_id), None)
        removed += 1
    return removed


def _insert_exact_output_scale(workflow, width, height):
    output_nodes = []
    for node in workflow.values():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict):
            continue
        class_type = str(node.get("class_type") or "")
        images = inputs.get("images")
        if isinstance(images, list) and images and (
            class_type in {"SaveImage", "PreviewImage", "SaveImageWebsocket"}
            or "filename_prefix" in inputs
        ):
            output_nodes.append(node)
    if not output_nodes:
        return 0
    numeric_ids = [int(node_id) for node_id in workflow if str(node_id).isdigit()]
    next_id = max(numeric_ids, default=0) + 1
    changed = 0
    for output_node in output_nodes:
        source = list(output_node["inputs"]["images"])
        scale_id = str(next_id)
        next_id += 1
        workflow[scale_id] = {
            "class_type": "ImageScale",
            "inputs": {
                "image": source,
                "upscale_method": "lanczos",
                "width": int(width),
                "height": int(height),
                "crop": "disabled",
            },
        }
        output_node["inputs"]["images"] = [scale_id, 0]
        changed += 1
    return changed


def _patch_remote_websocket_outputs(workflow, output_mode="mac"):
    if not REMOTE_WEBSOCKET_OUTPUT or not isinstance(workflow, dict):
        return {"replaced_save_nodes": 0, "output_prefix": "", "websocket_node_ids": []}
    replaced = 0
    output_prefix = ""
    websocket_node_ids = []
    for node_id, node in list(workflow.items()):
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        class_type = str(node.get("class_type") or "")
        images = inputs.get("images")
        if not isinstance(images, list) or not images:
            continue
        if class_type not in {"SaveImage", "PreviewImage"} and "filename_prefix" not in inputs:
            continue
        if not output_prefix:
            output_prefix = Path(str(inputs.get("filename_prefix") or "mobile").replace("\\", "/").strip("/")).name or "mobile"
        if BLOCK_REMOTE_ASSET_SAVE:
            node["class_type"] = "RandomPhotoPromptStreamImage"
            node["inputs"] = {"images": list(images)}
            websocket_node_ids.append(str(node_id))
        elif REMOTE_MAC_IMAGE_UPLOAD_URL and output_mode != "phone":
            node["class_type"] = "RandomPhotoPromptRemoteUploadImage"
            node["inputs"] = {"images": list(images), "filename_prefix": output_prefix}
        else:
            node["class_type"] = "SaveImageWebsocket"
            node["inputs"] = {"images": list(images)}
            websocket_node_ids.append(str(node_id))
        replaced += 1
    # Convert video output before remote submission and retain the Mac callback
    # URL injected for this specific phone task.
    if output_mode == "phone" or REMOTE_MAC_VIDEO_UPLOAD_URL:
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict) or str(node.get("class_type") or "") != "SaveVideo":
                continue
            video = inputs.get("video")
            if not isinstance(video, list) or not video:
                continue
            output_prefix = output_prefix or Path(str(inputs.get("filename_prefix") or "mobile_video").replace("\\", "/").strip("/")).name or "mobile_video"
            node["class_type"] = "RandomPhotoPromptRemoteUploadVideo"
            node["inputs"] = {
                "video": list(video),
                "filename_prefix": output_prefix,
                "format": inputs.get("format", "mp4"),
                "codec": inputs.get("codec", "h264"),
                "upload_url": inputs.get("upload_url", ""),
            }
            replaced += 1
    return {"replaced_save_nodes": replaced, "output_prefix": output_prefix, "websocket_node_ids": websocket_node_ids}


def _unpatched_remote_save_node_classes(workflow):
    if not isinstance(workflow, dict):
        return []
    classes = []
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if class_type in {"SaveImageWebsocket", "RandomPhotoPromptStreamImage", "RandomPhotoPromptRemoteUploadImage", "RandomPhotoPromptRemoteUploadVideo"}:
            continue
        if class_type == "PreviewImage" or "filename_prefix" in inputs or class_type.startswith("Save") or "Save" in class_type:
            classes.append(class_type or "unknown")
    return classes


def _force_websocket_only_image_outputs(workflow):
    if not isinstance(workflow, dict):
        return {"replaced": 0, "blocked": []}
    _prune_non_final_image_outputs(workflow)
    replaced = 0
    blocked = []
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if class_type in {"RandomPhotoPromptRemoteUploadImage", "RandomPhotoPromptRemoteUploadVideo"}:
            continue
        images = inputs.get("images")
        if (
            (class_type in {"SaveImage", "PreviewImage"} or "filename_prefix" in inputs or class_type.startswith("Save") or "Save" in class_type)
            and isinstance(images, list)
            and images
        ):
            output_prefix = Path(str(inputs.get("filename_prefix") or "remote_web").replace("\\", "/").strip("/")).name or "remote_web"
            if REMOTE_MAC_IMAGE_UPLOAD_URL:
                node["class_type"] = "RandomPhotoPromptRemoteUploadImage"
                node["inputs"] = {"images": list(images), "filename_prefix": output_prefix}
            else:
                node["class_type"] = "SaveImageWebsocket"
                node["inputs"] = {"images": list(images)}
            replaced += 1
            continue
        if class_type == "SaveImageWebsocket":
            continue
        if class_type == "SaveVideo" and isinstance(inputs.get("video"), list) and inputs.get("video"):
            if REMOTE_MAC_VIDEO_UPLOAD_URL:
                output_prefix = Path(str(inputs.get("filename_prefix") or "remote_video").replace("\\", "/").strip("/")).name or "remote_video"
                node["class_type"] = "RandomPhotoPromptRemoteUploadVideo"
                node["inputs"] = {
                    "video": list(inputs["video"]),
                    "filename_prefix": output_prefix,
                    "format": inputs.get("format", "mp4"),
                    "codec": inputs.get("codec", "h264"),
                }
                replaced += 1
                continue
            blocked.append(class_type or "unknown")
            continue
        if "filename_prefix" in inputs or class_type.startswith("Save") or "Save" in class_type:
            blocked.append(class_type or "unknown")
    return {"replaced": replaced, "blocked": blocked}


def _block_remote_asset_save_on_prompt(json_data):
    if not BLOCK_REMOTE_ASSET_SAVE or not isinstance(json_data, dict):
        return json_data
    prompt = json_data.get("prompt")
    result = _force_websocket_only_image_outputs(prompt)
    if result["blocked"]:
        detail = ", ".join(sorted(set(result["blocked"]))) or "unknown"
        json_data["prompt"] = {
            "random_photo_prompt_remote_asset_save_blocked": {
                "class_type": f"RPP_RemoteAssetSaveBlocked_{detail}",
                "inputs": {},
            }
        }
        extra_data = json_data.setdefault("extra_data", {})
        if isinstance(extra_data, dict):
            extra_data["random_photo_prompt_blocked_reason"] = f"已阻止远端资产落盘保存节点：{detail}"
        return json_data
    if result["replaced"]:
        extra_data = json_data.setdefault("extra_data", {})
        if isinstance(extra_data, dict):
            extra_data["random_photo_prompt_websocket_only"] = True
    return json_data


def _patch_mobile_workflow(template, prompt_item, width, height, seed, zit_model="", output_prefix=None, loras=None, zib_model="", workflow_key="", krea2_model="", apply_krea2_orientation_guard=True):
    workflow = copy.deepcopy(template)
    removed_auxiliary_outputs = _remove_mobile_auxiliary_outputs(workflow)
    model_cleanup_nodes = ensure_model_cleanup(workflow)
    positive_prompt = _prompt_text(prompt_item)
    negative_prompt = prompt_item.get("negative_prompt", "")
    resolved_zit_model = Path(str(zit_model or "").replace("\\", "/")).name
    resolved_zib_model = Path(str(zib_model or "").replace("\\", "/")).name
    resolved_krea2_model = Path(str(krea2_model or "").replace("\\", "/")).name
    is_krea2 = _is_krea2_workflow(workflow_key)
    if is_krea2 and apply_krea2_orientation_guard:
        positive_prompt, negative_prompt = _apply_krea2_portrait_orientation_guard(
            positive_prompt,
            negative_prompt,
            prompt_item,
            width,
            height,
        )
    use_zib_single = bool(resolved_zib_model and not resolved_zit_model)
    zib_single_output_rerouted = 0
    zib_single_sampler_settings = 0
    if use_zib_single:
        zib_single_output_rerouted = _route_zib_single_outputs(workflow)
        zib_single_sampler_settings = _patch_zib_single_sampler_settings(workflow, resolved_zib_model)
    zitb_sampler_settings = 0
    if workflow_key == "zitb_double":
        zitb_sampler_settings = _patch_zitb_double_sampler_settings(workflow, resolved_zib_model)
    base_width, base_height, output_scale, ultimate_scale = base_resolution_for_exact_output(workflow, width, height)
    exact_upscale_changed = _set_mobile_ultimate_upscale_by(workflow, ultimate_scale)
    patched = {
        "positive_text": 0,
        "negative_text": 0,
        "width": 0,
        "height": 0,
        "seed": 0,
        "steps": 0,
        "filename_prefix": 0,
        "zit_model": 0,
        "zib_model": 0,
        "krea2_model": 0,
        "lora": 0,
        "model_cleanup_nodes": model_cleanup_nodes,
        "base_width": base_width,
        "base_height": base_height,
        "output_scale": output_scale,
        "ultimate_scale": ultimate_scale,
        "exact_upscale_changed": exact_upscale_changed,
        "exact_output_scale_nodes": 0,
        "removed_auxiliary_outputs": removed_auxiliary_outputs,
        "bypassed_upscale_nodes": 0,
        "zib_single_output_rerouted": zib_single_output_rerouted,
        "zib_single_sampler_settings": zib_single_sampler_settings,
        "zitb_sampler_settings": zitb_sampler_settings,
        "krea2_negative_text_node": 0,
        "sampler_steps": None,
    }
    text_nodes = []
    if is_krea2:
        patched["krea2_negative_text_node"] = _patch_krea2_negative_text_node(workflow, negative_prompt)
    patched["lora"] = _patch_existing_lora_nodes(workflow, loras or [], workflow_key)
    if workflow_key == "zit_single":
        sampler_steps = 10 if resolved_zit_model == ZIT_SINGLE_TEN_STEP_MODEL else 8
    else:
        sampler_steps = 10 if is_krea2 else 8
    zit_unet_value = _zimage_unet_value(resolved_zit_model)
    zib_unet_value = _zimage_unet_value(resolved_zib_model)
    krea2_unet_value = _krea2_unet_value(resolved_krea2_model)
    model_consumers = _workflow_model_consumers(workflow)
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        class_type = str(node.get("class_type") or "")
        if class_type == "RandomPhotoPrompt":
            scale_label_map = {
                "normal": "一档",
                "bold": "二档",
                "bold_no_outfit": "三档",
                "nsfw": "四档",
            }
            era_label_map = {"modern": "现代", "ancient": "古装"}
            shot_label_map = {
                "head_shot": "头部",
                "half_body": "半身",
                "full_body": "全身",
            }
            inputs["scale"] = scale_label_map.get(str(prompt_item.get("scale") or ""), prompt_item.get("scale") or "二档")
            inputs["era"] = era_label_map.get(str(prompt_item.get("era") or ""), prompt_item.get("era") or "现代")
            inputs["shot"] = prompt_item.get("shot") or shot_label_map.get(str(prompt_item.get("shot_key") or ""), "随机")
            inputs["use_pregenerated_prompt"] = False
            inputs["cached_prompt"] = ""
            inputs["cached_negative_prompt"] = ""
            inputs["cached_signature"] = ""
            inputs["cached_prompt_source"] = ""
        if _node_meta(node).get("skip_mobile_prompt_patch") is True:
            continue
        if "text" in inputs and ("CLIPTextEncode" in class_type or "TextEncode" in class_type or "Conditioning" in class_type):
            text_nodes.append(node)
        if is_krea2 and "unet_name" in inputs and ("krea2" in str(inputs.get("unet_name") or "").lower() or krea2_unet_value):
            if krea2_unet_value:
                inputs["unet_name"] = krea2_unet_value
                patched["krea2_model"] += 1
            inputs["weight_dtype"] = "default"
        if resolved_zit_model and "unet_name" in inputs:
            current_unet = str(inputs.get("unet_name") or "")
            if _is_zit_turbo_model_name(current_unet):
                inputs["unet_name"] = zit_unet_value
                if inputs.get("weight_dtype") in {"fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"}:
                    inputs["weight_dtype"] = "default"
                patched["zit_model"] += 1
        if resolved_zib_model and "unet_name" in inputs:
            current_unet = str(inputs.get("unet_name") or "")
            normalized_unet = current_unet.replace("/", "\\").lower()
            consumers = model_consumers.get(str(node_id), set())
            is_zib_slot = normalized_unet.startswith("z_image\\zib") or "483" in consumers or (use_zib_single and _is_zit_turbo_model_name(current_unet))
            if is_zib_slot:
                inputs["unet_name"] = zib_unet_value
                if inputs.get("weight_dtype") in {"fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2", "bf16"}:
                    inputs["weight_dtype"] = "default"
                patched["zib_model"] += 1
        for key in ("width", "W", "image_width", "latent_width", "empty_latent_width", "瀹藉害"):
            if key in inputs and isinstance(inputs.get(key), (int, float, str)):
                inputs[key] = int(base_width)
                patched["width"] += 1
        for key in ("height", "H", "image_height", "latent_height", "empty_latent_height", "楂樺害"):
            if key in inputs and isinstance(inputs.get(key), (int, float, str)):
                inputs[key] = int(base_height)
                patched["height"] += 1
        for key in ("seed", "noise_seed"):
            if key in inputs and isinstance(inputs.get(key), (int, float, str)):
                inputs[key] = int(seed)
                patched["seed"] += 1
        if is_krea2 and class_type == "KSampler":
            if "cfg" in inputs:
                inputs["cfg"] = 1
            if "sampler_name" in inputs:
                inputs["sampler_name"] = "euler"
            if "scheduler" in inputs:
                inputs["scheduler"] = "simple"
        if not use_zib_single and class_type == "KSampler" and "steps" in inputs and isinstance(inputs.get("steps"), (int, float, str)):
            inputs["steps"] = sampler_steps
            patched["steps"] += 1
        if "filename_prefix" in inputs and isinstance(inputs.get("filename_prefix"), str):
            raw_prefix = str(inputs.get("filename_prefix") or "ComfyUI").replace("\\", "/").strip("/")
            base_prefix = Path(raw_prefix).name or "ComfyUI"
            final_prefix = output_prefix or base_prefix
            inputs["filename_prefix"] = final_prefix
            patched["filename_prefix"] += 1
    negative_nodes = {id(node) for node in text_nodes if _looks_negative_text(node)}
    if not negative_nodes and len(text_nodes) >= 2:
        negative_nodes.add(id(text_nodes[1]))
    for node in text_nodes:
        inputs = node["inputs"]
        if id(node) in negative_nodes:
            inputs["text"] = negative_prompt
            patched["negative_text"] += 1
        else:
            inputs["text"] = positive_prompt
            patched["positive_text"] += 1
    if patched["positive_text"] < 1:
        raise ValueError("工作流模板里没有找到可写入的正向提示词节点。")
    if resolved_zit_model and patched["zit_model"] < 1:
        raise ValueError("工作流模板里没有找到可替换的 z_image_turbo 模型节点。")
    if resolved_zib_model and patched["zib_model"] < 1:
        raise ValueError("工作流模板里没有找到可替换的 ZIB 模型节点。")
    if is_krea2 and resolved_krea2_model and patched["krea2_model"] < 1:
        raise ValueError("工作流模板里没有找到可替换的 Krea2 模型节点。")
    if not use_zib_single:
        patched["sampler_steps"] = sampler_steps
    patched["exact_output_scale_nodes"] = _insert_exact_output_scale(workflow, width, height)
    patched["removed_prompt_nodes"] = _remove_unreferenced_mobile_prompt_nodes(workflow)
    return workflow, patched


def _patch_mobile_video_workflow(template, prompt_item, image_load_name, source_image_path, seed, seconds=8, fps=24, output_prefix=None, positive_prompt=None, remote_source_url="", remote_video_upload_url="", video_mode="image"):
    workflow = copy.deepcopy(template)
    model_cleanup_nodes = ensure_model_cleanup(workflow)
    positive_prompt = positive_prompt or _prompt_text(prompt_item)
    negative_prompt = prompt_item.get("negative_prompt", "")
    is_image_to_video = str(video_mode or "image").strip().lower() == "image"
    # 图生视频保留首帧比例，并受 960 长边与 62 万像素上限约束；文生视频固定画布已满足两项限制。
    video_width, video_height = image_to_video_resolution(source_image_path) if is_image_to_video else (540, 960)
    seconds = max(1, min(30, int(seconds or 6)))
    # MiniMax H3 的原工作流按 24 FPS 计算长度并封装视频，其他帧率会破坏时长映射。
    fps = 24
    patched = {
        "positive_text": 0,
        "negative_text": 0,
        "load_image": 0,
        "resolution": 0,
        "seconds": 0,
        "fps": 0,
        "seed": 0,
        "filename_prefix": 0,
        "model_cleanup_nodes": model_cleanup_nodes,
    }
    if is_image_to_video:
        source_node_id = str(max((int(node_id) for node_id in workflow if str(node_id).isdigit()), default=0) + 1)
        source_node = {
            "class_type": "RandomPhotoPromptRemoteLoadImageFromMac" if remote_source_url else "LoadImage",
            "inputs": {"source_url": remote_source_url} if remote_source_url else {"image": image_load_name},
            "_meta": {"title": "MiniMax H3 首帧（本机来源）"},
        }
        for node in workflow.values():
            if str(node.get("class_type") or "") == "MiniMaxH3ImageToVideo":
                node.setdefault("inputs", {})["first_frame"] = [source_node_id, 0]
                workflow[source_node_id] = source_node
                patched["load_image"] = 1
                break
    text_nodes = []
    for node_id, node in list(workflow.items()):
        if not isinstance(node, dict):
            continue
        if str(node.get("class_type") or "") == "PreviewImage":
            workflow.pop(str(node_id), None)
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        class_type = str(node.get("class_type") or "")
        title = _node_title(node)
        if class_type == "ResolutionSelector":
            workflow.pop(str(node_id), None)
            continue
        if class_type == "MiniMaxH3ImageToVideo":
            inputs["width"] = video_width
            inputs["height"] = video_height
            patched["resolution"] += 1
        if "text" in inputs and ("CLIPTextEncode" in class_type or "TextEncode" in class_type or "Conditioning" in class_type):
            text_nodes.append(node)
        if class_type == "PrimitiveStringMultiline" and "value" in inputs:
            text_nodes.append(node)
        if class_type == "LoadImage" and "image" in inputs:
            if remote_source_url:
                node["class_type"] = "RandomPhotoPromptRemoteLoadImageFromMac"
                node["inputs"] = {"source_url": remote_source_url}
            else:
                inputs["image"] = image_load_name
            patched["load_image"] += 1
        if "fps" in inputs:
            inputs["fps"] = fps
            patched["fps"] += 1
        if "value" in inputs and isinstance(inputs.get("value"), (int, float, str)):
            if "秒" in title or "second" in title:
                inputs["value"] = seconds
                patched["seconds"] += 1
            elif "帧" in title or "fps" in title or "frame" in title:
                inputs["value"] = fps
                patched["fps"] += 1
        for key in ("seed", "noise_seed"):
            if key in inputs and isinstance(inputs.get(key), (int, float, str)):
                inputs[key] = int(seed)
                patched["seed"] += 1
        if "filename_prefix" in inputs and isinstance(inputs.get("filename_prefix"), str):
            raw_prefix = str(inputs.get("filename_prefix") or "video").replace("\\", "/").strip("/")
            base_prefix = Path(raw_prefix).name or "video"
            final_prefix = output_prefix or base_prefix
            inputs["filename_prefix"] = f"{MOBILE_VIDEO_OUTPUT_SUBFOLDER}/{final_prefix}"
            if remote_video_upload_url:
                inputs["upload_url"] = remote_video_upload_url
            patched["filename_prefix"] += 1
    negative_nodes = {id(node) for node in text_nodes if _looks_negative_text(node)}
    if not negative_nodes and len(text_nodes) >= 2:
        negative_nodes.add(id(text_nodes[1]))
    for node in text_nodes:
        inputs = node["inputs"]
        if "value" in inputs:
            inputs["value"] = positive_prompt
            patched["positive_text"] += 1
            continue
        if id(node) in negative_nodes:
            inputs["text"] = negative_prompt
            patched["negative_text"] += 1
        else:
            inputs["text"] = positive_prompt
            patched["positive_text"] += 1
    if patched["positive_text"] < 1:
        raise ValueError("视频工作流模板里没有找到可写入的正向提示词节点。")
    if is_image_to_video and patched["load_image"] < 1:
        raise ValueError("视频工作流模板里没有找到 LoadImage 节点。")
    if patched["resolution"] < 1:
        raise ValueError("视频工作流模板里没有找到 MiniMaxH3ImageToVideo 节点。")
    if patched["filename_prefix"] < 1:
        raise ValueError("视频工作流模板里没有找到 SaveVideo 文件名前缀。")
    return workflow, patched, {"width": video_width, "height": video_height, "seconds": seconds, "fps": fps}



def _available_loras():
    try:
        return sorted(
            name.replace("\\", "/")
            for name in folder_paths.get_filename_list("loras")
            if name.replace("\\", "/").startswith(f"{ZIMAGE_LORA_SUBDIR}/")
        )
    except Exception:
        lora_dir = Path(folder_paths.models_dir) / "loras" / ZIMAGE_LORA_SUBDIR
        if not lora_dir.exists():
            return []
        return sorted(
            f"{ZIMAGE_LORA_SUBDIR}/{path.relative_to(lora_dir).as_posix()}"
            for path in lora_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in LORA_MODEL_EXTENSIONS
        )


def _resolve_lora_name(value=None, available_loras=None):
    raw = str(value or "").replace("\\", "/").strip().strip("/")
    if not raw:
        return ""
    available = list(available_loras) if available_loras is not None else _available_loras()
    if raw in available:
        return raw
    raw_name = Path(raw).name
    matches = [name for name in available if Path(name.replace("\\", "/")).name == raw_name]
    if len(matches) == 1:
        return matches[0]
    raise ValueError(f"没有找到 LoRA：{raw}")


def _resolve_lora_strength(value=None):
    try:
        strength = float(value)
    except (TypeError, ValueError):
        strength = 0.8
    return max(-2.0, min(2.0, strength))
