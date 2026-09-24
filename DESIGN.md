# Design

## Purpose

Style LoRAを用いた画像生成を、ローカルGPU上で再現可能かつデモ運用可能な形にし、学習・推論・Androidからの利用までを一つのprojectとして管理する。

## Design principles

- **local GPUを主実行環境とする。** 生成の主要経路はPC上で完結させる。
- **reproducibilityを優先する。** model revision、LoRA SHA、prompt、seed、生成条件を記録する。
- **readinessを明示する。** process aliveと生成可能状態を分け、`/readyz` をデモ開始条件とする。
- **GPU workをboundedにする。** 単一workerと上限付きqueueでVRAM競合と無制限並列を避ける。
- **LAN公開はfail-closed。** loopback外へ公開するときはtoken認証を必須にする。
- **trainingとservingのcredential boundaryを分ける。** Kaggle tokenをWeb appへ渡さない。
- **generated artifactとmodel/cacheを分離する。** reset時に学習済みmodelやcacheを誤削除しない。
- **real GPU trainingをCIへ含めない。** CIは再現可能なstatic/unit/integration quality gateに限定する。

## Non-goals

- インターネットへ直接公開するpublic image-generation service。
- CIからKaggle GPU学習を自動起動すること。
- model/cacheと生成履歴を同一ライフサイクルで扱うこと。

## Source of truth

storage境界は `docs/storage-layout.md`、既知課題と解消計画は `docs/issue-resolution-plan.md`、model provenanceは `models/registry.json` とversion metadataを正本とする。
