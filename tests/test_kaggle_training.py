# ruff: noqa: E402, I001
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from kaggle_training import (
    exclusive_run_lock,
    load_metadata,
    parse_status,
    validate_downloaded_output,
)
from sync_kaggle_notebook import source_cells, synchronized


def test_parse_kaggle_status() -> None:
    assert parse_status("Kernel status: RUNNING") == "running"
    assert parse_status("Kernel status: COMPLETE") == "complete"
    assert parse_status("Kernel status: ERROR") == "error"


def test_kernel_metadata_is_private_gpu_training() -> None:
    metadata = load_metadata(PROJECT_ROOT / "kaggle" / "kernel-metadata.json")

    assert metadata["id"] == "palladiumailab/notebook27d1a07f12"
    assert metadata["is_private"] is True
    assert metadata["enable_gpu"] is True
    assert metadata["dataset_sources"] == [
        "palladiumailab/shikishi-ixy-style-v2-goal-v1"
    ]


def test_downloaded_output_must_match_result_sha(tmp_path: Path) -> None:
    artifact = tmp_path / "outputs" / "model.safetensors"
    artifact.parent.mkdir(parents=True)
    content = b"verified-lora"
    artifact.write_bytes(content)
    result = artifact.parent / "shikishi-training-result.json"
    result.write_text(
        json.dumps(
            {
                "artifact": {
                    "path": "/kaggle/working/outputs/model.safetensors",
                    "size_bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            }
        ),
        encoding="utf-8",
    )

    verified, _ = validate_downloaded_output(tmp_path)
    assert verified == artifact

    artifact.write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="does not match"):
        validate_downloaded_output(tmp_path)


def test_run_lock_rejects_parallel_orchestration(tmp_path: Path) -> None:
    with exclusive_run_lock(tmp_path):
        with pytest.raises(RuntimeError, match="Another Kaggle orchestration run"):
            with exclusive_run_lock(tmp_path):
                pass


def test_python_notebook_sync_matches_committed_notebook() -> None:
    source = PROJECT_ROOT / "kaggle" / "illustrious_xl_style_lora.py"
    notebook = PROJECT_ROOT / "kaggle" / "illustrious_xl_style_lora.ipynb"

    assert source_cells(source.read_text(encoding="utf-8"))
    assert synchronized(source, notebook)
