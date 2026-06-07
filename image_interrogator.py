from __future__ import annotations

import gc
import hashlib
import io
import os
import tempfile
from pathlib import Path

from PIL import Image


MODEL_DIR = Path(r"C:\ComfyUI-共享目录\LLM\Huihui-Qwen3-VL-4B-Instruct")
MAX_IMAGE_SIDE = 768

_MODEL = None
_PROCESSOR = None
_DEVICE = None

_BLOCKED_TERMS = (
    "explicit sexual act",
    "sex act",
    "genitals",
    "penis",
    "vagina",
    "porn",
    "pornographic",
    "oral sex",
    "intercourse",
    "masturbation",
    "sexual act",
    "口交",
    "性交",
    "插入",
    "自慰",
    "射精",
    "阴茎",
    "龟头",
    "阴道",
    "性器",
    "生殖器",
)

_INTERROGATION_PROMPT = """请把这张图片反推成可用于写真人像生成的中文正向提示词，必须按当前项目的六维度格式输出。
只输出六行自然中文提示词，不要标题、编号、Markdown、解释，也不要写“镜头：”“角色：”“妆容：”“穿着：”“姿势表情：”“场景灯光：”这类标签。
六行顺序固定为：
第一行写镜头构图：判断画面范围属于头部、上半身、半身、大半身或全身。头部是肩膀及以上；上半身是胸部及以上；半身是腰部及以上；大半身是小腿及以上；全身是完整身形可见。只描述实际看见的范围、角度、距离、俯仰视、画幅方向和构图，不要写看不见的身体部位。
第二行写角色主体：只描述图片里能看见的人物、皮肤、脸部、头发、体态和可见身体范围，不要编造固定人物身份、年龄或职业。保留实际可见特征，不要强行改写成项目固定角色。
第三行写妆容：描述眼妆、睫毛、眼线、眼影、肤质、唇部状态和整体妆感。唇部优先写纤薄原生唇形、透明无色水光、浅粉自然唇色；不要写深红、酒红、厚唇、嘟大嘴或夸张红唇。
第四行写穿着：描述可见服装、配饰、材质、颜色、半透明或薄款质感、覆盖范围和遮挡关系。颜色优先写阳光鲜艳的具体彩色，例如珊瑚粉、柠檬黄、薄荷绿、蜜桃橙、湖蓝、浅紫、玫瑰粉、阳光黄等；不要默认黑白灰。看不清就写可见边缘、配饰和遮挡状态。
第五行写姿势表情：描述头部方向、低头/抬头/仰视/俯视/抬眸/垂眸、视线、嘴部状态、手部位置、身体姿态和情绪。只写一个主要姿势家族，不要把站、坐、跪、躺混在同一行。
第六行写场景灯光：描述真实背景、空间氛围、主光方向、光色、皮肤反射和明暗关系。整体优先阳光、温暖、艳丽、高饱和、多色协调搭配；不要主动写真实彩虹。场景道具必须符合环境：海边/泳池/游艇/花园/露台只能用海水、沙滩、泳池、甲板、晴空、花草、喷泉、遮阳伞等户外来源；室内才可以写窗帘、白墙、玻璃、镜面、窗光。不要把室内道具硬放进室外。
如果图片是成人性感写真，只写非显式成人 glamour、遮挡、氛围、姿态和光影。不要写明确性行为、性器官、露出生殖器、插入、口交、自慰、射精、强迫或未成年相关内容。
每行尽量短而具体，总长度控制在 800 个中文字符以内。"""

_DIMENSION_LABEL_PREFIXES = (
    "镜头构图",
    "镜头",
    "构图",
    "角色主体",
    "角色",
    "主体",
    "人物",
    "妆容",
    "穿着",
    "服装",
    "姿势表情",
    "姿势",
    "表情",
    "场景灯光",
    "场景",
    "灯光",
)


class ImageInterrogationError(RuntimeError):
    pass


