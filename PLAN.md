# RAG-Chat-CLI 实施计划

> 本文件是 **可执行的下一步路线图**——按 sprint 拆分，每个 sprint 都能独立交付。
> 上层架构决策见 [`docs/ROADMAP.md`](docs/ROADMAP.md)；认证设计见 [`docs/AUTH_DESIGN.md`](docs/AUTH_DESIGN.md)。
>
> 维护：每完成一个 sprint 在标题前打 ✅，每出现新需求往最近 sprint 里追加。

---

## 0. 项目定位（不要忘）

我们做的是**像 Claude Code 一样的开发者工具**，不是 SaaS：

- 🏠 **用户自部署**，自己装 Ollama / 接 OpenAI / 选模型 / 加 API key
- 🔧 **我们只定义协议和 UI**：LLM Provider 接口、Tool 接口、KB 接口、Memory 接口
- 🎛️ **一切都暴露给用户控制**：模型切换、工具开关、记忆编辑、KB 管理
- ❌ **不做的事**：付费墙、托管模型、限制用户能用哪些模型、内置审核

参考心态：
- Claude Code 让用户自己选 Claude Opus/Sonnet/Haiku
- VS Code 让用户自己装扩展
- 我们让用户自己选 LLM Provider、自己管 KB、自己挂 Tool

底线只有一条：**只要符合协议（`LLMClient` / `Tool` / `KnowledgeBase`），就能接入**。

---

## 1. 已完成的事情

### 后端（保持稳定）
- ChatService（ReAct loop）+ LLM Protocol（Ollama / OpenAI 双实现）
- ToolRegistry + MCP stdio client
- PgvectorKnowledgeBase（hybrid RAG: vector + pg_trgm + RRF）
- FileKnowledgeBase（离线 fallback）
- ChatMemory（File / Postgres 两种）+ UserMemoryStore（长期记忆）
- AuthService（JWT + bcrypt + refresh rotation）
- FastAPI 暴露：auth / chat（SSE+WS）/ knowledge / me 全套
- Redis worker（异步 ingest）

### 前端（`websites/`）
- Next.js 16 + BFF 架构（浏览器→Next→FastAPI）
- Cookie 会话管理（HttpOnly + 自动 refresh in Route Handler）
- 登录/注册/聊天三页 MVP
- shadcn 风格 UI 组件库（自建，无依赖外部 shadcn CLI）
- 主题系统（cookie + SSR + 系统偏好检测，无 FOUC、无 React 19 script 警告）
- Markdown 渲染（react-markdown + remark-gfm + rehype-highlight）
- 代码块语言标签 + 一键复制
- 主题感知的代码高亮（GitHub Light / GitHub Dark）

---

## 2. 当前已知遗留问题

### 视觉
| # | 问题 | 根因 | 推荐方案 |
|---|------|------|----------|
| V1 | 侧边栏所有会话都叫 "Untitled" | 后端 `title=null`，从没自动起标题 | 首条消息前 30 字截断；后续可升级为 LLM 总结 |
| V2 | 侧边栏底部账户区 vs 聊天输入区不对齐 | 两边 `border-t` 在不同 Y 位置 | 去掉聊天输入区的 `border-t`，靠 backdrop-blur + scroll fade 自然过渡 |
| V3 | 登录/注册页背景跟 chat 一样 | 共用 `--background` token | 浅色路线：纯白 + 居中 logo + 两条品牌色细线条；不再叠渐变 |

### 功能
- **不知道在用哪个模型**（这次提出的）
- 没法切换模型
- 没法保存对话到 KB（CLI 的 `/save` 没暴露）
- 没法管理 KB 内容
- 没法上传文件
- 没法用联网搜索
- 没法编辑长期记忆

---

## 3. Sprint 规划

### Sprint 1 · 视觉收尾 + 自动标题（1 天）

**目标**：把上面 V1/V2/V3 三个视觉问题修了。

**具体改动**：
1. **会话自动标题**
   - 后端：`ChatService.generate()` 在第一条 user 消息后，如果 `session.title is None`，截取前 30 字写回
   - 触发时机：第一条 user 消息持久化后，异步 fire-and-forget
   - 升级版（v2）：用 LLM 一行总结（成本 ≈ 50 token）

2. **底部对齐**
   - `chat-view.tsx` 输入区去掉 `border-t`
   - 输入容器加 `shadow-[0_-8px_24px_-12px_rgba(0,0,0,0.08)]` 自然过渡
   - 滚动区底部加 `mask-image: linear-gradient(to top, transparent, black 24px)`

