"""Optional, remote-only Qwen Image 2.1 Turbo research backend."""
from __future__ import annotations

import gc
import json
import os
import re
from importlib import metadata
from pathlib import Path

MODEL_NAME = "Qwen-Image-2.1-Turbo"
SAMPLE_SIGMAS = (1.0, 0.978453, 0.95418, 0.926626, 0.89508, 0.845148, 0.704534, 0.414568)
REQUIRED_FILES = (
    "LICENSE", "model_index.json", "processor/chat_template.jinja",
    "processor/processor_config.json", "processor/tokenizer.json",
    "processor/tokenizer_config.json", "scheduler/scheduler_config.json",
    "text_encoder/config.json", "text_encoder/model.safetensors",
    "transformer/config.json", "transformer/diffusion_pytorch_model.safetensors.index.json",
    "transformer/diffusion_pytorch_model-00001-of-00002.safetensors",
    "transformer/diffusion_pytorch_model-00002-of-00002.safetensors",
    "vae/config.json", "vae/diffusion_pytorch_model.safetensors",
)


def dependency_errors():
    errors = []
    for package, minimum in (("diffusers", (0, 41, 0)), ("transformers", (5, 17, 0)), ("accelerate", (0, 0, 0))):
        try:
            version = metadata.version(package)
        except metadata.PackageNotFoundError:
            errors.append(f"缺少 {package}")
            continue
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
        if not match or tuple(map(int, match.groups())) < minimum:
            errors.append(f"{package} {version} 不满足 Qwen 2.1 要求")
    return errors


def validate_bundle(path):
    path = Path(path)
    missing = [name for name in REQUIRED_FILES if not (path / name).is_file() or not (path / name).stat().st_size]
    if missing:
        raise ValueError("Qwen 2.1 模型目录不完整：" + "、".join(missing))
    config = json.loads((path / "model_index.json").read_text(encoding="utf-8"))
    if config.get("_class_name") != "QwenImage21Pipeline":
        raise ValueError("此目录不是 Qwen Image 2.1 模型，不能使用旧版 Qwen 权重。")
    if config.get("sample_sigmas") != list(SAMPLE_SIGMAS):
        raise ValueError("模型缺少官方 Turbo 8 步采样表，拒绝使用其他采样表。")
    return path


def model_directory():
    import folder_paths

    explicit = os.environ.get("RPP_QWEN_IMAGE21_MODEL_DIR", "").strip()
    if explicit:
        return Path(explicit)
    roots = folder_paths.get_folder_paths("diffusers")
    candidates = [Path(root) / MODEL_NAME for root in roots]
    candidates.append(Path(folder_paths.models_dir) / "diffusers" / MODEL_NAME)
    return next((path for path in candidates if (path / "model_index.json").is_file()), candidates[-1])


def readiness_errors():
    errors = dependency_errors()
    try:
        validate_bundle(model_directory())
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
    return errors


class RandomPhotoPromptQwenImage21Turbo:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model_name": ([MODEL_NAME] if not readiness_errors() else [],),
            "prompt": ("STRING", {"multiline": True}),
            "width": ("INT", {"default": 864, "min": 32, "max": 1536, "step": 32}),
            "height": ("INT", {"default": 1536, "min": 32, "max": 1536, "step": 32}),
            "seed": ("INT", {"default": 0, "min": 0, "max": 18446744073709551615}),
            "research_only": ("BOOLEAN", {"default": True}),
        }}

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "generate"
    CATEGORY = "Random Photo/Research"
    DESCRIPTION = "Qwen Research License: non-commercial research/evaluation only. Requires official 2.1 Turbo Diffusers bundle."

    def generate(self, model_name, prompt, width, height, seed, research_only):
        if research_only is not True:
            raise ValueError("此接入仅用于非商业研究评估；商业用途需另获官方授权。")
        if model_name != MODEL_NAME:
            raise ValueError("此工作流仅支持官方 Qwen-Image-2.1-Turbo。")
        if not str(prompt).strip():
            raise ValueError("必须填写正向提示词。")
        if any(type(v) is not int or v < 32 or v > 1536 or v % 32 for v in (width, height)):
            raise ValueError("Qwen 图片宽高必须是 32 的倍数，且最长边不超过 1536。")
        errors = readiness_errors()
        if errors:
            raise RuntimeError("；".join(errors))

        # Only Windows execution imports inference libraries; registration is lightweight.
        import inspect
        import numpy as np
        import torch
        import comfy.model_management as management
        import comfy.utils
        from diffusers import QwenImage21Pipeline

        if not torch.cuda.is_available():
            raise RuntimeError("Qwen 推理仅允许在远端 CUDA GPU 执行。")
        signature = inspect.signature(QwenImage21Pipeline.__call__)
        if not {"use_kv_cache", "sigmas", "callback_on_step_end"}.issubset(signature.parameters):
            raise RuntimeError("Diffusers 缺少 Qwen 2.1 Turbo 所需 API，请安装包含 PR #14950 的官方源码版本。")
        management.throw_exception_if_processing_interrupted()
        management.unload_all_models()
        management.soft_empty_cache()
        progress = comfy.utils.ProgressBar(8)

        def on_step_end(pipe, step, timestep, callback_kwargs):
            management.throw_exception_if_processing_interrupted()
            progress.update_absolute(step + 1, 8)
            return callback_kwargs

        pipe = None
        result = None
        try:
            pipe = QwenImage21Pipeline.from_pretrained(
                str(validate_bundle(model_directory())), dtype=torch.bfloat16,
                local_files_only=True,
            )
            # Sequential offload bounds GPU residency on the 24 GB 4090.
            pipe.enable_sequential_cpu_offload()
            if hasattr(pipe.vae, "enable_tiling"):
                pipe.vae.enable_tiling()
            # No steps/sigmas override: the checkpoint owns the Turbo schedule and CFG default.
            result = pipe(
                prompt=prompt, width=width, height=height, use_kv_cache=True,
                generator=torch.Generator("cpu").manual_seed(seed),
                callback_on_step_end=on_step_end,
            )
            management.throw_exception_if_processing_interrupted()
            image = result.images[0]
            image = image.convert("RGBA" if image.mode == "RGBA" else "RGB")
            if image.size != (width, height):
                raise RuntimeError(f"Qwen 返回尺寸 {image.size} 与请求尺寸 {(width, height)} 不一致。")
            output = torch.from_numpy(np.array(image, dtype=np.float32) / 255.0).unsqueeze(0)
            return (output,)
        finally:
            try:
                if pipe is not None:
                    pipe.remove_all_hooks()
            finally:
                result = None
                pipe = None
                gc.collect()
                management.soft_empty_cache()
