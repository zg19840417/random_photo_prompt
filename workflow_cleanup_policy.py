"""Policies that keep remote ComfyUI model caches bounded between jobs."""


def _node_title(node):
    meta = node.get("_meta") if isinstance(node, dict) else None
    return str(meta.get("title") or "").lower() if isinstance(meta, dict) else ""


def remove_mobile_auxiliary_outputs(workflow):
    """Remove visual-only outputs while preserving GPU cleanup output nodes."""
    remove_ids = set()
    for node_id, node in list(workflow.items()):
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        title = _node_title(node)
        if class_type == "Image Comparer (rgthree)" or "compare" in title:
            remove_ids.add(str(node_id))

    for node_id, node in list(workflow.items()):
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if any(isinstance(value, list) and value and str(value[0]) in remove_ids for value in inputs.values()):
            class_type = str(node.get("class_type") or "")
            title = _node_title(node)
            if class_type == "Image Comparer (rgthree)" or "compare" in title:
                remove_ids.add(str(node_id))

    removed = 0
    for node_id in remove_ids:
        if workflow.pop(node_id, None) is not None:
            removed += 1
    return removed


def _next_node_id(workflow):
    numeric_ids = [int(node_id) for node_id in workflow if str(node_id).isdigit()]
    return str(max(numeric_ids, default=0) + 1)


def _terminal_output_source(workflow):
    output_classes = (
        "RandomPhotoPromptStreamImage",
        "SaveImageWebsocket",
        "SaveImage",
        "SaveVideo",
        "PreviewImage",
    )
    source_keys = ("images", "image", "video", "samples", "anything")
    for class_type in output_classes:
        for node in workflow.values():
            if not isinstance(node, dict) or str(node.get("class_type") or "") != class_type:
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            for key in source_keys:
                value = inputs.get(key)
                if isinstance(value, list) and len(value) >= 2 and str(value[0]) in workflow:
                    return [str(value[0]), value[1]]
    raise ValueError("工作流没有可连接显存清理节点的最终输出。")


def ensure_model_cleanup(workflow):
    """Enable existing cleanup nodes or inject one after the final output source."""
    cleanup_nodes = 0
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        if class_type == "easy cleanGpuUsed":
            cleanup_nodes += 1
            continue
        if class_type != "LayerUtility: PurgeVRAM V2":
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        inputs["purge_cache"] = True
        inputs["purge_models"] = True
        cleanup_nodes += 1
    if cleanup_nodes:
        return cleanup_nodes

    cleanup_id = _next_node_id(workflow)
    workflow[cleanup_id] = {
        "class_type": "easy cleanGpuUsed",
        "inputs": {"anything": _terminal_output_source(workflow)},
        "_meta": {"title": "任务结束清理显存"},
    }
    cleanup_nodes += 1
    return cleanup_nodes
