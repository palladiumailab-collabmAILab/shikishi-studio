from __future__ import annotations

import ast
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from types import CodeType
from typing import cast

import pytest

PROJECT_ROOT = Path(__file__).parents[1]
NOTEBOOK_PATH = PROJECT_ROOT / "colab" / "illustrious_xl_style_lora.ipynb"
SOURCE_PATH = PROJECT_ROOT / "colab" / "illustrious_xl_style_lora.py"
KAGGLE_NOTEBOOK_PATH = PROJECT_ROOT / "kaggle" / "illustrious_xl_style_lora.ipynb"
KAGGLE_SOURCE_PATH = PROJECT_ROOT / "kaggle" / "illustrious_xl_style_lora.py"


def _load_kaggle_artifact_helpers(tmp_path: Path) -> dict[str, object]:
    """Load pure helpers from the standalone notebook source without running GPU setup."""
    source_tree = ast.parse(KAGGLE_SOURCE_PATH.read_text(encoding="utf-8"))
    helper_names = {
        "compatible_resume_roots",
        "find_latest_state",
        "manifest_matches_experiment",
        "require",
        "save_training_result",
        "sha256_file",
        "training_identity",
        "verify_final_artifact",
        "write_json_atomically",
    }
    helper_nodes: list[ast.stmt] = []
    for node in source_tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in helper_names:
            helper_nodes.append(node)
    compiled: CodeType = compile(
        ast.fix_missing_locations(ast.Module(body=helper_nodes, type_ignores=[])),
        str(KAGGLE_SOURCE_PATH),
        "exec",
    )
    namespace: dict[str, object] = {
        "BASE_MODEL_REPOSITORY": "OnomaAIResearch/Illustrious-XL-v2.0",
        "BASE_MODEL_REVISION": "69459c1fe6f46db41ab31e6114f05acc0e06bcaa",
        "BASE_MODEL_SHA256": "base-model-sha256",
        "BASE_MODEL_SOURCE": "huggingface_download",
        "DATASET_NAME": "ixy_style",
        "EXPERIMENT_ID": "ixy-style-illustrious-xl-v20-lora-d8-a4-s42",
        "INPUT_ROOT": tmp_path / "input",
        "MIN_FINAL_LORA_BYTES": 1024 * 1024,
        "OUTPUT_DIR": tmp_path / "output",
        "OUTPUT_NAME": "ixy_style",
        "TRAINING_VARIANT": "linear",
        "Path": Path,
        "RESULT_METADATA": tmp_path / "output" / "shikishi-training-result.json",
        "RUN_MANIFEST": tmp_path / "output" / "shikishi-training-run.json",
        "RUN_MANIFEST_NAME": "shikishi-training-run.json",
        "RUN_ID": "ixy-style-run",
        "SD_SCRIPTS_COMMIT": "8f4ee8fc343b047965cd8976fca65c3a35b7593a",
        "UTC": UTC,
        "datetime": datetime,
        "json": json,
        "re": re,
        "sha256": sha256,
    }
    exec(compiled, namespace)
    namespace["state_pattern"] = re.compile(r"^ixy_style-step(\d+)-state$")
    return namespace


def test_colab_source_is_valid_python() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")

    ast.parse(source)


def test_notebook_has_matching_code_cells() -> None:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    notebook_code = "\n".join(
        "".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"
    )
    source = SOURCE_PATH.read_text(encoding="utf-8")

    for required_text in (
        'SD_SCRIPTS_COMMIT = "8f4ee8fc343b047965cd8976fca65c3a35b7593a"',
        "torch.cuda.is_available()",
        "archive.testzip()",
        "--cache_text_encoder_outputs",
        "--save_every_n_steps=200",
        "--save_last_n_steps_state=1",
        "--resume={resume_state}",
        'run("train", *train_command)',
    ):
        assert required_text in source
        assert required_text in notebook_code


def test_cached_text_outputs_do_not_shuffle_captions() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")

    assert "--cache_text_encoder_outputs" in source
    assert "--shuffle_caption" not in source


