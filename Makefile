# ─────────────────────────────────────────────────────────────────────────────
# rag-chat — project Makefile
#
# 运行约定:
#   - Python 命令统一走 `uv run`
#   - 前端命令统一走 `pnpm --dir web-app`
#   - docker 命令走 `docker compose`（v2 语法）
#
# 发现目标: `make` 或 `make help`
# ─────────────────────────────────────────────────────────────────────────────

SHELL := /usr/bin/env bash
.ONESHELL:
.DEFAULT_GOAL := help

# 可覆盖变量（使用: make logs SERVICE=api）
PROFILE ?= web
SERVICE ?=
COMPOSE ?= docker compose
PY      ?= uv run
PNPM    ?= pnpm --dir web-app

OLLAMA_CHAT_MODEL  ?= qwen2.5:1.5b
OLLAMA_EMBED_MODEL ?= nomic-embed-text

# ─── Help ────────────────────────────────────────────────────────────────────
.PHONY: help
help: ## 显示所有可用目标
	@awk 'BEGIN {FS = ":.*?## "} \
		/^# ── / { sub(/^# ── /, "\n\033[1;36m"); sub(/ ─+$$/, "\033[0m"); print; next } \
		/^[a-zA-Z0-9_.-]+:.*?## / { printf "  \033[1;32m%-20s\033[0m %s\n", $$1, $$2 }' \
		$(MAKEFILE_LIST)
	@echo ""

# ─── Setup ───────────────────────────────────────────────────────────────────
.PHONY: install install.py install.web install.hooks env
install: install.py install.web install.hooks ## 一次性安装 Python + Web + git hooks

install.py: ## uv sync 安装 Python 依赖
	uv sync

install.web: ## pnpm install 安装前端依赖
	$(PNPM) install

install.hooks: ## 安装 pre-commit 钩子（如已配置）
	@if [ -f .pre-commit-config.yaml ]; then \
		$(PY) pre-commit install; \
	else \
		echo "skip: .pre-commit-config.yaml not found"; \
	fi

env: ## 复制 .env.example → .env（不覆盖已存在）
	@if [ ! -f .env ] && [ -f .env.example ]; then \
		cp .env.example .env && echo "created .env"; \
	else \
		echo ".env already exists or .env.example missing, skip"; \
	fi

# ─── Dev (本地直跑，不走 docker) ──────────────────────────────────────────────
.PHONY: dev dev.api dev.worker dev.cli dev.web
dev: ## 同时起 api + worker + web（需要 tmux，否则请分别开三个终端）
	@if command -v tmux >/dev/null 2>&1; then \
		tmux new-session -d -s ragchat 'make dev.api'; \
		tmux split-window -h -t ragchat 'make dev.worker'; \
		tmux split-window -v -t ragchat 'make dev.web'; \
		tmux attach -t ragchat; \
	else \
		echo "tmux not found. 请分别运行: make dev.api | make dev.worker | make dev.web"; \
		exit 1; \
	fi

dev.api: ## 启动 FastAPI dev server (auto-reload)
	$(PY) uvicorn app.server:app --reload --host 0.0.0.0 --port 8000

dev.worker: ## 启动 ARQ worker
	$(PY) arq workers.worker.WorkerSettings --watch .

dev.cli: ## 启动交互式 CLI
	$(PY) python main.py chat

dev.web: ## 启动前端 vite dev server
	$(PNPM) dev

# ─── Docker ──────────────────────────────────────────────────────────────────
.PHONY: up up.cli up.train down logs ps rebuild
up: ## docker compose up -d（默认 PROFILE=web）
	$(COMPOSE) --profile $(PROFILE) up -d

up.cli: ## 一次性交互式 CLI 容器
	$(COMPOSE) --profile cli run --rm cli

up.train: ## 一次性训练容器
	$(COMPOSE) --profile train run --rm trainer

down: ## 停止所有容器
	$(COMPOSE) down

logs: ## docker compose logs -f [SERVICE=xxx]
	@if [ -z "$(SERVICE)" ]; then \
		$(COMPOSE) logs -f; \
	else \
		$(COMPOSE) logs -f $(SERVICE); \
	fi

