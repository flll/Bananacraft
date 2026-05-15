# Docker Minecraft（Bananacraft 用）

Purpur **26.1.2**・**フラット**ワールド・プラグイン（EssentialsX / WorldEdit）付きのサーバーを [itzg/minecraft-server](https://hub.docker.com/r/itzg/minecraft-server) で起動します。ワールドデータは **`../minecraft-data/`**（Git 管理外）。

## ポート（ホスト）

| ポート | 用途 |
|--------|------|
| **28888** | ゲーム接続（クライアント・Mineflayer ボット） |
| **28889** | RCON（`.env` の `RCON_PASSWORD` と一致） |

既定の 25565 / 25575 とは別ポートのため、ホスト上の別 MC サーバーと衝突しにくくしています。

## プラグイン

[docker-compose.yml](../docker-compose.yml) の `MODRINTH_PROJECTS` で自動取得:

- EssentialsX
- WorldEdit

初回起動後に `make mc-logs` でプラグイン読込を確認してください。26.1.2 向けバージョンが Modrinth に無い場合はログにエラーが出ます。そのときは [itzg Modrinth ドキュメント](https://github.com/itzg/docker-minecraft-server/blob/master/docs/mods-and-plugins/modrinth.md) を参照し、slug のバージョン指定を検討してください。

## コマンド

```bash
make mc-reset    # 初回 or VANILLA から移行時（データ削除・確認あり）
make mc-up       # 起動（jar + プラグイン DL で数分かかることがある）
make mc-logs     # ログ
make mc-attach   # コンソール（デタッチ: Ctrl+P → Ctrl+Q）
make mc-down     # 停止
```

**開発の推奨**: `make mc-up` のあと `make run`（UI はホスト、`.env` の `RCON_PORT=28889` / `MC_PORT=28888`）。

## 設定

- サーバー種別・バージョン・フラット・プラグイン一覧は **Compose で固定**（`.env` の `MC_TYPE` / `MC_VERSION` は参考）。
- メモリなどは `.env` の `MC_MEMORY` 等（[.env.example](../.env.example)）。
