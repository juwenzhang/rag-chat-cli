# Web Search 上下文优化方案

## 1. 问题背景

当前聊天链路已经支持 `web_search` / `web_fetch` 工具，并且搜索结果会作为 `role="tool"` 消息进入后续 LLM 调用。这个设计解决了“模型没有联网就直接回答”的问题，但也暴露了新的上下文管理风险。

典型报错：

```text
ollama /api/chat failed: 400 '{"error":"The prompt is too long: 325881, model maximum context length: 262144 ..."}'
```

这说明：发送给 Ollama `/api/chat` 的完整 `messages` 已超过模型上下文窗口。触发点通常不是 LLM 自身，而是工具结果、历史消息、本地 RAG 和网页证据一起进入 prompt 后发生了膨胀。

## 2. 根因分析

### 2.1 `web_search` 返回内容过大

Ollama 官方 `web_search` 结果可能包含 `title`、`url` 和较长 `content`。如果直接把 5 条搜索结果原样塞给 LLM，每条结果又携带长正文，就会形成很大的工具消息。

### 2.2 `web_fetch` 正文过长

`web_fetch` 用于抓取网页正文。如果每个页面返回几千到上万字符，再叠加多个页面，很容易超过模型预算。

### 2.3 工具消息被持久化后反复进入历史

工具结果会作为 `role="tool"` 写入会话历史。后续每一轮重新加载历史时，旧的 `web_search` / `web_fetch` 结果也会进入上下文。如果这些结果包含大段网页正文，多轮后会持续累积。

### 2.4 本地 RAG 与 Web Evidence 叠加

一个用户问题可能同时触发：

```text
本地知识库检索 + 用户历史 + web_search + web_fetch + 工具调用轨迹
```

单项内容看似可控，但组合后会快速膨胀。

### 2.5 查询文本没有压缩

自动 `web_search` 如果直接使用完整用户输入作为 query，用户一旦输入长日志、长文档或复杂任务描述，搜索请求和返回结果都会偏离主题并变大。

## 3. 为什么不能简单截断

直接截断虽然能降低 token，但会带来准确性风险：

- 可能截掉版本号、配置项、默认值、限制条件。
- 可能只保留页面开头导航，丢失正文。
- 可能导致模型基于残缺证据补全事实。
- 对 MySQL、Kubernetes、Nginx 等配置类问题，配置项名称和默认值尤其不能被随意截断。

因此优化目标不是“砍掉内容”，而是构建更可靠的 **Evidence Pack**：

```text
少量高相关来源 + 精简摘要 + 关键原文摘录 + URL 可追溯 + 明确证据边界
```

## 4. 推荐方案

### 4.1 `web_search` 轻量化

`web_search` 应只返回适合 LLM 初步判断的轻量证据：

```json
{
  "query": "...",
  "provider": "ollama",
  "results": [
    {
      "title": "...",
      "url": "...",
      "content": "短 snippet，不是完整正文"
    }
  ]
}
```

建议限制：

- query 最多 200~300 字符。
- 搜索结果最多 3~5 条。
- 单条 snippet 最多 500~800 字符。
- 总 `web_search` tool content 控制在几千字符以内。

### 4.2 `web_fetch` 精读化

`web_fetch` 不应该默认抓取大量页面，而应该在模型根据搜索结果选择最相关来源后再抓取。

建议限制：

- 每轮最多 2 次 `web_fetch`。
- 单次正文最多 4k~8k 字符。
- 优先抓官方文档、Reference Manual、API Reference。

### 4.3 历史工具消息压缩

当前 turn 的工具结果可以进入 LLM，但历史 turn 的工具结果不应该无限原样保留。

建议：

```text
当前 turn：保留精简后的工具结果。
历史 turn：将 web_search/web_fetch 压缩成标题、URL、短 quote、结果数量、是否成功。
```

示例：

```text
Previous tool result summary for web_search:
- Query: mysql8 configuration details
- Results: 5
- [1] MySQL 8.0 Reference Manual — https://dev.mysql.com/doc/...
- [2] Server System Variables — https://dev.mysql.com/doc/...
```

