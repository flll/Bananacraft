# 競合ベンチマーク

最終更新: 2026-06-04

North Star 概要: [NORTH_STAR.md](./NORTH_STAR.md) | 履歴: [IMPLEMENTATION_HISTORY.md](./IMPLEMENTATION_HISTORY.md)

---

## Tier 1 — 常時参照

### Bloxelizer — https://bloxelizer.com/

| 機能 | Bananacraft | 状態 |
|------|-------------|------|
| GLB/OBJ/STL → blocks | Tripo + GLB Path B | Partial |
| PNG/JPEG → voxel art | Concept 画像 → Tripo | Partial |
| `.schem` export | Path A stylize | Have |
| `.litematic` / Bedrock | `schem_litematic.py`（要 litemapy） | Have |
| レイヤスライス・編集 | `schem_preview.py` Y スライダー | Have |
| パレット swap / find-replace | `schem_resize.replace_block_type_in_schem` | Have |
| ドロップイン import | Blueprint `file_uploader` | Have |
| GLB ローカルボクセル→schem | Path B + `schem_writer.py` | Have |
| schem 手動リサイズ | Blueprint UI | Have |
| AI text/image 生成 | Tripo + Gemini | Partial |
| OSM リアル地形 | — | Missing |
| Skin → Statue | — | Missing |

### Higgsfield (HiggsCraft) — https://higgsfield.ai/plugins/minecraft

| 機能 | Bananacraft | 状態 |
|------|-------------|------|
| プロンプト → 建築 | Tripo stylize → schem | Partial |
| プロンプト → 画像 | Gemini concept | Partial |
| プロンプト → 動画 | — | Missing |
| Camera 参照画像 | `design_*_camera_reference.jpg` + Gemini 二重参照 | Have |
| Supercomputer 出力スロット UX | PipelineStatus | Partial |
| Generation Archive | 一覧 + ゾーン適用 + 再配置 | Have |
| Generate 前コスト表示 | 静的目安 + Tripo リンク | Have |
| ブロック逐次 materialize | Mineflayer（装飾 + schem 本体） | Have |
| ゲーム内 Mod (NeoForge) | Streamlit tailnet（Phase 4 文書化のみ） | Missing (意図) |
| `/higgsfield auth` 型認証 | API キー UI | 別方式 |

**凡例:** Have = 実用可 / Partial = 一部または品質不足 / Missing = 未実装

---

## Tier 2 — ロードマップ参照

| 製品 | URL | 形態 | パクる価値 |
|------|-----|------|------------|
| VibeBuild | https://github.com/WilliamStanton/vibe-build | Fabric + multi-agent | Planner/Executor、ghost preview |
| PromptCraft | https://github.com/tusharv2005/PromptCraft | Client Mod + fal.ai | Generate/Craft/Stream モード |
| MineClawd | https://github.com/Zhou-Shilin/MineClawd | Server Mod + OpenClaw | ゲーム内自律エージェント |
| ObjToSchematic | https://objtoschematic.com/ | Web | Constraint axis + Size |
| BuilderGPT | https://github.com/CyniaAI/BuilderGPT | Cynia Agents | NL → schem（paused） |

---

## ギャップ優先度（2026-06 更新）

1. **P0** — ゾーン vs schem サイズ — **緩和済み**（自動/手動リサイズ）。Tripo Path A 完全自動は未解決
2. **P1** — Bloxelizer parity — **Phase 1 完了**
3. **P2** — Higgsfield UX — **Phase 2 完了**
4. **P3** — `.litematic` — **PoC 完了**（litemapy 依存）
5. **P4** — ゲーム内 Mod — **文書化のみ** [PHASE4_MOD_BRIDGE.md](./PHASE4_MOD_BRIDGE.md)

詳細 Phase: [ROADMAP.md](./ROADMAP.md)
