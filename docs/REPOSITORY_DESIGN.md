# Bananacraft Core — リポジトリ設計書（開発者向け）

本書はコードベース上の責務分担・データの流れ・改修時の着手点をまとめたものです。背景やプロダクト思想は [Zenn: Bananacraft の記事](https://zenn.dev/nakaniship/articles/9f6eb4b7f8a44e) を参照してください（本書はその「実装マップ」役）。

---

## 目次

1. [目的とスコープ](#1-目的とスコープ)
2. [システム構成](#2-システム構成)
3. [Streamlit の Phase 設計](#3-streamlit-の-phase-設計)
4. [ディレクトリと主要モジュール](#4-ディレクトリと主要モジュール)
5. [プロジェクト成果物（`projects/`）](#5-プロジェクト成果物projects)
6. [v2 建築パイプライン](#6-v2-建築パイプライン)
7. [Mineflayer ボット](#7-mineflayer-ボット)
8. [環境変数](#8-環境変数)
9. [デプロイと運用](#9-デプロイと運用)
10. [拡張・改修ガイド](#10-拡張改修ガイド)
11. [レガシー・周辺コード](#11-レガシー周辺コード)
12. [用語メモ](#12-用語メモ)

---

## 1. 目的とスコープ

- 本リポジトリは **GCE 向けに整理された Bananacraft（デプロイ版）** です（[README.md](../README.md) の通り、レガシー削減済み）。
- **ユーザー向け操作手順**は README に集約。**本書は開発者が Phase・モジュール・JSON 成果物を追い、手直しするための設計参照**です。

---

## 2. システム構成

| 要素 | 技術・実装の所在 |
|------|------------------|
| フロント／オーケストレーション | Streamlit — [app/main.py](../app/main.py) のみ |
| LLM・画像生成 | **工程別ルーティング** — [app/ai/routing.py](../app/ai/routing.py)、[app/ai/key_store.py](../app/ai/key_store.py)、[app/ai/providers/stage_client.py](../app/ai/providers/stage_client.py)。既定は OpenAI（区画・建築 FC 等）・Anthropic（コンセプト・装飾）・Google（画像）。キー不足時は Gemini にフォールバック。UI からのキーは [app/ai/browser_keys.py](../app/ai/browser_keys.py) で localStorage と同期。 |
| 設計図 → ボクセル | [app/v2/carpenter.py](../app/v2/carpenter.py) + [app/v2/tools/](../app/v2/tools/) |
| 即時ワールド反映 | Minecraft RCON — [app/rcon_client.py](../app/rcon_client.py) |
| 逐次設置（演出） | Mineflayer — [AI_Carpenter_Bot/index.js](../AI_Carpenter_Bot/index.js) |
| プロジェクト保存 | [app/file_manager.py](../app/file_manager.py) → `projects/<プロジェクト名>/` |

```mermaid
flowchart TB
  subgraph streamlit [Streamlit app/main.py]
    Ph0[Phase0]
    Ph1[Phase1]
    Ph2[Phase2]
    Ph3[Phase3]
  end
  Ph0 --> Ph1 --> Ph2 --> Ph3
  Ph1 --> GC[GeminiClient chat image]
  Ph1 --> CP[CityPlanner infra tools]
  Ph2 --> Arch[Architect two-stage FC]
  Ph2 --> Carp[Carpenter TOOL_REGISTRY]
  Ph3 --> RCON[RconClient fill setblock]
  Ph3 --> Bot[Node Mineflayer]
  GC --> FS[(projects)]
  CP --> FS
  Arch --> FS
  Carp --> FS
  RCON --> MC[(Minecraft Server)]
  Bot --> MC
```

---

## 3. Streamlit の Phase 設計

状態は `st.session_state.phase`（整数）で管理されます。

| Phase | 画面の主旨 | 主に触るコード | 備考 |
|-------|------------|----------------|------|
| **0** | 新規プロジェクト作成、API キー確認 | [app/main.py](../app/main.py) 冒頭〜 `phase == 0` | `FileManager`、`GeminiClient`、`Architect` を初期化。既存 `concept_*` / `zoning_*` があれば復元して **1 へ** |
| **1** | コンセプトアート、ゾーニング、インフラ、テラフォーム | `phase == 1` | `GeminiClient` のチャット／画像、`CityPlanner`、`zoning_fixer` 経由の調整、任意で `Terraformer` |
| **2** | 区画（ゾーン）を 1 つ選び、外観画像 → 設計図（JSON）→ ブロック列 | `phase == 2` | `selected_zone`、`Architect.analyze_structure` / `generate_from_structure`、`CarpenterSession`、`BlueprintAnalyzer`（プレビュー）、3D は [app/v2/preview.py](../app/v2/preview.py) |
| **3** | 構造物の RCON 一括建築、クリア、装飾プラン生成、Mineflayer 実行 | `phase == 3` | `RconClient.build_voxels`、`Decorator`、`CarpenterSession.run_bot` |

**戻る操作**: Phase 3 から建物一覧へは `phase = 1`。Phase 3 で設計に戻るボタンは `phase = 2`。

---

## 4. ディレクトリと主要モジュール

| パス | 役割 |
|------|------|
| [app/main.py](../app/main.py) | UI・Phase 分岐・成果物の読み書きの集約点 |
| [app/api_client.py](../app/api_client.py) | コンセプト用チャット／画像／区画 JSON。内部で `ai.routing` の工程に応じたプロバイダを利用 |
| [app/ai/routing.py](../app/ai/routing.py) | `AIStage` ごとのプロバイダ（Google / OpenAI / Anthropic）とモデル ID の固定割当 |
| [app/ai/key_store.py](../app/ai/key_store.py) | ランタイム上の API キー辞書（Streamlit session / localStorage 由来が `.env` より優先） |
| [app/ai/browser_keys.py](../app/ai/browser_keys.py) | `streamlit-js-eval` 経由で localStorage 読み書き |
| [app/ai/providers/stage_client.py](../app/ai/providers/stage_client.py) | `complete_json` / `complete_text` / `complete_with_tools` / `generate_image_bytes` の実装 |
| [app/rcon_client.py](../app/rcon_client.py) | `SimpleRcon`（プロトコル）、`RconClient`（`fill` / `setblock` バッチ、`build_voxels`） |
| [app/file_manager.py](../app/file_manager.py) | `projects/<name>/` への JSON・テキスト・画像の保存読込 |
| [app/v2/architect.py](../app/v2/architect.py) | 建築用 Function Calling スキーマ `TOOL_DECLARATIONS`、2 段階解析、`BuildingInstruction` |
| [app/v2/carpenter.py](../app/v2/carpenter.py) | ツール実行エンジン、`CarpenterSession.run_bot`（Node 起動） |
| [app/v2/tools/](../app/v2/tools/) | 各ツール実装と [__init__.py の `TOOL_REGISTRY`](../app/v2/tools/__init__.py) |
| [app/v2/blueprint_analyzer.py](../app/v2/blueprint_analyzer.py) | 建築指示 JSON から壁・屋根・窓などの意味要素へ分解（装飾・解析用） |
| [app/v2/decorator.py](../app/v2/decorator.py) | 装飾プラン生成（Gemini + `decorate_element` 系） |
| [app/v2/city_planner.py](../app/v2/city_planner.py) | ゾーニング結果から道路・広場等 `INFRA_TOOLS` |
| [app/v2/zoning_fixer.py](../app/v2/zoning_fixer.py) | 区画 JSON の衝突検出・修正 |
| [app/v2/layout_engine.py](../app/v2/layout_engine.py) | レイアウト計算（ゾーン座標などと連携） |
| [app/v2/geometry/](../app/v2/geometry/) | ベジェ、階段、ボクセル化など幾何サブルーチン |
| [AI_Carpenter_Bot/](../AI_Carpenter_Bot/) | Mineflayer クライアント、`package.json` で依存管理 |
| [deployment/](../deployment/) | systemd ユニット例 |
| [setup.sh](../setup.sh) | 環境セットアップ |

---

## 5. プロジェクト成果物（`projects/`）

ルートは `FileManager(..., base_dir="projects")` により **`projects/<プロジェクト名>/`** です（Streamlit のカレントがリポジトリルートであることが前提。サービスファイルの `WorkingDirectory` と一致させる）。

### 5.1 グローバル（プロジェクト全体）

| ファイル | 読む側 | 書く側 | 内容の概要 |
|----------|--------|--------|--------------|
| `project_config.json` | main（サイドバー・Phase3） | main | `origin` 等ワールド基準座標 |
| `concept_input.txt` | （主に記録） | main | ユーザー入力 |
| `concept_reasoning.txt` | main、Decorator | main | コンセプト推敲の説明 |
| `concept_prompt_refined.txt` | main（復元） | main | 画像生成用プロンプト |
| `concept_art.jpg` | main、Phase2 参照 | main | コンセプト画像 |
| `concept_feedback_<timestamp>.txt` 等 | 記録 | main | フィードバックループ時 |
| `concept_art_<timestamp>.jpg` | 記録 | main | 同上 |
| `zoning_data.json` | main、CityPlanner、復元 | main / 修正フロー | 初期ゾーニング |
| `zoning_adjusted.json` | main（優先読込） | 衝突修正後 | 調整済みゾーニング |
| `infrastructure.json` | main | CityPlanner 実行後 | 道路・広場等のインフラ指示 |

### 5.2 ゾーン単位（`zone['id']` を `<id>` と表記）

| ファイル | 読む側 | 書く側 | 内容の概要 |
|----------|--------|--------|--------------|
| `design_<id>_decorated.jpg` | main、Decorator | main | 装飾込み外観 |
| `design_<id>_structure.jpg` | Architect Stage1 | main | 構造用外観 |
| `design_<id>_dec_<timestamp>.jpg` | main | main | 再生成時の装飾画像 |
| `building_<id>_instructions.json` | main、Analyzer、Decorator、Carpenter | Architect 経由で main | **ツール呼び出し列**（建築設計図） |
| `building_<id>_blocks_v2.json` | main、RCON、Decorator | Carpenter 経由で main | **相対座標のブロック列**（v2） |
| `building_<id>_decoration.json` | main（表示・ボット準備） | Decorator 経由で main | 装飾用のツール呼び出し列（JSON 配列として保存） |
| `bot_instructions_<id>.json` | Node ボット | main Phase3 | `{"instructions": [ {x,y,z,action,block}, ... ] }` 形式 |
| `full_build.json` | RCON／ボット例 | main（Merge ボタン） | 構造＋装飾をマージした `instructions` |
| `decoration.json` | main の一部 UI、手動コマンド例 | 別フローで配置した場合 | マージ UI は存在時のみ表示 |

**座標の考え方**: Phase3 の即時建築では `project_config.json` の `origin` と、選択ゾーンの `position.x` / `position.z` を足した **`build_origin`** を RCON に渡し、`building_*_blocks_v2.json` 内の相対座標と合成されます（`main.py` 内コメント参照）。

### 5.3 JSON のトップレベル形

[app/file_manager.py](../app/file_manager.py) の `save_json` は型注釈こそ `dict` だが、実装は `json.dump(data, ...)` のため **`list` をそのまま保存**できる。`infrastructure.json` および `building_<id>_decoration.json` は **指示オブジェクトの配列**として保存される。一方 `bot_instructions_<id>.json` や `full_build.json` は **`{"instructions": [...]}`** 形式で、Mineflayer 側の読み込み形式と一致させている。

---

## 6. v2 建築パイプライン

### 6.1 Architect（[app/v2/architect.py](../app/v2/architect.py)）

- **Stage 1**: 構造画像を入力に、建物を言語化した JSON（コンポーネント列）へ。`temperature=0.3` 前後で精度重視。
- **Stage 2**: Stage1 の JSON から **Function Calling** で `TOOL_DECLARATIONS` に沿った呼び出しへ。`temperature=0.5` 前後。
- 既定の LLM は [app/ai/routing.py](../app/ai/routing.py) の `ROUTES` で工程ごとに固定（例: OpenAI `gpt-5.5`、Anthropic `claude-sonnet-4-6`、フォールバック時の Gemini `gemini-3-pro-preview`）。変更する場合は同ファイルと [app/api_client.py](../app/api_client.py) 先頭の `TEXT_MODEL` / `IMAGE_MODEL`（`text_model` / `image_model` の再エクスポート）の整合を確認。
- **`VALID_BLOCKS`**: `draw_plane` 等の `enum` と一致させる。ブロック ID を増やすときはここと各ツール内の許容マテリアルも確認。

### 6.2 Carpenter と `TOOL_REGISTRY`

- [app/v2/carpenter.py](../app/v2/carpenter.py) が `TOOL_REGISTRY` からインスタンス化し、`execute(params, origin)` でブロック辞書列を生成。
- 同一座標は **後勝ち**（`block_map` で上書き）。
- `BlueprintAnalyzer` をコンストラクト時に注入すると、`set_analyzer` 対応ツールへ文脈が渡る。

### 6.3 CityPlanner（[app/v2/city_planner.py](../app/v2/city_planner.py)）

- `INFRA_TOOLS`（`draw_road`, `fill_zone`, `place_street_decor`）専用のスキーマ。建築ツール群とは別定義なので、**インフラ用の新ツールは `INFRA_TOOLS` と `TOOL_REGISTRY` の両方**が必要。

### 6.4 Decorator と BlueprintAnalyzer

- [app/v2/blueprint_analyzer.py](../app/v2/blueprint_analyzer.py): `draw_plane` / `place_window` / `place_door` 等から要素 ID・向き・範囲を構築。
- [app/v2/decorator.py](../app/v2/decorator.py): 完成イメージ画像＋コンセプト＋構造指示から装飾用の Function Calling を生成。API キーは `GEMINI_API_KEY`。

---

## 7. Mineflayer ボット

- 実装: [AI_Carpenter_Bot/index.js](../AI_Carpenter_Bot/index.js)
- **接続先**: 環境変数 `MC_HOST`（既定 `localhost`）、`MC_PORT`（既定 **28888**）— [AI_Carpenter_Bot/index.js](../AI_Carpenter_Bot/index.js)。`run_bot` は親の `os.environ` を subprocess に渡す。
- **引数**: `node index.js <PROJECT_NAME> [OriginX OriginY OriginZ] [FILENAME]`
- **入力ファイル**: `../projects/<PROJECT_NAME>/<FILENAME>`（既定 `decoration.json`）。中身は **`{ "instructions": [ ... ] }`** を想定。各要素は少なくとも `setblock` 用の `x,y,z,block`（および `action`）形式。
- Streamlit からは [app/v2/carpenter.py](../app/v2/carpenter.py) の `CarpenterSession.run_bot` が `cwd=AI_Carpenter_Bot` で `subprocess` 実行。

---

## 8. 環境変数

### 8.1 API キーの解決順（重要）

1. **Streamlit セッション**（サイドバー入力で更新される `api_key_context`）  
2. **ブラウザ localStorage**（初回ロード時に `streamlit-js-eval` で読み込み、任意で「ブラウザに保存」）  
3. **OS 環境変数**（`.env` / systemd の `EnvironmentFile`）

`localStorage` に保存したキーは **同一オリジン上で悪意のあるスクリプト（XSS）が実行されると読み取られる**可能性があります。本番ではサーバ側シークレット管理や、バックエンドプロキシ経由でのみ LLM を呼ぶ構成を推奨します。CSP（Content-Security-Policy）の強化や、信頼できない `components` の禁止も有効です。

### 8.2 変数一覧

| 変数 | 用途 |
|------|------|
| `GEMINI_API_KEY` | 画像生成（必須寄り）および OpenAI/Anthropic 未設定時の **全工程フォールバック** |
| `OPENAI_API_KEY` | 区画 JSON・躯体画像解析・建築 FC・インフラ FC（未設定時は Gemini に切替） |
| `ANTHROPIC_API_KEY` | コンセプト対話・装飾 FC（未設定時は Gemini） |
| `RCON_HOST` | 既定 `localhost` — [app/rcon_client.py](../app/rcon_client.py) |
| `RCON_PORT` | 既定 **28889**（Docker MC のホスト公開ポート） |
| `MC_HOST` / `MC_PORT` | Mineflayer ボット接続先（既定 `localhost` / **28888**） |
| `RCON_PASSWORD` | RCON ログイン |
| `STREAMLIT_PASSWORD` | 設定時のみログイン gate — [app/main.py](../app/main.py) `check_password` |

モデル ID の選定根拠（Function Calling 比較）の一例: [Berkeley Function Calling Leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html)。実装では `routing.py` の定数を製品方針として固定し、四半期などの周期で見直す運用を推奨します。

テンプレート: [.env.example](../.env.example)。systemd では `EnvironmentFile=` で `.env` を読み込む構成になっている（[deployment/bananacraft.service](../deployment/bananacraft.service)）。

---

## 9. デプロイと運用

- [setup.sh](../setup.sh): 仮想環境・依存関係・Streamlit 等の一括セットアップ。
- [docker-compose.yml](../docker-compose.yml): **`minecraft`**（Purpur **26.1.2**、フラット、Modrinth: EssentialsX / WorldEdit、ホスト **28888** / **28889**）と **`bananacraft`**。[Makefile](../Makefile): `make mc-up` / `make mc-attach` / `make mc-reset` / `make stack-up` / `make run`。
- [minecraft/README.md](../minecraft/README.md): ポート・プラグイン・移行手順。
- [deployment/bananacraft.service](../deployment/bananacraft.service): `streamlit run app/main.py --server.port 8501`。`User` / `WorkingDirectory` / `ExecStart` のパスは **実環境のユーザー名に合わせて編集**すること。
- [deployment/minecraft.service](../deployment/minecraft.service): 手動 `server.jar` 運用用（Docker を使う場合は不要）。
- RCON: `.env` の `RCON_PASSWORD` を Docker MC（itzg）または手動 `server.properties` と一致させる。

---

## 10. 拡張・改修ガイド

### 10.1 新建築ツール（構造物）を追加する場合

1. [app/v2/tools/](../app/v2/tools/) に新クラスを追加し、`execute(params, origin)` がブロック辞書を返すようにする。
2. [app/v2/tools/__init__.py](../app/v2/tools/__init__.py) の `TOOL_REGISTRY` に **Python 側のツール名**を登録。
3. [app/v2/architect.py](../app/v2/architect.py) の `TOOL_DECLARATIONS` に **同一ツール名**で JSON Schema を追加（Gemini がこの名前で呼び出す）。
4. ブロック型を `enum` で縛る場合は **`VALID_BLOCKS`** とスキーマの `enum` を同期。

**注意**: スキーマは Architect、実行は Carpenter と **二重定義**になる。片方だけ更新すると実行時エラーまたは無視されるので、変更チェックリストに両方を入れる。

### 10.2 インフラ専用ツールを追加する場合

- [app/v2/city_planner.py](../app/v2/city_planner.py) の `INFRA_TOOLS` に宣言を追加。
- 実行クラスを [app/v2/tools/](../app/v2/tools/) に実装し `TOOL_REGISTRY` に登録（既存の `DrawRoadTool` 等と同様）。

### 10.3 モデル・生成パラメータ

- 工程ごとのプロバイダ・モデル ID: [app/ai/routing.py](../app/ai/routing.py) の `ROUTES` / `effective_route`
- 実際の HTTP 呼び出し: [app/ai/providers/stage_client.py](../app/ai/providers/stage_client.py)
- 会話・コンセプト画像: [app/api_client.py](../app/api_client.py)
- 建築解析・FC: [app/v2/architect.py](../app/v2/architect.py)
- 都市インフラ: [app/v2/city_planner.py](../app/v2/city_planner.py)
- 装飾: [app/v2/decorator.py](../app/v2/decorator.py)

### 10.4 UI／Phase の変更

- Phase 番号・遷移・保存ファイル名はすべて [app/main.py](../app/main.py) に直書き。新 Phase や新成果物を足す場合は **grep で `fm.save` / `fm.load` を洗い出す**と漏れが防げる。

### 10.5 RCON の制約

- `fill` のボリューム上限対策として、クリア処理ではチャンク分割・`forceload` を使用（`main.py` Phase3）。大規模建築コマンドを追加する際は同様の制限に注意。

---

## 11. レガシー・周辺コード

現行の主導線は **v2 + Streamlit + RCON +（任意で）Mineflayer** です。次のモジュールは **過去実験・補助・未使用 import** が混在します。改修の優先度を下げるか、触る前に `main.py` から参照されているか grep してください。

| モジュール | メモ |
|------------|------|
| [app/meshy_client.py](../app/meshy_client.py) | `main.py` は import のみで本流 UI からは未使用の可能性大 |
| [app/voxelizer/](../app/voxelizer/)、[app/voxelizer.py](../app/voxelizer.py)、[app/advanced_voxelizer.py](../app/advanced_voxelizer.py) | メッシュ→ボクセル系。記事で言及の「3D メッシュ経由」ルートの名残 |
| [app/decorator.py](../app/decorator.py)（v2 以外） | v2 の [app/v2/decorator.py](../app/v2/decorator.py) と名前が衝突しやすい。UI は v2 を import |
| [app/gemini_refiner.py](../app/gemini_refiner.py)、[app/sample.py](../app/sample.py)、[app/compare_voxelizers.py](../app/compare_voxelizers.py) | ユーティリティ／検証用 |
| [app/facade.py](../app/facade.py) | 立面抽出など。主線からは独立 |

`Terraformer` は **Phase1 サイドバー**から呼ばれ、200x200 クリア等に使用（[app/terraformer.py](../app/terraformer.py)）。

---

## 12. 用語メモ

| 用語 | 本リポジトリでの意味 |
|------|---------------------|
| Phase | Streamlit の大ステップ（0〜3） |
| Zoning | `zoning_data.json` / `zoning_adjusted.json` の建物区画リスト |
| Blueprint | `building_<id>_instructions.json`（ツール呼び出しの列） |
| Carpenter | ツールを実行してブロック列へ落とすエンジン |
| v2 blocks | `building_<id>_blocks_v2.json`（RCON `build_voxels` 向け） |
| AI Carpenter Bot | Mineflayer で `setblock` を順次実行する Node プロセス |

---

## 改訂時のチェックリスト

- [ ] `main.py` の `phase` 分岐と成果物表に矛盾がないか
- [ ] 新ツール追加時、`architect.TOOL_DECLARATIONS` と `TOOL_REGISTRY` の双方を更新したか
- [ ] `VALID_BLOCKS`（および各ツールのマテリアル制約）を更新したか
- [ ] `.env.example` と README の記述を更新したか（新しい環境変数がある場合）
- [ ] systemd の `WorkingDirectory` が `projects/` 相対パスと整合するか
