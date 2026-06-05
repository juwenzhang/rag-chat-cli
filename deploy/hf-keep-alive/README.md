---
title: HF Keep-Alive
emoji: 🔄
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# hf-keep-alive

Pings configured Hugging Face Spaces on a fixed interval to prevent the
"no recent traffic → sleep" lifecycle. The container's main process is
an infinite asyncio loop, so HF will not reclaim the Space for being
idle either.

This Space is the **D** leg of the keep-alive design described in the
[main repo](https://github.com/juwenzhang/rag-chat-cli) at
`docs/ops/KEEPALIVE.md`. The **A** leg is a GitHub Actions cron that
also pings *this* Space, providing redundancy.

## Targets

Configured via the `TARGETS` env var (newline-separated URLs). Defaults
are baked into `app.py` for the rag-chat-cli stack.

## Operate

- HF Space rebuilds on every push to `main`.
- The HTTP server on `:7860` exists only to satisfy HF's "Space must
  expose an HTTP port" rule and to give external pings a 200.
- Logs in HF UI show every ping cycle.

## Deploy from the main repo

The canonical source for this Space lives at `deploy/hf-keep-alive/`
in the main repo. CI auto-deploys on every push that touches that
directory via `.github/workflows/deploy-hf-keep-alive.yml`.

Manual override (e.g. main repo's CI is down):

```bash
cd deploy/hf-keep-alive
git init -q -b main && git add -A && git commit -q -m "deploy"
git remote add hf "https://USER:TOKEN@huggingface.co/spaces/luhanxin/hf-keep-alive"
git push --force hf main
```
