# コードベース健全性修正計画（2026-08-24）

## 診断結果と修正方針

| 優先度 | 検出事項 | 根拠 | 修正 | 受入条件 |
|---|---|---|---|---|
| 高 | 生成メタデータJSONがLANへ直接公開される | `/images/*.png.json` がHTTP 200 | 静的な出力フォルダ公開をやめ、検証済みPNGだけ配信 | PNGは表示でき、JSONは404 |
| 高 | IP-Adapterがrevision未固定かつpickle形式 | 設定既定値がrevisionなし、`.bin`指定 | 固定revision＋safetensorsへ変更し、SHA記録 | オフラインキャッシュ解決とSHA一致 |
| 高 | Diffusersが画像エンコーダーへrevisionを伝播しない | 固定SHAのみのオフライン統合ロードが失敗 | 画像エンコーダーを同じrevisionから明示読込して登録 | 完全オフラインで統合ロード成功 |
| 中 | `BASE_MODEL`環境変数が無効 | Compose/READMEには存在するがSettingsが読まない | レジストリ読込時の明示overrideとして実装 | 環境変数の値が実行モデルへ反映 |
| 中 | キュー満杯時に停止処理が例外化し得る | `stop()`の`put_nowait(None)`が`queue.Full`未処理 | 満杯を許容し、未開始workerにも安全にする | 満杯・未開始でもstop成功 |
| 中 | 詳細パネルが`hidden`でも表示される | `.advanced { display:flex }`がhidden表示を上書き | `hidden`状態を明示CSSで優先 | Android幅で詳細ボタンが開閉 |
| 中 | 初期API失敗が未処理Promiseになる | 起動時の4 API呼出しにcatchなし | 初期化を集約し、画面に接続エラー表示 | consoleに未処理エラーなし |
| 中 | 必須品質ゲートが常時失敗 | Ruff 21件、format 2件、mypy 2件 | 手書きPythonを整形、不要ignore削除、生成Notebookを除外 | 4つのDockerゲート合格 |
| 低 | 壊れた履歴JSONを無言で破棄 | `_read_item()`が例外を返値だけで隠す | ファイル名付きwarningを記録 | 履歴継続かつ診断ログあり |

## 対象外

- 学習Notebookの動作変更、データセット削除、モデル再学習は行わない。
- 既存のユーザー変更を巻き戻さない。
- ジョブ永続DB化や認証追加は別設計とし、今回の小規模修正には含めない。

修正順は、回帰テスト追加、セキュリティ境界、実行設定と停止処理、UI復旧、
品質ゲート整備、Docker再配置の順とする。
