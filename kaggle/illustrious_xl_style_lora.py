# ruff: noqa: E402
# %% [markdown]
# # Illustrious XL v2.0 style LoRA training — Kaggle
#
# In Kaggle Notebook settings, select **Accelerator: GPU**. Add these private
# Kaggle Datasets as Inputs before running:
#
# - the Shikishi dataset archive, mounted at `/kaggle/input/shikishi-ixy-style`;
# - optionally, Illustrious-XL-v2.0.safetensors, mounted at
#   `/kaggle/input/illustrious-xl-v20`. If omitted, enable Internet and the
#   notebook downloads the public model itself.
#
# To resume after a prior run, add the previous Notebook output (or an exported
# state Dataset) as another Input. Only states accompanied by this notebook's
# matching run manifest are eligible for resume.

# %%
import os
from pathlib import Path

DATASET_NAME = "ixy_style_v2"
TRAINING_VARIANT = "locon"
TRAINING_PROFILES = {
    "linear": {
        "output_name": "ixy_style_v2_linear_r16_a8_s42",
        "experiment_id": "ixy-style-v2-linear-r16-a8-s42",
        "learning_rate": "8e-5",
        "network_args": (),
    },
    "locon": {
        "output_name": "ixy_style_v2_locon_r16_a8_c8_ca4_s42",
        "experiment_id": "ixy-style-v2-locon-r16-a8-c8-ca4-s42",
        "learning_rate": "6e-5",
        "network_args": ("conv_dim=8", "conv_alpha=4"),
    },
}
if TRAINING_VARIANT not in TRAINING_PROFILES:
    raise RuntimeError(f"Unsupported TRAINING_VARIANT: {TRAINING_VARIANT}")
TRAINING_PROFILE = TRAINING_PROFILES[TRAINING_VARIANT]
OUTPUT_NAME = str(TRAINING_PROFILE["output_name"])
EXPERIMENT_ID = str(TRAINING_PROFILE["experiment_id"])
RUN_ID = os.environ.get("SHIKISHI_RUN_ID", EXPERIMENT_ID).strip()
if not RUN_ID or len(RUN_ID) > 100:
    raise RuntimeError("SHIKISHI_RUN_ID must contain 1 to 100 characters")
BASE_MODEL_REPOSITORY = "OnomaAIResearch/Illustrious-XL-v2.0"
# Pin the Hugging Face snapshot used when a Kaggle Input model is not supplied.
# This is the repository commit returned by the Hugging Face model API on
# 2026-08-25.  Update deliberately together with the experiment identity.
BASE_MODEL_REVISION = "69459c1fe6f46db41ab31e6114f05acc0e06bcaa"
MIN_FINAL_LORA_BYTES = 1024 * 1024
INPUT_ROOT = Path("/kaggle/input")
# Kaggle may mount account-owned Dataset inputs under either /kaggle/input or
# /kaggle/input/datasets/<account>.  Support both layouts.
ACCOUNT_INPUT_ROOT = INPUT_ROOT / "datasets" / "palladiumailab"
DATASET_INPUT_DIR = next(
    (
        path
        for path in (
            INPUT_ROOT / "shikishi-ixy-style-v2-goal-v1",
            ACCOUNT_INPUT_ROOT / "shikishi-ixy-style-v2-goal-v1",
        )
        if path.is_dir()
    ),
    INPUT_ROOT / "shikishi-ixy-style-v2-goal-v1",
)
MODEL_INPUT_DIR = next(
    (
        path
        for path in (INPUT_ROOT / "illustrious-xl-v20", ACCOUNT_INPUT_ROOT / "illustrious-xl-v20")
        if path.is_dir()
    ),
    INPUT_ROOT / "illustrious-xl-v20",
)
DATASET_ARCHIVE = DATASET_INPUT_DIR / f"{DATASET_NAME}-style-lora.zip"
INPUT_BASE_MODEL = MODEL_INPUT_DIR / "Illustrious-XL-v2.0.safetensors"
WORK_ROOT = Path("/kaggle/working")
BASE_MODEL = (
    INPUT_BASE_MODEL
    if INPUT_BASE_MODEL.is_file()
    else WORK_ROOT / "Illustrious-XL-v2.0.safetensors"
)
BASE_MODEL_SOURCE = "kaggle_input" if INPUT_BASE_MODEL.is_file() else "huggingface_download"
OUTPUT_DIR = WORK_ROOT / "outputs" / OUTPUT_NAME
LOG_DIR = WORK_ROOT / "logs"
AUTOMATION_DIR = WORK_ROOT / "automation"
AUTOMATION_STATUS = AUTOMATION_DIR / "status.json"
FIRST_EPOCH_TARGET = AUTOMATION_DIR / "first_epoch_15_percent.json"
RUN_MANIFEST = OUTPUT_DIR / "shikishi-training-run.json"
RESULT_METADATA = OUTPUT_DIR / "shikishi-training-result.json"
RUN_MANIFEST_NAME = RUN_MANIFEST.name
FIRST_EPOCH_TARGET_RATIO = 0.15
MAX_AUTOMATIC_TRAIN_ATTEMPTS = 3

