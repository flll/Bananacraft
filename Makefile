# Bananacraft — よく使うコマンド（リポジトリルートで実行）
#
# 推奨フロー（初回）
#   make reset   # 初回 or サーバー設定を作り直したいとき
#   make up      # Minecraft + Bananacraft UI を一括起動（数分かかる）
#
# 日常的にホスト Python を書き換えながら開発したい場合
#   make up      # まず Minecraft を含むスタックを起動（UI コンテナは止めて構わない）
#   make dev     # ホスト venv で Streamlit を起動（コード変更が即反映）

PYTHON  ?= python3
VENV    ?= venv
PIP      = $(VENV)/bin/pip
STREAMLIT = $(VENV)/bin/streamlit

# .env を反映して BlueMap 用の MODRINTH_PROJECTS を解決する。
# ENABLE_BLUEMAP=true なら bluemap も同梱、それ以外は worldedit のみ。
ifneq (,$(wildcard .env))
  include .env
  export
endif

ifeq ($(ENABLE_BLUEMAP),true)
  export MODRINTH_PROJECTS ?= worldedit,bluemap
else
  export MODRINTH_PROJECTS ?= worldedit
endif

SECRETS_ENV ?= $(HOME)/.cursor/secrets/secret.env
CURSOR_ENV  ?= $(HOME)/.cursor/.env
COMPOSE_LOCAL = docker compose --profile local
COMPOSE_TS    = docker compose -f docker-compose.yml -f docker-compose.tailscale.yml --env-file .env --env-file $(SECRETS_ENV) $(if $(wildcard $(CURSOR_ENV)),--env-file $(CURSOR_ENV),)
COMPOSE_DEPLOY = docker compose -f docker-compose.yml -f docker-compose.tailscale-ui.yml --env-file .env --env-file $(SECRETS_ENV) $(if $(wildcard $(CURSOR_ENV)),--env-file $(CURSOR_ENV),)

ifneq (,$(filter deploy,$(MAKECMDGOALS)))
  DEPLOY_TARGET := $(word 2,$(MAKECMDGOALS))
endif

.PHONY: help install npm-install env-example fix-projects-perms \
	up up-tailscale down logs logs-mc ps attach reset dev \
	tailscale-keys push-secret-check skills-sync \
	deploy _deploy-bananacraft _check-ts-authkey _deploy-help

help:
	@echo "Bananacraft — make ターゲット"
	@echo ""
	@echo "  常用（サーバー前提）"
	@echo "    make up       Minecraft + Bananacraft UI を起動（http://localhost:8501）"
	@echo "    make down     すべて停止・削除"
	@echo "    make logs     全サービスのログを追跡"
	@echo "    make logs-mc  Minecraft のログのみ追跡"
	@echo "    make ps       コンテナの状態"
	@echo "    make attach   Minecraft コンソールに接続（デタッチ: Ctrl+P → Ctrl+Q）"
	@echo "    make reset    minecraft-data を削除（確認あり・設定変更時に使用）"
	@echo ""
	@echo "  ホスト開発（Python を直接編集して即反映）"
	@echo "    make install     venv + requirements + Mineflayer の依存"
	@echo "    make dev         Minecraft が起動済みである前提で Streamlit を venv 実行"
	@echo ""
	@echo "  Tailnet デプロイ（要 TS_AUTHKEY: ~/.cursor/.env または secret.env）"
	@echo "    make deploy                 実装済みサービスをすべて tailnet へ（現状: bananacraft のみ）"
	@echo "    make deploy bananacraft     Streamlit UI のみ（サイドカー経由・ホスト公開なし）"
	@echo "    make deploy minecraft       （準備中）Minecraft サイドカー — 未実装"
	@echo "    make deploy help            deploy サブコマンドの説明"
	@echo ""
	@echo "  Tailscale（レガシー）"
	@echo "    make up-tailscale        非推奨 — MC+UI 一体。代わりに make deploy bananacraft"
	@echo "    make tailscale-keys      TS_AUTHKEY 発行（要 TS_API_ACCESS_TOKEN）"
	@echo "    make push-secret-check   リモート secret.env の有無を確認"
	@echo ""
	@echo "  Skills（別リポジトリ flll/skills）"
	@echo "    make skills-sync         clone/pull flll/skills → ~/.cursor/skills へ symlink"
	@echo ""
	@echo "  その他"
	@echo "    make env-example         .env が無ければ .env.example をコピー"
	@echo "    make fix-projects-perms  projects/ を現在ユーザーに chown"

env-example:
	@test -f .env || cp .env.example .env

fix-projects-perms:
	@test -d projects || mkdir -p projects
	sudo chown -R $$(id -u):$$(id -g) projects

install: env-example
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt

npm-install:
	cd AI_Carpenter_Bot && npm install

