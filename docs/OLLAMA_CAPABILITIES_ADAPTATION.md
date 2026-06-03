# Ollama 能力适配评估

本文记录当前项目对 Ollama 模型能力的适配现状、已知问题与后续改造方向，重点覆盖：模型能力侧 Thinking、工具调用、Web Search / Web Fetch、Embeddings、Vision。

## 1. 背景

当前项目已经具备基础 ReAct 工具循环、SSE 流式输出、`thought` 事件、`tool_call` / `tool_result` 展示、来源面板与评分机制。但在和 Ollama 最新能力对齐时，还有几个明显差距：

1. `think` 目前是应用层 prompt + `<think>...</think>` 解析，并未真正启用 Ollama 原生 `think` 参数。
2. Ollama 响应中的 `message.thinking` 尚未解析。
3. 工具调用后，模型可能只输出工具调用而没有最终 `content`，前端会显示 `Response stopped`。
4. Web Search 目前走 DuckDuckGo HTML/Lite 页面，稳定性不如 Ollama 官方 Web Search API。
5. Embeddings 当前使用旧 `/api/embeddings` 单条循环接口，未对齐新 `/api/embed` 批量接口。
6. Vision 底层已有 `image_urls` 支持，但聊天链路尚未真正将上传图片作为 `images` 传给模型。

## 2. Ollama 原生 Thinking 能力

Ollama Chat API 支持请求字段：

```json
{
  "think": true
}
```

也支持部分模型的 thinking 等级：

```json
{
  "think": "low"
}
```

可选形式：

```text
true / false / "low" / "medium" / "high"
```

响应中，Ollama 将 thinking 和最终回答分离：

```json
{
  "message": {
    "thinking": "模型思考内容",
    "content": "最终回答"
  }
}
```

流式响应时，常见字段是：

```text
chunk.message.thinking
chunk.message.content
```

### 当前项目状态

当前 `OllamaClient.chat_stream` payload 只有：

```python
payload = {
    "model": model or self._chat_model,
    "messages": [_message_to_wire(m) for m in messages],
    "stream": True,
}
```

有工具时追加：

```python
payload["tools"] = [_tool_to_wire(t) for t in tools]
```

目前还没有：

```python
payload["think"] = True
```

也没有解析：

```python
msg.get("thinking")
```

所以当前不是 Ollama 原生 thinking，而是：

1. 后端主动发 `thought` 事件；
2. prompt 要求模型输出 `<think>...</think>`；
3. `ChatService` 解析 `<think>` 标签为 `thought` 事件。

## 3. 用户侧深度思考开关建议

建议将 thinking 做成用户可控能力，而不是永远强制打开。

### UI 建议

在聊天输入区增加：

```text
[深度思考]
```

更完整形态：

```text
Think: Off | Low | Medium | High
```

### 请求体建议

扩展 `MessageIn`：

```python
think: bool | Literal["low", "medium", "high"] | None = None
```

含义：

| 值 | 行为 |
| --- | --- |
| `None` | 使用模型/服务默认策略 |
| `False` | 请求禁用 thinking |
| `True` | 请求开启 thinking |
| `"low"` | 低强度 thinking |
| `"medium"` | 中等强度 thinking |
| `"high"` | 高强度 thinking |

### 后端建议

`LLMClient.chat_stream` 增加参数：

```python
think: bool | Literal["low", "medium", "high"] | None = None
```

`OllamaClient.chat_stream` 中：

```python
if think is not None:
    payload["think"] = think
```

## 4. 需要解析 `message.thinking`

当前 `ChatChunk` 只有：

```python
delta: str = ""
done: bool = False
usage: dict[str, object] | None = None
tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
```

建议扩展：

```python
thinking: str = ""
```

`OllamaClient` 解析：

```python
if isinstance(msg, dict):
    thinking = msg.get("thinking", "") or ""
    delta = msg.get("content", "") or ""
```

`ChatService` 处理：

```python
if chunk.thinking:
    yield {"type": "thought", "text": chunk.thinking}
```

这样前端的 `Thinking trace` 才能展示真正的模型能力侧 thinking。

## 5. 为什么会出现工具跑完但没有回答

前端显示 `Response stopped` 的条件是：

```text
streaming=false
content=""
error=null
```

这说明后端完成了，但 assistant 正文为空。

常见原因：

1. 模型第一轮只返回 `tool_calls`，没有 `content`。
2. 工具调用后，模型继续调用工具，迟迟不生成最终回答。
3. 如果启用了 Ollama 原生 thinking，但没有解析 `message.thinking`，大量输出会被丢弃。
4. 工具上限后的最终总结阶段，如果 `final_text` 为空，仍然会写入空 assistant 消息。
5. Web Search / Web Fetch 结果过长或失败，模型可能继续搜索而不是总结。

### 建议修复方向

1. 解析并展示 `message.thinking`。
2. 工具循环中聚合 `thinking`、`content`、`tool_calls`，并在下一轮一并传回 Ollama。
3. 若最终 content 为空，不应直接 `done`，应返回明确错误或再做一次强制短答。
4. 限制每轮 Web Search / Web Fetch 次数，避免重复搜索。
5. 工具结果过长时做摘要后再喂给模型。

## 6. Tool Calling 对齐 Ollama 文档

Ollama 文档建议工具调用流程：

1. 用户消息进入模型。
2. 模型返回 assistant message，可能包含：
   - `thinking`
   - `content`
   - `tool_calls`
