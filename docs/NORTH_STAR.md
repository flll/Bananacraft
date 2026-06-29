# Bananacraft North Star

**北極星競合:** [Bloxelizer](https://bloxelizer.com/) と [Higgsfield Minecraft](https://higgsfield.ai/plugins/minecraft)。

エージェント向け Skill: [flll/skills/bananacraft-north-star](https://github.com/flll/skills/tree/main/bananacraft-north-star)

---

## 何を目指すか

同じ問題空間 — **アイデア → ボクセル → ワールド反映** — を、Bananacraft 独自の強みで解く。

| 競合 | レイヤ | 強み |
|------|--------|------|
| **Bloxelizer** | ブラウザ | 3D/画像→ボクセル、フォーマット変換、パレット編集、Voxelizer UX |
| **Higgsfield** | ゲーム内 Mod | Supercomputer、参照画像、Archive、逐次 materialize |
| **Bananacraft** | Streamlit + Docker + RCON/Mineflayer | City Plan Phase、Tripo 統合、tailnet デプロイ |

## ポジショニング

- **Bloxelizer からパクる:** 変換・編集・プレビュー（ブラウザ側 UX）
- **Higgsfield からパクる:** 生成フロー・参照画像・演出・Archive（ワールド反映 UX）
- **独自:** Phase 0–3 オーケストレーション、ゾーン連動 Tripo、Mineflayer 演出

## パクる定義

機能・UX パターンの **parity** を目指す。競合のコードや API を無断転載しない。

## 既知ブロッカー

[KNOWN_CHALLENGES.md](./KNOWN_CHALLENGES.md) **#1**（ゾーン vs schem サイズ）を North Star parity の前提として先に解く。

## 非ゴール

- NeoForge Mod への初手全面移行（Phase 4 オプション）
- Hytale prefab 対応
- 競合 API のクローン

## 関連

- [COMPETITOR_BENCHMARK.md](./COMPETITOR_BENCHMARK.md) — 機能マトリクス
- [ROADMAP.md](./ROADMAP.md) — Phase 別計画
- [REPOSITORY_DESIGN.md](./REPOSITORY_DESIGN.md) — 実装マップ
