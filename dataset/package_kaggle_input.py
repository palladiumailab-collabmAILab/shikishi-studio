"""Package a prepared Style LoRA dataset as a Kaggle Notebook input ZIP."""

from __future__ import annotations

import argparse
import csv
import zipfile
from pathlib import Path


def add_tree(archive: zipfile.ZipFile, source: Path, destination_root: Path) -> int:
    count = 0
    for path in sorted(source.iterdir()):
        if path.is_file():
            archive.write(path, destination_root / path.name)
            count += 1
    return count


def package(processed: Path, reports: Path, output: Path, dataset_name: str) -> None:
    train = processed / "train"
    validation = processed / "validation"
    if not train.is_dir() or not validation.is_dir():
        raise FileNotFoundError("Expected processed/train and processed/validation directories.")
    manifest = reports / "split_manifest.csv"
    if not manifest.is_file():
        raise FileNotFoundError("Missing reports/split_manifest.csv.")
    with manifest.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if sum(row["split"] == "train" for row in rows) == 0:
        raise ValueError("The split manifest contains no training images.")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        train_files = add_tree(archive, train, Path(f"1_{dataset_name}"))
        validation_files = add_tree(archive, validation, Path("validation"))
        for report in sorted(reports.glob("*.csv")):
            archive.write(report, Path("reports") / report.name)
        archive.write(reports / "dataset_report.md", Path("reports/dataset_report.md"))
    print(f"Created: {output}")
    print(f"Training files: {train_files}")
    print(f"Validation files: {validation_files}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed", type=Path, required=True)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-name", default="ixy_style")
    args = parser.parse_args()
    package(args.processed, args.reports, args.output, args.dataset_name)


if __name__ == "__main__":
    main()
