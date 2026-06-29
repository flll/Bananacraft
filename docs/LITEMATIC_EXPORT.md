# `.litematic` エクスポート

**分類:** Bloxelizer parity（Phase 1 拡張）  
**実装:** `app/v2/schem_litematic.py`  
**UI:** Building → Blueprint → schem プレビュー →「schem 編集ツール」→「.litematic を書き出し」

---

## 概要

WorldEdit の Sponge `.schem` を Bedrock / Litematica 向け `.litematic` に変換するオプション機能です。Bloxelizer が提供する Bedrock 向けフォーマットのギャップを埋めます。

## 依存関係

```bash
pip install litemapy
```

未インストール時は UI に「litemapy が必要」と表示され、書き出しはスキップされます（アプリ本体の起動には影響しません）。

## 変換仕様

| 項目 | 挙動 |
|------|------|
| 入力 | Sponge schem v2（`schem_preview.parse_schem_blocks`） |
| 出力 | 単一リージョン `Bananacraft`、原点 (0,0,0) |
| 空気ブロック | スキップ（`skip_air=True`） |
| ブロック状態 | `minecraft:block[id]` 形式を `BlockState` に分解 |

## 制限

- 大規模 schem はメモリ上に全ブロックを展開するため、極端に大きいファイルでは失敗する可能性があります。
- WorldEdit 固有の NBT ブロックエンティティは変換しません。
- Bedrock 実機での動作確認は手動テストが必要です。

## 関連

- [COMPETITOR_BENCHMARK.md](./COMPETITOR_BENCHMARK.md) — `.litematic` 行
- [IMPLEMENTATION_HISTORY.md](./IMPLEMENTATION_HISTORY.md) — 2026-06-04 Phase 2–3 バッチ