def test_kaggle_notebook_uses_read_only_inputs_and_resumable_output() -> None:
    source = KAGGLE_SOURCE_PATH.read_text(encoding="utf-8")
    notebook = json.loads(KAGGLE_NOTEBOOK_PATH.read_text(encoding="utf-8"))
    notebook_code = "\n".join(
        "".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"
    )

    ast.parse(source)
    for required_text in (
        'INPUT_ROOT = Path("/kaggle/input")',
        'WORK_ROOT = Path("/kaggle/working")',
        "DATASET_ARCHIVE.name}.part*",
        'EXTRACTED_ROOT = WORK_ROOT / "datasets" / f"{DATASET_NAME}_prepared"',
        '"staging_dataset", source=',
        "first_epoch_target_reached=reached",
        '"AUTOMATION_TARGET_REACHED: "',
        "MAX_AUTOMATIC_TRAIN_ATTEMPTS = 3",
        'BASE_MODEL_REVISION = "69459c1fe6f46db41ab31e6114f05acc0e06bcaa"',
        "revision=BASE_MODEL_REVISION",
        "BASE_MODEL_SHA256 = sha256_file(BASE_MODEL)",
        "previous_sha256=previous_artifact_sha256",
        "save_training_result(artifact=artifact, attempts_used=attempt)",
        "RUN_MANIFEST_NAME",
        "for attempt in range(1, MAX_AUTOMATIC_TRAIN_ATTEMPTS + 1):",
        '"--save_last_n_steps_state=1"',
        'f"--resume={resume_state}"',
        '"--network_dim=16"',
        '"--network_alpha=8"',
        '"--max_train_steps=2400"',
        '"--resolution=1024,1024"',
        '"--min_snr_gamma=5"',
    ):
        assert required_text in source
        assert required_text in notebook_code

    assert "--cache_latents_to_disk" not in source
    assert "--cache_text_encoder_outputs_to_disk" not in source


def test_kaggle_artifact_verification_rejects_empty_output_and_records_sha256(
    tmp_path: Path,
) -> None:
    helpers = _load_kaggle_artifact_helpers(tmp_path)
    artifact_path = tmp_path / "output" / "ixy_style.safetensors"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"")

    verify_final_artifact = cast(Callable[..., dict[str, object]], helpers["verify_final_artifact"])
    with pytest.raises(RuntimeError, match="小さすぎます"):
        verify_final_artifact(artifact_path)

    content = b"x" * (1024 * 1024)
    artifact_path.write_bytes(content)
    metadata = verify_final_artifact(artifact_path)

    assert metadata == {
        "path": str(artifact_path),
        "size_bytes": len(content),
        "sha256": sha256(content).hexdigest(),
    }
    with pytest.raises(RuntimeError, match="更新されていません"):
        verify_final_artifact(artifact_path, previous_sha256=metadata["sha256"])
    save_training_result = cast(Callable[..., None], helpers["save_training_result"])
    save_training_result(artifact=metadata, attempts_used=2)
    saved_metadata = json.loads((tmp_path / "output" / "shikishi-training-result.json").read_text())
    assert saved_metadata["artifact"] == metadata
    assert saved_metadata["attempts_used"] == 2
    assert saved_metadata["base_model_revision"] == "69459c1fe6f46db41ab31e6114f05acc0e06bcaa"
    assert saved_metadata["base_model_sha256"] == "base-model-sha256"


def test_kaggle_resume_ignores_unrelated_states_without_matching_manifest(tmp_path: Path) -> None:
    helpers = _load_kaggle_artifact_helpers(tmp_path)
    input_root = tmp_path / "input"
    unrelated_state = input_root / "unrelated" / "ixy_style-step9999-state"
    unrelated_state.mkdir(parents=True)
    (unrelated_state / "optimizer.bin").write_bytes(b"state")

    compatible_root = input_root / "previous-output" / "outputs" / "ixy_style"
    compatible_root.mkdir(parents=True)
    training_identity = cast(Callable[[], dict[str, str]], helpers["training_identity"])
    identity = training_identity()
    (compatible_root / "shikishi-training-run.json").write_text(json.dumps(identity))
    compatible_state = compatible_root / "ixy_style-step200-state"
    compatible_state.mkdir()
    (compatible_state / "optimizer.bin").write_bytes(b"state")

    wrong_run_root = input_root / "wrong-run" / "outputs" / "ixy_style"
    wrong_run_root.mkdir(parents=True)
    wrong_identity = {**identity, "run_id": "different-run"}
    (wrong_run_root / "shikishi-training-run.json").write_text(json.dumps(wrong_identity))
    wrong_run_state = wrong_run_root / "ixy_style-step999-state"
    wrong_run_state.mkdir()
    (wrong_run_state / "optimizer.bin").write_bytes(b"state")

    find_latest_state = cast(Callable[[], tuple[int, Path] | None], helpers["find_latest_state"])
    assert find_latest_state() == (200, compatible_state)
