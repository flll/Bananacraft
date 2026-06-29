# Bananacraft — 既知の課題とノウハウ

**このファイルは忘れないためのメモです。** Agent / 開発者は Blueprint・Tripo・プレビュー改修の前に必ず読んでください。

関連: [TRIPO_MINECRAFT.md](./TRIPO_MINECRAFT.md)、[REPOSITORY_DESIGN.md](./REPOSITORY_DESIGN.md) §13

---

## 🔴 課題 #1: 建物サイズがゾーンと一致しない（最優先）

### 症状

- City Plan のゾーンは **12×12** なのに、Tripo `.schem` が **78×78×48** のように何倍も大きくなる。
- 毎回チャットで Agent に「小さくして」と指示しており、**手作業のたびにクレジットと時間を消費**している。

### 根本原因

| 段階 | 何が起きているか |
|------|------------------|
| Concept / Structure 画像 | プロンプトで「12 ブロック四方」と書いても、画像 AI は厳密なピクセル→ブロック対応を保証しない |
| Tripo `image_to_model` | **入力画像から 3D メッシュを作るだけ**で、ゾーン `width×depth` を API に渡していない |
| Tripo `stylize_model` | **Path A**: schem 直出力。**Size ノブ無し**（業界 Path B は ObjToSchematic の Constraint axis + Size あり） |
| `with_building_override(N)` | schem 外接を N にクランプしない。`block_size` は離散化粒度のみ |

**2026-05 修正:** `stylize_block_for_target` を逆転（小ゾーン → block_size **128**）。完全解決ではない — [TRIPO_MINECRAFT.md](./TRIPO_MINECRAFT.md) §1 参照。

### Agent チェックリスト

1. schem W×D×H（UI メタデータ）
2. ゾーン `max(width, depth)`
3. **1.5 倍超 = 失敗扱い**

### 正しい方向性

1. nanobanana → **二重変換を避ける**（§2）
2. schem bbox リサイズ（未実装）
3. Path B ローカル化（Tripo GLB + `target_voxel`）
4. `auto_size` / `align_image`（ゾーン連動 ON 時に試行）

---

## 🔴 課題 #2: 「1 ブロック = 1 ブロック」が Tripo 経路で崩れる

（変更なし — [TRIPO_MINECRAFT.md](./TRIPO_MINECRAFT.md) §4 参照）

---

## 🟡 課題 #3: schem プレビューのテクスチャ欠け・透明

### 対策（実装済み）

| 用途 | 推奨 |
|------|------|
| **schem プレビュー** | [`schem_glb_builder.py`](../app/v2/schem_glb_builder.py) + jar PNG + [`block_texture_resolver.py`](../app/v2/block_texture_resolver.py) |
| フォールバック | Plotly 単色 |
| ワールド内確認 | WorldEdit paste 後 `localhost:28888` |

---

## クイック参照

| やる | やらない |
|------|----------|
| GLB 経路 `target_voxel` 固定 | schem W×D×H をゾーンに合わせる |
| schem 経路 `block_size` 逆転（12→128） | nanobanana 1:1 保証 |
| jar 動的アトラスプレビュー | — |

---

## 変更履歴

| 日付 | メモ |
|------|------|
| 2026-05-20 | 初版 |
| 2026-05-20 | Path B 比較、block_size 逆転、jar GLB プレビュー |
