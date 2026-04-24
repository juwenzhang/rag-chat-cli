"""FileKnowledgeBase placeholder behaviour."""

from __future__ import annotations

import pytest

from core.knowledge.base import FileKnowledgeBase, KnowledgeBase


def test_file_kb_satisfies_protocol() -> None:
    kb = FileKnowledgeBase()
    assert isinstance(kb, KnowledgeBase)


@pytest.mark.asyncio
async def test_search_returns_empty_until_p7() -> None:
    kb = FileKnowledgeBase()
    hits = await kb.search("anything", top_k=4)
    assert hits == []
