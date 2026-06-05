# 工程化原则速查

写给自己和 future 自己的「30 秒就能扫完一遍」的速查表。每条规则都给**反例 → 正例**，不讲废话。

---

## 1. DDD（领域驱动设计）

### 1.1 它解决什么

把"业务规则"和"技术细节"分开，让代码长得**像业务**，而不是像数据库表。

### 1.2 四层模型（折中扁平版）

```
┌────────────────────────────────────────┐
│  入口层 (api/, cli/, ws/)              │  ← HTTP / WS / TUI / 定时任务
├────────────────────────────────────────┤
│  应用层 (service/<domain>/service.py)  │  ← 编排：调多个 domain + 平台 SDK
├────────────────────────────────────────┤
│  领域层 (service/<domain>/*)           │  ← 纯业务规则，无 IO
├────────────────────────────────────────┤
│  基础设施层 (service/platform/, db/)   │  ← Redis / DB / 对象存储 / HTTP
└────────────────────────────────────────┘
```

**依赖方向永远向下**：上层 import 下层，**下层永远不 import 上层**。
本仓库的执行约束在 [`backend/SERVICE_LAYOUT.md`](../backend/SERVICE_LAYOUT.md)。

### 1.3 核心概念

| 概念 | 一句话 | 本仓库例子 |
| --- | --- | --- |
| **Entity（实体）** | 有 ID、可变、生命周期 | `db.models.User`, `ChatSession` |
| **Value Object（值对象）** | 无 ID、不可变、按值相等 | `KnowledgeHit`, `SessionMeta`, `ChatMessage` |
| **Aggregate（聚合）** | 一组实体 + 值对象，外部只能通过聚合根访问 | `ChatSession` 是根，`Message` 必须通过它 |
| **Repository（仓储）** | 把"集合"概念抽象成接口，实现挂在基础设施层 | `DbChatMemory`、`PgvectorKnowledgeBase` |
| **Domain Service（领域服务）** | 跨多个聚合的纯业务逻辑 | `ChatService`、`KnowledgeService` |
| **Application Service** | 编排领域服务 + 基础设施 | 路由 handler 调 `ChatService` 那一层 |

### 1.4 反例 vs 正例

❌ **贫血模型**：实体只是 dataclass，业务规则全写在路由里
```python
# api/routers/chat.py
if session.user_id != current_user.id:
    raise HTTPException(403)
session.title = new_title
db.commit()
```

✅ **行为内聚**：实体/聚合自己保护不变量
```python
# service/memory/chat_memory.py
async def set_title(self, session_id: str, title: str) -> None:
    if row.user_id != self._user_id:
        return  # 防御性所有权检查
    row.title = title
```

---

## 2. SOLID（OO 五原则）

| 字母 | 原则 | 本仓库例子 |
| --- | --- | --- |
| **S** | Single Responsibility — 一个类只为一个变化原因而改 | `ChatService` 1k+ 行就是反例，待拆 |
| **O** | Open/Closed — 对扩展开放，对修改关闭 | `LLMClient` Protocol：加 provider 不动 chat |
| **L** | Liskov — 子类能替代父类不破坏行为 | `LLMRateLimitError` 必须能当 `LLMError` 抛 |
| **I** | Interface Segregation — 别给 client 它用不到的接口 | `ChatMemory` 只暴露 8 个方法，不混 admin |
| **D** | Dependency Inversion — 依赖抽象不依赖具体 | `ChatService` 收 `KnowledgeBase` Protocol，不 import pgvector |

---

## 3. SSOT（Single Source of Truth）

**只有一个地方说了算**。同一个事实多处定义 → 早晚漂移 → bug。

### 本仓库的 SSOT 实践

| 事实 | SSOT 在哪 | 反例 |
| --- | --- | --- |
| 流式事件类型 | `service/streaming/error_codes.py::EventType` | 路由里散写 `"text_delta"` 字面量 |
| 错误码 | `FlowErrorCode` / `TransportErrorCode` / `ErrorCode` (前端) | 前端 `if (msg.includes("rate")) ...` 字符嗅探 |
| 消息角色 | `MessageRole` enum（前后端各一份，值对齐） | 散写 `"user"` / `"assistant"` |
| LLM HTTP 错误分类 | `service/llm/_http_errors.py::classify_http_error` | 每个 client 自己解析 status |
| 用户身份 | `service/db/models/user.py` 一张表 | session storage / file / DB 三处都存 |

### 经验法则

> **三处复制 = 重构信号**。第二次复制忍一下，第三次出现立刻提取。

---

## 4. MVC vs MVVM（前端架构）

### 4.1 两者对比

| 角度 | MVC | MVVM |
| --- | --- | --- |
| 数据流 | 单向：Controller → Model → View | 双向绑定：View ⇄ ViewModel ⇄ Model |
| View 状态 | 由 Controller 主动 push | 自动反应 ViewModel 变化 |
| 测试粒度 | Controller / Model 可单测 | ViewModel 完全可单测，View 几乎不测 |
| 典型框架 | Rails、Spring MVC、早期 Backbone | Vue、Knockout、SwiftUI、Angular |

### 4.2 现代前端的真实形态

**React / Next.js 不是严格 MVC 也不是 MVVM**，更像 **Flux/单向数据流 + 组件即 ViewModel**：

```
   ┌──────────────┐    action    ┌──────────────┐
   │     View     │ ───────────► │    Store     │
   │  (Component) │              │  (Zustand /  │
   │              │ ◄─────────── │   Redux)     │
   └──────────────┘   subscribe  └──────────────┘
                                        │
                                        ▼
                                  ┌──────────────┐
                                  │   Service    │ ── HTTP / SSE / WS
                                  └──────────────┘
```

### 4.3 本仓库的层次（websites/）

