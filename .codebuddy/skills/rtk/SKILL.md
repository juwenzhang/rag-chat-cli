---
name: rtk
description: This skill should be used when working with RTK (Rust Token Killer), including installing RTK, initializing it for AI coding agents, deciding when to wrap shell commands with rtk, interpreting compressed command output, troubleshooting RTK setup, and configuring token-saving CLI workflows.
license: MIT
metadata:
  source: "https://github.com/rtk-ai/rtk/blob/develop/README.md"
---

# RTK

## Overview

Use RTK as a CLI proxy that compresses noisy command output before it enters an AI coding assistant context. Prefer RTK for long, repetitive, or verbose shell outputs such as tests, diffs, logs, directory listings, grep results, package listings, Docker/Kubernetes output, and build/lint failures.

Load `references/rtk-usage.md` when detailed command examples, installation options, configuration paths, or troubleshooting notes are needed.

## When to Use

Use this skill when the user asks to:

- Install, enable, configure, upgrade, or uninstall RTK.
- Initialize RTK for Claude Code, CodeBuddy-compatible workflows, Cursor, Gemini CLI, Codex, Windsurf, Cline/Roo, Kilo Code, or similar AI coding agents.
- Reduce token usage from shell command output.
- Replace noisy shell commands with compact `rtk` equivalents.
- Interpret RTK output from commands such as `rtk gain`, `rtk discover`, `rtk git status`, `rtk test`, `rtk grep`, or `rtk read`.
- Troubleshoot why commands are not being auto-rewritten through RTK hooks.
- Add project guidance for agents to use RTK command wrappers.

## Core Workflow

1. Detect whether `rtk` is installed before assuming it is available:

   ```bash
   rtk --version
   ```

2. If missing, recommend the least invasive install method for the user's OS:
   - macOS with Homebrew: `brew install rtk`
   - Linux/macOS quick install: inspect the install script first, then run the official installer only after user approval
   - Rust users: `cargo install --git https://github.com/rtk-ai/rtk`
   - Windows: use a prebuilt release or WSL for full hook support

3. Initialize RTK for the target agent only when the user asks for integration or automatic rewriting:

   ```bash
   rtk init -g
   rtk init -g --gemini
   rtk init -g --codex
   rtk init -g --agent cursor
   ```

4. Prefer explicit `rtk` wrappers for one-off command execution during coding sessions, especially when auto-rewrite status is unknown.

5. Use raw command output instead of RTK only when exact formatting is required, when a tool parses machine-readable output, or when debugging an RTK filter itself.

## Command Selection Guide

Use compact RTK commands for high-noise operations:

| Need | Prefer |
| --- | --- |
| Git status | `rtk git status` |
| Git diff | `rtk git diff` |
| Recent commits | `rtk git log -n 10` |
| Search code | `rtk grep "pattern" .` |
| Find files | `rtk find "*.py" .` |
| Read source compactly | `rtk read path/to/file.py` |
| Directory overview | `rtk ls .` |
| Python tests | `rtk pytest` or `rtk test pytest` |
| JS tests | `rtk jest`, `rtk vitest`, or `rtk test "npm test"` |
| TypeScript errors | `rtk tsc` |
| Python lint | `rtk ruff check` |
| Docker containers/logs | `rtk docker ps`, `rtk docker logs <container>` |
| Kubernetes output | `rtk kubectl pods`, `rtk kubectl logs <pod>` |
| Long generic command | `rtk summary <command>` or `rtk err <command>` |

For command outputs needed by other programs, avoid RTK wrappers unless human-readable compression is intended.

## Auto-Rewrite Guidance

Use auto-rewrite hooks for sustained AI coding sessions. After `rtk init`, restart the target AI tool before expecting commands to be rewritten.

Remember these limitations:

- Hook-based rewriting applies to shell/Bash tool calls.
- Built-in IDE/code tools do not necessarily pass through shell hooks.
- On native Windows, automatic shell hook support can be limited; prefer WSL for full support.
- If a command must not be rewritten, configure exclusions in RTK config rather than fighting the hook ad hoc.

## Safety and Privacy

Treat RTK installation and initialization as configuration-changing operations:

- Explain when a command downloads code, modifies shell config, or writes agent hook files.
- Do not run `curl | sh` without explicit user approval.
- Avoid enabling telemetry unless the user explicitly asks. RTK telemetry is opt-in according to the README; keep it disabled by default.
- Avoid passing secrets through commands that may be logged or summarized.

## Verification

After setup or changes, verify with:

```bash
rtk --version
rtk gain
rtk init --show
```

For a quick functional check, run a compact command:

```bash
rtk git status
```

If RTK reports a tee log path after a failing command, read that saved full output only when the compact output is insufficient.
