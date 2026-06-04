# README screenshots

The two top-level READMEs (`README.md`, `README.zh-CN.md`) reference
the following five images. Drop them in this directory with the exact
filenames below and both READMEs render correctly on GitHub.

> **Storage:** every image in this directory is tracked by **Git
> LFS** — see the root `.gitattributes`. New PNG / JPG / WEBP / GIF
> files added here are automatically routed to LFS, so the repo
> stays slim even as the screenshot collection grows. If you don't
> have `git-lfs` installed, clones will land tiny pointer files in
> place of real images; run `brew install git-lfs && git lfs pull`
> (or your platform's equivalent) once and they'll materialise.

| Filename | What it should show |
| --- | --- |
| `web-home-zh.png` | Web app home page, signed-in, **Chinese** UI. Suggested viewport: 1280×800. Crop to include the sidebar, header and the "今天想让我帮你什么？" hero. |
| `web-login-zh.png` | Web app sign-in card, **Chinese** UI. Capture the centered card with the "欢迎回来" headline. |
| `web-home-en.png` | Same as `web-home-zh.png` but with the language switched to **English**. |
| `web-login-en.png` | English sign-in card with the "Welcome back" headline. |
| `tui-login.png` | Ink terminal client (`lhx-rag`) sign-in screen. Best taken in a 120×40 (or larger) terminal window so the ASCII title doesn't wrap. |
| `tui-shell.png` | Ink terminal client main view — sessions sidebar (with the model footer pinned at the bottom), transcript, composer, status bar. |

Tips:

- Use a **dark terminal theme** for `tui-*.png` to keep the screenshots
  consistent with the on-screen colours.
- PNG, not JPG — small enough at < 500 kB each thanks to the flat UI
  surfaces.
- If you change any of these filenames, update the markdown image
  references in `README.md` and `README.zh-CN.md` in lockstep.
