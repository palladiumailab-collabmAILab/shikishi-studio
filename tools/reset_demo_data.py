from __future__ import annotations

import argparse
import shutil
from pathlib import Path

DEMO_DATA_DIRECTORIES = ("generated", "reference-images")


def reset_demo_data(root: Path, *, apply: bool) -> tuple[int, int]:
    files = 0
    bytes_removed = 0
    for directory_name in DEMO_DATA_DIRECTORIES:
        directory = root / directory_name
        if not directory.exists():
            continue
        for path in directory.iterdir():
            if path.is_symlink() or path.is_file():
                files += 1
                if path.is_file():
                    bytes_removed += path.stat().st_size
                if apply:
                    path.unlink()
            elif path.is_dir():
                nested_files = [item for item in path.rglob("*") if item.is_file()]
                files += len(nested_files)
                bytes_removed += sum(item.stat().st_size for item in nested_files)
                if apply:
                    shutil.rmtree(path)
    return files, bytes_removed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete generated and reference demo data without touching model caches."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--yes", action="store_true", help="Actually delete the demo data.")
    args = parser.parse_args()

    files, bytes_removed = reset_demo_data(args.root, apply=args.yes)
    action = "Removed" if args.yes else "Would remove"
    print(f"{action} {files} files ({bytes_removed} bytes).")
    if not args.yes:
        print("Dry run only. Re-run with --yes to delete generated/ and reference-images/ data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
