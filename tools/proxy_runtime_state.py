#!/usr/bin/env python3


PROMPT_PROGRESS = {}
ACTIVE_PROMPT_IDS = []
PROMPT_OUTPUT_PREFIX = {}
PROMPT_WS_WATCHERS = {}
PROMPT_WS_IMAGE_INDEX = {}
WS_OUTPUT_NODE_IDS = {}
PROMPT_NODE_TOTAL = {}
PROMPT_SEEN_NODES = {}


def remember_active_prompt(prompt_id):
    prompt_id = str(prompt_id or "").strip()
    if not prompt_id:
        return
    if prompt_id in ACTIVE_PROMPT_IDS:
        ACTIVE_PROMPT_IDS.remove(prompt_id)
    ACTIVE_PROMPT_IDS.append(prompt_id)
    del ACTIVE_PROMPT_IDS[:-64]


def forget_active_prompt(prompt_id):
    prompt_id = str(prompt_id or "").strip()
    if prompt_id in ACTIVE_PROMPT_IDS:
        ACTIVE_PROMPT_IDS.remove(prompt_id)


def clear_runtime_state(reason="", logger=None):
    before_watchers = len(PROMPT_WS_WATCHERS)
    for watcher in list(PROMPT_WS_WATCHERS.values()):
        try:
            watcher.cancel()
        except Exception:
            pass
    cleared_prompts = len(set(ACTIVE_PROMPT_IDS) | set(PROMPT_PROGRESS) | set(PROMPT_OUTPUT_PREFIX))
    PROMPT_PROGRESS.clear()
    ACTIVE_PROMPT_IDS.clear()
    PROMPT_OUTPUT_PREFIX.clear()
    PROMPT_WS_WATCHERS.clear()
    PROMPT_WS_IMAGE_INDEX.clear()
    WS_OUTPUT_NODE_IDS.clear()
    PROMPT_NODE_TOTAL.clear()
    PROMPT_SEEN_NODES.clear()
    if logger:
        logger(f"runtime state cleared reason={reason or 'manual'} watchers={before_watchers} prompts={cleared_prompts}")
    return {"watchers_cancelled": before_watchers, "prompts_cleared": cleared_prompts}


def active_prompt_for_progress(data):
    prompt_id = str((data or {}).get("prompt_id") or "").strip()
    if prompt_id:
        return prompt_id
    node = str((data or {}).get("node") or "").strip()
    for candidate in reversed(ACTIVE_PROMPT_IDS):
        progress = PROMPT_PROGRESS.get(candidate) or {}
        if not node or not progress.get("node") or progress.get("node") == node:
            return candidate
    return ACTIVE_PROMPT_IDS[-1] if ACTIVE_PROMPT_IDS else ""


def remember_progress_message(message):
    if not isinstance(message, dict) or message.get("type") != "executing":
        return
    data = message.get("data") or {}
    prompt_id = active_prompt_for_progress(data)
    if not prompt_id:
        return
    node = str(data.get("node") or "").strip()
    node_total = max(1, int(PROMPT_NODE_TOTAL.get(prompt_id) or 1))
    if not node:
        PROMPT_PROGRESS[prompt_id] = {"value": node_total, "max": node_total, "percent": 100, "node": "", "type": "node"}
        return
    seen = PROMPT_SEEN_NODES.setdefault(prompt_id, [])
    if node not in seen:
        seen.append(node)
    value = max(1, min(node_total, len(seen)))
    PROMPT_PROGRESS[prompt_id] = {
        "value": value,
        "max": node_total,
        "percent": max(0, min(100, round((value / node_total) * 100))),
        "node": node,
        "type": "node",
    }
