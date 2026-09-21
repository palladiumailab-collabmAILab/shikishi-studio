# Shikishi Studio

`ixy_style.safetensors` を Illustrious XL に適用して画像生成する、ローカルGPU向けWebアプリです。
KaggleでのStyle LoRA学習と、PC/Androidを使ったデモ運用を同じリポジトリで再現できるようにしています。

## Dockerで起動

通常のデモ環境ではCUDAを必須とし、起動時にベースモデルとIP-Adapterを読み込んでから
`/readyz` が成功するようにしています。初回だけモデル取得のためインターネット接続が必要です。
2回目以降は `hf-cache` Docker volume を再利用します。

```powershell
docker compose up --build -d shikishi
```

`http://localhost:8002` を開きます。準備確認は次です。

```powershell
Invoke-WebRequest http://localhost:8002/readyz
```

`200` と `{"status":"ready"}` が返るまではデモ開始扱いにしません。`/healthz` はプロセス生存のみ、
`/readyz` はCUDA、モデルwarmup、出力領域の書き込み可否を確認します。

停止:

```powershell
docker compose down
```

### Androidから確認する

安全側の既定ではポート8002を `127.0.0.1` にだけ公開し、認証を省略できます。Androidから使う場合は、
まず認証トークンを生成してから、信頼できる専用LANまたはPCのホットスポットへ公開してください。

```powershell
$env:SHIKISHI_AUTH_TOKEN = python tools/generate_auth_token.py
$env:SHIKISHI_BIND_HOST = '0.0.0.0'
docker compose up -d --force-recreate shikishi
```

Androidから `http://<PCのLAN IPv4アドレス>:8002` を開き、トークンを入力してログインします。
LAN公開時は、`SHIKISHI_AUTH_TOKEN` が未設定だとアプリが起動せず、API・履歴・参照画像・生成画像・
ダウンロードは認証なしでは利用できません。APIクライアントは
`Authorization: Bearer $env:SHIKISHI_AUTH_TOKEN` を送ります。インターネットへのポート転送は
行わないでください。共有・公共Wi-Fiではなく、管理できるLANを使用してください。

ブラウザのセッションは既定で24時間有効です。変更する場合は
`SHIKISHI_AUTH_SESSION_TTL_SECONDS` を設定します。LANモードは専用ネットワークで使い、必要に応じて
TLS終端プロキシを併用してください。

生成ジョブはPC側で継続します。Android側の通信が一時的に切れても約10分間再接続するため、
同じ生成要求を再送信しないでください。

### CPUで開発確認する場合

デモ用ComposeはCUDA必須です。CPUだけでAPI/UIを確認する必要がある場合は明示的に解除します。

```powershell
$env:REQUIRE_CUDA = '0'
$env:DEMO_WARMUP = '0'
docker compose up -d shikishi
```

## デモ前チェック

デモ日前にインターネット接続がある状態で一度 `shikishi` を起動し、`/readyz` が200になることを
確認します。これによりベースモデル、LoRA、IP-Adapterを事前に読み込み、必要な公開モデルを
Docker cacheへ取得します。

最低限、実機で次を確認します。

1. 通常生成 1024x1024 / 標準30 steps
2. キャラクター参照
3. 顔参照
4. pose img2img
5. 連続2〜3回の生成
6. Androidからの再接続

`models/registry.json` のLoRA情報と `models/loras/*.version.json` のSHA/来歴を確認してから使用します。

## デモデータの初期化

生成画像と参照画像だけを削除し、モデル・Hugging Face cacheは残します。既定はdry-runです。

```powershell
docker compose run --rm app python tools/reset_demo_data.py
docker compose run --rm app python tools/reset_demo_data.py --yes
```

対象は `generated/` と `reference-images/` のみです。

## ROG Phoneの画像・動画自動取り込み

WindowsでROG PhoneをUSB接続し、端末のロックを解除してUSB用途を「ファイル転送」にすると、
次の監視スクリプトで `DCIM`・`Pictures`・`Movies` の画像・動画を
既定では `%USERPROFILE%\Documents\shikishi-artifacts\rog-phone-media\` へ取り込めます。
端末上の原本は削除・移動せず、ローカルの一時領域へ転送してSHA-256を確認してから保存します。

初回だけPowerShell 5.1でタスクを登録します。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\watch-rog-phone-media.ps1 -Install
```

取り込み状態は `import-state.jsonl`、接続・未準備・失敗・完了は `import-log.jsonl` に記録します。
同じ相対パス・サイズ・端末更新日時のファイルは再取り込みせず、同名で内容が異なる場合は
SHA-256の先頭12文字を付けて別名保存します。保存先を変える場合は
`SHIKISHI_ARTIFACTS_ROOT` または `-DestinationRoot` を指定します。

