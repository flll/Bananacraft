# Bananacraft — よく使うコマンド（リポジトリルートで実行）

PYTHON  ?= python3
VENV    ?= venv
PIP      = $(VENV)/bin/pip
STREAMLIT = $(VENV)/bin/streamlit

.PHONY: help install npm-install run \
	docker-build docker-up docker-down docker-logs docker-ps \
	mc-up mc-down mc-logs mc-ps mc-attach mc-reset stack-up stack-down \
	env-example fix-projects-perms

help:
	@echo "Bananacraft — make ターゲット"
	@echo ""
	@echo "  ローカル開発（コード変更がそのまま反映されやすい）"
	@echo "    make install      venv を作成（無い場合）し requirements を入れる"
	@echo "    make npm-install  AI_Carpenter_Bot の npm install"
	@echo "    make run          Streamlit を venv で起動（http://127.0.0.1:8501）"
	@echo ""
	@echo "  Minecraft（Docker / Purpur 26.1.2 / ゲーム :28888 / RCON :28889）"
	@echo "    make mc-up        Minecraft のみ起動"
	@echo "    make mc-down      Minecraft を停止"
	@echo "    make mc-logs      Minecraft のログを追跡"
	@echo "    make mc-ps        Minecraft コンテナの状態"
	@echo "    make mc-attach    サーバーコンソールへ接続（デタッチ: Ctrl+P → Ctrl+Q）"
	@echo "    make mc-reset     minecraft-data を削除（Purpur 初回・設定変更時）"
	@echo "    推奨: make mc-reset → make mc-up → make run"
	@echo ""
	@echo "  Docker Bananacraft（コード変更後は build が必要）"
	@echo "    make docker-build  docker compose build bananacraft"
	@echo "    make docker-up     Bananacraft 起動（Minecraft も depends_on で起動）"
	@echo "    make stack-up      Minecraft + Bananacraft を一括起動"
	@echo "    make stack-down    全 Compose サービスを停止・削除"
	@echo "    make docker-down   stack-down と同じ"
	@echo "    make docker-logs   docker compose logs -f"
	@echo "    make docker-ps     docker compose ps"
	@echo ""
	@echo "  その他"
	@echo "    make env-example        .env が無ければ .env.example をコピー"
	@echo "    make fix-projects-perms projects/ を現在ユーザーに chown"

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

run: env-example
	@test -x $(STREAMLIT) || (echo "先に: make install" >&2; exit 1)
	$(STREAMLIT) run app/main.py --server.port=8501

mc-up: env-example
	docker compose up -d minecraft

mc-down:
	docker compose stop minecraft

mc-logs:
	docker compose logs -f minecraft

mc-ps:
	docker compose ps minecraft

mc-attach:
	@test -n "$$(docker compose ps -q minecraft 2>/dev/null)" || (echo "先に: make mc-up" >&2; exit 1)
	docker attach bananacraft-minecraft

mc-reset:
	@echo "WARNING: ./minecraft-data を削除します（ワールド・プラグイン・設定）"
	@read -p "続行? [y/N] " ans && test "$$ans" = y
	rm -rf minecraft-data

stack-up: env-example
	docker compose up --build -d

stack-down:
	docker compose down

docker-build:
	docker compose build bananacraft

docker-up: env-example
	docker compose up --build -d bananacraft

docker-down: stack-down

docker-logs:
	docker compose logs -f

docker-ps:
	docker compose ps
