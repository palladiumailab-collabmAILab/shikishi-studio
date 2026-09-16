# Shikishi Studio

`ixy_style.safetensors` を適用して Illustrious XL で画像を生成する、会話型のローカルWebアプリです。

## Dockerで起動（推奨）

Docker Desktop が起動している状態で、次を実行します。

```powershell
docker compose up --build -d
```

ブラウザで `http://localhost:8002` を開きます（既存のローカルアプリとポートが衝突しないようにしています）。初回の画像生成時だけ Diffusers形式の Illustrious XL v2.0 ベースモデル（約7 GB）がDockerボリュームにダウンロードされます。Compose設定は NVIDIA GPU をコンテナに明示的に割り当てます。

### Androidから確認する

PCとAndroidを同じLANへ接続し、PCでDocker版を起動した状態で、Androidの
ブラウザーから `http://<PCのLAN IPv4アドレス>:8002` を開きます。Windowsでは
次のコマンドでLANアドレスを確認できます。

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -like '192.168.*' -or $_.IPAddress -like '10.*' }
```

画面の「使用モデル」にKaggle Version番号とstep数が表示されれば、対象LoRAが
読み込まれています。アクセスできない場合は、PCとAndroidが同じネットワークに
いること、Dockerサービスが起動中であること、TCP 8002がLAN内で許可されている
ことを確認してください。インターネットへポート転送しないでください。

生成中にAndroidのWi-Fiが一時的に切れた場合、画面は最大約10分間、自動でPCへ
再接続します。生成ジョブはPC側で継続するため、再送信せずに待ってください。

停止は次です。

```powershell
docker compose down
```

## ローカルPythonでの起動

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e . -r requirements.txt
uvicorn app:app --reload
```

ブラウザで `http://127.0.0.1:8000` を開きます。初回の生成時に、既定の Illustrious XL ベースモデルがダウンロードされます（GPU推奨）。すでにローカルにベースモデルがある場合は、次のように起動できます。

```powershell
$env:BASE_MODEL = 'C:\path\to\Illustrious-XL-v2.0'
uvicorn app:app --reload
```

## 構成

- `models/registry.json`: 利用可能なベースモデル／LoRA／推奨強度のレジストリ
- `models/loras/ixy_style.safetensors`: Kaggle で学習した最終ステップ（3,000）のLoRA
- `studio/services/`: GPU生成、ジョブキュー、履歴、モデルレジストリのドメイン処理
- `studio/api.py`: HTTP APIルート
- `static/js/`: API通信、UI部品、画面制御を分離したフロントエンド
- `generated/`: 生成画像と、再現用パラメータを含むメタデータJSONの保存先
- `reference-images/`: 非公開の参照原本・正規化画像・検証メタデータの保存先

