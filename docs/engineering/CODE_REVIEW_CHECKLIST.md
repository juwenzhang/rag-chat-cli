# Code Review Checklist（本仓库专属）

打开 PR 之前自己扫一遍，从上往下，**遇到红线立即返工**，不要 merge。

> 通用工程原则见 [PRINCIPLES.md](PRINCIPLES.md)。本清单只列**本仓库具体约束**。

---

## A. 红线（违反必返工）

- [ ] **没有散落字符串字面量**当 type/code 用，全部走 enum
  - 后端：`service/core/streaming/error_codes.py::EventType / FlowErrorCode / TransportErrorCode`
  - 前端 web：`websites/src/lib/api/shared/enums.ts`
  - 前端 TUI：`clients/tui/src/api/enums.ts`
- [ ] **所有 LLM HTTP 调用**走 `service/llm/_http_errors.py::classify_http_error`，不要自己 `if status == 429`
- [ ] **`service/db/models/`** 不能 import `service/<domain>/`（避免循环）
- [ ] **`service/`** 不能 import `api/`（依赖方向永远向下，见 `backend/SERVICE_LAYOUT.md`）
- [ ] **不写测试**（明确策略，靠 lint + 类型 + 手测）
- [ ] **所有命令带 `rtk` 前缀**（在 chat/CR 描述里贴的命令也带）
- [ ] **不动 `openspec/`、`PLAN.md`**，文档归宿是 `docs/`

---

## B. Python 后端

### B.1 类型与枚举

- [ ] 新加状态机字面量？立刻提 enum：
  ```python
  # service/<domain>/state.py
  class XxxStatus(str, Enum):
      PENDING = "pending"
      ACTIVE = "active"
  ```
- [ ] `class FooError` 子类必须有 `code: ClassVar[str]`，匹配前端 `ErrorCode`
- [ ] `TypedDict` 字段用 `total=False`，可选字段写明，不要动态 setattr
- [ ] 函数签名能写 `-> None` / 具体类型就别 `-> Any`

### B.2 Service 层

- [ ] 业务校验抛 `service.core.errors.NotFoundError / ForbiddenError`，让 `api/middleware/errors.py` 映射 HTTP
- [ ] 流式生成器用 `_llm_error_event(exc)` helper，不要每处手拼 dict
- [ ] DB 操作走 short-lived `async with sf() as s`，**不要持有长会话**
- [ ] 跨用户访问数据：在 service 层做 ownership check，不只靠路由

### B.3 文件结构

- [ ] 新加文件控制在 **400 行以内**，超了就拆子模块
- [ ] `__init__.py` 只做 re-export，不写业务
- [ ] `_xxx.py` 私有模块（如 `_http_errors.py`）不上 `__all__`

### B.4 依赖

- [ ] 新增第三方包前，先看 `pyproject.toml` 是不是已经有等价物
- [ ] 没有 `import *`
- [ ] `from __future__ import annotations` 顶在第一行

---

## C. 前端（websites/ + clients/tui/）

### C.1 单向数据流

- [ ] 组件不直接 mutate store，只调 store action
- [ ] 没有 prop drilling > 2 层（用 store / context）
- [ ] 不在 component 里直接 `fetch()`，必走 `lib/api/`

### C.2 类型协议

- [ ] 流式事件 type 用 `StreamEventType` enum，**不要写 `"text_delta"` 字面量**
- [ ] 错误码用 `ErrorCode` 分支，**不要做字符串嗅探**（`msg.includes("rate")` ❌）
- [ ] 消息角色用 `MessageRole`，不混 `"user"` / `"assistant"`
- [ ] `as const` enum 派生 type：
  ```ts
  export const Foo = { A: "a", B: "b" } as const
  export type FooT = (typeof Foo)[keyof typeof Foo]
  ```

### C.3 React/Next 特有

- [ ] Server Component 默认，需要状态/事件再加 `"use client"`
- [ ] `useEffect` 依赖项完整，没有 lint disable
- [ ] 列表渲染稳定 `key`（**不用 index**）
- [ ] 表单：受控组件 + `react-hook-form`，不裸写 onChange 链

### C.4 TUI（Ink）特有

- [ ] 不在 render 里做 IO（IO 走 hook + store）
- [ ] 长文本流式输出走 `useReducer` 累加，不每帧 setState
- [ ] 退出/中断走 `AbortController`，不 leak Promise

---

## D. 协议 / 接口

- [ ] 改了 SSE/WS 事件 → 同步 `docs/backend/STREAM_PROTOCOL.md` 和 `ERROR_CODES.md`
- [ ] 改了路由 → 同步 OpenAPI（如果走自动生成）
- [ ] 加了新错误码 → 后端 `FlowErrorCode` + 前端 `ErrorCode` 同步加，UI 给出 fallback 文案
- [ ] 改了 DB 字段 → alembic migration 必须在 PR 内

---

## E. 文档与 commit

- [ ] commit 信息按 conventional：`refactor(scope): xxx` / `feat(scope): xxx`
- [ ] 大改动（>300 行 diff）写 commit body，列 What / Why / How
- [ ] 加新模块 → `docs/<area>/` 里写一篇说明，更新 `docs/README.md` 索引
- [ ] **不动 openspec/、PLAN.md**

---

## F. 性能 / 可观测

- [ ] 每秒 > 10 次的循环调用 → 想 Redis 缓存（见 `docs/backend/SERVICE_LAYOUT.md` 的三件套计划）
- [ ] LLM 调用 → 走限流装饰器（避免 429 烧 quota）
- [ ] N+1 查询 → 用 `selectinload` / `joinedload`
- [ ] 关键路径加 trace span（`service/core/observability.py`）

---

## G. 安全

- [ ] 所有 `/v1/*` 端点走 auth 中间件，不能裸 dep
- [ ] 多客户端走 `X-Client-Id` 白名单（见 `MULTI_CLIENT_AUTH_DESIGN.md`）
- [ ] 用户输入 → 长度限制 + 白名单字符
- [ ] 错误信息**不回显上游 HTML body**（用 `classify_http_error` 提取关键字段）
- [ ] 不在 log 里打 token / password / API key

---

## H. 代码闻起来不对的快速检测

打开 PR diff，扫这几个东西：

1. **超长函数**：`> 60 行` → 拆
2. **裸 `Any` / `unknown`**：写不出类型说明设计有问题
3. **`# TODO` / `# FIXME` 没立 issue**：要么做要么删
4. **复制粘贴**：3 处相似 → 提炼
5. **死代码**：`grep` 一下没引用就删
6. **`print` / `console.log`**：换成 logger
7. **裸 magic number**：`60` → `KEEPALIVE_SECONDS = 60`

---

## I. AI 协助 PR 的额外注意

- [ ] AI 生成的代码**通读一遍**，理解每一行，不理解的删/改
- [ ] AI 容易写**过度抽象**和**未来可能用到的接口** → 砍
- [ ] AI 容易**复制 docstring 不 update** → 检查注释和实现一致
- [ ] AI 给的命令**手动跑一遍**确认效果，不要直接 merge

---

## 速查口诀

> **enum 优先、SSOT、依赖向下、删比写值钱、注释只说为什么**。
