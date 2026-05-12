"""Prompt template system (#17 P3.4).

Replaces the hand-rolled ``_format_citation_prompt`` / ``_format_user_memory_prompt``
free functions in :mod:`core.chat_service` with a single
:class:`PromptBuilder`. The builder owns the template strings *and* the
composition rules (what order system messages appear in, when to emit a
default system message, etc.).

Why this exists:

* DRY — two RAG-style features (citations, user memories) were each
  building a system message inline; a third (e.g. agent persona) would
  duplicate the pattern again.
* Customisation — deployments / tests can swap out the default templates
  by constructing a :class:`PromptTemplates` with different strings.
* Testability — the builder is a pure function over its inputs; no IO.

Compose-on-build, not compose-on-class: there's no template inheritance
or partials. Adding a new system-message kind means adding a field to
:class:`PromptTemplates` and a branch in :meth:`PromptBuilder.build`,
not a new subclass. Keeps the indirection cheap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.llm.client import ChatMessage

if TYPE_CHECKING:
    from core.knowledge.base import KnowledgeHit
    from core.memory.user_memory import UserMemoryEntry

__all__ = [
    "DEFAULT_TEMPLATES",
    "PromptBuilder",
    "PromptTemplates",
]


_DEFAULT_SYSTEM = (
    "You are a helpful assistant. Be concise, accurate, and admit when you "
    "do not know something."
)

_DEFAULT_CITATION_INTRO = (
    "You have access to the following retrieved sources. Use them to "
    "ground your answer and cite them inline as [1], [2], … when relevant. "
    "If the sources do not contain the answer, say so plainly."
)

_DEFAULT_USER_MEMORY_INTRO = (
    "Long-term context about this user (apply when relevant; do not "
    "repeat verbatim unless asked):"
)


@dataclass(frozen=True, slots=True)
class PromptTemplates:
    """User-customizable template strings used by :class:`PromptBuilder`.

    Construct with the defaults via :data:`DEFAULT_TEMPLATES` and override
    only the fields you care about::

        templates = dataclasses.replace(DEFAULT_TEMPLATES, system="...")
    """

    system: str = _DEFAULT_SYSTEM
    citation_intro: str = _DEFAULT_CITATION_INTRO
    user_memory_intro: str = _DEFAULT_USER_MEMORY_INTRO


DEFAULT_TEMPLATES = PromptTemplates()


@dataclass(frozen=True, slots=True)
class PromptBuilder:
    """Compose the system-message prelude for a single LLM call.

    Pure data-in/data-out: every input is a method arg, no global state.
    The builder is cheap to instantiate; deployments typically construct
    one per :class:`~core.chat_service.ChatService` and reuse it.
    """

    templates: PromptTemplates = field(default_factory=lambda: DEFAULT_TEMPLATES)

    def build(
        self,
        *,
        system_override: str | None = None,
        memories: list[UserMemoryEntry] | None = None,
        hits: list[KnowledgeHit] | None = None,
    ) -> list[ChatMessage]:
        """Return the list of system messages to prepend before the user turn.

        Order (newest layer first, closer to the user turn):

        1. Persona / default system message — present iff
           ``system_override`` (or the template default) is non-empty.
        2. Long-term user memories — present iff ``memories`` is non-empty.
        3. Retrieved citation block — present iff ``hits`` is non-empty.

        A caller passing all-empty inputs gets ``[]`` so the legacy
        "no-system-prelude" code path is preserved.
        """
        out: list[ChatMessage] = []

        sys_text = system_override if system_override is not None else self.templates.system
        if sys_text:
            out.append(ChatMessage(role="system", content=sys_text))

        if memories:
            out.append(
                ChatMessage(
                    role="system",
                    content=_format_user_memories(self.templates.user_memory_intro, memories),
                )
            )

        if hits:
            out.append(
                ChatMessage(
                    role="system",
                    content=_format_citations(self.templates.citation_intro, hits),
                )
            )

        return out


# ---------------------------------------------------------------------------
# Rendering helpers (module-private — :class:`PromptBuilder` is the public API)
# ---------------------------------------------------------------------------


def _format_user_memories(intro: str, memories: list[UserMemoryEntry]) -> str:
    """Render long-term user memories as a numbered list under ``intro``.

    Reversed within the recent window so the oldest of the recent batch
    appears first — matches how humans read top-to-bottom.
    """
    lines = [intro, ""]
    for i, m in enumerate(reversed(memories), start=1):
        lines.append(f"{i}. {m.content}")
    return "\n".join(lines).rstrip()


def _format_citations(intro: str, hits: list[KnowledgeHit]) -> str:
    """Render retrieved hits as a numbered citation block under ``intro``.

    Numbering matches the rank order in ``hits`` so the UI can correlate
    ``[N]`` references back to the ``retrieval`` event payload.
    """
    lines = [intro, ""]
    for i, h in enumerate(hits, start=1):
        header = f"[{i}] {h.title or '(untitled)'}"
        if h.source:
            header += f"  ({h.source})"
        lines.append(header)
        lines.append(h.content.strip())
        lines.append("")
    return "\n".join(lines).rstrip()