```
src/
├── app/            ← Next.js 路由层（Server Component 优先）
├── features/       ← 业务域（chat, auth, knowledge）
│   └── chat/
│       ├── components/   ← View（纯渲染，最少状态）
│       ├── stores/       ← ViewModel（zustand store + selector）
│       └── hooks/        ← 编排 hook，胶水层
├── lib/
│   ├── api/        ← 服务层：fetcher、SSE 客户端、类型
│   └── sse/        ← 平台 SDK
└── components/ui/  ← 设计系统
```

**判定准则**：

| 代码 | 该放哪 | 反例 |
| --- | --- | --- |
| 渲染 + ARIA + 样式 | `components/` | 在组件里直接 fetch |
| 状态形状、reducer、selector | `stores/` | 跨组件用 prop drilling |
| 事件流编排（async + 多 store） | `hooks/` | 在 component 里写 useEffect 链 |
| HTTP / SSE / WS 调用 | `lib/api/` | 在 store 里直接 `fetch()` |

---

## 5. 单向数据流（Unidirectional Data Flow）

**Action → State → View → Action**。同一时刻只有一个方向。

### 反例：双向漂移

```ts
// 组件直接改 store 内部字段
chatStore.messages.push(newMsg)  // 直接 mutate
setLocalCopy([...chatStore.messages])  // 又复制一份本地
```

### 正例：派发 action

```ts
chatStore.appendMessage(newMsg)   // 唯一入口
const messages = useChatStore(s => s.messages)  // 只读订阅
```

---

## 6. 错误处理：Exception vs Result

### 何时抛异常

- **不可恢复**：DB 连不上、配置缺失、内部 bug
- **跨 4+ 层调用栈**：捕获噪声大于价值

### 何时用 Result/Tuple

- **业务可恢复**：表单校验、用户不存在、配额超
- **频繁路径**：每个调用方都要分支处理

### 本仓库的混合策略

```python
# 异常（service 层向上抛，路由层映射成 HTTP）
raise NotFoundError("session not found")

# 结构化事件（流式协议，每条消息都是值对象）
yield {"type": EventType.ERROR.value,
       "code": FlowErrorCode.RATE_LIMITED.value,
       "message": "..."}
```

---

## 7. 命名

| 层级 | 命名风格 | 例子 |
| --- | --- | --- |
| 模块 | 名词，单数 | `chat`, `auth`, `memory` |
| 类 | 名词 | `ChatService`, `OllamaClient` |
| 函数 | 动词 + 名词 | `build_chat_service_for_user`, `classify_http_error` |
| Protocol | 描述能力 | `KnowledgeBase`, `ChatMemory`（不加 `IXxx`） |
| 异常 | 后缀 `Error` | `LLMRateLimitError` |
| Enum | 单数名词，值小写带下划线 | `EventType.TEXT_DELTA` → `"text_delta"` |
| 私有 | 前导下划线 | `_classify_http_error` 仅内部用就别上 `__all__` |

**强约束**：见到 `data` / `info` / `obj` / `helper` / `utils` 这种词，立刻想想能不能换一个具体名词。

---

## 8. 其他高频原则

### 8.1 KISS — Keep It Simple, Stupid

第一版能跑就行。**别为想象中的需求加抽象**。

### 8.2 YAGNI — You Aren't Gonna Need It

砍掉「以后可能要用」的代码。本仓库刚删的 `FileChatMemory` 就是反例（保留两年没人用）。

### 8.3 DRY — Don't Repeat Yourself（但别过度）

复制 2 次以内不算重复，第 3 次必须提。**重复结构 ≠ 重复逻辑**：两段代码长得像但是为了不同业务原因而变化，**不要合并**。

### 8.4 Boy Scout Rule

「让你接触的代码比来时更干净一点」。每个 PR 顺手清 1~2 个小毛病，不要一次大重构。

### 8.5 Composition over Inheritance

需要复用就组合（DI / mixin），少继承。继承一旦超过 2 层基本就是噩梦。

### 8.6 Tell, Don't Ask

```python
# ❌ Ask
if user.tokens > 0:
    user.tokens -= 1

# ✅ Tell
user.consume_token()  # 内部自己判
```

### 8.7 Fail Fast

参数错、配置缺、依赖不在 → **启动时就崩**，不要带病运行到第 N 个请求才报错。

---

## 9. 代码闻起来不对的信号（code smell）

| 信号 | 含义 | 应对 |
| --- | --- | --- |
| 函数 > 60 行 | 职责太多 | 抽 helper |
| 类 > 500 行 | 聚合根肿了 | 拆子领域服务 |
| 方法参数 > 5 个 | 概念散乱 | 引入 dataclass / kwargs object |
| if/elif 链 > 5 个分支 | 缺多态 | 字典分派 / 策略模式 / enum + match |
| 函数嵌套 > 3 层 | 控制流难读 | 早返 + 抽出循环体 |
| 注释解释"做什么" | 代码不会说话 | 改名 / 拆函数（注释只解释"为什么"） |
| 大量字符串字面量 | SSOT 缺失 | 提 enum / 常量 |
| `# TODO` 超过 3 个月 | 假装会做 | 立 issue 或删掉 |

---

## 10. 给 future 自己的话

1. **现在能跑 > 完美架构**。先写丑的，让它跑，再慢慢挪到该在的地方。
2. **重构靠分批**，每次 ≤ 800 行 diff，配 docs 说明 why。
3. **删代码比写代码值钱**。能删 100 行远胜加 100 行。
4. **类型/枚举/Protocol 是给未来的自己留的礼物**，多写一点不亏。
5. **疑问就问 AI**，但**最终决定权在你**——AI 给的方案要看是否真的解决你的问题，而不是看起来很厉害。