SD_SCRIPTS_REF = "v0.9.1"
SD_SCRIPTS_COMMIT = "8f4ee8fc343b047965cd8976fca65c3a35b7593a"

# %%
import json
import shutil
import sys
from datetime import UTC, datetime
from hashlib import sha256

import torch


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def write_json_atomically(path: Path, payload: dict[str, object]) -> None:
    """Publish JSON only after its complete contents have been written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(path)


def training_identity() -> dict[str, str]:
    """Return the stable attributes required for a compatible resume."""
    return {
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "dataset_name": DATASET_NAME,
        "training_variant": TRAINING_VARIANT,
        "output_name": OUTPUT_NAME,
        "base_model_repository": BASE_MODEL_REPOSITORY,
        "base_model_revision": BASE_MODEL_REVISION,
        "base_model_source": BASE_MODEL_SOURCE,
        "base_model_sha256": BASE_MODEL_SHA256,
        "sd_scripts_commit": SD_SCRIPTS_COMMIT,
    }


def manifest_matches_experiment(path: Path) -> bool:
    """Reject untrusted, malformed, or incompatible resume manifests."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return all(payload.get(key) == value for key, value in training_identity().items())


def write_run_manifest() -> None:
    """Create or validate the local run ownership marker before saving state."""
    if RUN_MANIFEST.is_file():
        require(
            manifest_matches_experiment(RUN_MANIFEST),
            f"出力先に互換性のないrun manifestがあります: {RUN_MANIFEST}",
        )
        return
    write_json_atomically(
        RUN_MANIFEST,
        {
            **training_identity(),
            "created_at": datetime.now(UTC).isoformat(),
        },
    )


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_final_artifact(path: Path, *, previous_sha256: str | None = None) -> dict[str, object]:
    """Validate a newly written LoRA instead of trusting a trainer exit code."""
    require(path.is_file(), f"最終LoRA成果物が見つかりません: {path}")
    size_bytes = path.stat().st_size
    require(
        size_bytes >= MIN_FINAL_LORA_BYTES,
        f"最終LoRA成果物が小さすぎます: {path} ({size_bytes} bytes)",
    )
    artifact_sha256 = sha256_file(path)
    require(
        artifact_sha256 != previous_sha256,
        f"最終LoRA成果物が今回の試行で更新されていません: {path}",
    )
    return {
        "path": str(path),
        "size_bytes": size_bytes,
        "sha256": artifact_sha256,
    }


def save_training_result(*, artifact: dict[str, object], attempts_used: int) -> None:
    """Persist the evidence used to declare this training run successful."""
    write_json_atomically(
        RESULT_METADATA,
        {
            **training_identity(),
            "run_manifest": str(RUN_MANIFEST),
            "completed_at": datetime.now(UTC).isoformat(),
            "attempts_used": attempts_used,
            "artifact": artifact,
        },
    )


def write_automation_status(phase: str, **details: object) -> None:
    """Persist machine-readable progress for unattended Kaggle runs."""
    payload = {
        "phase": phase,
        "updated_at": datetime.now(UTC).isoformat(),
        "target_first_epoch_ratio": FIRST_EPOCH_TARGET_RATIO,
        **details,
    }
    write_json_atomically(AUTOMATION_STATUS, payload)