这样保留可追溯性，但避免旧网页正文重复进入 prompt。

### 4.4 自动查询压缩

自动搜索不应该直接使用完整用户输入。推荐将用户问题压缩为搜索 query：

```text
用户问题：mysql8 的深度理解以及配置详情
搜索 query：mysql 8 official documentation architecture configuration system variables
```

短 query 能提升搜索相关性，也能减少无关网页内容。

### 4.5 提示词约束

最终 LLM 应明确知道证据可能是压缩过的：

```text
Use the provided web evidence for factual claims.
Evidence may be compressed; do not assume omitted details.
Preserve exact option names, commands, versions, defaults, and caveats.
If evidence is insufficient, state the gap explicitly.
Cite sources when available.
```

对配置类问题，需要额外强调：

```text
For configuration topics:
- Preserve exact config keys.
- Preserve default values and version notes.
- Do not paraphrase option names.
- Separate official docs from community/blog sources.
```

## 5. 分阶段落地计划

### P0：立即止血

- 压缩自动 `web_search` query。
- 限制 `web_search` 返回结果数量与 snippet 长度。
- 限制 `web_fetch` 最大正文长度。
- 对历史 `tool` 消息做压缩，避免旧网页正文重复进入 prompt。

### P1：证据包结构化

- 构建统一 `Evidence Pack`。
- 区分 `summary`、`exact_terms`、`quotes`、`sources`。
- 对官方文档、博客、工具输出设置不同优先级。

### P2：Query-focused compression

- 对抓取网页做问题相关压缩。
- 保留配置项、命令、版本号、默认值。
- 让模型只读压缩后的 source notes。

### P3：统一上下文预算器

- 在发送 LLM 前做硬预算检查。
- 优先裁剪旧 tool 消息，再裁剪旧历史，再裁剪证据包。
- 为不同模型预设安全输入预算，例如上下文窗口的 60%~75%。

## 6. 本轮实现目标

本轮先落地 P0：

1. `web_search` query 压缩。
2. `web_search` snippet 和总内容预算限制。
3. `web_fetch` 正文长度上限收紧。
4. 历史工具消息压缩，当前 turn 工具结果仍可用于回答。
5. 自动 Web Evidence 指令注入，提醒模型不要基于被省略内容脑补。

这能最快解决 `prompt too long`，同时尽量保持回答准确性与来源可追溯。

## 7. 工业级方案评估：内容提炼 + 分层择优 + 分级摘要 + 动态路由

进一步演进时，不应停留在“字符限长”层面。更合理的完整方案是围绕 RAG/Web Evidence Pipeline 做四件事：

```text
内容提炼 + 分层择优 + 分级摘要 + 动态路由
```

它适配当前业务链路：

```text
用户问题
→ 本地知识库检索（RAG 片段）
→ WebSearch 拿到链接和摘要
→ WebFetch 拉取网页
→ 上下文聚合
→ 入 LLM
```

核心原则是：

```text
拒绝首尾截断、随机裁文本；
只淘汰整条低价值素材，或把高价值素材提炼成结构化证据；
不破坏单条高价值内容的语义完整性。
```

### 7.1 Fetch 阶段：单文档原位提炼

这是最优先落地的架构优化。

当前 `web_fetch` 的问题是：它拿到网页可读文本后再做长度限制。即使限制了字符数，也仍可能保留大量导航、页脚、侧边栏、无关章节，真正回答问题所需的信息可能反而被排到后面。

更合理的方式是在 Fetch 阶段直接做定向抽取：

1. `web_fetch` 接收用户问题或压缩 query。
2. 将网页正文按段落或章节切分。
3. 根据 query 对段落做相关性打分。
4. 只保留 top-k 相关段落，并按页面原始顺序重排。
5. 对长文档再生成单文档 `SourceNote`。

理想输出不是完整网页正文，而是：

```json
{
  "title": "MySQL 8.0 Reference Manual",
  "url": "https://dev.mysql.com/doc/...",
  "selection_strategy": "query_focused_paragraphs",
  "relevance": "high",
  "summary": "...",
  "exact_terms": ["innodb_buffer_pool_size", "max_connections"],
  "quotes": ["...", "..."],
  "missing_details": []
}
```