ワンショット確認と無効化:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\watch-rog-phone-media.ps1 -Once -DryRun -Verbose
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\watch-rog-phone-media.ps1 -Once -Verbose
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\watch-rog-phone-media.ps1 -Uninstall
```

端末がロック中または充電専用の場合は `not-ready` として記録し、端末側の原本には触れません。

## 生成機能

- `POST /api/jobs` で非同期ジョブを作成し、`GET /api/jobs/{id}` で進捗を取得
- GPU処理は単一workerで直列化し、pending queueを上限付きで保持
- prompt、seed、解像度、steps、CFG、LoRA強度、モデルrevision等を履歴JSONへ保存
- PNG/JPEG/WebP参照画像を検証し、原本と正規化PNGを分離保存
- img2img、IP-Adapter、顔refinementを必要時だけ使用
- IP-Adapterは処理後に解放し、通常生成時のVRAM占有を抑制

品質プリセットはドラフト 512x512/16 steps、標準 1024x1024/30 steps、高品質
1024x1024/40 stepsです。

## Kaggle Style LoRA学習

Kaggle操作はWebアプリから分離した専用 `kaggle-runner` で行います。`KAGGLE_API_TOKEN` は
`app` / `shikishi` へ渡らず、runnerだけが受け取ります。

Kaggle設定の正本は `kaggle/kernel-metadata.json` です。現在は以下を宣言しています。

- private Notebook
- GPU有効
- Internet有効
- `NvidiaTeslaT4` を既定acceleratorとして指定
- `palladiumailab/shikishi-ixy-style-v2-goal-v1` をDataset Inputとして指定

実行前に、モデル重みを変更する学習を本当に開始してよいことを確認してください。実行する場合:

```powershell
$env:KAGGLE_API_TOKEN = Read-Host -Prompt 'Kaggle API token'
$env:SHIKISHI_GIT_REVISION = git rev-parse HEAD
docker compose --profile ops run --rm kaggle-runner
```

runnerは以下を自動実行します。

1. API tokenとKaggle CLIの確認
2. 既存Kernelが `queued/running` でないことを確認
3. Python正本から一時Notebookを生成
4. `kernel-metadata.json` を検証
5. `kaggle kernels push` で投入・実行開始
6. `kaggle kernels status` を権威状態としてpoll
7. 失敗時だけ `kaggle kernels logs` を診断用に保存
8. 成功後 `kaggle kernels output` で成果物を取得
9. `shikishi-training-result.json` とLoRAのsize/SHA-256を照合
10. `artifacts/kaggle/<run-id>/orchestration.json` に実行証跡を保存

同時runは `.kaggle-run.lock` で拒否します。ブラウザ/Computer Useによる投入・status確認・output取得は
通常運用では不要です。

GPUを変更する場合:

```powershell
$env:KAGGLE_MACHINE_SHAPE = 'NvidiaL4'
```

Notebook内部にはGPU/空き容量/Inputのpreflight、互換manifestを使ったresume判定、最大3回の再試行、
進捗JSON、最終LoRAのSHA-256検証があります。別Kaggleセッションへの完全自動resumeは、前回outputの
`kernel_sources` 運用を実機確認するまで自動化対象外です。

### Notebook同期

`kaggle/illustrious_xl_style_lora.py` が正本です。

```powershell
python tools/sync_kaggle_notebook.py
python tools/sync_kaggle_notebook.py --check
```

旧PowerShell入口もPython版を呼び出す互換wrapperとして残しています。

## ローカルPython開発

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e ".[dev]"
uvicorn app:app --reload
```

通常の再現・検証経路はDockerです。`requirements.txt` の直接依存はデモ再build時の変動を抑えるため
検証対象versionへ固定しています。

## 品質ゲート

ローカルDockerとGitHub Actionsで同じ主要チェックを実行します。

```powershell
docker compose build app
docker compose run --rm app python -m ruff check .
docker compose run --rm app python -m ruff format --check .
docker compose run --rm app python -m mypy
docker compose run --rm app python -m pytest
docker compose run --rm app python tools/sync_kaggle_notebook.py --check
```

GitHub ActionsはPRと `main` pushでこれらを実行し、Kaggle runnerイメージもbuildします。実Kaggle GPU
学習はCIから起動しません。

## 主な保存領域

- `models/registry.json`: ベースモデル/LoRA/revision
- `models/loras/`: ローカル推論用LoRA
- `generated/`: 生成画像と再現metadata
- `reference-images/`: 非公開の参照原本・正規化画像
- `artifacts/kaggle/`: Kaggle orchestration/output（Git管理外）
- `C:\Users\palla\Documents\shikishi-artifacts\`: 大容量の学習正本・派生物

詳細は [docs/storage-layout.md](docs/storage-layout.md) と
[docs/issue-resolution-plan.md](docs/issue-resolution-plan.md) を参照してください。
