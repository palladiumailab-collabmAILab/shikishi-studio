from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CELL_MARKER = "# %%"
MARKDOWN_MARKER = "# %% [markdown]"


def source_cells(source: str) -> list[dict[str, Any]]:
    blocks: list[tuple[str, list[str]]] = []
    cell_type = "code"
    lines: list[str] = []

    def flush() -> None:
        nonlocal lines
        if lines:
            blocks.append((cell_type, lines))
        lines = []

    for line in source.splitlines():
        if line in {CELL_MARKER, MARKDOWN_MARKER}:
            flush()
            cell_type = "markdown" if line == MARKDOWN_MARKER else "code"
            continue
        lines.append(line)
    flush()

    cells: list[dict[str, Any]] = []
    for block_type, block_lines in blocks:
        rendered: list[str] = []
        for line in block_lines:
            if block_type == "markdown":
                if line == "#":
                    line = ""
                elif line.startswith("# "):
                    line = line[2:]
                elif line.startswith("#"):
                    line = line[1:]
            rendered.append(f"{line}\n")
        if block_type == "code":
            cells.append(
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": rendered,
                }
            )
        else:
            cells.append({"cell_type": "markdown", "metadata": {}, "source": rendered})
    return cells


def build_notebook(source_path: Path, template_path: Path) -> dict[str, Any]:
    notebook = json.loads(template_path.read_text(encoding="utf-8"))
    notebook["cells"] = source_cells(source_path.read_text(encoding="utf-8"))
    return notebook


def _normalized_cells(cells: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(str(cell.get("cell_type")), "".join(cell.get("source", [])).rstrip()) for cell in cells]


def synchronized(source_path: Path, notebook_path: Path) -> bool:
    actual = json.loads(notebook_path.read_text(encoding="utf-8"))
    expected = source_cells(source_path.read_text(encoding="utf-8"))
    actual_cells = actual.get("cells")
    if not isinstance(actual_cells, list):
        return False
    return _normalized_cells(actual_cells) == _normalized_cells(expected)


def write_notebook(source_path: Path, template_path: Path, output_path: Path) -> None:
    notebook = build_notebook(source_path, template_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(notebook, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize Kaggle notebook cells from Python.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("kaggle/illustrious_xl_style_lora.py"),
    )
    parser.add_argument(
        "--notebook",
        type=Path,
        default=Path("kaggle/illustrious_xl_style_lora.ipynb"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        if synchronized(args.source, args.notebook):
            print("Kaggle notebook is synchronized.")
            return 0
        print("Kaggle notebook is out of sync.")
        return 1

    output = args.output or args.notebook
    write_notebook(args.source, args.notebook, output)
    print(f"Synchronized Kaggle notebook: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
