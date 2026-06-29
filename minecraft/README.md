# Docker Minecraft（Bananacraft 用）

Purpur **26.1.2**・**フラット**ワールド・WorldEdit プラグイン（`.env` の `ENABLE_BLUEMAP=true` で BlueMap も追加）付きのサーバーを [itzg/minecraft-server](https://hub.docker.com/r/itzg/minecraft-server) で起動します。ワールドデータは **`../minecraft-data/`**（Git 管理外）。

リポジトリは「**Minecraft サーバーが常時起動している前提**」で書かれており、Bananacraft UI もまとめて `make up` で立ち上がります。

## ポート（ホスト）

| ポート | 用途 |
|--------|------|
| **28888** | ゲーム接続（クライアント・Mineflayer ボット） |
| **28889** | RCON（`.env` の `RCON_PASSWORD` と一致） |
| **8100** | BlueMap Web マップ（`ENABLE_BLUEMAP=true` のときのみ） |

既定の 25565 / 25575 とは別ポートのため、ホスト上の別 MC サーバーと衝突しにくくしています。

## プラグイン

[docker-compose.yml](../docker-compose.yml) の `MODRINTH_PROJECTS` で自動取得します。Makefile が `.env` の `ENABLE_BLUEMAP` を読んでスラッグ列を組み立てます。

- WorldEdit（既定で有効、Bananacraft の `.schem` 配置に必須）
- BlueMap（`ENABLE_BLUEMAP=true` のとき）

初回起動後に `make logs-mc` でプラグイン読込を確認してください。26.1.2 向けバージョンが Modrinth に無い場合はログにエラーが出ます。そのときは [itzg Modrinth ドキュメント](https://github.com/itzg/docker-minecraft-server/blob/master/docs/mods-and-plugins/modrinth.md) を参照し、slug のバージョン指定を検討してください。

## コマンド

```bash
make reset    # 初回 or 設定をリセットしたいとき（minecraft-data を削除）
make up       # Minecraft + Bananacraft UI 起動（jar + プラグイン DL で数分）
make logs-mc  # Minecraft のログ
make attach   # コンソール（デタッチ: Ctrl+P → Ctrl+Q）
make down     # すべて停止
```

**ホスト Python 開発**: `make up` のあと、`.env` の `RCON_HOST=localhost` に書き換えて `make dev`（venv で Streamlit を起動）。

## 設定

- サーバー種別・バージョン・フラット・プラグイン一覧は **Compose で固定**（`.env` の `MC_TYPE` / `MC_VERSION` は参考）。
- メモリなどは `.env` の `MC_MEMORY` 等（[.env.example](../.env.example)）。

## Tripo `.schem` を WorldEdit で配置する

詳細は [`docs/REPOSITORY_DESIGN.md`](../docs/REPOSITORY_DESIGN.md) §13 を参照。Bananacraft の Building ページから「📦 WorldEdit で配置 (.schem)」を押すと、次の処理が走ります。

1. `projects/<name>/building_<id>.schem` を `minecraft-data/plugins/WorldEdit/schematics/building_<id>.schem` にコピー
2. RCON 経由で以下のコマンド列を送信（[`app/v2/schem_deploy.py`](../app/v2/schem_deploy.py) `build_paste_commands`）

```
//world world
//pos1 <ox>,<oy>,<oz>
//schem load building_<id>.schem
//paste -a
say Bananacraft: pasted building_<id>.schem at <ox>,<oy>,<oz> (world=world)
```

サーバーコンソール (RCON) は WorldEdit のセッションを持たないので、**毎回 `//world <name>` でワールドを明示する必要があります**。`world` 以外のワールド名を使っているサーバーは `.env` の `BANANACRAFT_MC_WORLD` を書き換えてください。

確認手順:

1. `make up` でサーバー + UI を起動し、`make logs-mc` で WorldEdit ロード行を確認。
2. ホストから `ls minecraft-data/plugins/WorldEdit/schematics/` が見えること（書き込み権限も）。Bananacraft UI コンテナは [`docker-compose.yml`](../docker-compose.yml) で `./minecraft-data` を `/minecraft-data` にマウントしており、`WORLDEDIT_SCHEM_DIR=/minecraft-data/plugins/WorldEdit/schematics` 経由で同じディレクトリに書き込みます。
3. 初回は `make attach` で同じコマンドを手動実行し、`//paste` がコンソールから動くことを確認するのが安全（WorldEdit のバージョン差異で `//paste -ao <x> <y> <z>` 形式が必要なケースあり）。
4. 別ディレクトリを使う場合は環境変数 `WORLDEDIT_SCHEM_DIR` で明示します。
