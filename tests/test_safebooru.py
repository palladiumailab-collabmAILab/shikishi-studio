"""Tests for Safebooru download command construction."""

from pathlib import Path

import pytest

from shikishi.safebooru import DownloadConfig, build_command


def test_build_command_uses_tag_directory_and_archive(tmp_path: Path) -> None:
    """Each tag receives a dedicated directory and duplicate-download archive."""
    output_dir = tmp_path / "downloads"
    config = DownloadConfig(tag="ixy", page=4, output_dir=output_dir)

    command = build_command(config)

    tag_directory = output_dir / "ixy"
    assert command[:3] == ["gallery-dl", "--directory", str(tag_directory.resolve())]
    assert str((tag_directory / "gallery-dl-archive.sqlite").resolve()) in command
    assert "--write-tags" in command
    assert command[-1] == "https://safebooru.donmai.us/posts?page=4&tags=ixy"


def test_build_command_encodes_tag_and_adds_dry_run(tmp_path: Path) -> None:
    """Tags are URL-encoded while their safe directory name is preserved."""
    config = DownloadConfig(tag="blue sky", page=1, output_dir=tmp_path, dry_run=True)

    command = build_command(config)

    assert "--simulate" in command
    assert command[-1] == "https://safebooru.donmai.us/posts?page=1&tags=blue+sky"
    assert str((tmp_path / "blue sky").resolve()) in command


@pytest.mark.parametrize("tag, page", [("", 4), ("  ", 4), ("ixy", 0)])
def test_config_rejects_invalid_input(tmp_path: Path, tag: str, page: int) -> None:
    """Invalid source input is rejected before invoking gallery-dl."""
    with pytest.raises(ValueError):
        DownloadConfig(tag=tag, page=page, output_dir=tmp_path)