3. **登录/注册页背景重做**
   - 移除 `bg-brand-gradient` 和 floating orbs
   - 纯背景色 + 居中 logo + 一条很细的品牌色 underline 在 logo 下
   - Card 用 `shadow-lg shadow-foreground/[0.06]`，不用 glass

**交付物**：visual polish PR，不动后端任何接口。

---

### Sprint 2 · 模型与 Provider 管理 ⭐ 这次最重要（3-5 天）

> 让用户像 Claude Code 一样能在 UI 里切换 LLM Provider 和模型。

**设计思路**：

#### 2.1 引入 Provider 抽象

「Provider」= 一个 LLM 接入点。每个用户可以配多个：
- `id`: uuid
- `name`: 用户起的名字（"My Local Ollama"、"OpenRouter GPT-OSS"）
- `type`: `"ollama"` | `"openai_compatible"`
- `base_url`: `http://localhost:11434` 或 `https://api.openrouter.ai/v1`
- `api_key`: 加密存储，可选
- `is_default`: 用户的默认 provider
- `enabled`: 软删除

#### 2.2 数据库改动

**新表**：
```sql
-- providers
CREATE TABLE providers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('ollama', 'openai_compatible')),
  base_url TEXT NOT NULL,
  api_key_encrypted TEXT,           -- 用 settings 里的对称密钥加密
  is_default BOOLEAN DEFAULT FALSE,
  enabled BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (user_id, name)
);

-- user_preferences (key-value JSON, 可以以后扩别的)
CREATE TABLE user_preferences (
  user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  default_provider_id UUID REFERENCES providers(id) ON DELETE SET NULL,
  default_model TEXT,
  extra JSONB DEFAULT '{}',
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**chat_sessions 加两列**：
```sql
ALTER TABLE chat_sessions
  ADD COLUMN provider_id UUID REFERENCES providers(id) ON DELETE SET NULL,
  ADD COLUMN model TEXT;
```

#### 2.3 后端 API

```
GET    /providers                       # 列我的 providers
POST   /providers                       # 新增（带连通性测试）
PATCH  /providers/{id}                  # 改名 / 改 url / 改 key / set default
DELETE /providers/{id}                  # 软删

GET    /providers/{id}/models           # 实时拉 model list（带 30s 缓存）
POST   /providers/{id}/models/pull      # 只对 Ollama 有效，代理到 /api/pull（SSE 进度）
DELETE /providers/{id}/models/{name}    # 只对 Ollama 有效

GET    /me/preferences                  # 我的默认设置
PATCH  /me/preferences

# chat_sessions 接口扩展
PATCH  /chat/sessions/{id}              # 加 provider_id / model 字段
POST   /chat/stream                     # body 加 provider_id / model（覆盖 session 默认）
```

#### 2.4 ChatService 改造

```python
# 之前
service = ChatService(llm=OllamaClient.from_settings(settings), ...)

# 之后
async def build_chat_service_for_user(user_id, session_id) -> ChatService:
    session = await get_session(session_id)
    provider = await resolve_provider(user_id, session.provider_id)
    model = session.model or user_prefs.default_model
    llm = build_llm_client(provider, model)   # 工厂方法
    return ChatService(llm=llm, ...)

def build_llm_client(provider, model) -> LLMClient:
    if provider.type == "ollama":
        return OllamaClient(base_url=provider.base_url,
                            api_key=decrypt(provider.api_key_encrypted),
                            chat_model=model)
    elif provider.type == "openai_compatible":
        return OpenAIClient(base_url=provider.base_url,
                            api_key=decrypt(provider.api_key_encrypted),
                            chat_model=model)
