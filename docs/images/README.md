# README screenshots

The two top-level READMEs (`README.md`, `README.zh-CN.md`) reference
the following five images. Drop them in this directory with the exact
filenames below and both READMEs render correctly on GitHub.

> **Storage:** images live as ordinary git blobs (no LFS). This is
> intentional — GitHub's markdown renderer fetches embedded images
> through `raw.githubusercontent.com`, which does **not** dereference
> LFS pointers, so storing screenshots in LFS would show up as broken
> images on the rendered README. Plain blobs render everywhere with
> zero setup. Keep individual files under ~500 kB to stay friendly to
> shallow clones.

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
