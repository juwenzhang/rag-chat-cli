"""Contract tests for the LLMClient Protocol."""

from __future__ import annotations

from core.llm.client import ChatChunk, ChatMessage, LLMClient
from core.llm.ollama import OllamaClient


def test_chat_message_is_frozen() -> None:
    msg = ChatMessage(role="user", content="hi")
    assert msg.role == "user"
    assert msg.content == "hi"


def test_chat_chunk_defaults() -> None:
    chunk = ChatChunk(delta="hi")
    assert chunk.done is False
    assert chunk.usage is None


def test_fake_llm_is_llm_client(fake_llm_factory: type) -> None:
    fake = fake_llm_factory()
    assert isinstance(fake, LLMClient)


def test_ollama_client_is_llm_client() -> None:
    client = OllamaClient(
        base_url="http://localhost:11434",
        chat_model="m",
        embed_model="e",
    )
    assert isinstance(client, LLMClient)
    assert client.chat_model == "m"
    assert client.embed_model == "e"
