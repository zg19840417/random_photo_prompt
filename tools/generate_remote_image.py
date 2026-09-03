#!/usr/bin/env python3
import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import aiohttp
from PIL import Image

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from remote_preview_protocol import decode_preview_frame, websocket_connect_kwargs


DEFAULT_REMOTE_URL = "http://192.168.123.111:8188"
DEFAULT_ZIT_MODEL = "ZIT-beyondREALITY_V30.safetensors"
DEFAULT_ZIB_MODEL = "ZIB-redcraft22INT8INT4_zibDistilled.safetensors"
DEFAULT_KREA2_MODEL = "KREA2-darkBeast.safetensors"
WORKFLOW_KEYS = {"zit": "zit_single", "krea2": "redcraft_krea2", "double": "zitb_double"}


def parse_args():
    parser = argparse.ArgumentParser(description="调用远端 4090 ComfyUI 生成一张图片并直接保存到指定目录。")
    parser.add_argument("--workflow", required=True, choices=tuple(WORKFLOW_KEYS))
    parser.add_argument("--prompt", required=True, help="正向提示词")
    parser.add_argument("--negative-prompt", default="", help="负向提示词，仅 double 可用")
    parser.add_argument("--output", required=True, type=Path, help="调用方本地输出目录")
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1312)
    parser.add_argument("--zit-model", default="")
    parser.add_argument("--zib-model", default="")
    parser.add_argument("--krea2-model", default="")
    parser.add_argument("--timeout", type=int, default=1800, help="生成超时秒数")
    return parser.parse_args()


def validate_args(args):
    if not args.prompt.strip():
        raise ValueError("正向提示词不能为空。")
    if args.workflow != "double" and args.negative_prompt.strip():
        raise ValueError("单采工作流只接受正向提示词。")
    if args.width < 64 or args.height < 64 or args.width > 4096 or args.height > 4096:
        raise ValueError("宽高必须在 64 到 4096 之间。")
    if args.workflow == "zit" and (args.zib_model or args.krea2_model):
        raise ValueError("zit 工作流只能指定 --zit-model。")
    if args.workflow == "krea2" and (args.zit_model or args.zib_model):
        raise ValueError("krea2 工作流只能指定 --krea2-model。")
    if args.workflow == "double" and args.krea2_model:
        raise ValueError("double 工作流只能指定 --zit-model 和 --zib-model。")


def websocket_url(remote_url, client_id):
    parsed = urlparse(remote_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, f"{parsed.path.rstrip('/')}/ws", "", f"clientId={client_id}", ""))


def selected_models(args):
    if args.workflow == "zit":
        return args.zit_model or DEFAULT_ZIT_MODEL, "", ""
    if args.workflow == "krea2":
        return "", "", args.krea2_model or DEFAULT_KREA2_MODEL
    return args.zit_model or DEFAULT_ZIT_MODEL, args.zib_model or DEFAULT_ZIB_MODEL, ""


async def response_json(response):
    try:
        data = await response.json()
    except Exception:
        data = {"error": await response.text()}
    if response.status >= 400:
        raise RuntimeError(data.get("error") or f"HTTP {response.status}")
    return data


async def verify_models(session, remote_url, zit_model, zib_model, krea2_model):
    async with session.get(f"{remote_url}/random_photo_prompt/manual/status") as response:
        status = await response_json(response)
    required = (("ZIT", zit_model, status.get("zit_models", [])), ("ZIB", zib_model, status.get("zib_models", [])), ("Krea2", krea2_model, status.get("krea2_models", [])))
    for label, model, available in required:
        if model and model not in available:
            raise ValueError(f"远端不存在 {label} 模型：{model}")


def remote_queue_state(queue, prompt_id):
    running = queue.get("queue_running") or []
    pending = queue.get("queue_pending") or []
    if any(len(item) > 1 and str(item[1]) == prompt_id for item in running):
        return "running", 0
    for index, item in enumerate(pending):
        if len(item) > 1 and str(item[1]) == prompt_id:
            return "pending", len(running) + index
    return "unknown", None


async def report_queue_progress(session, remote_url, prompt_id):
    previous = None
    while True:
        try:
            async with session.get(f"{remote_url}/queue") as response:
                queue = await response_json(response)
            state, ahead = remote_queue_state(queue, prompt_id)
            if state == "running":
                if previous != state:
                    print("远端开始执行。", file=sys.stderr, flush=True)
                return
            if state == "pending":
                message = f"排队中，前方 {ahead} 个任务。"
                if message != previous:
                    print(message, file=sys.stderr, flush=True)
                    previous = message
        except Exception:
            pass
        await asyncio.sleep(2)


