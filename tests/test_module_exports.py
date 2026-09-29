import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("rpp_globals", "rpp_utils", "rpp_prompts", "rpp_workflow", "rpp_remote", "rpp_mobile", "rpp_nodes", "rpp_endpoints")


class ModuleExportTests(unittest.TestCase):
    """__init__.py 用 `from rpp_x import *` 聚合模块：__all__ 里有不存在的名字，整个节点就会导入失败。"""

    def test_every_all_entry_exists_in_its_module(self):
        for name in MODULES:
            tree = ast.parse((ROOT / f"{name}.py").read_text(encoding="utf-8"))
            defined = set()
            exported = None
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    defined.add(node.name)
                elif isinstance(node, ast.Assign):
                    defined |= {target.id for target in node.targets if isinstance(target, ast.Name)}
                    if any(getattr(target, "id", "") == "__all__" for target in node.targets):
                        value = node.value.args[0] if isinstance(node.value, ast.Call) else node.value
                        exported = ast.literal_eval(value)
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    defined.add(node.target.id)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    defined |= {(alias.asname or alias.name).split(".")[0] for alias in node.names}
            with self.subTest(module=name):
                self.assertIsNotNone(exported)
                self.assertEqual([entry for entry in exported if entry != "__all__" and entry not in defined], [])


if __name__ == "__main__":
    unittest.main()