大容量の原取得物・配布ZIP・再生成可能な派生物はリポジトリ外の
`C:\Users\palla\Documents\shikishi-artifacts\`へ分離します。正本と再生成方法は
[ローカル保存領域](docs/storage-layout.md)を参照してください。

## 生成ジョブ

生成は非同期ジョブとして扱われます。`POST /api/jobs` が即時にジョブIDを返し、`GET /api/jobs/{id}` で状態・進捗・生成結果を取得します。これにより、重いGPU生成中もUIは応答を維持します。

各履歴にはprompt、seed、解像度、steps、CFG、LoRA強度、モデルID、ベースモデル、アプリ版を保存します。

「1人構図」は既定でオンです。内部で `solo` を追加し、複数人物・コラージュ・
漫画パネル系の語をネガティブ側へ加えます。集合絵を作る場合だけオフにしてください。
「標準等身」も既定でオンです。通常等身をpositive側へ、chibi・極端なデフォルメを
negative側へ追加します。デフォルメ絵を作る場合だけオフにしてください。
キャラクター名は日本語より、学習元で使われる英語タグ形式（例：
`hayase yuuka (blue archive)`）の方が安定します。

品質プリセットは、構図確認用の「ドラフト」（512×512・16 steps）、通常生成の
「標準」（1024×1024・30 steps）、細部確認用の「高品質」（1024×1024・40 steps）
です。ポーズ画像と低stepsの組合せで実効denoise stepsが6未満になる場合は、輪郭破綻を
避けるため画面に警告を表示します。

「詳細」の「キャラ補正」には、原作外見へ寄せる検証済みプロンプトがあります。
蛍草は学習データに含まれないため完全な固有デザインの再現は保証できませんが、
「蛍草（陰陽師・原作寄せ）」で黒髪・緑白の和装・蒲公英を優先できます。

「キャラクター参照」ではPNG・JPEG・WebP（10MB以下）を最大6枚選び、画像ごとに
「全体・衣装」または「顔」の役割、切り抜き中心、拡大率を指定できます。同じ画像を
全体用と顔の拡大用に2回使うこともできます。全体をPlus ViT-H版で生成した後、
Plus Face版を弱いimg2imgとして順番に適用するため、両モデルをGPUへ同時搭載しません。

姿勢は「ポーズ指示」へ短い英語タグを入力する方法が基本です。構図画像が必要な場合だけ
「ポーズ・構図画像」を追加してください。生成履歴の「基準画像に追加」を押すと、良かった
出力を次のキャラクター参照へコピーできます。元の生成画像は変更・削除されません。
同一画像はSHA-256で再利用され、参照原本を重複保存しません。同じ参照IDをUI上で
「全体・衣装」と「顔」の2役に使うことは可能です。

IP-Adapterは追加VRAMを常時占有しないよう、対象生成の間だけ読み込み、完了後に解放
します。初回利用時は追加モデルの取得に時間がかかります。既定の全体強度は0.30、
顔強度は0.25です。参照が強すぎてポーズや背景が固定される場合は0.05ずつ下げます。
IP-Adapterは固定revisionのsafetensorsを使い、取得済み
ファイルの来歴とSHA-256は `models/ip_adapter.version.json` に記録しています。
通常版との比較が必要な場合は、次の設定で切り替えて再作成します。

```powershell
$env:IP_ADAPTER_WEIGHT_NAME = 'ip-adapter_sdxl.safetensors'
$env:IP_ADAPTER_IMAGE_ENCODER_SUBFOLDER = 'sdxl_models/image_encoder'
docker compose up -d --force-recreate shikishi
```

Plus版へ戻す場合は両方の環境変数を削除して同じ再作成コマンドを実行します。

課題ごとの判断、受入条件、保留条件は
[docs/issue-resolution-plan.md](docs/issue-resolution-plan.md) に記録しています。

## テスト

テスト専用Dockerターゲットを使います。

```powershell
docker build --target test -t shikishi-test .
docker run --rm shikishi-test
```

ベースモデルはサイズが大きいため、リポジトリには含めません。

## Kaggle Style LoRAの自動運転

`kaggle/illustrious_xl_style_lora.ipynb` は、起動後に人手を介さず学習を進める設計です。

- 読み取り専用のKaggle Inputから画像とcaptionを`/kaggle/working/datasets/`へ自動配置
- 学習プロセスが異常終了した場合、最新の保存済みstateから最大3回まで自動再試行
- `/kaggle/working/automation/status.json`へ進捗と再試行状態を保存
- 第1エポックが15%へ到達すると、`first_epoch_15_percent.json`を証跡として保存
- 学習中のstateを200stepごとに保存し、同じexperiment・run ID・モデル指紋の
  Kaggle出力を次回Inputへ追加すれば自動再開
- `SHIKISHI_RUN_ID`で再開対象の系統を明示（未指定時はexperiment ID）
- 最終LoRAのサイズ・更新・SHA-256を検証し、結果metadataを原子的に保存

Python形式のNotebookソースを変更した場合は、次のコマンドで`.ipynb`を同期します。

```powershell
.\tools\sync_kaggle_notebook.ps1
```

通常運用で想定するCodexの介入は、修正版NotebookをKaggleへ投入して実行を開始する1回だけです。GPU割当・Dataset Input・Internet設定はKaggle側で事前に設定されている必要があります。

## ソース配布

コミット済みソースをZIP化する場合は `git archive` を使用します。

```powershell
git archive --format=zip --output ..\shikishi-source.zip HEAD
```

`.gitattributes` により、LoRA重み、生成画像、参照画像、キャッシュ、データセットなどの
ローカル成果物は配布ZIPから除外されます。
