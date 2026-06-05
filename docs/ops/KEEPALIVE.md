# Hugging Face Spaces Keep-Alive

> **背景**：HF Space free tier 在长时间没有 HTTP 流量进入时会进入 sleep，下一次请求会触发 cold-start（30s ~ 几分钟）。我们的 backend / ollama / minio 三个 Space 都吃这个亏。本设计用**两条独立保活回路**消除冷启动。

## 1. 双保险设计（A + D）

```
                ┌──────────────────────────┐
   GitHub  ───► │ A. .github/workflows/    │ ──┐
   Actions     │    keepalive-hf.yml      │   │
   (cron 5m)   │                          │   │ HTTP GET
                └──────────────────────────┘   │
                                              ▼
   ┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
   │ rag-chat-backend     │   │ hf-ollama-service    │   │ hf-luhanxin-minio    │
   │  /health             │◄──┤                      │◄──┤                      │
   └──────────────────────┘   └──────────────────────┘   └──────────────────────┘
                                              ▲
                                              │ HTTP GET
                ┌──────────────────────────┐   │
                │ D. luhanxin/             │ ──┘
                │    hf-keep-alive (Space) │
                │    asyncio ping loop     │
                └──────────────────────────┘
                          ▲
                          │ HTTP GET（A 也打它，反向保活）
                          │
                       (A leg)
```

| Leg | 谁触发 | 频率 | 保自己活的方式 | 失败影响 |
| --- | --- | --- | --- | --- |
| **A** GitHub Actions cron | GH 调度器 | 每 5 分钟 | GitHub 不睡 | 偶尔 cron 漂移到 15min 才执行 |
| **D** HF Space `hf-keep-alive` | 容器内 asyncio loop | 每 5 分钟 | 主进程永不退出 + A 也打它 | HF 维护时短暂中断 |

**关键认识**：HF Space sleep 规则有两个独立豁免——
1. **流量豁免**：48h 内有外部 HTTP 请求 → 不睡
2. **进程豁免**：容器主进程持续运行 → 不睡

D 方案同时利用这两条（自己进程不退出 + A 还会从外部打它），**双重保险**。

## 2. 为什么不只用 A

GH Actions free tier cron：
- 队列调度延迟可达 15 分钟
- HF Space 域名的 DNS / 网关偶发 5xx
- GH Actions 偶尔维护，几小时无 cron

D 作为独立兜底：成本 = 1 个 Space slot（CPU basic 免费）。

## 3. 为什么不只用 D

D 自己就是 HF Space，它也吃 sleep 规则。虽然 D 的进程豁免理论上够用，但 HF 偶尔强制重启 Space（你 push 新 commit、HF 平台维护、容器异常退出），这种瞬间 D 不可用，A 兜底打它的 `:7860`，让它一启动就重新满足"流量豁免"。

## 4. 不选其他方案的原因

| 方案 | 不选原因 |
| --- | --- |
| Gradio Space + 自循环 ping | Gradio 多一层 UI 包装，对纯后台浪费 |
| UptimeRobot / Cron-job.org | 引入第三方依赖，可观测性不在自己控制下 |
| 在 backend 里加 self-ping | 逻辑入侵业务代码；backend 自己睡了就完了 |
| nginx 负载均衡 | 单实例 Space 没东西可 balance（详见会话 2026-06-06）|

## 5. 部署步骤

### 5.1 GitHub Actions（A 方案）

文件：`.github/workflows/keepalive-hf.yml`，已就位。**push 即生效**。

修改 ping 列表：直接编辑 `KEEPALIVE_TARGETS` env block，每行一个 URL（前缀 `GET ` 可选）。

如果想用 GitHub Variable 而不是把列表写死在 workflow 里，把 env 改成：
```yaml
env:
  KEEPALIVE_TARGETS: ${{ vars.KEEPALIVE_TARGETS }}
```
然后在 GitHub repo Settings → Secrets and variables → Actions → Variables 里加同名变量。

### 5.2 HF Space `hf-keep-alive`（D 方案）

源文件托管在本仓库 `deploy/hf-keep-alive/`：
- `Dockerfile` — slim Python 3.12 + httpx
- `app.py` — asyncio ping loop + `:7860` HTTP server
- `README.md` — HF Space 元数据 frontmatter（`sdk: docker`, `app_port: 7860`）
- `.dockerignore` — 排除 `__pycache__` 等

**初次创建 Space**：

```text
https://huggingface.co/new-space
  name: hf-keep-alive
  SDK: Docker
  visibility: public
```

**自动部署**（推荐）— `.github/workflows/deploy-hf-keep-alive.yml` 已就位：

- 触发条件：push 到 `master` / `main` / `refactor/tui-refactor` 且修改了 `deploy/hf-keep-alive/**` 或 workflow 文件本身
- 也支持 `workflow_dispatch` 手动触发
- 流程：squash `deploy/hf-keep-alive/` 内容到一个干净的单 commit，force-push 到 Space `main` 分支 → HF 自动 build Docker
- **依赖 GitHub repo secret `HF_TOKEN`**（已存在于 `deploy-hf-backend.yml`，复用即可）

**手动部署**（应急）：

```bash
cd deploy/hf-keep-alive
git init -q -b main && git add -A && git commit -q -m "deploy"
git remote add hf "https://luhanxin:${HF_TOKEN}@huggingface.co/spaces/luhanxin/hf-keep-alive"
git push --force hf main
```

部署完后 HF Space 会自动 build Docker，~2 分钟。看 logs 应该看到：
```
ping loop: 3 target(s), interval=300s
http listening on :7860
ping https://luhanxin-rag-chat-backend.hf.space/health -> 200
...
```

### 5.3 验证

```bash
# A 方案：GH Actions tab → 看 "keep-alive HF spaces" 每 5 分钟跑一次绿色
# D 方案：
curl https://luhanxin-hf-keep-alive.hf.space/
# {"ok":true,"now":"2026-06-06T...","targets":3,"interval_s":300}
```

## 6. 可调参数

| 变量 | 默认 | 说明 | 作用域 |
| --- | --- | --- | --- |
| `PING_INTERVAL_S` | 300 | D 容器内 ping 间隔 | hf-keep-alive Space env |
| `PING_TIMEOUT_S` | 30 | D 单次 ping 超时 | hf-keep-alive Space env |
| `TARGETS` | 见 `app.py` | D 的目标 URL 列表（newline-separated） | hf-keep-alive Space env |
| `KEEPALIVE_TARGETS` | 见 workflow | A 的目标 URL 列表 | repo Variables 或 workflow inline |
| `PORT` | 7860 | D 的 HTTP server 端口 | HF Space 自动注入 |

## 7. 后续考虑

- **如果还是冷启动**：把 `PING_INTERVAL_S` 调小到 180（3 分钟）。HF 的 sleep 阈值不公开，社区经验是 ~30 分钟无流量后开始考虑回收。
- **如果加新 Space**：同时改 `KEEPALIVE_TARGETS`（A）和 `app.py::DEFAULT_TARGETS`（D），两边对称。
- **如果 ping 列表频繁变化**：把 D 的 `TARGETS` 改成 HF Space env var 注入，免去重新 push 镜像。