require(
    torch.cuda.is_available(),
    "GPU が見つかりません。Kaggle Settings で Accelerator を GPU に変更してください。",
)
gpu = torch.cuda.get_device_properties(0)
vram_gib = gpu.total_memory / 1024**3
gpu_capability = torch.cuda.get_device_capability(0)
free_gib = shutil.disk_usage(WORK_ROOT).free / 1024**3
require(
    vram_gib >= 14,
    f"GPU メモリが不足しています: {gpu.name} ({vram_gib:.1f} GiB)。P100/T4 以上を選んでください。",
)
require(
    gpu_capability >= (7, 0),
    f"GPU 世代が非対応です: {gpu.name} (sm_{gpu_capability[0]}{gpu_capability[1]})。"
    "Kaggle Settings で GPU T4 x2 を選んでください。",
)
require(free_gib >= 15, f"Kaggle作業領域の空きが不足しています: {free_gib:.1f} GiB")
MOUNTED_TRAIN_DIRS = sorted(DATASET_INPUT_DIR.glob(f"[1-9]*_{DATASET_NAME}_*"))
require(
    DATASET_ARCHIVE.is_file()
    or any(DATASET_INPUT_DIR.glob(f"{DATASET_ARCHIVE.name}.part*"))
    or MOUNTED_TRAIN_DIRS,
    f"データセットInputが見つかりません: {DATASET_ARCHIVE}、分割ZIP、または"
    f" {DATASET_INPUT_DIR}/<repeat>_{DATASET_NAME}_*",
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
write_automation_status("preflight_complete", gpu=gpu.name, free_gib=round(free_gib, 2))
print(f"GPU: {gpu.name} ({vram_gib:.1f} GiB)")
print(f"GPU capability: sm_{gpu_capability[0]}{gpu_capability[1]}")
print(f"Working disk free: {free_gib:.1f} GiB")

# %%
import shlex
import subprocess
from collections.abc import Callable


def run(
    label: str,
    *command: str,
    line_handler: Callable[[str], None] | None = None,
    check: bool = True,
) -> int:
    log_path = LOG_DIR / f"{DATASET_NAME}-{label}.log"
    print("+", shlex.join(command))
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            log_file.write(line)
            log_file.flush()
            if line_handler is not None:
                line_handler(line)
        return_code = process.wait()
    if check and return_code:
        raise RuntimeError(f"{label} が失敗しました (exit {return_code})。ログ: {log_path}")
    return return_code


repository = WORK_ROOT / "sd-scripts"
if repository.is_dir():
    completed = subprocess.run(
        ("git", "-C", str(repository), "rev-parse", "HEAD"), capture_output=True, text=True
    )
    if completed.returncode or completed.stdout.strip() != SD_SCRIPTS_COMMIT:
        shutil.rmtree(repository)
if not repository.is_dir():
    run(
        "clone-sd-scripts",
        "git",
        "clone",
        "--depth",
        "1",
        "--branch",
        SD_SCRIPTS_REF,
        "https://github.com/kohya-ss/sd-scripts.git",
        str(repository),
    )

actual_commit = subprocess.check_output(
    ("git", "-C", str(repository), "rev-parse", "HEAD"), text=True
).strip()
require(actual_commit == SD_SCRIPTS_COMMIT, f"sd-scripts の版が想定外です: {actual_commit}")
os.chdir(repository)
run(
    "install-sd-scripts",
    sys.executable,
    "-m",
    "pip",
    "install",
    "--quiet",
    "--disable-pip-version-check",
    "-r",
    "requirements.txt",
)
# Kaggle Python 3.12 image ships NumPy 2, while this stable sd-scripts stack
# imports TensorFlow binaries built against NumPy 1.x.
run(
    "install-numpy-compat",
    sys.executable,
    "-m",
    "pip",
    "install",
    "--quiet",
    "--disable-pip-version-check",
    "--force-reinstall",
    "numpy<2",
)
run("configure-accelerate", "accelerate", "config", "default", "--mixed_precision", "fp16")
run("verify-trainer", sys.executable, "sdxl_train_network.py", "--help")

if not BASE_MODEL.is_file():
    from huggingface_hub import hf_hub_download

    hf_hub_download(
        repo_id=BASE_MODEL_REPOSITORY,
        filename=BASE_MODEL.name,
        local_dir=BASE_MODEL.parent,
        revision=BASE_MODEL_REVISION,
    )
require(
    BASE_MODEL.is_file() and BASE_MODEL.stat().st_size > 6 * 1024**3,
    f"モデルが見つかりません、または不完全です: {BASE_MODEL}。"
    "Internetを有効にするか、モデルInputを追加してください。",
)
BASE_MODEL_SHA256 = sha256_file(BASE_MODEL)
write_run_manifest()
write_automation_status(
    "base_model_ready",
    base_model_source=BASE_MODEL_SOURCE,
    base_model_sha256=BASE_MODEL_SHA256,
    base_model_revision=BASE_MODEL_REVISION,
)

# %%
import re
import zipfile

if MOUNTED_TRAIN_DIRS:
    # Kaggle Input is read-only. Stage image/caption pairs under /kaggle/working
    # so all trainer caches and state files are guaranteed to be writable.
    EXTRACTED_ROOT = WORK_ROOT / "datasets" / f"{DATASET_NAME}_prepared"
    write_automation_status(
        "staging_dataset", source=[str(path) for path in MOUNTED_TRAIN_DIRS]
    )
    for mounted_train_dir in MOUNTED_TRAIN_DIRS:
        staged_train_dir = EXTRACTED_ROOT / mounted_train_dir.name
        staged_train_dir.mkdir(parents=True, exist_ok=True)
        source_files = [
            path
            for path in mounted_train_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".txt"}
        ]
        require(source_files, f"画像またはcaptionが見つかりません: {mounted_train_dir}")
        for source_path in source_files:
            destination_path = staged_train_dir / source_path.name
            if (
                not destination_path.is_file()
                or destination_path.stat().st_size != source_path.stat().st_size
            ):
                shutil.copy2(source_path, destination_path)
    VALIDATION_DATA_DIR = DATASET_INPUT_DIR / "validation"
    print(f"Dataset staged in writable storage: {EXTRACTED_ROOT}")
