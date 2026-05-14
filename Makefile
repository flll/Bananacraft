# Bananacraft — よく使うコマンド（リポジトリルートで実行）
# https://www.gnu.org/software/make/manual/html_node/Phony-Targets.html

PYTHON  ?= python3
VENV    ?= venv
PIP      = $(VENV)/bin/pip
STREAMLIT = $(VENV)/bin/streamlit

.PHONY: help install npm-install run docker-build docker-up docker-down docker-logs docker-ps env-example

help:
	@echo "Bananacraft — make ターゲット"
	@echo ""
	@echo "  ローカル開発（コード変更がそのまま反映されやすい）"
	@echo "    make install      venv を作成（無い場合）し requirements を入れる"
	@echo "    make npm-install  AI_Carpenter_Bot の npm install"
	@echo "    make run          Streamlit を venv で起動（http://127.0.0.1:8501）"
	@echo ""
	@echo "  Docker（イメージに app が焼かれる。コード変更後は build が必要）"
	@echo "    make docker-build  docker compose build"
	@echo "    make docker-up     docker compose up --build -d"
	@echo "    make docker-down   docker compose down"
	@echo "    make docker-logs   docker compose logs -f"
	@echo "    make docker-ps     docker compose ps"
	@echo ""
	@echo "  その他"
	@echo "    make env-example   .env が無ければ .env.example をコピー（既にある場合は何もしない）"

env-example:
	@test -f .env || cp .env.example .env

install: env-example
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt

npm-install:
	cd AI_Carpenter_Bot && npm install

run: env-example
	@test -x $(STREAMLIT) || (echo "先に: make install" >&2; exit 1)
	$(STREAMLIT) run app/main.py --server.port=8501

docker-build:
	docker compose build

docker-up: env-example
	docker compose up --build -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

docker-ps:
	docker compose ps
