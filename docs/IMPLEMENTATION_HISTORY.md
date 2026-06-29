# Bananacraft 実装履歴（AI / 開発者向け）

**目的:** 未来の AI モデルと開発者が、North Star ロードマップとコードの対応を時系列で追えるようにする正本。

関連: [NORTH_STAR.md](./NORTH_STAR.md) | [ROADMAP.md](./ROADMAP.md) | [COMPETITOR_BENCHMARK.md](./COMPETITOR_BENCHMARK.md)

---

## 記録ルール

1. 機能追加・方針変更時は **本ファイル末尾にエントリを追記**（削除しない）
2. エントリ形式: `YYYY-MM-DD` / フェーズ / 分類（Bloxelizer|Higgsfield|独自）/ 変更ファイル / 検証方法
3. [KNOWN_CHALLENGES.md](./KNOWN_CHALLENGES.md) の課題が解消したら、エントリに `closes #N` を明記

---

## 2026-06-04 — North Star 基盤（Phase 0）

| 項目 | 内容 |
|------|------|
| 分類 | 独自 |
| 成果 | `bananacraft-north-star` Skill（flll/skills）、`NORTH_STAR.md`、`COMPETITOR_BENCHMARK.md`、`ROADMAP.md`、`.cursor/rules/karpathy-guidelines.mdc` |
| 競合 | Tier 1: [Bloxelizer](https://bloxelizer.com/)、[Higgsfield Minecraft](https://higgsfield.ai/plugins/minecraft) |
| コミット | Bananacraft `a18bd1c`、skills `f6f3c4b` |

---

## 2026-06-04 — Phase 1 Bloxelizer parity（変換・編集）

| 項目 | 内容 |
|------|------|
| 分類 | Bloxelizer 相当 |
| 機能 | Y レイヤスライス、ゾーン vs schem 1.5x 警告、ドロップイン import（schem/画像/GLB）、Path B（`advanced_voxelizer` → `schem_writer.py`） |
| ファイル | `app/v2/schem_writer.py`, `app/v2/schem_preview.py`, `app/pages_v2/building.py`, `tests/test_schem_tripo.py` |
| 検証 | `TestSchemWriterRoundtrip` OK；UI: Blueprint → ドロップイン → GLB→schem → プレビュー → Build paste |
| コミット | `76eb90e` |

---

## 2026-06-04 — Phase 2 着手（Higgsfield 生成 UX）

| 項目 | 内容 |
|------|------|
| 分類 | Higgsfield 相当 |
| 機能 | Tripo クレジット目安（Generate 前）、Generation Archive（プロジェクト内 schem 一覧） |
| ファイル | `app/pages_v2/building.py`, `docs/COMPETITOR_BENCHMARK.md` |
| コミット | `3a59906` |

---

## 2026-06-04 — Phase 2–3 完了バッチ

| 項目 | 内容 |
|------|------|
| 分類 | Bloxelizer + Higgsfield + 独自 |
| 機能 | 下表参照 |
| ドキュメント | 本ファイル、`docs/LITEMATIC_EXPORT.md`、`docs/PHASE4_MOD_BRIDGE.md`、ROADMAP / BENCHMARK / KNOWN_CHALLENGES 更新 |

### 実装一覧

| 機能 | 分類 | モジュール |
|------|------|------------|
| Camera 参照スロット | Higgsfield | `building.py` Design 節、`design_*_camera_reference.jpg` |
| Archive → ゾーン適用・再配置 | Higgsfield | `building.py` `_render_generation_archive` |
| schem ブロック種 find-replace | Bloxelizer | `schem_resize.replace_block_type_in_schem` |
| schem 自動リサイズ（Tripo 後） | Phase 3 / ObjToSchematic 的 | `schem_resize.auto_resize_schem_file`, `mesh_architect.py` |
| 手動リサイズボタン | Phase 3 | Blueprint UI |
| `.litematic` export | Bloxelizer | `schem_litematic.py`（要 litemapy） |
| Mineflayer 逐次設置（本体） | Higgsfield | Build 節オプション → `AI_Carpenter_Bot` |
| Phase 4 Mod ブリッジ | — | 文書化のみ（実装見送り） |

### KNOWN_CHALLENGES との関係

- **#1 ゾーン vs schem サイズ:** Tripo Path A はダウンロード後に `auto_resize_schem_file` を試行。Path B / 手動リサイズでも対応。完全自動は Tripo 側 Size API 不在のため **緩和**（1.5x 以内を目標）
- **#2 1ブロック=1ブロック:** Path B + Camera 参照で改善。Tripo stylize 単体は未解決

---

## 次に読むべきファイル（実装マップ）

| 関心 | パス |
|------|------|
| UI オーケストレーション | `app/pages_v2/building.py` |
| Tripo → schem | `app/v2/mesh_architect.py` |
| schem 読み書き・編集 | `app/v2/schem_preview.py`, `schem_writer.py`, `schem_resize.py`, `schem_litematic.py` |
| WorldEdit 配置 | `app/v2/schem_deploy.py` |
| ローカル GLB ボクセル | `app/advanced_voxelizer.py` |
| Mineflayer | `AI_Carpenter_Bot/index.js`, `app/v2/carpenter.py` |

---

## 変更履歴（メタ）

| 日付 | 変更 |
|------|------|
| 2026-06-04 | 初版作成（Phase 0–3 バッチ記録） |
| 2026-06-04 | Phase 2–3 実装完了: Camera, Archive 適用/再配置, schem 編集, Mineflayer schem, litematic, mesh_architect 自動リサイズ |