```

#### 2.5 前端 UI

**A. 工具栏（每次对话都看到）**
- 在 chat-toolbar 当前 "Thinking" badge 旁加一个 **Model Selector**
- 点击：弹出 Popover
- Popover 内容：
  ```
  Provider: [Ollama (local) ▾]
  Model:    [qwen2.5:1.5b ▾]
  ──────────────────────────
  Manage providers →   /settings/providers
  ```
- 修改后立即写回 session（PATCH `/chat/sessions/{id}`）

**B. 设置页 `/settings/providers`**
- Tab 布局：Providers / Models / API Keys
- Providers tab：
  - List of cards (name, type, url, model count, default badge, enabled toggle)
  - "+ Add provider" → 引导式表单：
    1. 选类型 (Ollama / OpenAI-compatible)
    2. 填 url
    3. 填 key（Ollama 可空）
    4. 点 "Test connection" → 实时拉一次 models 验证
    5. 保存
- Models tab（选中某个 Ollama provider 后显示）：
  - 已安装：列表 + 大小 + 删除按钮
  - 拉取新模型：输入框（autocomplete 自动 ollama hub 流行模型）→ Pull 按钮 → 进度条（SSE）

**C. 第一次登录的引导**
- 没配 provider 时，登录后引导到 `/settings/providers/new`
- 给个默认的 "Local Ollama (http://localhost:11434)" 模板，一键创建

#### 2.6 安全
- `api_key_encrypted`: 用 Fernet（或 NaCl）+ 一个 `ENCRYPTION_KEY` env 变量
- 接口返回时 key 永不出现明文，只返回是否设置（`has_api_key: true`）
- 修改时单独传 `api_key`（不传则保留原值）

#### 2.7 交付物
- alembic migration 0004
- `core/providers/` 模块（CRUD + 加密 + 工厂）
- 6 个 API route
- Web 端：toolbar model selector + `/settings/providers` 完整页面
- 文档：在 `docs/` 加 `PROVIDERS.md` 解释模型如何接入

---

### Sprint 3 · 知识库 Web 集成（3-5 天）

> 后端已经全部就位，只缺 Web UI。这是项目最有差异化的能力。

**核心理解（必须先讲清楚）**：

#### 3.1 「AI 回答什么时候向量化？」的答案

**默认：永远不会。** 这是有意为之。

```
对话 → ChatMemory（messages 表，纯文本）
              ↓
       ❌ 默认不会进 chunks 表（向量库）

进向量库的路径只有两条：
  1. 用户点 ⭐「保存到知识库」 → 显式保存
  2. 用户开启「自动反思保存」 → critic LLM 评分 >阈值 才存
```

**为什么不全自动**：
- 90% 对话是噪声（澄清、闲聊、试错）
- 全存会污染检索（垃圾进垃圾出）
- KB 是「精选过的知识」，不是「日志」
- 用户已经被 ChatGPT/Claude 训练成不期待「全自动记忆」

#### 3.2 要做的 UI

**A. 消息底部加「保存」按钮**
- AssistantMessage 的 ActionRow 里加 ⭐ Star icon
- 点击：弹出小 Popover：
  - 标题（默认取对话标题或自动总结）
  - 标签（可选）
  - 确认保存
- 后端：POST `/knowledge/documents` 带 `{title, content: "Q: ...\nA: ...", source: "chat", session_id, message_id}`

**B. ChatToolbar 加「自动保存」开关**
- 三档：off / smart (默认 0.7 阈值) / aggressive (0.5 阈值)
- 开启后调 critic 端点评分（已有 `/save` 后端逻辑）

**C. 新建 `/knowledge` 页面**
- 侧栏：文档列表（搜索框 + 按 source 过滤：chat / web / file / manual）
- 主区：选中文档后显示 metadata + chunks + 删除按钮
- 顶部：「上传文件」按钮 + 「全文搜索」框

**D. 消息里的检索 hits 可点击**
- 当前 retrieval block 是只读的折叠 list
- 改为：点 `[1]` 角标 → 跳转 `/knowledge/{doc_id}#chunk-{chunk_id}` 高亮原文

#### 3.3 后端可能要补
- `POST /knowledge/documents/reflect` — 接收 `{session_id, message_id, threshold}`，运行 critic，自动决定是否存
- `chat_sessions.auto_reflect_threshold` 字段记录用户选的阈值

---

### Sprint 4 · 工具系统 + 联网搜索（1 周）

> 框架已经支持 tool calling，缺真正有用的内置 tool。

#### 4.1 Web Search Tool

**第一阶段：Tavily**（推荐起步）
- 免费 1000 次/月
- 专为 LLM 优化（返回的内容已经压缩好）
- 一行配 API key

实现：
```python
# core/tools/web_search.py
class TavilySearchTool(FunctionTool):
    name = "web_search"
    description = "Search the web for current information"
    parameters = {...}
    async def call(self, query: str) -> str: ...
```

**第二阶段：Brave / SearXNG**（自部署）

#### 4.2 Tool 启用机制

- 当前所有注册的 tool 对 agent 都「随时可用」
- 想做：用户/会话级别开关
  - `user_preferences.enabled_tools: JSONB` = `["web_search", "calculator", ...]`
  - ChatService build 时按这个 filter ToolRegistry

#### 4.3 UI

- 工具栏加「🌐」按钮 → toggle web search
- 设置页加 "Tools" tab：
  - 列出所有 tool（来自 ToolRegistry + MCP）
  - 每个 tool 一个 toggle
  - 需要 API key 的 tool 旁边「Configure」按钮