up: env-example
	$(COMPOSE_LOCAL) up --build -d

push-secret-check:
	@test -f $(SECRETS_ENV) || (echo "Missing $(SECRETS_ENV). From Windows: infra/push-secret-env.ps1 <ssh-host>" >&2; exit 1)
	@echo "OK: $(SECRETS_ENV)"

skills-sync:
	chmod +x infra/scripts/skills-sync.sh
	infra/scripts/skills-sync.sh

tailscale-keys: push-secret-check
	chmod +x infra/scripts/tailscale-create-service-key.sh
	SECRETS_ENV=$(SECRETS_ENV) infra/scripts/tailscale-create-service-key.sh

_check-ts-authkey:
	@tskey=""; \
	if [ -f "$(SECRETS_ENV)" ]; then \
	  tskey=$$(awk -F= '/^TS_AUTHKEY=/ { v=$$0; sub(/^TS_AUTHKEY=/,"",v); gsub(/^["'\'']|["'\'']$$/,"",v); print v }' "$(SECRETS_ENV)"); \
	fi; \
	if [ -z "$$tskey" ] || [ $${#tskey} -le 20 ]; then \
	  if [ -f "$(CURSOR_ENV)" ]; then \
	    tskey=$$(awk -F= '/^TS_AUTHKEY=/ { v=$$0; sub(/^TS_AUTHKEY=/,"",v); gsub(/^["'\'']|["'\'']$$/,"",v); print v }' "$(CURSOR_ENV)"); \
	  fi; \
	fi; \
	if [ -z "$$tskey" ] || [ $${#tskey} -le 20 ]; then \
	  echo "TS_AUTHKEY が空です。" >&2; \
	  echo "  1) infra/cursor.env.example を ~/.cursor/.env にコピーし tag:bananacraft 付きキーを設定" >&2; \
	  echo "  2) または make tailscale-keys（要 secret.env の TS_API_ACCESS_TOKEN）" >&2; \
	  echo "  ACL: infra/tailscale-acl-snippet.json を Tailscale Admin に追加済みか確認" >&2; \
	  exit 1; \
	fi

_deploy-help:
	@echo "Tailnet deploy — 利用可能なターゲット"
	@echo ""
	@echo "  make deploy                 すべて（現状 = bananacraft UI のみ）"
	@echo "  make deploy bananacraft     Streamlit UI + tailscale-bananacraft"
	@echo "  make deploy minecraft       未実装（後日対応）"
	@echo ""
	@echo "前提: ~/.cursor/.env または $(SECRETS_ENV) に TS_AUTHKEY"
	@echo "手順: infra/tailscale-deploy.md"

_deploy-bananacraft: env-example push-secret-check _check-ts-authkey
	$(COMPOSE_DEPLOY) up --build -d tailscale-bananacraft bananacraft

deploy:
	@case "$(DEPLOY_TARGET)" in \
	  help) $(MAKE) _deploy-help ;; \
	  ""|all|bananacraft) $(MAKE) _deploy-bananacraft ;; \
	  minecraft) echo "minecraft は未対応。後日 make deploy minecraft で MC サイドカーを追加予定です。" >&2; exit 1 ;; \
	  *) echo "不明: $(DEPLOY_TARGET)。make help または make deploy help を参照" >&2; exit 1 ;; \
	esac

%:
	@:

up-tailscale: env-example push-secret-check _check-ts-authkey
	@echo "注意: make up-tailscale は非推奨です。UI のみなら make deploy bananacraft を使ってください。" >&2
	$(COMPOSE_TS) up --build -d

down:
	-$(COMPOSE_DEPLOY) down --remove-orphans 2>/dev/null || true
	-$(COMPOSE_TS) down --remove-orphans 2>/dev/null || true
	-$(COMPOSE_LOCAL) down --remove-orphans 2>/dev/null || true

logs:
	$(COMPOSE_LOCAL) logs -f

logs-mc:
	$(COMPOSE_LOCAL) logs -f minecraft

ps:
	$(COMPOSE_LOCAL) ps

attach:
	@test -n "$$($(COMPOSE_LOCAL) ps -q minecraft 2>/dev/null)" || (echo "先に: make up" >&2; exit 1)
	docker attach bananacraft-minecraft

reset:
	@echo "WARNING: ./minecraft-data を削除します（ワールド・プラグイン・設定）"
	@read -p "続行? [y/N] " ans && test "$$ans" = y
	rm -rf minecraft-data

dev: env-example
	@test -x $(STREAMLIT) || (echo "先に: make install" >&2; exit 1)
	@test -n "$$($(COMPOSE_LOCAL) ps -q minecraft 2>/dev/null)" || (echo "先に: make up（Minecraft を起動してから）" >&2; exit 1)
	$(STREAMLIT) run app/main.py --server.port=8501
