# Bananacraft — Tailnet デプロイ（UI）

Streamlit UI を Tailscale サイドカー経由で tailnet のみ公開する手順。ホストの `8501` はバインドしません。

## 前提（Phase 0）

### ACL

[`tailscale-acl-snippet.json`](tailscale-acl-snippet.json) を [Tailscale Access controls](https://login.tailscale.com/admin/acls) に反映すること。

**必須:**

1. **tagOwners** — `tag:bananacraft` の所有者（例: `group:admin`）
2. **grants** — `tag:bananacraft` ノードへの到達許可

`group:admin` → `*` だけでは **不足** なことがある。`lll-legacy` は `tag:server` 付きのため、次の grant が必要:

```json
"grants": [
  { "src": ["group:admin"], "dst": ["tag:bananacraft"], "ip": ["*"] },
  { "src": ["tag:server", "lll-legacy"], "dst": ["tag:bananacraft"], "ip": ["*"] }
]
```

API で一括適用（要 `TS_API_ACCESS_TOKEN` または OAuth）:

```bash
# 現行 ACL を取得 → grants を追記 → POST
curl -sf -H "Authorization: Bearer $TOKEN" \
  "https://api.tailscale.com/api/v2/tailnet/${TAILNET}/acl" -o /tmp/acl.hujson
# 編集後
curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  --data-binary @/tmp/acl.hujson \
  "https://api.tailscale.com/api/v2/tailnet/${TAILNET}/acl"
```

未設定の場合、ノードは tailnet に参加できない、または **ピア一覧に表示されず curl がタイムアウト** します。

### TS_AUTHKEY

`tag:bananacraft` 付きの reusable キーを用意する。

| 配置先 | 用途 |
|--------|------|
| `~/.cursor/.env` | **推奨** — マシン固有（[`cursor.env.example`](cursor.env.example) をコピー） |
| `~/.cursor/secrets/secret.env` | 既存の秘密ファイル（`TS_AUTHKEY=` が空の場合は `.env` 側を使う） |

キー発行:

- [Auth keys](https://login.tailscale.com/admin/settings/keys) で手動作成
- または `make tailscale-keys`（要 `secret.env` の `TS_API_ACCESS_TOKEN`）

## デプロイ

```bash
cd /path/to/Bananacraft
make down
make deploy              # 実装済みサービスすべて（現状 = UI のみ）
# または
make deploy bananacraft  # UI のみ（明示）
```

`make deploy minecraft` は **未実装**（後日 `docker-compose.tailscale.yml` で MC サイドカーを追加予定）。

## 検証

```bash
docker ps --filter name=bananacraft
docker logs bananacraft-tailscale-ui --tail 40
curl -sI http://bananacraft:8501    # tailnet 上のマシンから
ss -tlnp | grep 8501                # ホストでは空であること
make help                           # deploy 行が表示されること
```

| 項目 | 期待値 |
|------|--------|
| UI URL（tailnet） | `http://bananacraft:8501` |
| ホスト `8501` | リッスンしない |
| コンテナ | `bananacraft-tailscale-ui`, `bananacraft` |

## ローカル開発との切り替え

| 用途 | コマンド |
|------|----------|
| localhost（MC + UI、ホストポートあり） | `make up` / `make down` |
| tailnet（UI のみ、ホストポートなし） | `make deploy bananacraft` / `make down` |
| レガシー（MC+UI 一体 tailnet） | `make up-tailscale`（非推奨） |

Compose ファイル:

- [`docker-compose.tailscale-ui.yml`](../docker-compose.tailscale-ui.yml) — UI サイドカーのみ（`make deploy`）
- [`docker-compose.tailscale.yml`](../docker-compose.tailscale.yml) — 将来のフル tailnet / `make deploy minecraft` 用

メタデータ: [`services.yaml`](services.yaml)