- 消息里 tool_call block 已经做得不错，保持

#### 4.4 搜索结果是否入 KB？

**v1：不入。** 只作为当轮 context，避免污染。
**v2：可选入。** 搜索 tool 的参数加 `cache: bool`，存的话 `source='web'`，去重 by URL，TTL 7 天。

---

### Sprint 5 · 文件上传 + 长期记忆 + MCP（视需求）

- **文件上传**：拖拽到 chat 输入框 → POST `/knowledge/upload` → 入 worker 队列 → 进 KB
- **长期记忆编辑器**：`/settings/memories` 页面，CRUD `user_memories` 表
- **MCP server 管理**：`/settings/mcp` 页面，配置 stdio command，启停

---

### Sprint 6 · 工程化收尾

- 会话搜索（已有 UI 框，连后端全文搜索）
- 导出对话（Markdown / JSON）
- 模型 / Provider 调用统计（已有 UsageAccumulator，做个 dashboard）
- OpenTelemetry 接入指南（docs/OBSERVABILITY.md）
- Docker Compose 一键部署（postgres + redis + ollama + api + web）

---

## 4. 不做的事（明确的边界）

- ❌ 内置付费 / 订阅 / 配额系统
- ❌ 托管 LLM（不替用户跑 Ollama 不替用户付 OpenAI 钱）
- ❌ 内容审核 / 关键词过滤（用户自己的部署，自己负责）
- ❌ 强制用户必须用某个 provider
- ❌ 替用户决定哪些对话该入 KB（保持显式控制）
- ❌ 闭源任何东西，所有 UI 状态都能在 API 里看到 / 改

---

## 5. 优先级建议

| 顺序 | Sprint | 时间 | 价值 |
|-----|--------|------|------|
| 1 | Sprint 1 视觉收尾 | 1 天 | 立刻能用，体验质变 |
| 2 | Sprint 2 模型管理 | 3-5 天 | **当前最痛**——用户根本不知道在用啥 |
| 3 | Sprint 3 知识库 UI | 3-5 天 | 项目最大差异化能力的兑现 |
| 4 | Sprint 4 联网搜索 | 1 周 | 让 agent 真的有用 |
| 5 | Sprint 5 文件/记忆/MCP | 视需求 | 锦上添花 |
| 6 | Sprint 6 工程化 | 1 周 | 准备开源 / 给别人用 |

---

## 6. 与既有文档关系

| 文档 | 角色 |
|------|------|
| [`PLAN.md`](./PLAN.md) | **本文**——可执行 Sprint 计划，随实现更新 |
| [`docs/ROADMAP.md`](./docs/ROADMAP.md) | 高层架构演进（v1 单机 → v2 Client-Server） |
| [`docs/AUTH_DESIGN.md`](./docs/AUTH_DESIGN.md) | 认证升级设计（JWT + Cookie + 邮箱码） |
| [`AGENTS.md`](./AGENTS.md) | 后端架构总纲（保持稳定） |
| [`docs/STREAM_PROTOCOL.md`](./docs/STREAM_PROTOCOL.md) | SSE/WS 事件契约 |
| [`README.md`](./README.md) / [`README.zh-CN.md`](./README.zh-CN.md) | 给用户看的入门 |
| [`websites/README.md`](./websites/README.md) | Web 端架构说明（BFF 模式） |

新增（Sprint 落地时再写）：
- `docs/PROVIDERS.md` — Sprint 2 交付
- `docs/KNOWLEDGE_BASE.md` — Sprint 3 交付
- `docs/TOOLS.md` — Sprint 4 交付

---

## 7. 当前对话记录的核心决策

把这次和上一轮对话沉淀的关键判断列在这里，避免漂移：

1. **定位** — 工具不是 SaaS，用户自部署，所有能力暴露给用户
2. **架构** — 混合模式（CLI 可本地直连 OR 连 Server）；Web 强制连 Server
3. **BFF 模式** — 浏览器只跟 Next.js 通话，Next.js server-side 调 FastAPI
4. **认证** — Cookie + email code，全部在 Next.js BFF 层管 Cookie
5. **主题** — Cookie SSR + 系统偏好检测，绝不渲染 `<script>` 在 React 树里
6. **模型管理** — 每用户可配多 Provider，每会话可指定 model（Sprint 2 落地）
7. **向量化** — 默认不自动入库，只有 `/save` + `/reflect` 两条路径
8. **联网搜索** — 走 Tool 协议接入，结果默认不入库

---

**下一步**：跑 Sprint 1，1 天搞定视觉收尾 + 自动标题。要不要现在开始？
