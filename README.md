# Bananacraft Core (Deployment)

This is the deployment version of Bananacraft, stripped of legacy code and optimized for GCE.

開発者向けのリポジトリ設計・データフロー・改修ガイドは [docs/REPOSITORY_DESIGN.md](docs/REPOSITORY_DESIGN.md) を参照してください。

## API キーとマルチ LLM

- **既定割当**: 区画 JSON・建築／インフラの Function Calling は OpenAI（`gpt-5.5`）、コンセプト対話と装飾は Anthropic（`claude-sonnet-4-6`）、参照付き画像生成は Google Gemini（`gemini-3-pro-preview` / `gemini-3-pro-image-preview`）。実装は [app/ai/routing.py](app/ai/routing.py) で固定されています。
- **単一キー運用**: `OPENAI_API_KEY` や `ANTHROPIC_API_KEY` が無くても、`GEMINI_API_KEY` のみで全工程が Gemini にフォールバックします。
- **ブラウザ永続化**: Streamlit サイドバーから `GEMINI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` を入力し、「ブラウザに保存」で **localStorage** に JSON 保存できます（依存: `streamlit-js-eval`）。**XSS があるページではキーが窃取されうる**ため、信頼できる環境でのみ利用し、本番ではサーバ側シークレットやプロキシ方式を推奨します。
- **Function Calling のベンチマーク例**: [Berkeley Function Calling Leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html) をモデル選定の参考にし、リリース周期で `routing.py` の ID を見直してください。

## 起動方法（Makefile）

```bash
cp .env.example .env   # 未作成の場合
# .env に GEMINI_API_KEY および RCON_PASSWORD を設定

make help            # ターゲット一覧
```

| 用途 | コマンド |
|------|----------|
| **開発（おすすめ）** | `make mc-reset`（初回）→ `make mc-up` → `make run` |
| **UI もコンテナ** | `make stack-up` |
| **Minecraft のみ** | `make mc-up` / `make mc-down` / `make mc-logs` / `make mc-attach` |

- **UI**: [http://localhost:8501](http://localhost:8501)
- **Minecraft**: Purpur **26.1.2**・フラットワールド。ゲーム **`localhost:28888`**、RCON **`localhost:28889`**（`.env` の `RCON_PASSWORD`）
- **ワールドデータ**: `./minecraft-data/`（Git 管理外）。詳細は [minecraft/README.md](minecraft/README.md)
- **プロジェクトデータ**: `./projects`（`make run` はホスト、`make stack-up` はコンテナにマウント）
- **権限（PermissionError）**: `make fix-projects-perms`、または `.env` の `DOCKER_UID` / `DOCKER_GID` を `id -u` / `id -g` に合わせて `docker compose build --no-cache`

停止: `make stack-down` または `make mc-down`（Minecraft のみ）

## Docker Compose（localhost / サーバ共通）

`docker-compose.yml` には **minecraft**（Purpur 26.1.2 + EssentialsX / WorldEdit、[itzg/minecraft-server](https://hub.docker.com/r/itzg/minecraft-server)）と **bananacraft** の 2 サービスがあります。`make stack-up` と同等:

```bash
docker compose up --build -d
```

## 📦 Contents
- **app/**: Streamlit Application (v2)
- **AI_Carpenter_Bot/**: Node.js Mineflayer Bot
- **deployment/**: Systemd configs
- **setup.sh**: One-click setup script

## 🚀 GCE Deployment Guide

### 1. Upload to GCE
Clone this repository to your GCE instance (e.g. `/home/nakanishi/bananacraft-core`).

### 2. Run Setup
```bash
cd bananacraft-core
chmod +x setup.sh
./setup.sh
```

### 3. Configure
Copy the environment file and edit it:
```bash
cp .env.example .env
nano .env
```
*Set your `GEMINI_API_KEY`（最低限・画像とフォールバック用）および任意で `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`。詳細は `.env.example` と上記「API キーとマルチ LLM」を参照。*

### 4. Setup Minecraft Server

**Docker（推奨）**: `make mc-reset`（初回）→ `make mc-up`。Purpur 26.1.2・フラット・プラグイン付き。ポート **28888** / **28889**。

**手動**: 別途 `server.jar` を配置し、`server.properties` で RCON を有効化。`.env` の `RCON_PORT` / `MC_PORT` を手動サーバーのポートに合わせる。

### 5. Auto-Start Service
Link the systemd services:

```bash
# Edit paths in services if username is not 'nakanishi'
nano deployment/bananacraft.service
nano deployment/minecraft.service

# Link and Start
sudo cp deployment/bananacraft.service /etc/systemd/system/
sudo cp deployment/minecraft.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable minecraft
sudo systemctl enable bananacraft

sudo systemctl start minecraft
# Wait for server to load...
sudo systemctl start bananacraft
```

## 🛠️ Usage
Access the app at `http://<YOUR_GCE_IP>:8501`.
- **Phase 3**: Click "Run AI Carpenter (Auto)" to spawn the builder bot.
