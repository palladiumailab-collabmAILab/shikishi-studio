# Style LoRA dataset preparation

This tool prepares a **new** SDXL / Illustrious XL Style LoRA dataset. It never
edits, moves, or deletes the source images or their captions.

## Setup (Windows)

```powershell
cd C:\Users\palla\Documents\shikishi\dataset
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

The current ixy source is a flat directory containing matching image and
`.txt` files, so it can be used directly:

```powershell
python prepare_dataset.py `
  --input C:\Users\palla\Documents\shikishi-artifacts\prepared-datasets\ixy_style\1_ixy_style `
  --output .\processed `
  --config .\config.yaml
```

It also accepts this optional layout:

```text
source/
├── images/
└── tags/
```

Use `--overwrite` only to replace a previous `processed/` output. Source data
is never a deletion target.

## What the tool does

- verifies every image with Pillow, and excludes only unreadable, too-small,
  or extreme-aspect-ratio files;
- removes only byte-for-byte duplicate images automatically;
- calculates pHash and writes near-duplicate pairs to
  `reports/duplicate_candidates.csv`; candidates remain in the dataset;
- writes uncertain quality signals (JPEG compression, blank area, manga /
  sketch-related source tags) to `reports/review_candidates.csv`;
- normalizes captions, removes configured metadata tags, and preserves visual
  content tags such as subject, composition, clothing, and background;
- splits train/validation deterministically while keeping pHash-connected
  candidate groups in the same split;
- copies original image bytes without cropping, resizing, or re-encoding.

## Tag categories

Danbooru-style text captions do not by themselves say whether an arbitrary tag
is an artist, character, or copyright. To avoid unsafe guesswork, this tool
only removes the explicit entries in `remove_tags` by default. Provide a CSV
through `tag_category_file` with `tag,category` columns to remove all tags in
the configured `remove_categories` reliably.

## Outputs

```text
processed/
├── train/                 # image + same-name .txt caption
└── validation/            # image + same-name .txt caption

reports/
├── dataset_report.md
├── tag_frequency.csv
├── duplicate_candidates.csv
├── excluded_images.csv
├── review_candidates.csv
├── split_manifest.csv
└── processing.log
```

Tune all thresholds and tag rules in `config.yaml`. Captions are not randomly
changed; configure caption shuffle and tag dropout (for example `0.1`) in the
training tool instead.
