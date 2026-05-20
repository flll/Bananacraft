# Bananacraft Core (Deployment)

This is the deployment version of Bananacraft, stripped of legacy code and optimized for GCE.

開発者向けのリポジトリ設計・データフロー・改修ガイドは [docs/REPOSITORY_DESIGN.md](docs/REPOSITORY_DESIGN.md) を参照してください。

## アプリの流れ（UI v2）

`st.navigation` ベースのマルチページ構成で、画面上部の **横ステッパー** が常に現在地を示します。

| Step | ページ | 何をする |
|------|-------|---------|
| 1. Setup    | [`app/pages_v2/setup.py`](app/pages_v2/setup.py)       | プロジェクト作成 / 既存を開く |
| 2. Concept  | [`app/pages_v2/concept.py`](app/pages_v2/concept.py)   | コンセプト文 → AI が街のコンセプトアートを生成 / 反復改善 |
| 3. City Plan| [`app/pages_v2/city_plan.py`](app/pages_v2/city_plan.py) | ゾーニング・インフラ（道路 / 広場）生成と Building List |
| 4. Building | [`app/pages_v2/building.py`](app/pages_v2/building.py) | 個別建物の **Design → Blueprint → Build → Decorate**（縦サブステッパー）|
| Settings    | [`app/pages_v2/settings.py`](app/pages_v2/settings.py) | API キー / Origin XYZ / Terraformer / プロジェクトリセット |

共通 UI コンポーネントは [`app/ui/`](app/ui/) に集約されています（stepper, breadcrumbs, buttons, status_card, feature_card, theme, onboarding, state）。

## API キーとマルチ LLM

- **既定割当**: 区画 JSON・建築／インフラの Function Calling は OpenAI（`gpt-5.5`）、コンセプト対話と装飾は Anthropic（`claude-sonnet-4-6`）、参照付き画像生成は Google Gemini（`gemini-3-pro-preview` / `gemini-3-pro-image-preview`）、画像→3D メッシュは Tripo3D。実装は [app/ai/routing.py](app/ai/routing.py) で固定されています。
- **単一キー運用**: `OPENAI_API_KEY` や `ANTHROPIC_API_KEY` が無くても、`GEMINI_API_KEY` のみで全工程が Gemini にフォールバックします。Mesh-First Architect だけは別途 `TRIPO_API_KEY`（`tsk_` で始まる）が必要です。
- **設定場所**: 左サイドバーの **Settings ページ** からまとめて入力できます。「ブラウザに保存」で **localStorage** に JSON 保存（依存: `streamlit-js-eval`）。**XSS があるページではキーが窃取されうる**ため、信頼できる環境でのみ利用し、本番ではサーバ側シークレットやプロキシ方式を推奨します。
- **Function Calling のベンチマーク例**: [Berkeley Function Calling Leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html) をモデル選定の参考にし、リリース周期で `routing.py` の ID を見直してください。

## 起動方法（Makefile）

```bash
cp .env.example .env   # 未作成の場合
# .env に GEMINI_API_KEY および RCON_PASSWORD を設定

make help            # ターゲット一覧
```

Bananacraft は **Minecraft サーバーが起動している前提**のリポジトリです。基本は `make up` ひとつで Minecraft（Purpur + WorldEdit）と Bananacraft UI がまとめて立ち上がります。

| 用途 | コマンド |
|------|----------|
| **常用（おすすめ）** | `make reset`（初回のみ）→ **`make up`** |
| **停止 / 再起動** | `make down` / 再起動は再度 `make up` |
| **ログ確認** | `make logs`（全部）/ `make logs-mc`（Minecraft のみ）/ `make attach`（コンソール） |
| **ホスト Python 開発** | `make up` のあとに `make install` → **`make dev`**（`.env` の `RCON_HOST=localhost` に書き換えて使用） |

