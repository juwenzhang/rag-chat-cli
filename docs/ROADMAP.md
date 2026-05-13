# RAG-Chat-CLI 演进路线图

> 本文档总结了项目从 v1.x 单机 CLI 演进到 v2.x 多端 Client-Server 架构的设计决策。
> 阅读对象：贡献者、维护者、需要理解项目方向的下游使用者。

---

## 1. 现状（v1.x）

```
┌──────────────────────────────────────────┐
│ rag-chat CLI (Python, prompt_toolkit)    │
│   ├─ ChatService (ReAct loop)            │
│   ├─ LLM (Ollama / OpenAI-compatible)    │
│   ├─ KnowledgeBase (File / pgvector)     │
│   ├─ Memory (File / Postgres)            │
│   └─ Tools + MCP                         │
└──────────────────────────────────────────┘

附带 FastAPI (api/) 暴露同一个 ChatService 的能力，
但 CLI 自身不通过 API 调用——直接组装 core/。
```

**问题：**
1. CLI 是 monolithic 的：用户必须本地准备 Python + Ollama + (可选) Postgres。
2. CLI 和 API 数据各自管理：CLI 的会话 Web 端看不到，反之亦然。
3. 没有 Web UI，普通用户无法零成本试用。
4. JWT-only 认证安全性不足，无验证码、无防 XSS（access token 暴露在 JS）。

---

## 2. 目标架构（v2.x，Daemon/Client-Server）

```
┌───────────────────────────────────────────────────┐
│  lhx-rag Server (Daemon)                           │
│  FastAPI + ChatService + LLM/KB/Memory/Tools      │
│  本地 :8000 或远程 https://rag.example.com         │
└──────┬─────────────┬─────────────┬───────────────┘
       │ HTTP/SSE/WS │ HTTP/SSE/WS │ HTTP/SSE/WS
       │             │             │
┌──────┴──────┐ ┌────┴────┐ ┌──────┴──────┐
│ Python CLI  │ │ Web 前端 │ │ 第三方应用    │
│ (轻量 Client)│ │(Next.js)│ │ (任意语言)    │
└─────────────┘ └─────────┘ └─────────────┘
```

### 关键设计：混合模式（Hybrid）

CLI 同时支持两种工作方式：

| 模式 | 命令 | 适用场景 |
|------|------|----------|
| **本地直连** | `rag-chat chat`（现状） | 离线、单机、零依赖 |
| **连接 Server** | `rag-chat chat --server http://localhost:8000` | 多端共享、远程协作 |

> 不采用「纯 Client-Server」（强制连接 Server）的原因：
> 1. 本地 Ollama 用户不需要额外部署成本
> 2. 离线场景仍然可用
> 3. 渐进式迁移，零破坏性变更

---

## 3. 实施分期

### Phase 1 ✅（当前）：Web 前端 + 认证升级

**目标：** 让普通用户能通过浏览器访问，认证更安全。

- [x] 架构演进文档（本文）
- [ ] 认证升级设计文档（`docs/AUTH_DESIGN.md`）
- [ ] `websites/` Next.js 16 项目骨架
- [ ] 后端认证升级：HttpOnly Cookie + 邮箱验证码
- [ ] 登录/注册/聊天页面 MVP

### Phase 2：Transport 抽象层

**目标：** CLI 接入混合模式，代码不重复。

- [ ] 定义 `ChatTransport` Protocol（`core/transport/protocol.py`）
- [ ] 实现 `LocalTransport`（包裹现有 ChatService）
- [ ] 实现 `RemoteTransport`（HTTP/SSE Client）
- [ ] CLI 添加 `--server`、`--token` 参数
- [ ] `rag-chat serve` 后台守护进程子命令

### Phase 3：生产打磨

- [ ] Docker Compose 一键部署（Postgres + Redis + Ollama + Server + Web）
- [ ] 部署文档（自部署 VPS、Render、Fly.io）
- [ ] 监控面板（Prometheus / OpenTelemetry）
- [ ] 多用户 / 团队功能

### Phase 4（可选）：SaaS 化

- [ ] 计费系统
- [ ] 多租户隔离
- [ ] 托管 Ollama / OpenAI key 代理
- [ ] 官方 Web UI 上线

---

## 4. 关键决策记录

### 4.1 为什么选 Option A（混合模式）而不是 Option B/C？

| 方案 | 评估 | 结论 |
|------|------|------|
| A：混合模式 | 改动小、兼容性最好、用户自由 | ✅ 采用 |
| B：纯 Client-Server | 强制部署 Server，离线用户失去能力 | 拒绝 |
| C：Transport 抽象层 | 设计最优雅，但开发成本高 | Phase 2 实现 |

实际上 **Option A 的实现路径就是 Option C 的子集**——先做混合模式落地，再抽象 Transport 协议。两者不矛盾。

### 4.2 为什么 Web 前端不放独立仓库？

- 后端 API 和前端契约耦合（schema 同步）
- monorepo 让 `make ci` 能同时校验
- 用户克隆一个仓库就能跑全栈
- 未来可独立 deploy（前端推 Vercel，后端推 Render）

### 4.3 为什么选 Next.js 16？

- App Router + RSC 简化 SSR
- 内置 SSE / Streaming UI 支持
- TypeScript 一等公民
- 部署生态成熟（Vercel / 自托管）

### 4.4 为什么不做 Node.js SDK？

短期不做，理由：
- 当前优先解决「普通用户能用」（Web UI 即可）
- SDK 是开发者需求，可在 Phase 3 之后再做
- OpenAPI 已有，第三方可自动生成 client

但未来会做，长期目标参照 `@anthropic-ai/sdk`。

---

## 5. 公共 API 层（v2.x 的契约）

所有 Client（CLI / Web / 第三方）都通过这层调用：

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/auth/register` | 注册（带邮箱验证码） |
| POST | `/auth/login` | 登录（Cookie 下发） |
| POST | `/auth/code/send` | 发送验证码 |
| POST | `/auth/refresh` | 刷新 access token（Cookie） |
| POST | `/auth/logout` | 登出，清除 Cookie |
| GET | `/me` | 当前用户 |
| GET/POST | `/chat/sessions` | 会话管理 |
| POST | `/chat/stream` | SSE 流式聊天 |
| WS | `/ws/chat` | WebSocket 聊天（支持 abort） |
| GET/POST/DELETE | `/knowledge/documents` | 知识库 CRUD |
| GET | `/knowledge/search` | 检索 |

详细 schema 参见 `docs/openapi.json`。

---

## 6. 兼容性承诺

- v1.x 的 `rag-chat chat` 行为不变（本地直连模式继续工作）
- v2.x 之前所有 API 端点保持向后兼容
- 数据库 migration 单调向前（不回滚）
- 旧 JWT 在 Cookie 模式下仍能解析

---

## 7. 参考

- [AUTH_DESIGN.md](./AUTH_DESIGN.md) — 认证升级详细方案
- [STREAM_PROTOCOL.md](./STREAM_PROTOCOL.md) — 流式事件契约
- [AGENTS.md](../AGENTS.md) — 架构总纲
- Anthropic SDK 设计：https://github.com/anthropics/anthropic-sdk-python（对标参考）
