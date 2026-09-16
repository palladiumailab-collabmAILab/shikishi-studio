# ixy Style LoRA v2 品質チェック報告

実施日: 2026-08-25  
対象ベースモデル: `Illustrious-XL-v2.0.safetensors`  
対象データセット: `ixy_style_v2 / 20260825-goal-v1`  
学習データ: primary 845、composite auxiliary 102、diversity auxiliary 38、full-body boost 40、実効1,025枚

## 判定

| 項目 | Linear | LoCon |
|---|---:|---:|
| Kaggle実行 | PASS | PASS |
| 最終step到達 | 2400 / 2400 | 2400 / 2400 |
| 最終LoRA保存 | PASS | PASS |
| 300 step checkpoint | 8個 | 8個 |
| run/result manifest | PASS | PASS |
| Safetensors構造 | PASS | PASS |
| メタデータと設定の一致 | PASS | PASS |
| 既存LoRAの非変更 | PASS | PASS |
| 生成画像による目視QA | PASS | PASS |

構造・実行品質・生成動作はPASS。見た目の判定は、同一条件の8枚を確認した範囲でのQA判定であり、入力画像との完全一致を保証するものではない。

## 学習結果

- [Linear版 Kaggleログ](https://www.kaggle.com/code/palladiumailab/shikishi-ixy-style-v2-linear/logs?scriptVersionId=344784056): 2時間37分31秒、最終`avr_loss=0.0546`。
- [LoCon版 Kaggleログ](https://www.kaggle.com/code/palladiumailab/shikishi-ixy-style-v2-locon/logs?scriptVersionId=344822893): 3時間04分45秒、最終`avr_loss=0.0561`、平均key norm=`0.0975`。
- いずれも最終checkpoint保存後に`model saved.`を確認した。
- NCCLの終了warningは出たが、モデル保存後の終了処理に関するwarningで、Kaggle結果は`successful`だった。

## 構造検査

### Linear

- ファイル: `ixy_style_v2_linear_r16_a8_s42.safetensors`
- サイズ: 85,511,668 bytes
- SHA-256: `C3FC6C4F9E3EA95F0E3F619921C1E445FD79151E89813F5E88FD1405A07241A7`
- テンソル: 2,166個、すべてF16
- LoRA down/up: 各722、alpha: 722
- rank / alpha: 16 / 8
- 学習率: `8e-5`

### LoCon

- ファイル: `ixy_style_v2_locon_r16_a8_c8_ca4_s42.safetensors`
- サイズ: 93,103,488 bytes
- SHA-256: `3D996C222D9F65BC931A1CA47971D1F066698C43EF917DC469628367F3632B07`
- テンソル: 2,364個、すべてF16
- LoRA down/up: 各788、alpha: 788、3x3 convolution系: 38
- rank / alpha: 16 / 8
- conv_dim / conv_alpha: 8 / 4
- 学習率: `6e-5`

両方について、Safetensorsヘッダーのサイズ、テンソル数、dtype、データoffsetの範囲を検査し、不正なoffsetや空の出力がないことを確認した。メタデータの学習画像数は1,025、学習stepは2,400、解像度は1024x1024で、今回の学習設定と一致する。

## 生成画像による目視QA

ベースモデル、プロンプト、seed、解像度、steps、CFGを揃え、各LoRAで4構図ずつ生成した。生成条件は768x1024、20 steps、CFG 5.0、seed 42–45。全8枚でLoRA読込エラー、CUDA OOM、空画像は発生しなかった。

生成後に8枚すべてをPNGとして開けること、サイズが768x1024であること、manifest記載のSHA-256と一致することも確認した。
QA補助スクリプトはRuff check / format checkともにPASS。

| 構図 | 観察 | 判定 |
|---|---|---|
| p01 full body | Linearは正面シルエット、LoConは背面寄りのシルエット。植物の輪・金色の中心物は強く出たが、杖が顔を隠すためキャラ確認には不向き。 | 生成PASS / 構図再試行推奨 |
| p02 portrait | 青髪、濃紺リボン、青白い衣装、花飾り、金色の葉を安定して保持。LoConは葉脈と装飾の描き込みがやや強い。 | PASS |
| p03 dynamic | 手を伸ばす動き、青白い衣装、金色植物のアークを両版が保持。LoConは輪郭と葉・金装飾の密度が強い。 | PASS |
| p04 diagonal | 大きな布面と金色の縁取り、白いパネル状背景が出て、スタイルは強い。衣装面積が大きくキャラ固有造形の確認には弱い。 | 生成PASS / 構図再試行推奨 |

### スタイル面の結論

- 両版とも、暗めで細い輪郭線、低彩度の白青面、金色アクセント、植物・装飾の反復、白いパネル状の余白という参照群由来のフィルターが生成結果に現れた。
- この固定条件では、LoConの方が葉・金装飾・輪郭の密度と“絵師の手癖”を強く反映した。
- Linearは全身構図でシルエットが比較的素直に出たが、LoConは装飾性と画面全体の統一感が強い。
- したがって、今回の目的（参照絵師の個性を強く載せる）にはLoConを第一候補とする。ただし、入力キャラの衣装・顔・正面性を優先する場合は、LoRA強度を下げるかLinear版との比較を推奨する。

### 生成画像

- [QA manifest](<C:/Users/palla/Documents/shikishi-artifacts/loras/ixy_style_v2/visual_qa_20260825/visual_qa_manifest.json>)
- [Linear p01](<C:/Users/palla/Documents/shikishi-artifacts/loras/ixy_style_v2/visual_qa_20260825/linear_p01_fullbody.png>) / [LoCon p01](<C:/Users/palla/Documents/shikishi-artifacts/loras/ixy_style_v2/visual_qa_20260825/locon_p01_fullbody.png>)
- [Linear p02](<C:/Users/palla/Documents/shikishi-artifacts/loras/ixy_style_v2/visual_qa_20260825/linear_p02_portrait.png>) / [LoCon p02](<C:/Users/palla/Documents/shikishi-artifacts/loras/ixy_style_v2/visual_qa_20260825/locon_p02_portrait.png>)
- [Linear p03](<C:/Users/palla/Documents/shikishi-artifacts/loras/ixy_style_v2/visual_qa_20260825/linear_p03_dynamic.png>) / [LoCon p03](<C:/Users/palla/Documents/shikishi-artifacts/loras/ixy_style_v2/visual_qa_20260825/locon_p03_dynamic.png>)
- [Linear p04](<C:/Users/palla/Documents/shikishi-artifacts/loras/ixy_style_v2/visual_qa_20260825/linear_p04_diagonal.png>) / [LoCon p04](<C:/Users/palla/Documents/shikishi-artifacts/loras/ixy_style_v2/visual_qa_20260825/locon_p04_diagonal.png>)

## 成果物

- [Linear LoRA](<C:/Users/palla/Documents/shikishi-artifacts/loras/ixy_style_v2/ixy_style_v2_linear_r16_a8_s42.safetensors>)
- [LoCon LoRA](<C:/Users/palla/Documents/shikishi-artifacts/loras/ixy_style_v2/ixy_style_v2_locon_r16_a8_c8_ca4_s42.safetensors>)
- [学習トラブルシューティングログ](<C:/Users/palla/Documents/shikishi/logs/kaggle_lora_troubleshooting.md>)

既存の`models/loras/ixy_style.safetensors`は上書きしていない。
