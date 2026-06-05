# Error Codes

流式 `error` 事件的 `code` 字典。`code` 是稳定的机器可读标识，前端按 `code` 分支决定提示样式与 CTA；`message` 仅作为兜底文案。

事件骨架：

```json
{
  "type": "error",
  "code": "llm_rate_limited",
  "message": "Ollama upstream rate-limited",
  "upstream_status": 429,
  "upstream_url": "https://ollama.com/upgrade",
  "retry_after": 60
}
```

> 同一帧形态用于 SSE (`POST /chat/stream`) 与 WebSocket (`/ws/chat`)。
> 协议骨架见 [STREAM_PROTOCOL.md](STREAM_PROTOCOL.md)。

---

## LLM 上游错误（来自 `service.llm.*`）

| code | 触发条件 | 字段 | UI 建议 |
|---|---|---|---|
| `llm_rate_limited` | 上游 429 / quota 耗尽 / 网关限流（Cloudflare / ollama.com 前置 CDN HTML 429） **或** 本地 Redis 限流（每用户每窗口超额，见 [`REDIS_INTEGRATION.md`](REDIS_INTEGRATION.md)） | `upstream_status`、`retry_after` | 黄色 toast：「暂时被限流，X 秒后自动重试」 |
| `llm_subscription_required` | Ollama Cloud 返回 "requires a subscription, upgrade for access: <URL>" | `upstream_url` | 升级 CTA 按钮链到 `upstream_url` |
| `llm_unauthorized` | 401/403：API key 缺失或无效 | `upstream_status` | 提示去 `/settings/providers` 重配 key |
| `llm_model_not_found` | 404：模型未拉取 / 名字写错 | — | 引导 `ollama pull <model>` 或换模型 |
| `llm_upstream_unavailable` | 5xx / 上游返回 HTML 错误页 / 连接超时 | `upstream_status` | 红色：「LLM 服务暂不可用」 |
| `llm_error` | 兜底：未识别的 LLM 错误 | — | 红色：原 `message` |

字段约定：

- `upstream_status` 为整数 HTTP 状态码（`int | null`）。
- `upstream_url` 仅在我们能从错误体中可靠提取时填充（如 `https://ollama.com/upgrade`）。
- `retry_after` 单位**秒**，从 `Retry-After` 响应头解析；若上游未给则为 `null`，前端自行决定退避策略。

---

## ChatService 流程错误

非 LLM 上游错误，由 `service.chat.service.ChatService.generate()` 自身产生：

| code | 触发条件 | UI 建议 |
|---|---|---|
| `ABORTED` | 客户端中止（WebSocket `{type:"abort"}` / HTTP 断开） | 静默或灰色提示，不视为故障 |
| `retrieval_failed` | KnowledgeBase.search() 抛出 | 提示「检索失败，已跳过 RAG」并继续显示已有 token |
| `memory_read_failed` | 加载历史失败（DB 异常） | 红色：「无法读取会话历史」 |
| `memory_write_failed` | 写入消息失败 | 红色：「消息未保存，请重试」 |
| `max_steps_reached` | ReAct 步数耗尽仍未收敛到无 tool 调用 | 灰色：「Agent 推理步数耗尽，已强制总结输出」 |
| `unexpected` | `ChatService.generate()` 内部未捕获异常 | 红色：通用错误 + 可附 request_id |

---

## 传输层错误

| code | 来源 | 含义 |
|---|---|---|
| `PROTOCOL` | `coerce_event` 无法把字典验证成 `StreamEvent` | 后端发出了不合协议的帧；提示「服务端协议异常」 |
| `INTERNAL` | router 层未捕获异常（`api/routers/chat_stream.py` / `chat_ws.py` 的 `except Exception`） | 与 REST 5xx 等价，附 `X-Request-ID` 便于排查 |
| `PARSE` | 仅由前端 SSE 解析器产生（`websites/.../sse/client.ts`、`clients/tui/src/api/sse.ts`），后端不会发出 | 客户端拿到了非 JSON 的 `data:` 行 |

---

## 不再使用的 code

| code | 替换为 | 备注 |
|---|---|---|
| ~~`llm_error`（裸字符串、含 HTML body）~~ | 上述细分 code（`llm_rate_limited` / `llm_subscription_required` / ...） | 旧实现把所有 LLM 错误塞进同一个 code 并把 200 字节 HTML 当 message 回显，前端只能 grep 文本判断订阅墙；新实现按上游响应特征分流。`llm_error` 保留为兜底。 |
| ~~`UNKNOWN`~~ | `unexpected` | `ChatService.to_completion()` 内部 fallback 文案 |

---

## 前端实现位置

- Web：`websites/src/features/chat/components/message-view/message-error-block.tsx` — `switch (error.code)` 分支决定提示样式与 CTA。
- TUI：`clients/tui/src/components/transcript/render-message.ts` — 同上，渲染为终端着色文本。

类型定义：

- 后端：`service/llm/client.py::LLMError`（基类）+ 子类；`api/streaming/protocol.py::ErrorEvent`。
- Web：`websites/src/lib/api/shared/types.ts::ErrorPayload`。
- TUI：`clients/tui/src/api/types.ts::ErrorPayload`。

新增 code 时三处一起改，并补这张表。
