# %% [markdown]
# # Illustrious XL v2.0 style LoRA training
#
# Before running: Colab's **Runtime** menu must show a GPU (T4, L4, or better).
# Run every cell in order. The notebook stops early with an actionable error if
# the runtime, uploaded dataset, model download, or trainer installation is not
# ready. Training and installation logs are saved under `MyDrive/shikishi/logs/`.

# %%
from google.colab import drive  # type: ignore[import-not-found]

drive.mount("/content/drive")

from pathlib import Path

DRIVE_ROOT = Path("/content/drive/MyDrive/shikishi")
DATASET_NAME = "ixy_style"
OUTPUT_NAME = DATASET_NAME
DATASET_ARCHIVE = DRIVE_ROOT / f"{DATASET_NAME}-colab.zip"
BASE_MODEL = Path("/content/Illustrious-XL-v2.0.safetensors")
OUTPUT_DIR = DRIVE_ROOT / "outputs" / OUTPUT_NAME
LOG_DIR = DRIVE_ROOT / "logs"

# This exact upstream commit was audited with the command line below. Do not
# replace it with the moving `main` branch: reproducibility matters here.
SD_SCRIPTS_REF = "v0.9.1"
SD_SCRIPTS_COMMIT = "8f4ee8fc343b047965cd8976fca65c3a35b7593a"

# %%
import os
import shutil
import sys

import torch


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


require(
    torch.cuda.is_available(),
    "GPU が見つかりません。ランタイムを GPU に変更してから再起動してください。",
)
gpu = torch.cuda.get_device_properties(0)
vram_gib = gpu.total_memory / 1024**3
free_gib = shutil.disk_usage("/content").free / 1024**3
require(
    vram_gib >= 14,
    f"GPU メモリが不足しています: {gpu.name} ({vram_gib:.1f} GiB)。T4 (16 GiB) 以上を選んでください。",
)
require(
    free_gib >= 25,
    f"Colab ディスク空き容量が不足しています: {free_gib:.1f} GiB。ランタイムを再起動して空きを確保してください。",
)
require(
    DRIVE_ROOT.is_dir(),
    f"Google Drive に {DRIVE_ROOT} がありません。Drive を正しくマウントしてください。",
)

LOG_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
print(f"GPU: {gpu.name} ({vram_gib:.1f} GiB)")
print(f"Colab free disk: {free_gib:.1f} GiB")
print(f"Drive root: {DRIVE_ROOT}")

# %%
import shlex
import subprocess


def run(label: str, *command: str) -> None:
    """Stream a command to the cell and retain a full, persistent log in Drive."""
    log_path = LOG_DIR / f"{DATASET_NAME}-{label}.log"
    print("+", shlex.join(command))
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            log_file.write(line)
        return_code = process.wait()
    if return_code:
        raise RuntimeError(f"{label} が失敗しました (exit {return_code})。完全なログ: {log_path}")


repository = Path("/content/sd-scripts")
if repository.is_dir():
    completed = subprocess.run(
        ("git", "-C", str(repository), "rev-parse", "HEAD"),
        capture_output=True,
        text=True,
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
    "install-torch",
    sys.executable,
    "-m",
    "pip",
    "install",
    "--quiet",
    "--disable-pip-version-check",
    "torch==2.6.0",
    "torchvision==0.21.0",
    "--index-url",
    "https://download.pytorch.org/whl/cu124",
)
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
run("configure-accelerate", "accelerate", "config", "default", "--mixed_precision", "fp16")
run("verify-trainer", sys.executable, "sdxl_train_network.py", "--help")

# %%
import re
import zipfile

from huggingface_hub import hf_hub_download


