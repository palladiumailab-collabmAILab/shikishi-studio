"""Tests for resumable restoration of missing Safebooru tag files."""

from pathlib import Path

import pytest

from shikishi.tag_restore import TagRestoreConfig, post_id_from_path, restore_tags


def test_post_id_from_path_extracts_gallery_dl_danbooru_id() -> None:
    """Downloaded filenames identify the public post used for restoration."""
    assert post_id_from_path(Path("danbooru_12345_hash.png")) == 12345
    assert post_id_from_path(Path("custom-name.png")) is None


def test_restore_tags_creates_missing_caption_and_preserves_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Restoration is safe to run repeatedly on a partially completed directory."""
    image = tmp_path / "danbooru_12345_hash.png"
    image.write_bytes(b"image")
    existing = tmp_path / "danbooru_2_hash.jpg"
    existing.write_bytes(b"image")
    existing.with_suffix(".txt").write_text("manual tag\n", encoding="utf-8")
    monkeypatch.setattr("shikishi.tag_restore.fetch_tags", lambda _: "tag_one, tag_two")
    monkeypatch.setattr("shikishi.tag_restore.time.sleep", lambda _: None)

    result = restore_tags(TagRestoreConfig(tmp_path))

    assert result.restored == 1
    assert result.skipped_existing == 1
    assert (tmp_path / "danbooru_12345_hash.txt").read_text(encoding="utf-8") == (
        "tag_one, tag_two\n"
    )


def test_fetch_tags_rejects_missing_directory(tmp_path: Path) -> None:
    """Invalid source directories are rejected before any network request."""
    with pytest.raises(ValueError, match="does not exist"):
        TagRestoreConfig(tmp_path / "missing")
