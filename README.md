# Bananacraft Core (Deployment)

This is the deployment version of Bananacraft, stripped of legacy code and optimized for GCE.

開発者向けのリポジトリ設計・データフロー・改修ガイドは [docs/REPOSITORY_DESIGN.md](docs/REPOSITORY_DESIGN.md) を参照してください。

## API キーとマルチ LLM

- **既定割当**: 区画 JSON・建築／インフラの Function Calling は OpenAI（`gpt-5.5`）、コンセプト対話と装飾は Anthropic（`claude-sonnet-4-6`）、参照付き画像生成は Google Gemini（`gemini-3-pro-preview` / `gemini-3-pro-image-preview`）。実装は [app/ai/routing.py](app/ai/routing.py) で固定されています。
- **単一キー運用**: `OPENAI_API_KEY` や `ANTHROPIC_API_KEY` が無くても、`GEMINI_API_KEY` のみで全工程が Gemini にフォールバックします。
- **ブラウザ永続化**: Streamlit サイドバーから `GEMINI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` を入力し、「ブラウザに保存」で **localStorage** に JSON 保存できます（依存: `streamlit-js-eval`）。**XSS があるページではキーが窃取されうる**ため、信頼できる環境でのみ利用し、本番ではサーバ側シークレットやプロキシ方式を推奨します。
- **Function Calling のベンチマーク例**: [Berkeley Function Calling Leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html) をモデル選定の参考にし、リリース周期で `routing.py` の ID を見直してください。

## Docker Compose（localhost / サーバ共通）

リポジトリルートで次を実行します（初回はビルドに数分かかることがあります）。

```bash
cp .env.example .env   # 未作成の場合
# .env に GEMINI_API_KEY および RCON_* を設定

docker compose up --build -d
```

- **UI**: [http://localhost:8501](http://localhost:8501)
- **プロジェクトデータ**: ホストの `./projects` がコンテナの `/app/projects` にマウントされます。
- **権限（PermissionError）**: 以前に **root で動いていた Docker** が `projects/` 内を `root` 所有で作ると、ホストで **`make run` など一般ユーザー**から `concept_input.txt` 等へ書けず `Permission denied` になります。ホストで `make fix-projects-perms`（`sudo chown`）を一度実行するか、`.env` の `DOCKER_UID` / `DOCKER_GID` を `id -u` / `id -g` に合わせてから `docker compose build --no-cache` し直してください（[Dockerfile](Dockerfile) は非 root で起動します）。
- **ホスト上の Minecraft（RCON）**へ接続する場合は `.env` で `RCON_HOST=host.docker.internal` を推奨します（`docker-compose.yml` で Linux 向け `extra_hosts` を設定済みです）。

停止・削除:

```bash
docker compose down
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
Install your Minecraft Server separately (e.g., in `~/minecraft_server`).
Make sure `server.properties` has:
- `enable-rcon=true`
- `rcon.port=25575`
- `rcon.password` matching your .env

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