else:
    part_pattern = re.compile(re.escape(DATASET_ARCHIVE.name) + r"\.part(\d+)$")
    parts = sorted(
        (
            (int(match.group(1)), path)
            for path in DATASET_INPUT_DIR.iterdir()
            if (match := part_pattern.match(path.name))
        ),
        key=lambda item: item[0],
    )
    if parts:
        part_numbers = [number for number, _ in parts]
        require(
            part_numbers == list(range(1, len(parts) + 1)),
            f"分割ZIPの番号が連続していません: {part_numbers}",
        )
        source_archive = WORK_ROOT / DATASET_ARCHIVE.name
        temporary_archive = source_archive.with_suffix(".partial")
        with temporary_archive.open("wb") as destination:
            for _, part in parts:
                require(part.stat().st_size > 0, f"空の分割ZIPがあります: {part.name}")
                with part.open("rb") as source:
                    shutil.copyfileobj(source, destination, length=16 * 1024 * 1024)
        temporary_archive.replace(source_archive)
    else:
        source_archive = DATASET_ARCHIVE

    with zipfile.ZipFile(source_archive) as archive:
        bad_member = next(
            (
                member.filename
                for member in archive.infolist()
                if Path(member.filename).is_absolute() or ".." in Path(member.filename).parts
            ),
            None,
        )
        require(bad_member is None, f"危険なZIPパスを検出しました: {bad_member}")
        corrupt_member = archive.testzip()
        require(corrupt_member is None, f"データセットZIPが壊れています: {corrupt_member}")
        EXTRACTED_ROOT = WORK_ROOT / "datasets" / f"{DATASET_NAME}_prepared"
        EXTRACTED_ROOT.mkdir(parents=True, exist_ok=True)
        archive.extractall(EXTRACTED_ROOT)
# sd-scripts expects the parent directory whose repeat-named child folder
# contains the images (for example, ``1_ixy_style/``), not that child itself.
TRAIN_DATA_DIR = EXTRACTED_ROOT
if not MOUNTED_TRAIN_DIRS:
    VALIDATION_DATA_DIR = EXTRACTED_ROOT / "validation"
