import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_rpp_prompts():
    folder_paths = types.ModuleType("folder_paths")
    folder_paths.models_dir = tempfile.gettempdir()
    folder_paths.get_output_directory = tempfile.gettempdir
    folder_paths.get_input_directory = tempfile.gettempdir
    folder_paths.get_filename_list = lambda _category: []
    sys.modules.setdefault("folder_paths", folder_paths)
    server = types.ModuleType("server")

    class PromptServer:
        instance = types.SimpleNamespace()

    server.PromptServer = PromptServer
    sys.modules.setdefault("server", server)
    import rpp_prompts

    return rpp_prompts


class PromptPassthroughTests(unittest.TestCase):
    """提交给模型的提示词不再被任何改写层处理：手填、反推和自动生成的文字都原样使用。"""

    def test_custom_prompt_text_is_submitted_verbatim(self):
        rpp_prompts = _load_rpp_prompts()
        custom = "她克制微笑，一只手轻点嘴角，胸线边缘的蕾丝，或者看向别处，\\n\\n第二段"
        self.assertEqual(rpp_prompts._prompt_text({"positive_prompt": custom, "compact_prompt": custom}), custom)

    def test_mobile_prompt_equals_engine_prompt_for_the_same_seed(self):
        rpp_prompts = _load_rpp_prompts()
        from prompt_engine import generate_prompt_items

        for scale, shot, orientation, aspect in (("bold", "half_body", "横图", "landscape"), ("normal", "full_body", "竖图", "portrait"), ("bold_no_outfit", "head_shot", "方图", "square")):
            with self.subTest(scale=scale, shot=shot):
                item, resolution = rpp_prompts._build_mobile_prompt_for_scope(scale, rpp_prompts.MOBILE_SCOPE_PRESETS[shot], "passthrough", "modern", orientation)
                engine = generate_prompt_items(1, {"scale": scale, "shot": shot, "era": "modern", "aspect": aspect, "width": resolution["width"], "height": resolution["height"]}, "passthrough")[0]
                self.assertEqual(rpp_prompts._prompt_text(item), engine["positive_prompt"])


if __name__ == "__main__":
    unittest.main()
