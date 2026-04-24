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
.PHONY: db.up db.init db.migrate db.rev db.downgrade db.reset db.shell redis.shell
db.up: ## 启动 postgres (pgvector)。P5 后会同时起 redis。
	$(COMPOSE) --profile db up -d postgres

db.init: ## 首次初始化：probe + alembic upgrade head + 校验 pgvector
	$(PY) python scripts/db_init.py

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

redis.shell: ## [P5] redis-cli — redis service lands in add-redis-and-workers.
	@echo "[skip] redis service not in docker-compose yet (P5)."
	@exit 2

# ─── Ollama ──────────────────────────────────────────────────────────────────
.PHONY: ollama.pull ollama.ps
ollama.pull: ## 拉取默认 chat + embed 模型
	$(COMPOSE) exec ollama ollama pull $(OLLAMA_CHAT_MODEL)
	$(COMPOSE) exec ollama ollama pull $(OLLAMA_EMBED_MODEL)

ollama.ps: ## 列出 ollama 已拉取模型
	$(COMPOSE) exec ollama ollama list

# ─── Quality ─────────────────────────────────────────────────────────────────
# 单一真相来源：与 CI workflow .github/workflows/ci.yml 对齐。
# mypy 通过 `uvx` 运行，不依赖本地 venv 预装。
.PHONY: lint lint-fix fmt fmt-check typecheck test test-fast test-cov test-cov-strict ci
# Use the project's venv (`uv run`) rather than a fresh uvx environment so
# mypy can see the real dependency set (SQLAlchemy, pgvector, etc.).
MYPY ?= uv run mypy

lint: ## ruff check（只报告，不修）
	$(PY) ruff check .

lint-fix: ## ruff check --fix
	$(PY) ruff check . --fix

fmt: ## ruff format（写入）
	$(PY) ruff format .

fmt-check: ## ruff format --check（不写入）
	$(PY) ruff format --check .

typecheck: ## mypy --strict（走 uv run，能解析项目所有依赖）
	$(MYPY) --strict . --explicit-package-bases

test: ## 跑所有 pytest
	$(PY) pytest -q

test-fast: ## 跳过 slow / pg / redis / integration 标记
	$(PY) pytest -q -m "not slow and not pg and not redis and not integration"

test-cov: ## pytest-cov（软门：只报告，不退出码）
	uvx --with pytest-cov --with pytest-asyncio --with rich --with pydantic-settings --with prompt_toolkit --with httpx pytest --cov --cov-report=term-missing --cov-report=xml
	python scripts/check_coverage.py --soft

test-cov-strict: ## pytest-cov（硬门：未达 AGENTS.md §12 阈值则失败）
	uvx --with pytest-cov --with pytest-asyncio --with rich --with pydantic-settings --with prompt_toolkit --with httpx pytest --cov --cov-report=term-missing --cov-report=xml
	python scripts/check_coverage.py

ci: lint fmt-check typecheck test ## 本地一把梭：与 CI 等价的组合

# ─── Legacy / future-module shims ────────────────────────────────────────────
# 下列 target 引用了尚未落地的模块（P4+ 才会实装）。
# 保留 target 让 Makefile 文档表达"未来蓝图"，实际调用时返回提示 + exit 2，
# 避免开发者误以为失败是 bug。
.PHONY: test.api test.web
test.api: ## [P5] API tests — awaits add-fastapi-rest-api
	@echo "[skip] tests/api/ not yet bootstrapped (P5). See openspec/changes/add-fastapi-rest-api/."
	@exit 2

test.web: ## [P7] Web tests — awaits build-web-views-auth-chat-knowledge
	@echo "[skip] web-app/ not yet bootstrapped. See openspec/changes/build-web-views-auth-chat-knowledge/."
	@exit 2

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
