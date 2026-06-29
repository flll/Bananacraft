# 競合ベンチマーク

最終更新: 2026-06

North Star 概要: [NORTH_STAR.md](./NORTH_STAR.md)

---

## Tier 1 — 常時参照

### Bloxelizer — https://bloxelizer.com/

| 機能 | Bananacraft | 状態 |
|------|-------------|------|
| GLB/OBJ/STL → blocks | Tripo + GLB 経路 | Partial |
| PNG/JPEG → voxel art | Concept 画像 → Tripo | Partial |
| `.schem` export | Path A stylize | Have |
| `.litematic` / Bedrock | — | Missing |
| レイヤスライス・編集 | `schem_preview.py` Y スライダー | Have |
| パレット swap / find-replace | — | Missing |
| ドロップイン import | Blueprint `file_uploader` | Have |
| GLB ローカルボクセル→schem | Path B + `schem_writer.py` | Have |
| AI text/image 生成 | Tripo + Gemini | Partial |
| OSM リアル地形 | — | Missing |
| Skin → Statue | — | Missing |

### Higgsfield (HiggsCraft) — https://higgsfield.ai/plugins/minecraft

| 機能 | Bananacraft | 状態 |
|------|-------------|------|
| プロンプト → 建築 | Tripo stylize → schem | Partial |
| プロンプト → 画像 | Gemini concept | Partial |
| プロンプト → 動画 | — | Missing |
| Camera 参照画像 | concept + dropin 画像 | Partial |
| Supercomputer 出力スロット UX | PipelineStatus | Partial |
| Generation Archive | `projects/` ファイル | Partial |
| Generate 前コスト表示 | — | Missing |
| ブロック逐次 materialize | Mineflayer | Have |
| ゲーム内 Mod (NeoForge) | Streamlit tailnet | Missing (意図) |
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

## ギャップ優先度

1. **P0** — ゾーン vs schem サイズ（[KNOWN_CHALLENGES.md](./KNOWN_CHALLENGES.md) #1）
2. **P1** — Bloxelizer: schem プレビュー強化、ドロップイン import
3. **P2** — Higgsfield: 参照画像スロット、Archive UI、コスト表示
4. **P3** — フォーマット拡張（`.litematic`）
5. **P4** — ゲーム内 Mod ブリッジ（オプション）

詳細 Phase: [ROADMAP.md](./ROADMAP.md)
