# GCP Secret Manager — cursor-secret

Bananacraft / Cursor 用の機密（`secret.env` 形式）は GCP プロジェクト **lll-fish** の Secret Manager シークレット **cursor-secret** に格納します。

> リポジトリに `secret.env` や SA JSON をコミットしないでください。

## 前提

- `gcloud` インストール済み、`gcloud auth login` 済み
    gcloud config set project lll-fish
    gcloud services enable secretmanager.googleapis.com --project=lll-fish

## 初回のみ: シークレット作成

```
gcloud secrets create cursor-secret \
  --replication-policy=automatic \
  --project=lll-fish
```

（本環境では既に作成済みの場合があります。）  
`~/.cursor/secrets/secret.env`

## 日常運用 — 実行する gcloud コマンド

### 最新版をローカルへ取り込む（値はターミナルに出さない）

```
mkdir -p ~/.cursor/secrets
gcloud secrets versions access latest \
  --secret=cursor-secret \
  --project=lll-fish \
  > ~/.cursor/secrets/secret.env
chmod 600 ~/.cursor/secrets/secret.env
```

リポジトリヘルパー:

```
cp infra/gcp/gcp-bootstrap.env.example ~/.config/cursor/gcp-bootstrap.env
./infra/scripts/load-secrets-gcp.sh
```

### 新しいバージョンをアップロード

```
gcloud secrets versions add cursor-secret \
  --data-file=$HOME/.cursor/secrets/secret.env \
  --project=lll-fish
```

### バージョン一覧（メタデータ）

```
gcloud secrets versions list cursor-secret --project=lll-fish
```

### シークレットの説明

```
gcloud secrets describe cursor-secret --project=lll-fish
```

## サービスアカウントへの IAM

デプロイ用 SA に最新版の読み取り:

```
SA_EMAIL="your-sa@lll-fish.iam.gserviceaccount.com"
gcloud secrets add-iam-policy-binding cursor-secret \
  --project=lll-fish \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"
```

CI からバージョンを追加する場合は `roles/secretmanager.secretVersionManager` など必要最小限を付与してください。

## 関連ファイル


| ファイル                                                             | 役割                                       |
| ---------------------------------------------------------------- | ---------------------------------------- |
| [../config.yaml](../config.yaml)                                 | `gcp.project_id` / `gcp.secret_name`     |
| [gcp-bootstrap.env.example](gcp-bootstrap.env.example)           | `~/.config/cursor/gcp-bootstrap.env` の雛形 |
| [../scripts/load-secrets-gcp.sh](../scripts/load-secrets-gcp.sh) | GSM → `~/.cursor/secrets/secret.env`     |


`make up-tailscale` は **~/.cursor/secrets/secret.env** を参照します。起動前に上記の取得または `load-secrets-gcp.sh` を実行してください。