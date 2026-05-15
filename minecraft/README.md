# Docker Minecraft（Bananacraft 用）

`make mc-up` または `make stack-up` で [itzg/minecraft-server](https://hub.docker.com/r/itzg/minecraft-server) が起動し、ワールドデータはリポジトリ直下の **`../minecraft-data/`** に保存されます（Git 管理外）。

## ポート

| ポート | 用途 |
|--------|------|
| 25565 | ゲーム接続（Mineflayer ボットはホストから `localhost:25565`） |
| 25575 | RCON（`.env` の `RCON_PASSWORD` と一致） |

## 初回起動

- 初回は `server.jar` のダウンロードとワールド生成のため **数分**かかります。
- `docker compose logs -f minecraft` で `Done` や RCON 有効のログを確認してください。
- EULA は Compose の `EULA=TRUE` で同意済みです。

## 設定

ルートの `.env` で `MC_TYPE` / `MC_VERSION` / `MC_MEMORY` / `RCON_PASSWORD` などを変更できます。詳細は [.env.example](../.env.example) を参照。

## 推奨運用

- **開発**: `make mc-up` のあと `make run`（Streamlit はホスト、MC は Docker）
- **一式コンテナ**: `make stack-up`（UI は http://localhost:8501）