def _ensure_model_path() -> None:
    required = ("config.json", "model.safetensors.index.json", "preprocessor_config.json")
    missing = [name for name in required if not (MODEL_DIR / name).exists()]
    if missing:
        raise ImageInterrogationError(
            f"未找到本地图像反推模型文件：{', '.join(missing)}。请检查模型目录：{MODEL_DIR}"
        )


def _load_model():
    global _MODEL, _PROCESSOR, _DEVICE
    if _MODEL is not None and _PROCESSOR is not None:
        return _MODEL, _PROCESSOR, _DEVICE

    _ensure_model_path()
    try:
        import torch
        from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
    except Exception as exc:
        raise ImageInterrogationError(f"图像反推依赖缺失：{exc}") from exc

    _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if _DEVICE == "cuda" else torch.float32
    try:
        _PROCESSOR = AutoProcessor.from_pretrained(
            str(MODEL_DIR),
            local_files_only=True,
            trust_remote_code=True,
        )
        _MODEL = Qwen3VLForConditionalGeneration.from_pretrained(
            str(MODEL_DIR),
            dtype=dtype,
            device_map="auto" if _DEVICE == "cuda" else None,
            local_files_only=True,
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )
        _MODEL.eval()
        if _DEVICE == "cpu":
            _MODEL.to(_DEVICE)
    except Exception as exc:
        raise ImageInterrogationError(f"本地图像反推模型加载失败：{exc}") from exc
    return _MODEL, _PROCESSOR, _DEVICE


def release_interrogator_model() -> None:
    global _MODEL, _PROCESSOR, _DEVICE
    _MODEL = None
    _PROCESSOR = None
    _DEVICE = None
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass


def _clean_prompt(text: str) -> str:
    lines = []
    for raw_line in str(text).splitlines():
        line = " ".join(raw_line.split()).strip(" -_*`#\t")
        if not line:
            continue
        line = line.lstrip("0123456789一二三四五六七八九十.、)） ")
        for prefix in _DIMENSION_LABEL_PREFIXES:
            for sep in ("：", ":", " - ", "—", "-"):
                marker = f"{prefix}{sep}"
                if line.startswith(marker):
                    line = line[len(marker) :].strip()
                    break
            else:
                continue
            break
        if line:
            lines.append(line)
    if len(lines) > 6:
        lines = lines[:5] + ["，".join(lines[5:])]
    text = "\n".join(lines)
    lowered = text.lower()
    if any(term.lower() in lowered for term in _BLOCKED_TERMS):
        raise ImageInterrogationError("反推结果包含项目禁止的显式成人内容，已拒绝写入。")
    if len(text) > 800:
        text = text[:800].rstrip(" ,.;。，、")
    return text.strip(" ,.;。")


def _image_to_temp_file(image: Image.Image) -> str:
    image = image.copy()
    image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
    handle = tempfile.NamedTemporaryFile(prefix="random_photo_prompt_", suffix=".png", delete=False)
    path = handle.name
    handle.close()
    image.save(path, format="PNG")
    return path


def interrogate_image_bytes(image_bytes: bytes) -> dict[str, str]:
    if not image_bytes:
        raise ImageInterrogationError("图片为空。")

    signature = hashlib.sha256(image_bytes).hexdigest()[:16]
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        raise ImageInterrogationError(f"无法读取上传图片：{exc}") from exc

    model, processor, _device = _load_model()
    image_path = _image_to_temp_file(image)
    try:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image_path},
                    {"type": "text", "text": _INTERROGATION_PROMPT},
                ],
            }
        ]
        inputs = processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
        inputs = inputs.to(model.device)
        output = model.generate(
            **inputs,
            max_new_tokens=360,
            do_sample=False,
            repetition_penalty=1.05,
        )
        output_trimmed = [
            out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, output)
        ]
        prompt = processor.batch_decode(
            output_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]
    except Exception as exc:
        raise ImageInterrogationError(f"图像反推失败：{exc}") from exc
    finally:
        try:
            os.remove(image_path)
        except OSError:
            pass
        release_interrogator_model()

    prompt = _clean_prompt(prompt)
    return {
        "prompt": prompt,
        "caption": prompt,
        "signature": f"interrogate|{signature}",
    }
