# Chat Observability, Sources, Evaluation, and Vision

本设计不走 OpenSpec，直接作为当前聊天体验改造的实现说明。

## 目标

当前聊天回答偏“干回答”：用户只能看到最终文本，难以知道模型是否检索了知识库、是否调用了 `web_search` / `web_fetch`、答案引用来自哪里，也缺少回答质量评分。图片上传也更多是“图片链接 + caption”，还不是对话时直接进入 VL 理解链路。

本轮改造分四层推进：

1. **可观测回答**：展示可审计的思考/动作轨迹，例如“正在检索知识库”“正在调用 web_search”。不暴露模型私有链式推理，只展示产品级执行轨迹。
2. **统一来源**：将本地文档、网页、图片、工具输出统一成 `AnswerSource`，在回答下方展示来源面板。
3. **回答评分**：使用常驻评分模型 `gemma4:31b-cloud` 对回答进行结构化评分，并允许后续加入用户反馈。
4. **图片理解**：用户选择图片后，优先由当前 vision 模型理解；若当前模型不是 vision，则使用常驻 VL 模型做图片理解，再把理解结果注入主模型。

## 常驻模型角色

| 角色 | 推荐模型 | 说明 |
| --- | --- | --- |
| Chat | 用户选择 | 正常对话回答模型 |
| Vision | `qwen3-vl:235b-cloud` | 图片理解、OCR、图表理解 |
| Evaluator | `gemma4:31b-cloud` | 回答质量评分、来源充分性判断 |
| Embedding | 当前 embedding 配置 | 知识库向量检索 |

`gemma4:31b-cloud` 不需要被硬编码成一种模型类型；它本质仍是 chat/instruct 模型。系统应通过配置把它指定为 `evaluation.model`。

## 事件与 UI 映射

后端已有 SSE 事件：

- `thought`：产品级思考/动作轨迹
- `retrieval`：本地 RAG 命中
- `tool_call`：模型请求调用工具
- `tool_result`：工具执行结果
- `token`：回答增量文本
- `done`：回答完成，携带 `sources`、`usage`、`model`、`provider_name`

前端需要：

- 将 `thought` 追加到当前 assistant message 的 `thoughts`。
- 将 `done.sources` 写入当前 assistant message 的 `sources`。
- 回答区按顺序展示：

```text
思考/动作轨迹
来源面板
回答正文
工具调用详情
评分卡片
操作按钮与元信息
```

## 来源统一

统一使用 `AnswerSource`：

```ts
interface AnswerSource {
  source_type: "document" | "web" | "image" | "tool";
  rank: number;
  title?: string | null;
  quote?: string | null;
  score?: number | null;
  source?: string | null;
  url?: string | null;
  document_id?: string | null;
  chunk_id?: string | null;
}
```

展示规则：

- `document`：显示文档标题、score、片段，可跳转文档页。
- `web`：显示网页标题、URL、摘录，外链打开。
- `image`：显示图片标题/文件名、caption/quote。
- `tool`：显示工具名或工具输出摘要。

## 评分机制

评分模型：`gemma4:31b-cloud`。

建议配置：

```env
EVALUATION_ENABLED=true
EVALUATION_MODEL=gemma4:31b-cloud
EVALUATION_TIMEOUT=120
```

评分输出固定 JSON：

```json
{
  "overall": 4,
  "helpfulness": 4,
  "groundedness": 3,
  "citation_quality": 4,
  "completeness": 5,
  "risk": "low",
  "comment": "回答整体有用，但部分结论缺少网页来源支撑。"
}
```

评分维度：

- `overall`：总体质量
- `helpfulness`：是否解决问题
- `groundedness`：是否有依据，是否幻觉少
- `citation_quality`：来源引用是否充分
- `completeness`：是否完整覆盖问题
- `risk`：`low` / `medium` / `high`
- `comment`：简短中文评语

初期实现可以是“点击评分”或“回答完成后自动异步评分”。长期建议自动异步评分，不阻塞主回答。

## 图片理解链路

理想链路：

```text
用户上传图片
  ↓
Asset 存储
  ↓
聊天请求携带 image_asset_ids
  ↓
后端读取图片
  ↓
当前模型支持 vision ?
  ├─ 是：直接 ChatMessage.image_urls 给当前模型
  └─ 否：常驻 VL 模型生成图片理解摘要
          ↓
      主模型结合用户问题 + 图片理解摘要回答
  ↓
AnswerSource(source_type="image") 进入来源面板
```

当前代码已有 `ChatMessage.image_urls`、Ollama/OpenAI 图片序列化和图片 caption 能力，因此图片链路不需要推翻，只需要把聊天请求从 markdown 图片链接升级为 `image_asset_ids` + `image_urls`。

## 本轮可直接落地范围

1. 文档沉淀本设计。
2. 前端展示 `thought` 与 `done.sources`。
3. 新增统一来源面板，覆盖 document/web/image/tool。
4. 新增 `gemma4:31b-cloud` 评分配置、评分表、评分接口和前端评分入口。
5. 图片直连 VL 聊天链路作为下一步，避免本轮改动过大。
