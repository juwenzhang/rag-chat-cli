"""Model tag classification helpers."""

from __future__ import annotations

from typing import Literal

__all__ = ["classify_model_kind", "is_cloud_model_tag", "is_embedding_model_tag"]

_EMBEDDING_PREFIXES: tuple[str, ...] = (
    "bge-",
    "e5-",
    "gte-",
    "all-minilm",
    "instructor",
    "paraphrase-",
    "stella-",
    "text-embedding-",
    "jina-embed",
)


def is_embedding_model_tag(tag: str) -> bool:
    """Heuristic: is ``tag`` an embedding model rather than a chat model?"""
    t = tag.lower()
    if "embed" in t:
        return True
    leaf = t.rsplit("/", 1)[-1]
    return leaf.startswith(_EMBEDDING_PREFIXES)


def classify_model_kind(tag: str) -> Literal["chat", "embedding"]:
    return "embedding" if is_embedding_model_tag(tag) else "chat"


def is_cloud_model_tag(tag: str) -> bool:
    """Heuristic: an Ollama tag is ``cloud`` when it ends in ``-cloud``."""
    return tag.lower().endswith("-cloud")
