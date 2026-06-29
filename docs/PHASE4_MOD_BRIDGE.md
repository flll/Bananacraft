# Phase 4 — ゲーム内 Mod ブリッジ（設計メモ）

**ステータス:** 文書化のみ（実装見送り、2026-06-04）  
**前提:** Phase 2 Higgsfield parity が Streamlit 上で完了してから再評価

---

## なぜ見送りか

| 理由 | 説明 |
|------|------|
| North Star | Bananacraft の正系 UI は **Streamlit + tailnet**。Higgsfield の NeoForge Mod は「メタファ」であり必須ではない |
| コスト | Mod 配布・バージョン追従・認証は Streamlit API キー方式より重い |
| 既存経路 | WorldEdit + RCON + Mineflayer で「生成 → 配置」は既に E2E 可能 |

## 競合の Mod パターン（参照のみ）

- **Higgsfield / HiggsCraft** — ゲーム内 Supercomputer、Generation Archive、逐次 materialize
- **PromptCraft** — Client Mod + 外部 API
- **VibeBuild** — Fabric + ghost preview

コード無断転載は行わない。UX のみベンチマーク。

## 将来実装する場合の候補

### A. 薄い NeoForge Mod（推奨候補）

- `/bananacraft paste <schem>` — tailnet 上の Bananacraft API から schem URL を取得して paste
- `/bananacraft status` — 直近ジョブの成否
- 認証: ワンタイムトークン（Higgsfield `/auth` 相当を簡略化）

### B. RCON トリガのみ（最小）

- Mod なし。Streamlit から既存 `schem_deploy` + `paste_via_rcon` を継続
- ゲーム内 UI は諦め、tailnet ブラウザを正とする

### C. WebSocket ブリッジ

- Mineflayer 既存ボットを拡張し、ゲーム内チャットコマンドで Streamlit ジョブをキュー

## 判断基準（再開時）

1. tailnet 以外でプレイするユーザー比率
2. WorldEdit paste の失敗率（`KNOWN_CHALLENGES` #1 残存時は Mod も同じサイズ問題を抱える）
3. NeoForge 1.21.x とのメンテコスト

## 関連

- [ROADMAP.md](./ROADMAP.md) Phase 4
- [NORTH_STAR.md](./NORTH_STAR.md) — 非ゴール「初手 Mod 全面移行」
