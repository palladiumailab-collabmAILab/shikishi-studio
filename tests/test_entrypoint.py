"""Tests for the command-line entry point."""

from pytest import CaptureFixture

from shikishi.__main__ import main


def test_main_prints_help_without_a_command(capsys: CaptureFixture[str]) -> None:
    """The initial command provides command help."""
    main([])

    captured = capsys.readouterr()
    assert "download-safebooru-images" in captured.out
