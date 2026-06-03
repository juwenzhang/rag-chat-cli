# RTK Command Rule

在本项目中，AI 执行或建议 shell 命令时，应优先使用 `rtk` 包裹高噪声命令，以减少终端输出进入上下文时的 token 消耗。

## 默认策略

优先显式使用 `rtk` 包裹命令，不依赖自动 hook 是否生效。

常见转换：

- `git status` -> `rtk git status`
- `git diff` -> `rtk git diff`
- `git log ...` -> `rtk git log ...`
- `ls ...` -> `rtk ls ...`
- `find ...` -> `rtk find ...`
- `grep ...` / `rg ...` -> 优先改用 `rtk grep ...`
- `cat path/to/file` -> 优先改用 `rtk read path/to/file`
- `pytest ...` -> `rtk pytest ...` 或 `rtk test "pytest ..."`
- `npm test` / `pnpm test` / `yarn test` -> `rtk test "<original command>"`
- `tsc ...` -> `rtk tsc ...`
- `ruff check ...` -> `rtk ruff check ...`
- `docker ps` -> `rtk docker ps`
- `docker logs ...` -> `rtk docker logs ...`
- `kubectl ...` -> 优先使用对应的 `rtk kubectl ...`
- 长输出或未知命令 -> `rtk summary <command>` 或 `rtk err <command>`

## 未安装时的处理

如果需要执行适合 `rtk` 包裹的命令，但检测到当前 macOS 环境没有安装 `rtk`：

1. 先询问用户是否需要帮忙自动安装 `rtk`。
2. 如果用户同意安装，优先使用 Homebrew：

   ```bash
   brew install rtk
   ```

3. 安装后告知用户如何使用：

   ```bash
   rtk --version
   rtk git status
   rtk git diff
   rtk ls .
   rtk gain
   ```

4. 如用户希望启用自动 rewrite，再说明可执行：

   ```bash
   rtk init -g
   ```

   执行后通常需要重启 AI 编程工具或终端会话。

5. 如果用户不同意自动安装，不要继续尝试安装；只提供官方安装链接，让用户自行决定：
   - https://github.com/rtk-ai/rtk
   - https://www.rtk-ai.app/zh/

仅考虑 macOS 使用场景，不需要提供 Windows 安装或兼容性说明。

## 回答后的节省统计反馈

在每次完成涉及命令执行、代码检查、搜索、diff、测试、构建、提交等操作的回答前，如果 `rtk` 可用，应执行：

```bash
rtk gain
```

并在最终回答中简短反馈 RTK 当前统计，例如：

```text
RTK 统计：本次/累计节省情况见 rtk gain 输出。
```

如果 `rtk gain` 输出包含本次会话或最近命令的节省数据，优先反馈最近命令/本次会话；否则反馈累计统计。若 `rtk` 不可用，则按“未安装时的处理”执行，不要伪造节省数据。

## 例外情况

以下情况可以绕过 `rtk`，直接使用原生命令：

- 需要完整、精确、机器可解析输出，例如 JSON 被后续命令解析。
- 需要完整 diff/patch 内容用于精确编辑、审查或生成补丁。
- 命令输出很短，使用 `rtk` 没有明显收益。
- `rtk` 已确认不可用，且用户暂不安装。
- 用户明确要求不要使用 `rtk`。

绕过 `rtk` 时，应简短说明原因。

## 验证

需要确认 `rtk` 是否可用时，使用：

```bash
rtk --version
rtk gain
```

如果 `rtk` 不可用，先询问用户是否需要在 macOS 上通过 Homebrew 自动安装；用户拒绝时，提供官方安装链接。
