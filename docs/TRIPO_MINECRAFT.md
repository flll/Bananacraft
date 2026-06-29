# Tripo3D × Minecraft — ノウハウ集

Agent / 開発者向け。**Blueprint・Tripo 改修前に必読。**

関連: [KNOWN_CHALLENGES.md](./KNOWN_CHALLENGES.md)、[REPOSITORY_DESIGN.md](./REPOSITORY_DESIGN.md) §13

---

## 1. 概要

Bananacraft は **Path A**（Tripo `stylize_model` → `.schem` 直出力）を採用している。
コミュニティの主流は **Path B**（Tripo GLB → ObjToSchematic → `.schem`）で、**サイズ制御**が Path A に無い。

| | Path A（Bananacraft schem 経路） | Path B（業界標準） |
|---|----------------------------------|-------------------|
| 流れ | 画像 → image_to_model → stylize minecraft → `.schem` | 画像 → image_to_model → GLB → ObjToSchematic → `.schem` |
| サイズ制御 | **なし**（メッシュスケール任せ） | **Constraint axis + Size** |
| ブロック割当 | Tripo AI 自動（150+ 種） | vanilla.atlas + パレット |
| 1:1 ボクセル絵 | 不向き | voxel size を指定可能 |
| クレジット | image_to_model + stylize | image_to_model + ローカル変換 |

---

## 2. Tripo API クックブック

### 2.1 `image_to_model`

実装: [`app/tripo_client.py`](../app/tripo_client.py) `create_image_task`

| パラメータ | Bananacraft 既定 | 意味 |
|-----------|-----------------|------|
| `auto_size` | `False` | メッシュスケール自動推定 |
| `orientation` | `"default"` | `"align_image"` で画像向きに合わせる |
| `texture_alignment` | `"original_image"` | `"geometry"` は再テクスチャ感低減の可能性 |
| `texture` / `pbr` | `True` | 連続メッシュ + PBR |
| `face_limit` | `30000` | ポリゴン上限 |
| `geometry_quality` | `standard` | `detailed` は細部増 → schem 巨大化リスク |

### 2.2 `stylize_model`（minecraft）

| パラメータ | 公式 | 中国語 UI | 解釈 |
|-----------|------|-----------|------|
| `block_size` | default **80** | **32〜128** | **小 = 細かい = ブロック数増 = 外接大** / **大 = 粗い = 外接縮小の可能性** |
| `style` | `minecraft` | 同左 | 出力 `.schem`（gzip NBT） |

**「block_size=1 で 1:1」は公式 API に存在しない。**

### 2.3 `stylize_block_for_target`（Bananacraft 自動算出）

[`app/v2/tripo_config.py`](../app/v2/tripo_config.py):

```text
小ゾーン → block_size 大 (128 寄り) → 粗い離散化 → 外接縮小を期待
大ゾーン → block_size 小 (32 寄り) → 細かい離散化
```

| target_blocks（ゾーン最長辺） | block_size |
|------------------------------|------------|
| 12 | 128 |
| 24 | 107 |
| 32 | 99 |
| 48 | 82 |
| 96 | 32 |

式: `n <= 12` なら **128**、それ以外は `clamp(32, 128, round(128 - (n - 4) * 96 / 92))`

---

## 3. ObjToSchematic から学ぶ Size 制御

[ObjToSchematic](https://objtoschematic.com/) Voxelise 設定:

- **Constraint axis**: Y なら高さ = Size ブロックに正規化
- **Size**: ゾーン `max(width, depth)` をここに入れる

Bananacraft GLB 経路は [`mesh_architect.py`](../app/v2/mesh_architect.py) の `target_voxel` が同等概念。
**schem 経路だけが欠落** — 中長期は Path B ローカル化または schem bbox リサイズ。

---

## 4. nanobanana / MC ブロック画入力

### 鉄則

```
❌ nanobanana → image_to_model (連続メッシュ) → stylize → .schem
✅ 1 ピクセル/1 セル = 1 minecraft ブロック（再メッシュ化しない）
```

Tripo stylize を通す限り **1:1 は保証されない**。

### Structure 画像

- 白背景・正距離アイソメ
- 装飾最小（躯体優先）
- [`api_client.py`](../app/api_client.py) のプロンプトで「1 ブロック = 1 立方体」を維持

### 生成後チェック

- schem W×D vs ゾーン `max(width, depth)`
- **1.5 倍超 = 失敗扱い** — Build せず再生成方針を提示

---

## 5. トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| schem が 6 倍大きい | Path A に Size ノブ無し / block_size 小さすぎ | block_size→128、Path B 検討 |
| 1 面にドット絵 | 連続メッシュ→再離散化 | nanobanana は GLB+ローカル voxelize |
| 葉・ランタン散乱 | Tripo 自動 palette | Path B またはパレット制限 |
| プレビュー透明 | vanilla.atlas 部分集合 | jar 動的アトラス（`schem_glb_builder`） |
| paste 失敗 | 拡張子なし load | `//schem load name.schem`（修正済み） |

---

## 6. Bananacraft コードマッピング

| 段階 | ファイル |
|------|----------|
| Tripo 設定 | `app/v2/tripo_config.py` |
| image_to_model + stylize | `app/v2/mesh_architect.py`, `app/tripo_client.py` |
| schem 配置 | `app/v2/schem_deploy.py` |
| schem 書き出し（Path B ローカル） | `app/v2/schem_writer.py` |
| schem プレビュー | `app/v2/schem_preview.py`, `app/v2/schem_glb_builder.py` |
| テクスチャ解決 | `app/v2/block_texture_resolver.py` |
| jar PNG | `app/v2/mc_assets.py` |
| GLB ボクセル（Path B 相当） | `advanced_voxelizer` + `schem_writer`（UI ドロップイン） / `mesh_architect` GLB 経路 |

---

## 7. 参考リンク

- [Tripo Stylization](https://www.tripo3d.ai/features/ai-model-stylization)
- [Tripo Python SDK API](https://github.com/VAST-AI-Research/tripo-python-sdk/blob/master/docs/API.md)
- [ComfyUI TripoStylizeModel](https://comfyai.run/documentation/TripoStylizeModel)
- [ObjToSchematic 2.0](https://objtoschematic.com/)
- [Toolify: Tripo + ObjToSchematic](https://www.toolify.ai/ai-news/transform-images-to-minecraft-structures-a-comprehensive-guide-3388943)
- [BlockGPT schem ワークフロー](https://blockgpt.ai/blog/how-to-generate-minecraft-schematics-using-ai)

---

## 8. 変更履歴

| 日付 | メモ |
|------|------|
| 2026-06-04 | Path B ローカル: Blueprint ドロップイン GLB → advanced_voxelizer → schem_writer |
| 2026-05-20 | 初版。Path A/B 比較、block_size 逆転式、トラブルシュート |
