"""Command-line entry point for shikishi."""

from argparse import ArgumentParser
from pathlib import Path

from shikishi.dataset import DatasetConfig, export_dataset, package_dataset, split_archive
from shikishi.safebooru import DownloadConfig, download_images
from shikishi.style_curation import StyleCurationConfig, export_curated_style_dataset
from shikishi.tag_restore import TagRestoreConfig, restore_tags


def build_parser() -> ArgumentParser:
    """Create the command-line interface."""
    parser = ArgumentParser(prog="shikishi")
    subparsers = parser.add_subparsers(dest="command")

    download_parser = subparsers.add_parser(
        "download-safebooru-images", help="Download images from a Safebooru tag."
    )
    download_parser.add_argument("--tag", required=True, help="Safebooru tag, for example ixy")
    download_parser.add_argument("--page", type=int, default=4, help="Results page to download.")
    download_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("downloads"),
        help="Parent directory; a tag subdirectory is created inside it.",
    )
    download_parser.add_argument(
        "--dry-run", action="store_true", help="List matches without downloading files."
    )

    restore_parser = subparsers.add_parser(
        "restore-safebooru-tags",
        help="Restore missing tag sidecars from Safebooru for existing Danbooru filenames.",
    )
    restore_parser.add_argument("--images-dir", required=True, type=Path)
    restore_parser.add_argument(
        "--request-delay",
        type=float,
        default=0.6,
        help="Seconds to wait after each public API request.",
    )

    dataset_parser = subparsers.add_parser(
        "export-style-dataset", help="Create a Kohya-compatible SDXL style-LoRA dataset."
    )
    dataset_parser.add_argument("--source-dir", required=True, type=Path)
    dataset_parser.add_argument("--output-dir", type=Path, default=Path("datasets"))
    dataset_parser.add_argument("--dataset-name", required=True)
    dataset_parser.add_argument("--trigger-word", required=True)
    dataset_parser.add_argument("--repeats", type=int, default=10)

    package_parser = subparsers.add_parser(
        "package-style-dataset", help="Create a ZIP file for Google Colab from an exported dataset."
    )
    package_parser.add_argument("--output-dir", type=Path, default=Path("datasets"))
    package_parser.add_argument("--dataset-name", required=True)
    package_parser.add_argument("--trigger-word", default="package-only")
    package_parser.add_argument("--repeats", type=int, default=10)

    split_parser = subparsers.add_parser(
        "split-colab-archive", help="Split a dataset ZIP into Google Drive upload-sized parts."
    )
    split_parser.add_argument("--archive", required=True, type=Path)
    split_parser.add_argument("--part-size-mb", type=int, default=95)

    curation_parser = subparsers.add_parser(
        "curate-style-dataset",
        help="Create a traceable goal-focused style-LoRA dataset from review manifests.",
    )
    curation_parser.add_argument("--source-dir", required=True, type=Path)
    curation_parser.add_argument("--curation-labels", required=True, type=Path)
    curation_parser.add_argument("--split-manifest", required=True, type=Path)
    curation_parser.add_argument("--clustering-manifest", required=True, type=Path)
    curation_parser.add_argument("--output-dir", required=True, type=Path)
    curation_parser.add_argument("--dataset-name", default="ixy_style_v2")
    curation_parser.add_argument("--trigger-word", default="ixy_style_v2")
    curation_parser.add_argument("--composite-aux-limit", type=int, default=128)
    curation_parser.add_argument("--diversity-aux-limit", type=int, default=48)
    curation_parser.add_argument("--seed", type=int, default=42)

    ui_parser = subparsers.add_parser(
        "serve-ui", help="Launch the optional local Illustrious XL generation UI."
    )
    ui_parser.add_argument("--host", default="127.0.0.1")
    ui_parser.add_argument("--port", type=int, default=7860)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run the requested command."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "download-safebooru-images":
        download_config = DownloadConfig(
            tag=args.tag,
            page=args.page,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
        )
        download_images(download_config)
        return

    if args.command == "restore-safebooru-tags":
        result = restore_tags(
            TagRestoreConfig(args.images_dir, request_delay_seconds=args.request_delay)
        )
        print(
            "Tag restoration complete: "
            f"restored={result.restored}, existing={result.skipped_existing}, "
            f"unrecognized={result.skipped_unrecognized}, missing={result.missing_posts}"
        )
        return

    if args.command == "export-style-dataset":
        dataset_config = DatasetConfig(
            source_dir=args.source_dir,
            output_dir=args.output_dir,
            dataset_name=args.dataset_name,
            trigger_word=args.trigger_word,
            repeats=args.repeats,
        )
        count = export_dataset(dataset_config)
        destination = dataset_config.training_directory.resolve()
        print(f"Exported {count} image/caption pair(s) to {destination}")
        return

    if args.command == "package-style-dataset":
        dataset_config = DatasetConfig(
            source_dir=Path("."),
            output_dir=args.output_dir,
            dataset_name=args.dataset_name,
            trigger_word=args.trigger_word,
            repeats=args.repeats,
        )
        archive = package_dataset(dataset_config)
        print(f"Created Colab archive: {archive.resolve()}")
        return

    if args.command == "split-colab-archive":
        parts = split_archive(args.archive, args.part_size_mb)
        print(f"Created {len(parts)} archive part(s).")
        return

    if args.command == "curate-style-dataset":
        counts = export_curated_style_dataset(
            StyleCurationConfig(
                source_dir=args.source_dir,
                curation_labels=args.curation_labels,
                split_manifest=args.split_manifest,
                clustering_manifest=args.clustering_manifest,
                output_dir=args.output_dir,
                dataset_name=args.dataset_name,
                trigger_word=args.trigger_word,
                composite_aux_limit=args.composite_aux_limit,
                diversity_aux_limit=args.diversity_aux_limit,
                seed=args.seed,
            )
        )
        print(f"Curated style dataset created: {counts}")
        return

    if args.command == "serve-ui":
        from shikishi.ui import launch_ui

        launch_ui(args.host, args.port)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
