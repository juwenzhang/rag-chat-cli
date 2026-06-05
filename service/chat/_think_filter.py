"""Stream-time splitter for ``<think>...</think>`` reasoning tags.

Some Ollama-hosted models emit reasoning inline in the same SSE stream
as the final answer, wrapped in ``<think>`` tags. The filter pulls them
apart so the chat orchestrator can route each piece to a different
event type (``thought`` vs ``token``).

Internal to :mod:`service.chat` — the leading underscore signals that
public consumers should not import this directly.
"""

from __future__ import annotations

from typing import ClassVar

__all__ = ["ThinkTagStreamFilter"]


class ThinkTagStreamFilter:
    """Split streamed text into answer tokens and ``<think>`` thought text."""

    _OPEN: ClassVar[str] = "<think>"
    _CLOSE: ClassVar[str] = "</think>"

    def __init__(self) -> None:
        self._buffer: str = ""
        self._in_think: bool = False

    def feed(self, text: str) -> list[tuple[str, str]]:
        self._buffer += text
        return self._drain(final=False)

    def flush(self) -> list[tuple[str, str]]:
        return self._drain(final=True)

    def _drain(self, *, final: bool) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        while self._buffer:
            if self._in_think:
                idx = self._find(self._CLOSE)
                if idx >= 0:
                    self._emit(out, "thought", self._buffer[:idx])
                    self._buffer = self._buffer[idx + len(self._CLOSE) :]
                    self._in_think = False
                    continue
                if final:
                    self._emit(out, "thought", self._buffer)
                    self._buffer = ""
                break

            idx = self._find(self._OPEN)
            if idx >= 0:
                self._emit(out, "token", self._buffer[:idx])
                self._buffer = self._buffer[idx + len(self._OPEN) :]
                self._in_think = True
                continue
            keep = 0 if final else len(self._OPEN) - 1
            safe_len = max(0, len(self._buffer) - keep)
            if safe_len:
                self._emit(out, "token", self._buffer[:safe_len])
                self._buffer = self._buffer[safe_len:]
            break
        if final:
            self._buffer = ""
        return out

    def _find(self, tag: str) -> int:
        return self._buffer.lower().find(tag)

    @staticmethod
    def _emit(out: list[tuple[str, str]], kind: str, text: str) -> None:
        if text:
            out.append((kind, text))
