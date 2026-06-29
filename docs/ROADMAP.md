# Bananacraft ロードマップ

North Star: [NORTH_STAR.md](./NORTH_STAR.md) | ベンチマーク: [COMPETITOR_BENCHMARK.md](./COMPETITOR_BENCHMARK.md) | 履歴: [IMPLEMENTATION_HISTORY.md](./IMPLEMENTATION_HISTORY.md)

---

## Phase 0 — 基盤（完了）

- [x] `bananacraft-north-star` Skill（flll/skills）
- [x] NORTH_STAR / COMPETITOR_BENCHMARK / ROADMAP ドキュメント
- [x] Karpathy guidelines（flll/skills + `.cursor/rules/`）
- [x] skill-manifest / verify-skills 整合

---

## Phase 1 — Bloxelizer parity（変換・編集）— 2026-06 完了

**目標:** ブラウザ内で変換・プレビュー・配置まで 1 フロー。

| タスク | 状態 |
|--------|------|
| schem プレビュー強化（Y レイヤスライス、ゾーン警告） | 完了 |
| GLB/PNG/schem ドロップイン import | 完了 |
| GLB → ボクセル → `.schem`（Path B、Size=ゾーン最長辺） | 完了 |
| `.litematic` export | 完了（要 litemapy、[LITEMATIC_EXPORT.md](./LITEMATIC_EXPORT.md)） |
| schem ブロック種 find-replace | 完了（`schem_resize.py`） |
| 手動リサイズ UI | 完了 |

**成功条件（Karpathy §4）:**

- サンプル GLB → UI schem 化 → プレビュー → RCON paste（Build セクションから paste）— **達成**
- ゾーンサイズ誤差 **1.5x 以内** — Path B / 手動・自動リサイズで **緩和**。Tripo Path A 単体は警告 + 自動リサイズ試行

---

## Phase 2 — Higgsfield parity（生成 UX）— 2026-06 完了

**目標:** 参照画像 + プロンプト → 生成 → ゾーン内配置、Archive から再配置。

| タスク | 状態 |
|--------|------------|
| 参照画像スロット（Camera 相当） | 完了 — `design_*_camera_reference.jpg` |
| Generation Archive UI（適用・再配置） | 完了 |
| Generate 前 Tripo クレジット見積もり | 完了 |
| Mineflayer 逐次設置（schem 本体） | 完了 — Build 節 |

**成功条件:**

- 参照画像 1 枚 + プロンプト → paste 成功 — **Camera + Concept 二重参照で改善**
- Archive から過去生成を再配置可能 — **達成**

---

## Phase 3 — サイズ制御（ObjToSchematic 融合）— 2026-06 緩和完了

**目標:** [KNOWN_CHALLENGES.md](./KNOWN_CHALLENGES.md) #1 解消。

| タスク | 状態 |
|--------|------|
| Path B ローカル化（GLB → schem + Size） | 完了 |
| schem bbox リサイズ | 完了 — `schem_resize.auto_resize_schem_file` |
| Tripo 後自動リサイズ | 完了 — `mesh_architect.py` |
| `stylize_block_for_target` をフォールバック化 | 既存（完全解決ではない） |

**成功条件:**

- 12×12 ゾーン → schem W×D が 1.5x 以内 — **自動リサイズ + 手動ボタンで緩和**（Tripo 単体は未保証）

---

## Phase 4 — オプション: ゲーム内ブリッジ

**ステータス:** 文書化のみ → [PHASE4_MOD_BRIDGE.md](./PHASE4_MOD_BRIDGE.md)

- NeoForge 薄い Mod または RCON トリガ（Supercomputer メタファのみ）
- Streamlit tailnet は維持

---

## 非ゴール

- 競合コード無断転載
- Hytale prefab
- 初手 Mod 全面移行
