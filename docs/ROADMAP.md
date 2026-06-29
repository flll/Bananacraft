# Bananacraft ロードマップ

North Star: [NORTH_STAR.md](./NORTH_STAR.md) | ベンチマーク: [COMPETITOR_BENCHMARK.md](./COMPETITOR_BENCHMARK.md)

---

## Phase 0 — 基盤（完了）

- [x] `bananacraft-north-star` Skill（flll/skills）
- [x] NORTH_STAR / COMPETITOR_BENCHMARK / ROADMAP ドキュメント
- [x] Karpathy guidelines（flll/skills + `.cursor/rules/`）
- [x] skill-manifest / verify-skills 整合

---

## Phase 1 — Bloxelizer parity（変換・編集）

**目標:** ブラウザ内で変換・プレビュー・配置まで 1 フロー。

| タスク | 関連コード |
|--------|------------|
| schem プレビュー強化（レイヤ、パレット） | `app/v2/schem_preview.py`, `block_texture_resolver.py` |
| GLB/PNG/schem ドロップイン import | `app/pages_v2/building.py` |
| `.litematic` export 調査 | 新規 or ライブラリ選定 |

**成功条件（Karpathy §4）:**

- サンプル GLB → UI schem 化 → プレビュー → RCON paste
- ゾーンサイズ誤差 **1.5x 以内**

---

## Phase 2 — Higgsfield parity（生成 UX）

**目標:** 参照画像 + プロンプト → 生成 → ゾーン内配置、Archive から再配置。

| タスク | 関連コード |
|--------|------------|
| 参照画像スロット（Camera 相当） | `app/api_client.py`, `building.py` |
| Generation Archive UI | `app/file_manager.py`, 新 UI |
| Generate 前 Tripo クレジット見積もり | `app/tripo_client.py`, UI |
| Mineflayer 逐次設置オプション既定化 | `AI_Carpenter_Bot/` |

**成功条件:**

- 参照画像 1 枚 + プロンプト → paste 成功
- Archive から過去生成を再配置可能

---

## Phase 3 — サイズ制御（ObjToSchematic 融合）

**目標:** [KNOWN_CHALLENGES.md](./KNOWN_CHALLENGES.md) #1 解消。

| タスク | 関連コード |
|--------|------------|
| Path B ローカル化（GLB → schem + Size） | `mesh_architect.py`, `voxel_glb_builder.py` |
| または schem bbox リサイズ | 新規ユーティリティ |
| `stylize_block_for_target` をフォールバック化 | `tripo_config.py` |

**成功条件:**

- 12×12 ゾーン → schem W×D が 1.5x 以内（自動、手動調整不要）

---

## Phase 4 — オプション: ゲーム内ブリッジ

**前提:** Phase 2 完了後にアーキテクチャ判断。

- NeoForge 薄い Mod または RCON トリガ（Supercomputer メタファのみ）
- Streamlit tailnet は維持

---

## 非ゴール

- 競合コード無断転載
- Hytale prefab
- 初手 Mod 全面移行
