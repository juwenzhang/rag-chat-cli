"""Model tag classification helpers."""

from __future__ import annotations

from typing import Literal

__all__ = [
    "classify_model_kind",
    "is_cloud_model_tag",
    "is_embedding_model_tag",
    "is_vision_model_tag",
]

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


def is_vision_model_tag(tag: str) -> bool:
    """Heuristic: is ``tag`` a vision / multimodal chat model?"""
    t = tag.lower()
    leaf = t.rsplit("/", 1)[-1]
    compact = leaf.replace("-", "").replace("_", "").replace(".", "")
    return any(
        marker in compact
        for marker in (
            "vision",
            "llava",
            "bakllava",
            "moondream",
            "minicpmv",
            "qwenvl",
            "qwen25vl",
            "qwen2vl",
            "geminivision",
            "gpt4v",
            "gpt4o",
        )
    )


def classify_model_kind(tag: str) -> Literal["chat", "embedding", "vision"]:
    if is_embedding_model_tag(tag):
        return "embedding"
    if is_vision_model_tag(tag):
        return "vision"
    return "chat"


def is_cloud_model_tag(tag: str) -> bool:
    """Heuristic: an Ollama tag is cloud-hosted when it uses cloud suffix syntax."""
    t = tag.strip().lower()
    return t.endswith(":cloud") or t.endswith("-cloud")
