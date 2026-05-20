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

.PHONY: help install npm-install env-example fix-projects-perms \
	up down logs logs-mc ps attach reset dev

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
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

logs-mc:
	docker compose logs -f minecraft

ps:
	docker compose ps

attach:
	@test -n "$$(docker compose ps -q minecraft 2>/dev/null)" || (echo "先に: make up" >&2; exit 1)
	docker attach bananacraft-minecraft

reset:
	@echo "WARNING: ./minecraft-data を削除します（ワールド・プラグイン・設定）"
	@read -p "続行? [y/N] " ans && test "$$ans" = y
	rm -rf minecraft-data

dev: env-example
	@test -x $(STREAMLIT) || (echo "先に: make install" >&2; exit 1)
	@test -n "$$(docker compose ps -q minecraft 2>/dev/null)" || (echo "先に: make up（Minecraft を起動してから）" >&2; exit 1)
	$(STREAMLIT) run app/main.py --server.port=8501