| サービス | URL / ポート |
|----------|-------------|
| Bananacraft UI | [http://localhost:8501](http://localhost:8501) |
| Minecraft ゲーム | `localhost:28888` |
| RCON | `localhost:28889`（`.env` の `RCON_PASSWORD`） |
| BlueMap Web マップ（`ENABLE_BLUEMAP=true` 時のみ） | [http://localhost:8100](http://localhost:8100) |

- **ワールドデータ**: `./minecraft-data/`（Git 管理外）。詳細は [minecraft/README.md](minecraft/README.md)
- **プロジェクトデータ**: `./projects`（`make up` ではコンテナ、`make dev` ではホストから直接読み書き）
- **BlueMap**: `.env` の `ENABLE_BLUEMAP=true` にすると Modrinth から自動取得して Web マップが有効になります。Bananacraft の RCON 設置や `.schem` 配置には不要なので既定オフ。
- **権限（PermissionError）**: `make fix-projects-perms`、または `.env` の `DOCKER_UID` / `DOCKER_GID` を `id -u` / `id -g` に合わせて `make up` を再実行（再 build）

## Docker Compose

[docker-compose.yml](docker-compose.yml) に **minecraft**（Purpur 26.1.2 + WorldEdit、任意で BlueMap、[itzg/minecraft-server](https://hub.docker.com/r/itzg/minecraft-server)）と **bananacraft** の 2 サービスがあります。`make up` は内部で次と同等です。

```bash
docker compose up --build -d
```

UI コンテナは `depends_on` で Minecraft の healthcheck を待ってから起動します。コンテナ間は compose 内の DNS で `minecraft` を名前解決するため、`.env` の `RCON_HOST=minecraft` が既定です（`make dev` でホスト直起動するときだけ `localhost` に書き換えてください）。

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

**Docker（推奨）**: `make reset`（初回）→ `make up`。Purpur 26.1.2・フラット・WorldEdit 付き。ポート **28888** / **28889**、任意で BlueMap **8100**。

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
Access the app at `http://<YOUR_GCE_IP>:8501`. 4 ステップを順に進めてください：

1. **Setup** — プロジェクト名を入力（または既存プロジェクトを開く）
2. **Concept** — 一文の説明から AI がコンセプトアートを生成
3. **City Plan** — ゾーニング & インフラを生成、Building List から建物を選択
4. **Building** — Design → Blueprint（Tripo3D + voxel）→ Build（RCON / WorldEdit）→ Decorate（AI Carpenter Bot）の縦サブステッパー

> Tripo が `.schem`（WorldEdit スキマティック）を返した場合は、`projects/<name>/building_<id>.schem` として保存し、Build セクションの「📦 WorldEdit で配置 (.schem)」から `//paste` で一括設置できます。設計方針は [`docs/REPOSITORY_DESIGN.md`](docs/REPOSITORY_DESIGN.md) §13、サーバー側手順は [`minecraft/README.md`](minecraft/README.md) を参照。

### 🧊 Tripo3D 設定（Settings ページ）

Building → Blueprint で使う Tripo3D の挙動は、**Settings ページ > 「🧊 Tripo3D 設定」**
からチューニングできます。設定は `~/.config/bananacraft/tripo_config.json` に永続化されます。

**建物ごとの規模は触らなくて OK** — City Plan のゾーン `width × depth` から、Concept 画像プロンプトと Tripo Blueprint の両方が同じ値で連動して動きます。Settings で触るのはスタイルやテクスチャ全体の挙動だけです。

主要な項目（通常モード）：

| 設定 | 推奨値 | 効能 |
|---|---|---|
| `style` | `minecraft` | image_to_model 完了後に `stylize_model` で適用される後処理スタイル。Tripo 側で Minecraft ブロック風メッシュに変換 |
| `geometry_quality` | `standard` | `detailed` にすると細部が増える代わりに時間／クレジット増 |
| `face_limit` | 30000 | 多いほどメッシュ細部が出るが、ボクセル化負荷も増す |
| `texture_alignment` | `original_image` | concept art の色を優先（Minecraft ブロックと色合わせしやすい） |
| `use_texture_model` | OFF | ONで `texture_model` ([v3.0-20250812](https://docs.tripo3d.ai/texture/texture-model-v3-0-20250812.html)) を後段実行し、テクスチャだけ高品質に再生成 |

#### 自動サイズ連動（デフォルト ON）

- Blueprint 作成時に `target_blocks = max(zone.width, zone.depth)` を計算し、`TripoConfig.with_building_override(target_blocks)` で
  - GLB 経路: `voxel_lower_bound = voxel_upper_bound = target_blocks`
  - schem 経路: `style_block_size = stylize_block_for_target(target_blocks)`（target_blocks=32 で従来の 80、大きいほど小さく）
  をその場で上書きします。Concept 画像のプロンプトに書かれた「幅 W × 奥行 D × 高さ約 H ブロック / 合計 N ブロック四方」と Blueprint が**完全に同じ N で動く**ことを保証する仕組みです。
- Building ページの PipelineStatus に `自動サイズ設定: ゾーン最長辺 N blocks → voxel=[N, N], block_size=...` という行が出るので、効いているか目視で確認できます。

#### 上級者モード（手動上書き）

上級者モード（`⚙️` トグル）を ON にすると、以下が出現します:

| 項目 | 役割 |
|---|---|
| `🧊 Voxel 解像度` expander | `voxel_lower_bound` / `voxel_upper_bound` の手動スライダー |
| 同 expander 内のチェック `auto_size_from_zone` | **OFF にするとゾーン連動が無効化**され、ここの lo/hi/block_size がそのまま使われる（旧挙動） |
| `style_block_size` スライダー（Model expander 内） | stylize_model の粒度を直接指定 |
| `🎲 Seed と補助` expander | `model_seed` / `texture_seed` / `enable_image_autofix` |

旧挙動が必要なケース（同じ解像度で大小違うゾーンを揃えたい等）以外は、**通常モードのまま** Tripo3D 設定を放置してかまいません。

#### 🖌️ Texture Model（後段テクスチャ精製）

`use_texture_model = ON` にすると、`image_to_model` で出来たベースメッシュに対して [`texture_model`](https://docs.tripo3d.ai/texture/texture-model-v3-0-20250812.html) を追加実行し、**テクスチャだけ高品質に焼き直し**ます。

- **ベネフィット**: コンセプトアートの色合いがより忠実にメッシュに焼かれ、Minecraft ブロック割当の精度が上がる
- **コスト**: Tripo クレジット追加消費 (`texture_quality=detailed` なら +10 cr) + 60〜120 秒の追加生成時間
- **推奨タイミング**: ハニカム模様や原木の節など、色のニュアンスが重要な建物を作る時
- **デフォルト OFF**: 通常は `image_to_model` 単発で十分な品質が出る

### 🧱 Minecraft 公式テクスチャの自動取得

Voxel プレビューは Minecraft 公式のブロックテクスチャを使って表示できます。

- **挙動**: 初回起動時にバックグラウンドで Mojang 公式の [`version_manifest_v2.json`](https://piston-meta.mojang.com/mc/game/version_manifest_v2.json) から最新 release を解決し、`client.jar` を `~/.cache/bananacraft/mc/<version>/client.jar` にダウンロードします。SHA1 検証付きなので破損／改ざんを検知します。
- **テクスチャ展開**: `assets/minecraft/textures/block/*.png` を抽出し、`vanilla.atlas` の `atlasColumn/atlasRow` 座標に従って 1 枚の 320×320 PNG (`~/.cache/bananacraft/voxel_atlas_official_<version>.png`) に焼き直します。
- **フォールバック**: ダウンロード失敗・ネットワーク不通時は手作りピクセルアトラス (`voxel_atlas_procedural.png`) に自動で切り替わるので、起動を妨げません。
- **コントロール**: `Settings → 🧱 Minecraft アセット` セクションでステータス確認・再ダウンロード・jar キャッシュ削除ができます。「**手作りアトラスを強制使用**」トグルを ON にすると公式 jar の取得を抑止できます (`~/.config/bananacraft/mc_assets_prefs.json` に永続化)。

#### ライセンス・運用上の注意

- ダウンロードした `client.jar` は **Bananacraft の配布物には含まれません**。各ユーザーのキャッシュディレクトリにのみ保存されます。
- Minecraft EULA に従って **個人利用範囲**でのみ動作する想定です。商用配布や再配布、リソースパック化などの二次配布はしないでください。
- `.gitignore` に `.cache/` を追加しているので、リポジトリにキャッシュが入り込むことはありません。
