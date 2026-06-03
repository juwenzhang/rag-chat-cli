# RTK Usage Reference

Source: https://github.com/rtk-ai/rtk/blob/develop/README.md

## Purpose

RTK (Rust Token Killer) is a single Rust binary that proxies common CLI commands and compresses their output before it reaches an AI coding assistant context. It is designed to reduce token usage from common development commands such as `git`, test runners, linters, search commands, Docker/Kubernetes commands, and logs.

Core output reduction strategies:

1. Smart filtering: remove comments, progress bars, boilerplate, and unrelated noise.
2. Grouping: aggregate files, errors, or logs by useful dimensions.
3. Truncation: preserve relevant context while cutting redundant output.
4. Deduplication: collapse repeated lines and logs with counts.

## Installation

Recommended on macOS:

```bash
brew install rtk
```

Quick install for Linux/macOS, after inspecting the remote script and getting user approval:

```bash
curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh
```

Rust/Cargo install:

```bash
cargo install --git https://github.com/rtk-ai/rtk
```

Verify:

```bash
rtk --version
rtk gain
```

If `rtk gain` fails after a Cargo install, check for package-name collision with another `rtk` package and prefer `cargo install --git https://github.com/rtk-ai/rtk`.

## Initialization

General/default setup:

```bash
rtk init -g
```

Agent-specific examples:

```bash
rtk init -g --gemini
rtk init -g --codex
rtk init -g --agent cursor
rtk init -g --agent windsurf
rtk init --agent cline
rtk init --agent kilocode
rtk init --agent antigravity
```

Useful setup flags:

```bash
rtk init -g --auto-patch
rtk init -g --hook-only
rtk init --show
rtk init -g --uninstall
```

Restart the target AI coding tool after initialization.

## Common Commands

Files and search:

```bash
rtk ls .
rtk read file.rs
rtk read file.rs -l aggressive
rtk smart file.rs
rtk find "*.rs" .
rtk grep "pattern" .
rtk diff file1 file2
```

Git:

```bash
rtk git status
rtk git log -n 10
rtk git diff
rtk git add
rtk git commit -m "msg"
rtk git push
rtk git pull
```

GitHub CLI:

```bash
rtk gh pr list
rtk gh pr view 42
rtk gh issue list
rtk gh run list
```

Tests:

```bash
rtk jest
rtk vitest
rtk playwright test
rtk pytest
rtk go test
rtk cargo test
rtk rake test
rtk rspec
rtk err <cmd>
rtk test <cmd>
```

Build and lint:

```bash
rtk lint
rtk lint biome
rtk tsc
rtk next build
rtk prettier --check .
rtk cargo build
rtk cargo clippy
rtk ruff check
rtk golangci-lint run
rtk rubocop
```

Packages and data:

```bash
rtk pnpm list
rtk pip list
rtk pip outdated
rtk bundle install
rtk prisma generate
rtk json config.json
rtk deps
rtk env -f AWS
rtk log app.log
rtk curl <url>
rtk wget <url>
rtk summary <long command>
rtk proxy <command>
```

Containers and cloud:

```bash
rtk docker ps
rtk docker images
rtk docker logs <container>
rtk docker compose ps
rtk kubectl pods
rtk kubectl logs <pod>
rtk kubectl services
rtk aws sts get-caller-identity
rtk aws logs get-log-events
```

Analytics:

```bash
rtk gain
rtk gain --graph
rtk gain --history
rtk gain --daily
rtk gain --all --format json
rtk discover
rtk discover --all --since 7
rtk session
```

Global flags:

```bash
rtk -u <command>        # ultra compact
rtk -v <command>        # verbose; repeat for more verbosity
```

## Configuration

Typical config paths:

- Linux: `~/.config/rtk/config.toml`
- macOS: `~/Library/Application Support/rtk/config.toml`

Example:

```toml
[hooks]
exclude_commands = ["curl", "playwright"]

[tee]
enabled = true
mode = "failures" # "failures", "always", or "never"
```

When a command fails, RTK may save full raw output to a tee file, such as `~/.local/share/rtk/tee/...log`. Use the tee output only when the compact failure summary is insufficient.

## Troubleshooting Checklist

1. Run `rtk --version` to confirm the binary is available.
2. Run `rtk init --show` to inspect current hook/config installation.
3. Restart the AI coding tool after initialization.
4. Confirm the command path uses a shell/Bash tool call; built-in file/search tools may bypass shell hooks.
5. Use explicit wrappers like `rtk git status` if auto-rewrite is uncertain.
6. Check `exclude_commands` if a command is not being rewritten.
7. On Windows, prefer WSL for full hook support.
8. Use raw command output when exact formatting or machine-readable output is required.

## Uninstall

```bash
rtk init -g --uninstall
brew uninstall rtk
cargo uninstall rtk
```
