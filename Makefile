# ─────────────────────────────────────────────────────────────────────────────
# rag-chat — project Makefile
#
# 运行约定:
#   - Python 命令统一走 `uv run`
#   - 前端命令统一走 `pnpm --dir websites`
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
PY_DEV  ?= uv run --extra dev
PNPM    ?= pnpm --dir websites

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

install.hooks: ## 安装 Git hooks（pre-commit / commit-msg / pre-push）
	@if [ -f .pre-commit-config.yaml ]; then \
		$(PY) pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push; \
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
.PHONY: dev dev.all dev.api dev.worker dev.cli dev.web

# 可覆盖的端口/主机：make dev.api PORT=8001 HOST=127.0.0.1
HOST ?= 0.0.0.0
PORT ?= 8000

dev: ## 推荐入口：跑迁移 + 起 FastAPI（一键调通后端）
	@$(MAKE) --no-print-directory db.init
	@$(MAKE) --no-print-directory dev.api

dev.all: ## 同时起 api + worker + web（需要 tmux，否则请分别开三个终端）
	@if command -v tmux >/dev/null 2>&1; then \
		tmux new-session -d -s ragchat 'make dev.api'; \
		tmux split-window -h -t ragchat 'make dev.worker'; \
		tmux split-window -v -t ragchat 'make dev.web'; \
		tmux attach -t ragchat; \
	else \
		echo "tmux not found. 请分别运行: make dev.api | make dev.worker | make dev.web"; \
		exit 1; \
	fi

dev.api: ## 启动 FastAPI dev server (auto-reload)。端口被占时打印占用进程。
	@if lsof -nP -iTCP:$(PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
		echo "✗ port $(PORT) is already in use:"; \
		lsof -nP -iTCP:$(PORT) -sTCP:LISTEN | sed 's/^/    /'; \
		echo "→ 解决: \`kill <PID>\` 或换端口: \`make dev.api PORT=8001\`"; \
		exit 1; \
	fi
	$(PY) uvicorn api.app:create_app --factory --reload --host $(HOST) --port $(PORT)

dev.worker: ## 启动后台 worker
	$(PY) python main.py worker

dev.cli: ## 启动交互式 CLI
	$(PY) python main.py chat

dev.web: ## 启动 Next.js 前端 dev server
	$(PNPM) dev

.PHONY: dev.kill
dev.kill: ## 强制释放 dev.api 端口（默认 8000，可 PORT=xxx 覆盖）
	@PIDS=$$(lsof -nP -iTCP:$(PORT) -sTCP:LISTEN -t 2>/dev/null); \
	if [ -z "$$PIDS" ]; then \
		echo "port $(PORT) is free"; \
	else \
		echo "killing $$PIDS on port $(PORT)"; \
		kill $$PIDS || kill -9 $$PIDS; \
	fi

# ─── Docker ──────────────────────────────────────────────────────────────────
.PHONY: up down logs ps rebuild
up: ## docker compose up -d（默认启动本地依赖服务）
	$(COMPOSE) --profile $(PROFILE) up -d

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
	$(PY_DEV) python scripts/db_init.py

db.migrate: ## alembic upgrade head
	$(PY_DEV) alembic upgrade head

db.rev: ## 生成 alembic 迁移文件（用法: make db.rev m="add users")
	@if [ -z "$(m)" ]; then echo "用法: make db.rev m=\"message\""; exit 1; fi
	$(PY_DEV) alembic revision --autogenerate -m "$(m)"

db.downgrade: ## alembic downgrade -1
	$(PY_DEV) alembic downgrade -1

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
# 单一真相来源：与 CI workflow .github/workflows/ci.yml 和 Git hooks 对齐。
.PHONY: backend.lint backend.lint-fix backend.fmt backend.fmt-check backend.typecheck backend.compile backend.verify
.PHONY: web.lint web.lint-fix web.fmt web.fmt-check web.typecheck web.verify web.build
.PHONY: lint lint-fix fmt fmt-check typecheck compile verify ci
MYPY ?= uv run mypy
PY_MODULES := api service tui main.py settings.py scripts

backend.lint: ## 后端 ruff check
	$(PY) ruff check .

backend.lint-fix: ## 后端 ruff check --fix
	$(PY) ruff check . --fix

backend.fmt: ## 后端 ruff format（写入）
	$(PY) ruff format .

backend.fmt-check: ## 后端 ruff format --check
	$(PY) ruff format --check .

backend.typecheck: ## 后端 mypy
	$(MYPY) $(PY_MODULES)

backend.compile: ## 后端 compileall（语法/导入路径烟测）
	python3 -m compileall -q $(PY_MODULES) alembic

backend.verify: ## 后端完整质量检查
	$(PY) python scripts/quality.py backend

web.lint: ## 前端 ESLint
	$(PNPM) lint

web.lint-fix: ## 前端 ESLint --fix
	$(PNPM) lint:fix

web.fmt: ## 前端 Prettier（写入）
	$(PNPM) format

web.fmt-check: ## 前端 Prettier check
	$(PNPM) format:check

web.typecheck: ## 前端 TypeScript noEmit
	$(PNPM) typecheck

web.verify: ## 前端完整质量检查
	$(PY) python scripts/quality.py frontend

web.build: ## 前端生产构建
	$(PNPM) build

lint: backend.lint web.lint ## 前后端 lint

lint-fix: backend.lint-fix web.lint-fix ## 前后端 lint 自动修复

fmt: backend.fmt web.fmt ## 前后端格式化

fmt-check: backend.fmt-check web.fmt-check ## 前后端格式检查

typecheck: backend.typecheck web.typecheck ## 前后端类型检查

compile: backend.compile ## 后端 compileall

verify: backend.verify web.verify ## 前后端质量检查（不跑旧测试）

ci: verify ## 与 CI / Git hooks 对齐的组合

# ─── API extras (P6 add-fastapi-rest-api) ───────────────────────────────────
.PHONY: openapi openapi.check
openapi: ## 导出 OpenAPI schema → docs/openapi.json
	$(PY) python scripts/dump_openapi.py

openapi.check: ## 验证 docs/openapi.json 与当前代码一致（CI 用）
	$(PY) python scripts/dump_openapi.py
	git diff --quiet docs/openapi.json || { \
		echo "docs/openapi.json is stale — run 'make openapi' and commit."; \
		exit 1; \
	}

# ─── Seed / Ingest ───────────────────────────────────────────────────────────
.PHONY: ingest
ingest: ## 全量把 knowledge/ 入库 + 向量化
	$(PY) python -m tui.cli ingest ./knowledge

# ─── Release / Clean ─────────────────────────────────────────────────────────
.PHONY: build.api build.web clean nuke
build.api: ## 构建 api 镜像
	docker build -f Dockerfile -t rag-chat-api .

build.web: ## 前端生产构建
	$(PNPM) build

clean: ## 清理缓存
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	rm -rf websites/.next websites/out websites/dist websites/.turbo

nuke: clean ## [危险] clean + docker compose down -v（连卷一起删）
	@read -p "将删除所有容器和数据卷，输入 yes 继续: " ans; \
	if [ "$$ans" = "yes" ]; then \
		$(COMPOSE) down -v; \
	else \
		echo "aborted"; \
	fi