这不是粗暴截断，而是问题相关的信息提炼。

### 7.2 RAG + Web 双数据源统一候选池

本地 RAG、Search 摘要、Fetch 内容不应各走各的上下文入口。更合理的是统一成候选池：

```text
EvidenceCandidate
- source_type: document | web_search | web_fetch
- title
- content / summary
- url / document_id
- source authority
- retrieval score
- rerank score
- freshness hint
```

然后统一排序和预算分配。

打分规则可以分阶段：

#### 简版规则打分

```text
官方域名 +3
标题命中 query +2
正文命中关键术语 +1
本地知识库高分片段 +2
重复来源 -2
低质量泛科普 -1
```

#### 高级 Rerank

后续可接：

- embedding similarity
- cross-encoder reranker
- 小模型 relevance judge

当上下文接近预算时，淘汰策略应该是：

```text
整条删除低分素材，不从高分素材中间截断。
```

### 7.3 同源合并和去重

WebSearch 很容易返回多个同站点页面，RAG 片段也可能与网页内容重复。应增加去重层：

```text
URL normalize
canonical URL 合并
domain + title similarity 去重
content hash / simhash 去重
同知识点合并成一条 SourceNote
```

去重后，LLM 看到的是合并后的知识点，而不是重复表达。

### 7.4 分层上下文架构

不要把所有原始材料都塞进同一轮主模型 prompt。更合理的链路是：

```text
第一轮：素材分类与摘要
- 本地 RAG 资料
- WebSearch 资料
- WebFetch 资料

第二轮：正式回答
- 只加载聚合后的 Evidence Pack
- 原始明细不进入主 prompt

后续追问：
- 按 source_id 动态加载原始明细
```

这相当于将一次“大包 prompt”拆成多轮“小包处理”，是工业 RAG 常见做法。

### 7.5 动态工具调用管控

工具不是越多越好。工具调用应该有准入和上限：

```text
web_search:
- 宽泛 query 返回 3 条
- 精准 query 返回 5 条
- 每轮最多 1 次

web_fetch:
- 只有高相关 / 官方 / 权威链接才抓取
- 每轮最多 2 次
- 不递归抓页面内子链接，除非证据严重不足
```

当前已经实现了基础上限，但还缺少基于 rerank 的准入。

### 7.6 上下文分级装载

建议给上下文分区：

```text
LLM 总上下文窗口
= 系统提示词
+ 用户问题
+ 对话历史预算
+ 本地 RAG 预算
+ WebSearch 预算
+ WebFetch 预算
+ 当前工具结果预算
+ 回复预留预算
```

每个分区有固定预算。预算用完后，新内容不再进入本轮 prompt，而是进入外置缓存，后续用户追问再加载。

### 7.7 双 LLM 分层推理

这是进阶方案：

```text
小模型：读取全量 RAG + Web 原始素材，做筛选、提炼、整合。
主模型：只读取小模型产出的 Evidence Pack，生成最终答案。
```

优点：

- 主模型上下文稳定。
- 原始素材处理成本更低。
- 深度问题准确性更高。

缺点：

- 架构复杂度增加。
- 延迟增加。
- 需要评估小模型摘要质量。

因此建议后置。

## 8. 当前项目已实现能力

| 能力 | 当前状态 | 说明 |
| --- | --- | --- |
| `web_search` 自动触发 | 已实现 | `auto` 策略下，对官方文档、最新信息、深度总结类问题自动搜索 |
| `web_search` 次数限制 | 已实现 | 每个 turn 最多 1 次 |
| `web_fetch` 次数限制 | 已实现 | 每个 turn 最多 2 次 |
| `web_search` query 压缩 | 已实现 | query 最长 240 字符 |
| `web_search` 结果轻量化 | 已实现 | 最多 5 条；单条 snippet 700 chars；总 snippet 3000 chars |
| `web_fetch` 正文限长 | 已实现 | 单次最多 6000 chars |
| 历史 tool message 压缩 | 已实现 | 历史 `web_search` / `web_fetch` 不再完整进入后续 prompt |
| Evidence instruction | 已实现 | 提醒模型证据可能被压缩，不要脑补，保留精确配置项 |
| Sources UI 展示 | 已实现 | 支持 sources 面板、滚动、Markdown、Mermaid、横向滚动和动态扩宽 |