part_pattern = re.compile(re.escape(DATASET_ARCHIVE.name) + r"\.part(\d+)$")
parts = sorted(
    (
        (int(match.group(1)), path)
        for path in DRIVE_ROOT.iterdir()
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
    source_archive = Path("/content") / DATASET_ARCHIVE.name
    temporary_archive = source_archive.with_suffix(".partial")
    with temporary_archive.open("wb") as destination:
        for _, part in parts:
            require(part.stat().st_size > 0, f"空の分割ZIPがあります: {part.name}")
            with part.open("rb") as source:
                shutil.copyfileobj(source, destination, length=16 * 1024 * 1024)
    temporary_archive.replace(source_archive)
else:
    source_archive = DATASET_ARCHIVE

require(
    source_archive.is_file(),
    f"データセットがありません: {DATASET_ARCHIVE} または .part001 以降をDriveへ置いてください。",
)
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
    require(corrupt_member is None, f"ZIPが壊れています: {corrupt_member}")
    extracted_root = Path("/content/datasets") / DATASET_NAME
    shutil.rmtree(extracted_root, ignore_errors=True)
    archive.extractall("/content/datasets")

TRAIN_DATA_DIR = Path("/content/datasets") / DATASET_NAME
image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
images = [path for path in TRAIN_DATA_DIR.rglob("*") if path.suffix.lower() in image_extensions]
missing_captions = [
    path.name
    for path in images
    if not path.with_suffix(".txt").is_file()
    or not path.with_suffix(".txt").read_text(encoding="utf-8").strip()
]
require(images, f"画像が見つかりません: {TRAIN_DATA_DIR}")
require(
    not missing_captions, f"タグ .txt がない画像があります（先頭10件）: {missing_captions[:10]}"
)
require(
    (TRAIN_DATA_DIR / f"1_{DATASET_NAME}").is_dir(),
    "学習用フォルダ 1_<dataset_name> がありません。Shikishiで書き出したZIPを使ってください。",
)
print(f"Dataset ready: {len(images)} images, {len(images)} captions")

os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
hf_hub_download(
    repo_id="OnomaAIResearch/Illustrious-XL-v2.0",
    filename=BASE_MODEL.name,
    local_dir=BASE_MODEL.parent,
)
require(
    BASE_MODEL.is_file() and BASE_MODEL.stat().st_size > 6 * 1024**3,
    "ベースモデルのダウンロードが不完全です。ランタイムを再起動してこのセルを再実行してください。",
)
print(f"Base model ready: {BASE_MODEL.stat().st_size / 1024**3:.2f} GiB")

# %%
os.chdir(repository)
state_pattern = re.compile(rf"^{re.escape(OUTPUT_NAME)}-step(\d+)-state$")
saved_states = sorted(
    (
        (int(match.group(1)), path)
        for path in OUTPUT_DIR.iterdir()
        if path.is_dir()
        and (match := state_pattern.match(path.name))
        and (path / "optimizer.bin").is_file()
    ),
    reverse=True,
)
resume_state = saved_states[0][1] if saved_states else None
if resume_state is None:
    print("Training mode: new run")
else:
    print(f"Training mode: resume from step {saved_states[0][0]} ({resume_state})")

train_command = (
    "accelerate",
    "launch",
    "--num_cpu_threads_per_process=2",
    "sdxl_train_network.py",
    f"--pretrained_model_name_or_path={BASE_MODEL}",
    f"--train_data_dir={TRAIN_DATA_DIR}",
    f"--output_dir={OUTPUT_DIR}",
    f"--output_name={OUTPUT_NAME}",
    "--network_module=networks.lora",
    "--network_dim=8",
    "--network_alpha=4",
    "--resolution=768,768",
    "--enable_bucket",
    "--min_bucket_reso=512",
    "--max_bucket_reso=1024",
    "--train_batch_size=1",
    "--max_train_steps=3000",
    "--learning_rate=1e-4",
    "--optimizer_type=AdamW8bit",
    "--lr_scheduler=cosine",
    "--mixed_precision=fp16",
    "--save_precision=fp16",
    "--cache_latents",
    "--cache_latents_to_disk",
    "--cache_text_encoder_outputs",
    "--cache_text_encoder_outputs_to_disk",
    "--gradient_checkpointing",
    "--no_half_vae",
    "--max_data_loader_n_workers=0",
    "--network_train_unet_only",
    "--caption_extension=.txt",
    "--save_model_as=safetensors",
    "--save_every_n_steps=200",
    "--save_last_n_steps_state=1",
    "--save_state",
    "--seed=42",
)
if resume_state is not None:
    train_command += (f"--resume={resume_state}",)
run("train", *train_command)

# %% [markdown]
# Training checkpoints and the resumable state are stored in
# `MyDrive/shikishi/outputs/ixy_style/`. On the next run, the notebook finds
# the newest complete step-state automatically and resumes from it. At most
# 199 steps are lost after an unexpected Colab termination. Full logs remain
# in `MyDrive/shikishi/logs/`.
