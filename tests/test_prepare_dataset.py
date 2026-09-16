"""Regression tests for the standalone dataset preparation script."""

from pathlib import Path

from dataset.prepare_dataset import prepare


def test_empty_dataset_writes_zero_safe_reports(tmp_path: Path) -> None:
    """An input with no usable images still produces actionable reports."""
    source = tmp_path / "source"
    output = tmp_path / "processed"
    source.mkdir()
    config = tmp_path / "config.yaml"
    config.write_text(
        "\n".join(
            [
                "min_width: 512",
                "min_height: 512",
                "min_aspect_ratio: 0.25",
                "max_aspect_ratio: 4.0",
                "validation_ratio: 0.05",
                "random_seed: 42",
                "dominant_tag_warning_ratio: 0.75",
                "duplicate:",
                "  phash_enabled: false",
                "quality_filter:",
                "  enabled: false",
            ]
        ),
        encoding="utf-8",
    )

    prepare(source, output, config, overwrite=False)

    report = output.parent / "reports" / "dataset_report.md"
    frequencies = output.parent / "reports" / "tag_frequency.csv"
    assert "Valid images: 0" in report.read_text(encoding="utf-8")
    assert "No tag exceeded" in report.read_text(encoding="utf-8")
    assert frequencies.read_text(encoding="utf-8") == "tag,count,ratio\n"