这些能力属于 P0 止血层：先控制上下文爆炸，并保证模型知道证据边界。

## 9. 当前未实现能力与问题

### 9.1 Fetch 定向抽取未实现

当前 `web_fetch` 仍主要是正文清洗后压缩，尚未按用户问题做段落级相关性选择。

风险：

- 长页面中真正相关章节可能不在前部。
- 导航、页脚、侧栏仍可能占用预算。
- 配置类问题的关键参数可能被普通字符限长丢掉。

### 9.2 SourceNote 结构化摘要未实现

当前没有统一的 source note 结构，例如：

```text
summary
key_facts
exact_terms
quotes
missing_details
```

风险：

- 配置项、默认值、版本号没有结构化保真。
- LLM 难以区分摘要、原文摘录和缺失信息。

### 9.3 RAG + Web 统一候选池未实现

本地 RAG 和 Web Evidence 仍然是两条相对独立的链路，没有统一打分、统一去重、统一预算。

风险：

- 本地知识和网页证据可能重复。
- 低价值网页可能挤占高价值本地知识预算。
- 无法按全局相关性做整条素材淘汰。

### 9.4 Rerank 未实现

当前没有 cross-encoder 或小模型 rerank。

风险：

- WebSearch 排名不一定等于业务相关性。
- 模型可能 fetch 低质量结果。
- 预算容易被泛科普内容占用。

### 9.5 外置 Evidence Cache 未实现

当前证据要么进入 prompt，要么被压缩，没有一个可按需二次加载的外置缓存。

风险：

- 用户追问某个 source 细节时，无法精确加载原始明细。
- 压缩后的历史信息无法恢复更多上下文。

### 9.6 上下文配额分区未实现

当前已有局部限制，但还没有完整的预算分区：

```text
history budget
local_rag budget
web_search budget
web_fetch budget
current_tool budget
reply reserve
```

风险：

- 某一类内容仍可能挤占其他重要内容。
- 只能靠局部限长，缺少全局预算治理。

## 10. 建议后续落地优先级

### P1：Fetch 定向抽取

最优先。实现成本较低，收益最高。

建议做法：

```text
web_fetch(url, query)
→ HTML text
→ paragraph chunks
→ query keyword scoring
→ top-k paragraphs
→ 按原始顺序重排
→ 返回 excerpts + compact text
```

### P2：EvidenceCandidate + 规则 Rerank

统一本地 RAG 与 Web Evidence：

```text
EvidenceCandidate[]
→ rule-based rerank
→ 去重
→ 整条素材择优
```

先用规则，不急着上模型 reranker。

### P3：SourceNote 结构化摘要

为长文档生成：

```text
summary
key_facts
exact_terms
quotes
missing_details
```

配置类问题必须保留：

- 精确配置项名称
- 默认值
- 版本条件
- 命令示例
- caveats / warning

### P4：Evidence Cache

将完整 source 存到缓存，prompt 只放 `SourceNote`。

用户追问时根据 `source_id` 动态加载原始明细。

### P5：统一上下文预算器

最后建立完整预算分区，控制所有来源进入 LLM 的体积。

## 11. 结论

当前实现已经能防止 `web_search` / `web_fetch` 直接把 prompt 撑爆，但还不是最终形态。

最终方向应该是：

```text
不要做粗暴截断；
把原始材料变成可追溯、可压缩、可重排、可按需加载的 Evidence Pack；
让主模型只读取高价值证据；
把低价值内容整条淘汰或放入缓存，而不是随机裁剪。
```

短期优先做 `Fetch 定向抽取`，中期做 `EvidenceCandidate + Rerank`，长期做 `SourceNote + Evidence Cache + 统一上下文预算器`。