ps: ## 查看容器状态
	$(COMPOSE) ps

rebuild: ## 不用缓存重建所有镜像
	$(COMPOSE) build --no-cache

# ─── Database ────────────────────────────────────────────────────────────────
.PHONY: db.up db.migrate db.rev db.downgrade db.reset db.shell redis.shell
db.up: ## 仅起 postgres + redis（用于本地直跑时依赖）
	$(COMPOSE) up -d postgres redis

db.migrate: ## alembic upgrade head
	$(PY) alembic upgrade head

db.rev: ## 生成 alembic 迁移文件（用法: make db.rev m="add users")
	@if [ -z "$(m)" ]; then echo "用法: make db.rev m=\"message\""; exit 1; fi
	$(PY) alembic revision --autogenerate -m "$(m)"

db.downgrade: ## alembic downgrade -1
	$(PY) alembic downgrade -1

db.reset: ## [DEV 专用] 删库重建 + 迁移（二次确认）
	@read -p "确认要删掉本地开发库吗？输入 yes 继续: " ans; \
	if [ "$$ans" = "yes" ]; then \
		$(COMPOSE) exec postgres psql -U rag -d postgres -c "DROP DATABASE IF EXISTS ragdb;"; \
		$(COMPOSE) exec postgres psql -U rag -d postgres -c "CREATE DATABASE ragdb;"; \
		$(MAKE) db.migrate; \
	else \
		echo "aborted"; \
	fi

db.shell: ## 进 postgres psql
	$(COMPOSE) exec postgres psql -U rag -d ragdb

redis.shell: ## 进 redis-cli
	$(COMPOSE) exec redis redis-cli

# ─── Ollama ──────────────────────────────────────────────────────────────────
.PHONY: ollama.pull ollama.ps
ollama.pull: ## 拉取默认 chat + embed 模型
	$(COMPOSE) exec ollama ollama pull $(OLLAMA_CHAT_MODEL)
	$(COMPOSE) exec ollama ollama pull $(OLLAMA_EMBED_MODEL)

ollama.ps: ## 列出 ollama 已拉取模型
	$(COMPOSE) exec ollama ollama list

# ─── Quality ─────────────────────────────────────────────────────────────────
.PHONY: lint fmt test test.api test.web check
lint: ## ruff check + mypy + web lint
	$(PY) ruff check .
	-$(PY) mypy api core db cache workers settings.py 2>/dev/null || echo "mypy: 部分目标路径尚未落地，跳过"
	$(PNPM) lint

fmt: ## ruff format + prettier
	$(PY) ruff format .
	$(PNPM) format

test: ## 运行 Python 测试
	$(PY) pytest -q

test.api: ## 仅运行 API 测试
	$(PY) pytest tests/api -q

test.web: ## 前端测试
	$(PNPM) test

check: lint test ## CI 聚合: lint + test

# ─── Seed / Ingest ───────────────────────────────────────────────────────────
.PHONY: seed.user ingest
seed.user: ## 交互式创建管理员用户
	$(PY) python -m app.cli user create

ingest: ## 全量把 knowledge/ 入库 + 向量化
	$(PY) python -m app.cli ingest ./knowledge

# ─── Release / Clean ─────────────────────────────────────────────────────────
.PHONY: build.api build.trainer build.web clean nuke
build.api: ## 构建 api 镜像
	docker build -f docker/Dockerfile.app -t rag-chat-api .

build.trainer: ## 构建 trainer 镜像（胖）
	docker build -f docker/Dockerfile.trainer -t rag-chat-trainer .

build.web: ## 前端生产构建
	$(PNPM) build

clean: ## 清理缓存
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -type d -name '.pytest_cache' -prune -exec rm -rf {} +
	rm -rf web-app/dist web-app/.vite

nuke: clean ## [危险] clean + docker compose down -v（连卷一起删）
	@read -p "将删除所有容器和数据卷，输入 yes 继续: " ans; \
	if [ "$$ans" = "yes" ]; then \
		$(COMPOSE) down -v; \
	else \
		echo "aborted"; \
	fi
