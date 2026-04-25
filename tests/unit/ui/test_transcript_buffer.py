"""TranscriptBuffer behaviour — append, streaming, cap."""

from __future__ import annotations

from ui.transcript import Line, TranscriptBuffer


def test_add_user_and_system_lines() -> None:
    buf = TranscriptBuffer()
    buf.add_user("hi")
    buf.add_system("ok")
    lines = buf.lines()
    assert [(line.role, line.text) for line in lines] == [("user", "hi"), ("system", "ok")]


def test_streaming_assistant_accumulates_then_commits() -> None:
    buf = TranscriptBuffer()
    buf.start_assistant()
    buf.append_to_assistant("hel")
    buf.append_to_assistant("lo")
    # Mid-stream lines() should expose the in-flight chunk verbatim.
    mid = buf.lines()
    assert mid[-1].role == "assistant"
    assert mid[-1].text == "hello"
    buf.end_assistant(duration_ms=42)
    final = buf.lines()
    # end_assistant rich-renders the assistant line, so .text is now an
    # ANSI-padded string. We only assert structure + that the original
    # content survives somewhere inside the rendered output.
    assert len(final) == 2
    assert final[0].role == "assistant"
    assert final[0].rendered is True
    assert "hello" in final[0].text
    assert final[1] == Line(role="system", text="done in 42 ms")


def test_writing_new_line_during_stream_flushes_assistant() -> None:
    """Sanity: if a system line arrives mid-stream, we don't lose tokens."""
    buf = TranscriptBuffer()
    buf.start_assistant()
    buf.append_to_assistant("partial")
    buf.add_error("net", "boom")  # forces flush
    out = [(line.role, line.text) for line in buf.lines()]
    assert out == [("assistant", "partial"), ("error", "net: boom")]


def test_cap_drops_oldest() -> None:
    buf = TranscriptBuffer(max_lines=3)
    for i in range(5):
        buf.add_system(f"line-{i}")
    out = [line.text for line in buf.lines()]
    assert out == ["line-2", "line-3", "line-4"]