image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
TRAIN_IMAGE_DIRS = sorted(EXTRACTED_ROOT.glob(f"[1-9]*_{DATASET_NAME}_*"))
images = [
    path
    for train_image_dir in TRAIN_IMAGE_DIRS
    for path in train_image_dir.iterdir()
    if path.suffix.lower() in image_extensions
]
validation_images = (
    [path for path in VALIDATION_DATA_DIR.iterdir() if path.suffix.lower() in image_extensions]
    if VALIDATION_DATA_DIR.is_dir()
    else []
)
missing_captions = [
    path.name
    for path in images
    if not path.with_suffix(".txt").is_file()
    or not path.with_suffix(".txt").read_text(encoding="utf-8").strip()
]
require(images, f"画像が見つかりません: {TRAIN_IMAGE_DIRS}")
require(
    not missing_captions, f"タグ .txt がない画像があります（先頭10件）: {missing_captions[:10]}"
)
require(TRAIN_IMAGE_DIRS, "学習用フォルダ <repeat>_<dataset_name>_<group> がありません。")
print(f"Dataset ready: {len(images)} train images, {len(validation_images)} validation images")
write_automation_status(
    "dataset_ready",
    train_images=len(images),
    validation_images=len(validation_images),
    train_data_dir=str(TRAIN_DATA_DIR),
)

# %%
import math
import re
import time

os.chdir(repository)
state_pattern = re.compile(rf"^{re.escape(OUTPUT_NAME)}-step(\d+)-state$")


def compatible_resume_roots() -> list[Path]:
    """Find only output directories explicitly marked for this experiment.

    Kaggle mounts unrelated datasets beneath ``/kaggle/input``.  Searching
    every ``*-state`` directory can resume an incompatible optimizer state, so
    the manifest is the ownership and compatibility boundary.
    """
    manifest_paths = [RUN_MANIFEST]
    if INPUT_ROOT.is_dir():
        manifest_paths.extend(INPUT_ROOT.rglob(RUN_MANIFEST_NAME))
    roots: list[Path] = []
    for manifest_path in manifest_paths:
        if manifest_path.is_file() and manifest_matches_experiment(manifest_path):
            root = manifest_path.parent
            if root not in roots:
                roots.append(root)
    return roots


def find_latest_state() -> tuple[int, Path] | None:
    saved_states = sorted(
        (
            (int(match.group(1)), path)
            for search_root in compatible_resume_roots()
            for path in search_root.glob(f"{OUTPUT_NAME}-step*-state")
            if path.is_dir()
            and (match := state_pattern.match(path.name))
            and (path / "optimizer.bin").is_file()
        ),
        reverse=True,
    )
    return saved_states[0] if saved_states else None


