# Proposal: Bootstrap `settings.py` and `.env.example`

## Why

目前项目的配置散落在 `config.json`、`utils/config.py` 与零散的 `os.environ` 读取中，违反 AGENTS.md §7 "单一配置入口" 和 §16 "禁止直接 `os.getenv`" 的硬约束。后续所有阶段（DB/Redis/Ollama/JWT/RAG）都强依赖一个统一、可类型化、可本地覆盖的配置层。

## What Changes

- 新增 `settings.py`（`pydantic-settings`），集中声明所有运行时参数。
- 新增 `.env.example`，作为本地/容器环境变量的范本。
- 在 `pyproject.toml` 中加入 `pydantic-settings` 依赖，并拆分 `[optional-dependencies].train` / `.dev` 两组。
- 约定：新代码**禁止**再 `os.environ[...]` 读配置，统一 `from settings import settings`。

> **施工期变更**（2026-04-24 归档时补记）：仓库在本 change 落地前已完成"干净化"，
> `config.json` 与 `utils/config.py` 均被删除。因此原方案中的 `load_legacy_config()`
> 适配层以及"不动 `utils/*`"的约束均已失效，施工过程中一并作废，相关 task 也在
> `tasks.md` 中标注删除。现实落点仅包含上面 4 条。

## Non-goals

- 不引入 FastAPI、DB、Redis 等运行时依赖（后续 change 再做）。
- 不做 secret 管理（Vault / SOPS 等）。
- 不做配置热重载。

## Impact

- **受影响路径**：`settings.py`（新增）、`.env.example`（新增）、`pyproject.toml`（加 dep + 拆 extras + 加 `[tool.pytest.ini_options]`）、`tests/unit/test_settings.py`（新增）、`README.md` / `AGENTS.md`（文档同步）。
- **风险**：低。纯新增 + 非破坏；仓库此前已通过"干净化"彻底清除旧配置入口。
- **回退方式**：删除 `settings.py` + `.env.example` + `tests/unit/test_settings.py`，回滚 `pyproject.toml` 即可。
