from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sync_kaggle_notebook import write_notebook

DEFAULT_METADATA = Path("kaggle/kernel-metadata.json")
DEFAULT_SOURCE = Path("kaggle/illustrious_xl_style_lora.py")
DEFAULT_NOTEBOOK = Path("kaggle/illustrious_xl_style_lora.ipynb")
DEFAULT_ARTIFACT_ROOT = Path("artifacts")
STATUS_PATTERN = re.compile(r"kernel status:\s*([a-z0-9_-]+)", re.IGNORECASE)
ACTIVE_STATUSES = {"queued", "pending", "running"}
SUCCESS_STATUSES = {"complete", "completed"}
FAILURE_STATUSES = {"error", "failed", "cancelled", "canceled"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def parse_status(output: str) -> str | None:
    match = STATUS_PATTERN.search(output)
    if match:
        return match.group(1).lower()
    lowered = output.lower()
    for status in sorted(ACTIVE_STATUSES | SUCCESS_STATUSES | FAILURE_STATUSES):
        if status in lowered:
            return status
    return None


def run_kaggle(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = ["kaggle", *args]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"Kaggle CLI failed ({completed.returncode}): {detail}")
    return completed


def kernel_status(kernel_id: str, *, allow_missing: bool = False) -> str | None:
    completed = run_kaggle("kernels", "status", kernel_id, check=False)
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    if completed.returncode != 0:
        lowered = output.lower()
        if allow_missing and ("404" in lowered or "not found" in lowered):
            return None
        raise RuntimeError(f"Unable to query Kaggle kernel status: {output.strip()}")
    status = parse_status(output)
    if status is None:
        raise RuntimeError(f"Unrecognized Kaggle kernel status output: {output.strip()}")
    return status


def wait_for_terminal_status(
    kernel_id: str,
    *,
    poll_interval: float,
    timeout: float,
    manifest_path: Path,
    manifest: dict[str, object],
) -> str:
    deadline = time.monotonic() + timeout
    while True:
        status = kernel_status(kernel_id)
        manifest["kernel_status"] = status
        manifest["updated_at"] = utc_now()
        write_json_atomic(manifest_path, manifest)
        print(f"Kaggle kernel status: {status}")
        if status in SUCCESS_STATUSES | FAILURE_STATUSES:
            return status
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for Kaggle kernel {kernel_id}")
        time.sleep(poll_interval)


def load_metadata(path: Path, machine_shape: str | None = None) -> dict[str, object]:
    metadata = json.loads(path.read_text(encoding="utf-8"))
    required = {"id", "code_file", "language", "kernel_type"}
    missing = sorted(required - metadata.keys())
    if missing:
        raise ValueError(f"kernel metadata is missing: {', '.join(missing)}")
    if metadata.get("is_private") is not True:
        raise ValueError("Kaggle training kernel must remain private")
    if metadata.get("enable_gpu") is not True:
        raise ValueError("Kaggle training kernel must enable GPU")
    if machine_shape:
        metadata["machine_shape"] = machine_shape
    return metadata


def validate_downloaded_output(run_dir: Path) -> tuple[Path, dict[str, object]]:
    result_paths = list(run_dir.rglob("shikishi-training-result.json"))
    if len(result_paths) != 1:
        raise RuntimeError(
            f"Expected exactly one shikishi-training-result.json, found {len(result_paths)}"
        )
    metadata = json.loads(result_paths[0].read_text(encoding="utf-8"))
    artifact = metadata.get("artifact")
    if not isinstance(artifact, dict):
        raise RuntimeError("Training result does not contain artifact metadata")
    artifact_path_value = artifact.get("path")
    expected_size = artifact.get("size_bytes")
    expected_sha = artifact.get("sha256")
    if not isinstance(artifact_path_value, str):
        raise RuntimeError("Training result artifact path is invalid")
    if not isinstance(expected_size, int) or expected_size <= 0:
        raise RuntimeError("Training result artifact size is invalid")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise RuntimeError("Training result artifact SHA-256 is invalid")

    basename = Path(artifact_path_value).name
    candidates = [path for path in run_dir.rglob(basename) if path.is_file()]
    for candidate in candidates:
        if candidate.stat().st_size != expected_size:
            continue
        if sha256_file(candidate).lower() == expected_sha.lower():
            return candidate, metadata
    raise RuntimeError(f"Downloaded LoRA does not match training result metadata: {basename}")


@contextmanager
def exclusive_run_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".kaggle-run.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"Another Kaggle orchestration run is active: {lock_path}") from exc
    try:
        os.write(descriptor, f"pid={os.getpid()} started={utc_now()}\n".encode())
        os.close(descriptor)
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def prepare_staging(
    staging: Path,
    *,
    source: Path,
    notebook_template: Path,
    metadata_path: Path,
    machine_shape: str | None,
) -> tuple[str, str]:
    metadata = load_metadata(metadata_path, machine_shape)
    notebook_name = str(metadata["code_file"])
    output_notebook = staging / notebook_name
    write_notebook(source, notebook_template, output_notebook)
    (staging / "kernel-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return str(metadata["id"]), sha256_file(output_notebook)


def run(args: argparse.Namespace) -> int:
    if not os.getenv("KAGGLE_API_TOKEN"):
        raise RuntimeError("KAGGLE_API_TOKEN is required")
    if shutil.which("kaggle") is None:
        raise RuntimeError("Kaggle CLI is not installed")

    artifact_root: Path = args.artifact_root
    machine_shape = os.getenv("KAGGLE_MACHINE_SHAPE") or None
    with exclusive_run_lock(artifact_root):
        metadata = load_metadata(args.metadata, machine_shape)
        kernel_id = str(metadata["id"])
        current_status = kernel_status(kernel_id, allow_missing=True)
        if current_status in ACTIVE_STATUSES:
            raise RuntimeError(
                f"Kaggle kernel already has an active run ({current_status}); "
                "refusing to replace it"
            )

        run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        run_dir = artifact_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        manifest_path = run_dir / "orchestration.json"
        source_sha = sha256_file(args.source)
        manifest: dict[str, object] = {
            "run_id": run_id,
            "kernel_id": kernel_id,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "state": "preparing",
            "machine_shape": machine_shape or metadata.get("machine_shape"),
            "source_sha256": source_sha,
            "git_revision": os.getenv("SHIKISHI_GIT_REVISION", "unknown"),
        }
        write_json_atomic(manifest_path, manifest)

        with tempfile.TemporaryDirectory(prefix="kaggle-stage-", dir=artifact_root) as temp_dir:
            staging = Path(temp_dir)
            kernel_id, notebook_sha = prepare_staging(
                staging,
                source=args.source,
                notebook_template=args.notebook,
                metadata_path=args.metadata,
                machine_shape=machine_shape,
            )
            manifest["notebook_sha256"] = notebook_sha
            manifest["state"] = "submitting"
            write_json_atomic(manifest_path, manifest)
            run_kaggle("kernels", "push", "-p", str(staging))

        manifest["state"] = "running"
        manifest["submitted_at"] = utc_now()
        write_json_atomic(manifest_path, manifest)
        status = wait_for_terminal_status(
            kernel_id,
            poll_interval=args.poll_interval,
            timeout=args.timeout,
            manifest_path=manifest_path,
            manifest=manifest,
        )
        if status not in SUCCESS_STATUSES:
            logs = run_kaggle("kernels", "logs", kernel_id, check=False)
            diagnostic = (logs.stdout or logs.stderr)[-8000:]
            (run_dir / "kaggle-failure.log").write_text(diagnostic, encoding="utf-8")
            manifest["state"] = "failed"
            manifest["finished_at"] = utc_now()
            write_json_atomic(manifest_path, manifest)
            raise RuntimeError(f"Kaggle kernel finished with status: {status}")

        manifest["state"] = "downloading"
        write_json_atomic(manifest_path, manifest)
        run_kaggle("kernels", "output", kernel_id, "-p", str(run_dir), "-o")
        artifact_path, result_metadata = validate_downloaded_output(run_dir)
        manifest["state"] = "complete"
        manifest["finished_at"] = utc_now()
        manifest["verified_artifact"] = str(artifact_path.relative_to(run_dir))
        artifact_metadata = result_metadata["artifact"]
        if not isinstance(artifact_metadata, dict):
            raise RuntimeError("Training result artifact metadata changed after validation")
        manifest["artifact_sha256"] = artifact_metadata["sha256"]
        write_json_atomic(manifest_path, manifest)
        print(f"Verified Kaggle artifact: {artifact_path}")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit, monitor, download, and verify Shikishi Kaggle training."
    )
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--notebook", type=Path, default=DEFAULT_NOTEBOOK)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--poll-interval", type=float, default=30.0)
    parser.add_argument("--timeout", type=float, default=6 * 60 * 60)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