3. 程序执行工具。
4. 将 tool result 以 `role="tool"` 追加回 messages。
5. 再次调用模型。
6. 直到模型不再返回 `tool_calls`，输出最终回答。

流式场景下，需要聚合每个 chunk 的：

```text
thinking
content
tool_calls
```

然后将聚合后的 assistant message 加回上下文。

### 当前差距

当前 `ChatMessage` 没有 `thinking` 字段。因此工具循环中上一轮 thinking 无法传回 Ollama。

建议：

```python
@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str
    thinking: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    tool_name: str | None = None
    sources: tuple[dict[str, Any], ...] = ()
    image_urls: tuple[str, ...] = ()
```

Ollama 序列化时：

```python
if m.thinking:
    out["thinking"] = m.thinking
```

工具消息建议带：

```python
{"role": "tool", "tool_name": tc.name, "content": result.content}
```

## 7. Web Search / Web Fetch 能力

Ollama 官方提供：

```text
POST https://ollama.com/api/web_search
POST https://ollama.com/api/web_fetch
```

Web Search 请求：

```json
{
  "query": "what is ollama?",
  "max_results": 5
}
```

返回：

```json
{
  "results": [
    {
      "title": "...",
      "url": "...",
      "content": "..."
    }
  ]
}
```

当前项目的 `web_search` 是抓 DuckDuckGo HTML/Lite 页面，缺点是：

- 国内/容器网络容易超时；
- HTML 结构不稳定；
- 无官方 SLA；
- 结果字段较弱。

建议：

1. 如果配置了 `OLLAMA_API_KEY`，优先使用 Ollama 官方 Web Search / Web Fetch。
2. 官方 API 失败时 fallback 到 DuckDuckGo HTML/Lite。
3. Web Search 结果统一转成 `AnswerSource(source_type="web")`。

## 8. Embeddings 能力

Ollama 新文档推荐：

```text
POST /api/embed
```

请求：

```json
{
  "model": "embeddinggemma",
  "input": ["text one", "text two"],
  "dimensions": 768,
  "truncate": true
}
```

响应：

```json
{
  "model": "embeddinggemma",
  "embeddings": [[0.1, 0.2]],
  "total_duration": 123,
  "load_duration": 123,
  "prompt_eval_count": 8
}
```

当前项目使用旧接口：

```python
POST /api/embeddings
{"model": target_model, "prompt": text}
```

且逐条循环调用。

建议升级：

1. 优先 `/api/embed`；
2. 批量传 `input: string[]`；
3. 支持 `dimensions`；
4. 支持 `truncate`；
5. 旧 `/api/embeddings` 作为 fallback。

## 9. Vision 能力

Ollama Vision REST API 使用：

```json
{
  "model": "gemma3",
  "messages": [
    {
      "role": "user",
      "content": "What is in this image?",
      "images": ["<base64-image-data>"]
    }
  ]
}
```

当前项目底层已有：

```python
image_urls: tuple[str, ...] = ()
```

`OllamaClient` 会把 `data:` URL 转成 base64 payload。

但聊天链路目前还没有真正把用户上传图片作为 `image_asset_ids -> base64 -> images` 传入模型。

建议：

1. 前端发送 `image_asset_ids`，而不是只把图片转成 markdown 链接。
2. 后端读取 asset bytes。
3. 转成 base64 或 data URL。
4. 如果当前模型是 vision 模型，直接传给当前模型。
5. 如果当前模型不是 vision，使用常驻 VL 模型先生成图片理解摘要，再交给主模型回答。

## 10. 推荐实施优先级

### P0：修复“工具跑完但没有回答”

- `ChatChunk` 增加 `thinking`。
- `OllamaClient` 解析 `message.thinking`。
- `ChatService` 把 thinking 转成 `thought` 事件。
- 如果最终 content 为空，不要静默完成，改成明确错误或强制短答。

### P1：用户级深度思考开关

- 前端 composer 增加 Think 开关。
- 请求体增加 `think`。
- BFF/store 透传。
- `OllamaClient` payload 加 `think`。

### P2：工具调用协议对齐

- `ChatMessage` 增加 `thinking` 和 `tool_name`。
- 工具循环传回 assistant 的 `thinking/content/tool_calls`。
- tool result 带 `tool_name`。

### P3：Ollama 官方 Web Search / Web Fetch

- 使用 `OLLAMA_API_KEY`。
- 优先官方 API。
- fallback 到 DuckDuckGo。

### P4：Embeddings 升级

- `/api/embed`。
- 批量 input。
- dimensions。
- truncate。
- fallback `/api/embeddings`。

### P5：Vision 聊天链路

- `image_asset_ids`。
- asset bytes -> base64。
- vision 模型直接理解。
- 非 vision 模型走常驻 VL 模型生成 image context。

## 11. 总结

当前项目已经有 ReAct、工具调用、来源展示、评分、应用层 thinking 的基础。但要充分利用 Ollama 最新能力，需要重点补齐：

1. 原生 `think` 请求参数；
2. `message.thinking` 解析；
3. 工具调用时传回 thinking；
4. 空回答兜底；
5. 官方 Web Search / Web Fetch；
6. 新 `/api/embed`；
7. Vision 图片链路。

最优先的是 P0 和 P1，因为它们直接影响当前用户看到的“web_search / web_fetch 做了，但最后没有回答”的问题。
