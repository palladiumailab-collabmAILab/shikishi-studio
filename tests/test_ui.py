"""Tests for validation at the local generation UI boundary."""

from pathlib import Path

import pytest

from shikishi.ui import generate_image


def test_generate_image_rejects_blank_prompt(tmp_path: Path) -> None:
    """A missing prompt fails before model dependencies are loaded."""
    with pytest.raises(ValueError, match="Prompt"):
        generate_image(
            str(tmp_path / "base.safetensors"),
            str(tmp_path / "lora.safetensors"),
            "",
            "",
            1024,
            1024,
            20,
            5,
            42,
        )


def test_generate_image_rejects_missing_model_file(tmp_path: Path) -> None:
    """Invalid filesystem paths have an actionable message."""
    with pytest.raises(ValueError, match="Base model"):
        generate_image(
            str(tmp_path / "base.safetensors"),
            str(tmp_path / "lora.safetensors"),
            "test",
            "",
            1024,
            1024,
            20,
            5,
            42,
        )


def test_generate_image_rejects_dimensions_not_divisible_by_eight(tmp_path: Path) -> None:
    """SDXL's latent dimensions are validated before inference starts."""
    base = tmp_path / "base.safetensors"
    lora = tmp_path / "lora.safetensors"
    base.write_bytes(b"test")
    lora.write_bytes(b"test")

    with pytest.raises(ValueError, match="divisible"):
        generate_image(str(base), str(lora), "test", "", 1025, 1024, 20, 5, 42)
