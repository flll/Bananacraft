# Bananacraft Core (Deployment)

This is the deployment version of Bananacraft, stripped of legacy code and optimized for GCE.

開発者向けのリポジトリ設計・データフロー・改修ガイドは [docs/REPOSITORY_DESIGN.md](docs/REPOSITORY_DESIGN.md) を参照してください。

Gemini 呼び出しは工程別に専用 API キー（およびコード固定の強モデル ID）へルーティングされます。未設定のキーは `GEMINI_API_KEY` にフォールバックします。詳細は [.env.example](.env.example) と設計書の「環境変数」節を参照してください。

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
*Set your `GEMINI_API_KEY` and `RCON_PASSWORD`.*

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
