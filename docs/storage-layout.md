# ローカル保存領域

リポジトリには、実装と再現に必要な最小限のデータだけを置く。`<ARTIFACTS_ROOT>` は `SHIKISHI_ARTIFACTS_ROOT`、未指定時は `%USERPROFILE%\\Documents\\shikishi-artifacts\\` を表す。

| 場所 | 役割 | 扱い |
|---|---|---|
| `<ARTIFACTS_ROOT>\prepared-datasets\ixy_style\1_ixy_style\` | キャプション整備済みの学習正本 | リポジトリ外で保持・編集禁止 |
| `models/loras/` | ローカル推論用LoRA | 保持 |
| `generated/` | 生成画像と再現メタデータ | 保持 |
| `reference-images/` | 参照原本・正規化画像 | 保持・非公開 |
| `<ARTIFACTS_ROOT>\rog-phone-media\` | ROG Phoneから取り込んだ画像・動画とJSONL証跡 | リポジトリ外で保持 |
| `dataset/reports/` | データ処理の証跡 | 保持 |
| `<ARTIFACTS_ROOT>\` | 原取得物、配布ZIP、退避済み派生物 | リポジトリ外で保管 |

## 外部アーカイブ

- `source-downloads/ixy/`: 加工前の取得物
- `prepared-datasets/ixy_style/`: キャプション整備済みの学習正本
- `packages/`: 代表となるColab/Kaggle用ZIP
- `cleanup-20260825/derived/processed/`: 再生成可能な処理済みデータ
- `cleanup-20260825/duplicates/`: SHA-256一致を確認した分割ZIPと旧Kaggle ZIP
- `cleanup-20260825/caches/`: 退避時点の開発キャッシュ

## 再生成

処理済みデータは正本から再生成できる。

```powershell
$artifactsRoot = if ($env:SHIKISHI_ARTIFACTS_ROOT) { $env:SHIKISHI_ARTIFACTS_ROOT } else { Join-Path $env:USERPROFILE 'Documents\shikishi-artifacts' }
python dataset/prepare_dataset.py `
  --input "$artifactsRoot\prepared-datasets\ixy_style\1_ixy_style" `
  --output dataset/processed `
  --config dataset/config.yaml
```

Kaggle入力ZIPは処理済みデータとレポートから再作成する。

```powershell
python dataset/package_kaggle_input.py `
  --processed dataset/processed `
  --reports dataset/reports `
  --output dataset/kaggle_input/ixy_style-style-lora.zip `
  --dataset-name ixy_style
```
