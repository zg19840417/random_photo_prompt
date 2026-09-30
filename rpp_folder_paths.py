"""Mac 服务所需的目录接口；不加载 ComfyUI，也不创建或搬移目录。"""
import os
from pathlib import Path
from types import ModuleType


class LocalFolderPaths(ModuleType):
    def __init__(self, root):
        super().__init__("folder_paths")
        self.base_path = str(Path(root).expanduser().resolve())
        self.models_dir = str(Path(self.base_path) / "models")

    def get_output_directory(self):
        return str(Path(self.base_path) / "output")

    def get_input_directory(self):
        return str(Path(self.base_path) / "input")

    def get_directory_by_type(self, directory_type):
        if directory_type in {"input", "output", "temp"}:
            return str(Path(self.base_path) / directory_type)
        return None

    def get_filename_list(self, category):
        subdirs = {"loras": ("loras",), "diffusion_models": ("unet", "diffusion_models")}
        if category not in subdirs:
            raise KeyError(category)
        extensions = {".ckpt", ".pt", ".pt2", ".bin", ".pth", ".safetensors", ".pkl", ".sft"}
        names = set()
        for subdir in subdirs[category]:
            root = Path(self.models_dir) / subdir
            visited = set()
            for directory, children, files in os.walk(root, followlinks=True):
                real = Path(directory).resolve()
                if real in visited:
                    children[:] = []
                    continue
                visited.add(real)
                children[:] = [name for name in children if name != ".git"]
                for name in files:
                    if Path(name).suffix.lower() in extensions:
                        names.add(str((Path(directory) / name).relative_to(root)))
        return sorted(names)
