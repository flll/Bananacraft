# syntax=docker/dockerfile:1
# Mineflayer ボット用に Node をビルドし、Python Streamlit と結合する
FROM node:22-bookworm-slim AS carpenter
WORKDIR /build
COPY AI_Carpenter_Bot/package.json AI_Carpenter_Bot/package-lock.json ./
RUN npm ci
COPY AI_Carpenter_Bot/ ./

FROM python:3.12-slim-bookworm
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY --from=carpenter /build ./AI_Carpenter_Bot

RUN mkdir -p projects

# ホストの ./projects マウントと所有者を揃える（ローカル streamlit と混在しにくい）
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g "${APP_GID}" bananacraft \
    && useradd --no-log-init -m -u "${APP_UID}" -g bananacraft bananacraft \
    && chown -R bananacraft:bananacraft /app
USER bananacraft

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app/main.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--browser.gatherUsageStats=false"]