async def generate(args):
    validate_args(args)
    args.output.mkdir(parents=True, exist_ok=True)
    if not args.output.is_dir():
        raise ValueError(f"输出路径不是目录：{args.output}")
    remote_url = os.environ.get("RPP_REMOTE_URL", DEFAULT_REMOTE_URL).rstrip("/")
    zit_model, zib_model, krea2_model = selected_models(args)
    client_id = f"rpp_cli_{uuid.uuid4().hex}"
    timeout = aiohttp.ClientTimeout(total=args.timeout)
    started = time.monotonic()
    image_bytes = None
    image_extension = ".png"
    prompt_id = ""
    output_prefix = ""
    sampler_steps = None
    completed = False
    queue_reporter = None

    async with aiohttp.ClientSession(timeout=timeout) as session:
        await verify_models(session, remote_url, zit_model, zib_model, krea2_model)
        async with session.ws_connect(
            websocket_url(remote_url, client_id),
            heartbeat=30,
            **websocket_connect_kwargs(),
        ) as websocket:
            await websocket.send_json({"type": "feature_flags", "data": {"supports_preview_metadata": True}})
            while True:
                negotiation = await websocket.receive()
                if negotiation.type == aiohttp.WSMsgType.TEXT:
                    negotiation_event = json.loads(negotiation.data)
                    if negotiation_event.get("type") == "feature_flags":
                        break
                if negotiation.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                    raise RuntimeError("远端 WebSocket 在图片协议协商完成前断开。")
            payload = {
                "workflow": WORKFLOW_KEYS[args.workflow],
                "custom_prompt_source": "manual",
                "custom_prompt": args.prompt.strip(),
                "exact_prompt": True,
                "custom_resolution": f"{args.width}x{args.height}",
                "client_id": client_id,
                "zit_model": zit_model,
                "zib_model": zib_model,
                "krea2_model": krea2_model,
                "scale": "normal",
                "era": "modern",
            }
            if args.workflow == "double" and args.negative_prompt.strip():
                payload["negative_prompt"] = args.negative_prompt.strip()
            async with session.post(f"{remote_url}/random_photo_prompt/manual/generate", json=payload) as response:
                data = await response_json(response)
            job = (data.get("jobs") or [{}])[0]
            prompt_id = str(job.get("prompt_id") or "")
            output_prefix = str(job.get("output_prefix") or "")
            sampler_steps = (job.get("patched") or {}).get("sampler_steps") if args.workflow != "double" else None
            if not prompt_id or not output_prefix:
                raise RuntimeError((data.get("errors") or [{"error": "任务提交失败。"}])[0].get("error"))
            print(f"已提交 {prompt_id}", file=sys.stderr, flush=True)
            queue_reporter = asyncio.create_task(report_queue_progress(session, remote_url, prompt_id))

            try:
                while not (completed and image_bytes):
                    message = await websocket.receive()
                    if message.type == aiohttp.WSMsgType.BINARY:
                        frame = decode_preview_frame(message.data)
                        if frame is None:
                            continue
                        if frame["prompt_id"] and frame["prompt_id"] != prompt_id:
                            continue
                        image_extension = ".jpg" if frame["image_type"] == 1 else ".png"
                        image_bytes = frame["image_bytes"]
                        continue
                    if message.type == aiohttp.WSMsgType.TEXT:
                        event = json.loads(message.data)
                        event_data = event.get("data") or {}
                        event_prompt_id = str(event_data.get("prompt_id") or "")
                        if event_prompt_id and event_prompt_id != prompt_id:
                            continue
                        if event.get("type") == "executing":
                            node = event_data.get("node")
                            if node is None:
                                completed = True
                            else:
                                print(f"执行节点 {node}", file=sys.stderr, flush=True)
                        elif event.get("type") in {"execution_error", "execution_interrupted"}:
                            raise RuntimeError(event_data.get("exception_message") or "远端任务执行失败。")
                        continue
                    if message.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                        raise RuntimeError("远端 WebSocket 在任务完成前断开。")
            finally:
                if queue_reporter:
                    queue_reporter.cancel()
                    await asyncio.gather(queue_reporter, return_exceptions=True)

    target = (args.output / f"{output_prefix}_00001{image_extension}").resolve()
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(image_bytes)
    temporary.replace(target)
    with Image.open(BytesIO(image_bytes)) as image:
        actual_width, actual_height = image.size
    if (actual_width, actual_height) != (args.width, args.height):
        target.unlink(missing_ok=True)
        raise RuntimeError(
            f"远端返回尺寸 {actual_width}x{actual_height}，与请求尺寸 {args.width}x{args.height} 不一致。"
        )
    elapsed = round(time.monotonic() - started, 3)
    return {
        "image_path": str(target),
        "workflow": args.workflow,
        "zit_model": zit_model or None,
        "zib_model": zib_model or None,
        "krea2_model": krea2_model or None,
        "width": actual_width,
        "height": actual_height,
        "steps": sampler_steps,
        "elapsed_seconds": elapsed,
        "prompt_id": prompt_id,
    }


def main():
    try:
        result = asyncio.run(generate(parse_args()))
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
