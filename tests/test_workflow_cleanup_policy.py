import json
from pathlib import Path

from workflow_cleanup_policy import ensure_model_cleanup, remove_mobile_auxiliary_outputs


PLUGIN_DIR = Path(__file__).resolve().parents[1]


def test_visual_auxiliary_nodes_are_removed_but_gpu_cleanup_is_retained():
    workflow = {
        "compare": {"class_type": "Image Comparer (rgthree)", "inputs": {}},
        "cleanup": {"class_type": "easy cleanGpuUsed", "inputs": {"anything": ["image", 0]}},
        "image": {"class_type": "ImageScale", "inputs": {}},
    }

    removed = remove_mobile_auxiliary_outputs(workflow)

    assert removed == 1
    assert "compare" not in workflow
    assert "cleanup" in workflow


def test_purge_nodes_always_unload_models_and_cache():
    workflow = {
        "purge": {
            "class_type": "LayerUtility: PurgeVRAM V2",
            "inputs": {"purge_cache": False, "purge_models": False, "anything": ["sample", 0]},
        },
        "cleanup": {"class_type": "easy cleanGpuUsed", "inputs": {"anything": ["image", 0]}},
    }

    cleanup_nodes = ensure_model_cleanup(workflow)

    assert cleanup_nodes == 2
    assert workflow["purge"]["inputs"]["purge_cache"] is True
    assert workflow["purge"]["inputs"]["purge_models"] is True


def test_double_sample_template_keeps_terminal_cleanup_node():
    workflow = json.loads((PLUGIN_DIR / "mobile_workflow_api_2.json").read_text(encoding="utf-8"))

    remove_mobile_auxiliary_outputs(workflow)
    cleanup_nodes = ensure_model_cleanup(workflow)

    assert cleanup_nodes >= 1
    assert any(node.get("class_type") == "easy cleanGpuUsed" for node in workflow.values())


def test_double_sample_template_releases_the_first_model_before_the_second_stage():
    workflow = json.loads((PLUGIN_DIR / "mobile_workflow_api_2.json").read_text(encoding="utf-8"))

    stage_cleanup = workflow["597"]

    assert stage_cleanup["class_type"] == "LayerUtility: PurgeVRAM V2"
    assert stage_cleanup["inputs"] == {
        "anything": ["501", 0],
        "purge_cache": True,
        "purge_models": True,
    }
    assert workflow["502"]["inputs"]["samples"] == ["597", 0]


def test_every_mobile_workflow_has_cleanup_after_policy_application():
    paths = sorted(PLUGIN_DIR.glob("mobile_workflow_api*.json"))
    assert paths

    for path in paths:
        workflow = json.loads(path.read_text(encoding="utf-8"))
        remove_mobile_auxiliary_outputs(workflow)
        cleanup_nodes = ensure_model_cleanup(workflow)

        assert cleanup_nodes >= 1, path.name
        assert any(
            node.get("class_type") in {"easy cleanGpuUsed", "LayerUtility: PurgeVRAM V2"}
            for node in workflow.values()
        ), path.name


def test_minimax_h3_disables_optional_sageattention_runtime():
    workflow = json.loads((PLUGIN_DIR / "minimax_h3_workflow_api.json").read_text(encoding="utf-8"))
    loader = next(node for node in workflow.values() if node.get("class_type") == "DiffusionModelLoaderKJ")

    assert loader["inputs"]["sage_attention"] == "disabled"


def test_minimax_h3_uses_the_mobile_runtime_limits():
    workflow = json.loads((PLUGIN_DIR / "minimax_h3_workflow_api.json").read_text(encoding="utf-8"))
    scheduler = next(node for node in workflow.values() if node.get("class_type") == "BasicScheduler")
    resolution = next(node for node in workflow.values() if node.get("class_type") == "ResolutionSelector")

    assert scheduler["inputs"]["steps"] == 12
    assert resolution["inputs"]["megapixels"] == 0.23
