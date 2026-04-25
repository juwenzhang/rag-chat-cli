# Tasks: Bootstrap Settings & Env

> 每一项均应为一个独立 commit；`- [ ]` 代表待办，勾选后为已完成。

## 1. 依赖

- [x] 1.1 在 `pyproject.toml` 的 `[project].dependencies` 中加入 `pydantic-settings>=2.2`。
- [x] 1.2 `uv sync` 并确认 `uv.lock` 更新成功。
- [x] 1.3 执行 `uv run python -c "import pydantic_settings; print(pydantic_settings.__version__)"` 验证可导入。

## 2. 新增 `.env.example`

- [x] 2.1 在仓库根目录创建 `.env.example`，字段严格对齐 AGENTS.md §7。
- [x] 2.2 将 `.env` 加入 `.gitignore`（确认已在）。
- [x] 2.3 在 `README.md`（或 `docs/README.md`）加一段"首次运行：`cp .env.example .env`"。

## 3. 新增 `settings.py`

- [x] 3.1 在仓库根创建 `settings.py`，按 design.md 定义 6 个分组 BaseModel。
- [x] 3.2 实现 `Settings` 顶层类，启用嵌套 delimiter `__` 与 `.env` 加载。
- [x] 3.3 对 `JWT_SECRET` 字段使用 `AliasChoices("AUTH__JWT_SECRET", "JWT_SECRET")` 双名兼容，其他关键字段同理（`DATABASE_URL`、`REDIS_URL`、`OLLAMA_BASE_URL` 等）。
- [x] 3.4 导出 module-level 单例 `settings = Settings()`，并加 `__all__ = ["settings", "Settings"]`。
- [x] 3.6 在 `env=dev` 且无 `JWT_SECRET` 时 fallback 到 `"dev-insecure-secret"` 并 `logger.warning`；`env=prod` 时必须显式配置，否则 raise。

> 实现备注：3.3 的扩展范围按实际需求调整 —— pydantic-settings 的 AliasChoices 无法对嵌套子模型生效，
> 改用顶层 `model_validator(mode="before")` 将 `.env.example` 中的所有扁平名
> （`JWT_SECRET` / `DATABASE_URL` / `REDIS_URL` / `OLLAMA_BASE_URL` / `OLLAMA_CHAT_MODEL` / …）
> 映射到嵌套分组，与嵌套名（如 `AUTH__JWT_SECRET`）等价。

> ~~3.5 `load_legacy_config()`~~、~~4.1/4.2 适配 `utils/config.py`~~ 已在 2026-04-24
> "干净化" 清理中作废：`config.json` 与 `utils/config.py` 已从仓库移除，
> 不再需要 legacy shim。

## 5. 测试

- [x] 5.1 新增 `tests/unit/test_settings.py`（若 `tests/unit/` 不存在则一并创建）。
- [x] 5.2 用例：空环境（dev fallback 生效）、`env=prod` 无 secret 应 raise、扁平 alias 与嵌套 alias 双名等价。
- [x] 5.3 运行 `uv run pytest tests/unit/test_settings.py -q` 全部通过。

## 6. 验收

- [x] 6.1 `python -c "from settings import settings; print(settings.ollama.chat_model)"` 输出 `qwen2.5:1.5b`。
- [x] 6.2 `ruff check settings.py` 无错。
- [x] 6.3 更新 AGENTS.md §19 Change Log 追加一行："Bootstrap settings.py (pydantic-settings) + .env.example"。
