# Codex Software Development Harness

This file starts from the canonical common contract in `palladiumailab-collabmAILab/codex-dev-harness`. The common harness is the source of truth; Shikishi Studio-specific rules are isolated in the final section. See `docs/harness-upstream.md` for the pinned upstream revision.

このファイルは全作業に必要な不変条件だけを定義します。システム・開発者指示とユーザーの明示依頼を優先し、リポジトリ内では現在地に近い `AGENTS.override.md` / `AGENTS.md` を優先します。条件付きの詳細手順は該当する skill だけを読みます。

## 不変条件

- 依頼の目的、変更範囲、受け入れ条件を先に確認する。実装方針または完了判定を左右する曖昧さが残る場合は勝手に補完せず、ユーザーに確認する。
- 長期に有効な製品・システム仕様は対象リポジトリの `docs/specs/` を正本として扱う。関連仕様がある変更では先に参照し、仕様と実装が矛盾する場合は黙ってどちらかへ寄せず矛盾を明示する。
- テスト、lint、build、調査結果は受け入れ条件を裏づける証拠として扱い、それ自体をタスク完了や実質的な進捗とみなさない。テスト・評価器・閾値を合格のためだけに弱めない。
- 依頼されていない機能・依存関係・外部連携・大規模リファクタリングを追加しない。
- 作業前に既存の未コミット変更を確認して保持する。`git reset --hard`、`git clean`、`git checkout --` 等で他者の変更を捨てない。
- 最寄りの指示、対象コード、関連仕様、関連テスト、必要な設定だけを読む。無目的な全件走査や巨大ログの展開を避ける。
- 変更は小さく目的単位に保ち、既存の構成・命名・依存関係・フォーマッタ・パッケージマネージャを尊重する。
- 実行可能なソフトウェアは Docker で再現可能な開発・検証経路を持たせる。ホストでの直接実行は高速化のために使ってよいが、Dockerで再現できない状態を完成扱いしない。
- Python を含むリポジトリでは、新規・既存を問わず Ruff を lint / format の標準品質ゲートとして使用する。型検査やテストなどRuffと直交する検証は必要に応じて維持する。
- GitHubで管理する実行可能なソフトウェアでは、GitHub Actions を標準の遠隔品質ゲートとする。PRで lint / format、テスト、型チェック、build、その他プロジェクト固有の検証を適用範囲に応じて実行し、ローカル検証の成功だけで完了扱いしない。期待されるCIが存在しない、実行不能、または失敗している場合は、その状態を解消するか明示的なブロッカーとして報告する。
- 変更後は差分を再確認し、変更に比例したテスト・型チェック・lint・build・手動確認を行う。実行できない検証は理由を明記する。
- 秘密情報、秘密鍵、トークン、不要な個人情報を出力・コミット・外部送信しない。
- 依頼のないデプロイ、外部書き込み、課金、データ削除、権限変更、force push を行わない。

## 標準ワークフロー

1. 目的・制約・受け入れ条件・変更対象を短く整理し、重要な曖昧さは実装前にユーザーへ確認する。
2. 関連する `docs/specs/`、コード、テストを根拠付きで調査する。
3. 最小の変更を実装する。
4. 変更に比例したローカル検証を実行する。
5. GitHubへ反映する作業では、対象commit / PRのGitHub Actions結果を確認する。
6. 各受け入れ条件を満たす証拠を確認し、変更内容、検証結果、残るリスクだけを簡潔に報告する。

## モデルルーティング

- 既定: `gpt-5.6-sol / medium` — 実装、設計、デバッグ、レビュー、最終統合。
- Sol利用枠を温存する限定worker: `gpt-5.6-luna / max` — 候補抽出、機械的変換、限定探索、独立した読み取り中心の確認。
- Luna/max が受け入れ条件を満たさない、または局所探索を越える判断が必要なら、同じ失敗を反復せず証拠を短く引き継いで Sol/medium へ昇格する。
- 追加のモデルやrouting分岐は、ユーザー指定または repo-local eval で利用枠・速度・品質の測定可能な改善が確認された場合だけ導入する。

## Skill の入口

- `repo-research`: 未知のリポジトリ、複雑な依存関係、外部仕様を実装前に調査するとき。
- `github-operations`: GitHubへの作成・同期・push/pull・Issue・PR等を明示的に依頼されたとき。
- `self-improvement`: agent/workflow を評価付きで反復改善するとき。
- `long-running-work`: 長時間または複数セッションにまたがる作業を分割・引き継ぐとき。
- その他の skill は、その frontmatter の適用条件を満たす場合だけ読みます。

GitHub操作の明示依頼がない通常のローカル開発では、GitHubへ自動的に書き込みません。

## 検証の比例性

- 可逆で影響の小さい変更では、実装をそのまま写すだけのテストを増やさない。
- バグ修正、公開API、永続化、認証・認可、並行性、課金、セキュリティでは回帰を示す検証を優先する。
- 同じ検証を再実行しても実装・成果物・判断材料が変わらない場合は進捗と数えず、戦略変更、ブロッカー提示、追加確認のいずれかに切り替える。

## Shikishi Studio 固有ルール

- Build and maintain Shikishi Studio as a Python application with small, reviewable changes.
- Use [rules/README.md](rules/README.md) as the project-specific rule index. Follow the matching architecture, reliability, data-processing, testing, security, operations, UI, Python, Git, and Docker rule files.
- Consult [skills/python-development/SKILL.md](skills/python-development/SKILL.md) for Python implementation/refactoring/review, [skills/python-dependency-selection/SKILL.md](skills/python-dependency-selection/SKILL.md) when a material dependency choice is open, and [skills/codebase-health-review/SKILL.md](skills/codebase-health-review/SKILL.md) for explicit repository-health work.
- Keep reusable CLI/data-processing code in `src/shikishi/`, web/API code in `app.py` and `studio/`, browser assets in `static/`, and tests in `tests/`.
- Validate data at external boundaries and raise actionable errors. Never silently discard invalid input.
- Preserve source data. Write transformed data and generated artifacts to separate, traceable locations.
- Never train, fine-tune, merge, rewrite, overwrite, or otherwise mutate model weights without first telling the user exactly what will change and receiving explicit approval for that weight-changing operation. Prefer dedicated, reviewable training tools such as the Kaggle notebook. Inference-only adapter scales, downloading an unchanged published artifact, and checksum verification do not mutate weights. Save approved training results as new, versioned, provenance-recorded artifacts unless overwrite is explicitly approved.
- Do not hardcode secrets. Use environment variables and document newly introduced variables in `.env.example`.
- For Python/runtime changes, the project quality path is `docker compose build app`, `docker compose run --rm app python -m ruff check .`, `docker compose run --rm app python -m ruff format --check .`, `docker compose run --rm app python -m mypy`, and `docker compose run --rm app python -m pytest`.
- Documentation-only and other narrowly scoped changes may use a smaller check when the omitted gates cannot exercise the changed surface.
- Keep commits focused and use conventional prefixes. Do not include unrelated changes, secrets, virtual environments, caches, generated artifacts, or machine-specific configuration.