class TrainingMonitor:
    """Parse trainer output and persist the unattended-run acceptance signal."""

    step_pattern = re.compile(r"steps:.*\|\s*(\d+)/(\d+)")

    def __init__(self, batches_per_epoch: int) -> None:
        self.batches_per_epoch = batches_per_epoch
        self.target_step = math.ceil(batches_per_epoch * FIRST_EPOCH_TARGET_RATIO)
        self.last_persisted_step = -1

    def observe(self, line: str) -> None:
        match = self.step_pattern.search(line)
        if match is None:
            return
        global_step = int(match.group(1))
        if global_step == self.last_persisted_step:
            return
        first_epoch_step = min(global_step, self.batches_per_epoch)
        first_epoch_ratio = first_epoch_step / self.batches_per_epoch
        reached = first_epoch_step >= self.target_step
        if reached or global_step % 10 == 0:
            write_automation_status(
                "training",
                global_step=global_step,
                first_epoch_step=first_epoch_step,
                first_epoch_batches=self.batches_per_epoch,
                first_epoch_ratio=round(first_epoch_ratio, 6),
                first_epoch_target_step=self.target_step,
                first_epoch_target_reached=reached,
            )
            self.last_persisted_step = global_step
        if reached and not FIRST_EPOCH_TARGET.is_file():
            FIRST_EPOCH_TARGET.write_text(
                json.dumps(
                    {
                        "reached": True,
                        "global_step": global_step,
                        "first_epoch_step": first_epoch_step,
                        "first_epoch_batches": self.batches_per_epoch,
                        "first_epoch_ratio": first_epoch_ratio,
                        "reached_at": datetime.now(UTC).isoformat(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(
                "AUTOMATION_TARGET_REACHED: "
                f"first epoch {first_epoch_step}/{self.batches_per_epoch} "
                f"({first_epoch_ratio:.2%})"
            )


base_train_command = (
    "accelerate",
    "launch",
    "--num_processes=1",
    "--num_machines=1",
    "--num_cpu_threads_per_process=2",
    "sdxl_train_network.py",
    f"--pretrained_model_name_or_path={BASE_MODEL}",
    f"--train_data_dir={TRAIN_DATA_DIR}",
    f"--output_dir={OUTPUT_DIR}",
    f"--output_name={OUTPUT_NAME}",
    "--network_module=networks.lora",
    "--network_dim=16",
    "--network_alpha=8",
    "--network_dropout=0.05",
    "--scale_weight_norms=1.0",
    "--resolution=1024,1024",
    "--enable_bucket",
    "--min_bucket_reso=512",
    "--max_bucket_reso=1536",
    "--bucket_reso_steps=64",
    "--train_batch_size=1",
    "--max_train_steps=2400",
    f"--learning_rate={TRAINING_PROFILE['learning_rate']}",
    "--optimizer_type=AdamW",
    "--lr_scheduler=cosine",
    "--lr_warmup_steps=120",
    "--min_snr_gamma=5",
    "--mixed_precision=fp16",
    "--save_precision=fp16",
    "--cache_latents",
    "--cache_text_encoder_outputs",
    "--gradient_checkpointing",
    "--no_half_vae",
    "--max_data_loader_n_workers=0",
    "--network_train_unet_only",
    "--caption_extension=.txt",
    "--save_model_as=safetensors",
    "--save_every_n_steps=300",
    "--save_last_n_steps_state=1",
    "--save_state",
    "--seed=42",
)
if TRAINING_PROFILE["network_args"]:
    base_train_command += ("--network_args", *TRAINING_PROFILE["network_args"])
monitor = TrainingMonitor(len(images))
final_artifact = OUTPUT_DIR / f"{OUTPUT_NAME}.safetensors"
last_failure = "trainer did not run"
for attempt in range(1, MAX_AUTOMATIC_TRAIN_ATTEMPTS + 1):
    previous_artifact_sha256 = sha256_file(final_artifact) if final_artifact.is_file() else None
    latest_state = find_latest_state()
    train_command = base_train_command
    if latest_state is None:
        print(f"Training attempt {attempt}: new run")
    else:
        resume_step, resume_state = latest_state
        train_command += (f"--resume={resume_state}",)
        print(f"Training attempt {attempt}: resume from step {resume_step} ({resume_state})")
    write_automation_status(
        "training_start",
        attempt=attempt,
        max_attempts=MAX_AUTOMATIC_TRAIN_ATTEMPTS,
        resume_step=latest_state[0] if latest_state else None,
    )
    return_code = run(
        f"train-attempt-{attempt}",
        *train_command,
        line_handler=monitor.observe,
        check=False,
    )
    if return_code == 0:
        try:
            artifact = verify_final_artifact(
                final_artifact,
                previous_sha256=previous_artifact_sha256,
            )
            save_training_result(artifact=artifact, attempts_used=attempt)
        except RuntimeError as error:
            last_failure = str(error)
            write_automation_status(
                "training_output_invalid",
                attempt=attempt,
                return_code=return_code,
                error=last_failure,
                retry_available=attempt < MAX_AUTOMATIC_TRAIN_ATTEMPTS,
            )
        else:
            write_automation_status(
                "training_complete",
                attempts_used=attempt,
                artifact=artifact,
                result_metadata=str(RESULT_METADATA),
            )
            break
    else:
        last_failure = f"trainer exit {return_code}"
    write_automation_status(
        "training_retry_pending",
        attempt=attempt,
        return_code=return_code,
        error=last_failure,
        retry_available=attempt < MAX_AUTOMATIC_TRAIN_ATTEMPTS,
    )
    if attempt == MAX_AUTOMATIC_TRAIN_ATTEMPTS:
        raise RuntimeError(
            f"学習が成功条件を満たさないまま{MAX_AUTOMATIC_TRAIN_ATTEMPTS}回終了しました: "
            f"{last_failure}。"
            f"ログ: {LOG_DIR / f'{DATASET_NAME}-train-attempt-{attempt}.log'}"
        )
    time.sleep(10)

# %% [markdown]
# Publish the Notebook output with **Save Version** after training. To resume in
# a later session, add that Notebook output as an Input, then run this notebook
# again. Kaggle inputs are read-only; only `/kaggle/working` becomes an output.
