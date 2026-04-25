"""Unit tests for api.streaming.protocol."""

from __future__ import annotations

import pytest


def test_token_event_roundtrip() -> None:
    from api.streaming.protocol import TokenEvent, coerce_event

    evt = coerce_event({"type": "token", "delta": "hi"})
    assert isinstance(evt, TokenEvent)
    assert evt.delta == "hi"


def test_done_event_roundtrip() -> None:
    from api.streaming.protocol import DoneEvent, coerce_event

    evt = coerce_event({"type": "done", "duration_ms": 123, "usage": {"prompt": 4}})
    assert isinstance(evt, DoneEvent)
    assert evt.duration_ms == 123
    assert evt.usage == {"prompt": 4}


def test_error_event_roundtrip() -> None:
    from api.streaming.protocol import ErrorEvent, coerce_event

    evt = coerce_event({"type": "error", "code": "ABORTED", "message": "stop"})
    assert isinstance(evt, ErrorEvent)
    assert evt.code == "ABORTED"


def test_retrieval_event_maps_snippet() -> None:
    from api.streaming.protocol import RetrievalEvent, coerce_event

    evt = coerce_event(
        {
            "type": "retrieval",
            "hits": [
                {"snippet": "abc", "score": 0.9, "title": "doc1"},
                {"snippet": "def", "score": 0.3},
            ],
        }
    )
    assert isinstance(evt, RetrievalEvent)
    assert len(evt.hits) == 2
    assert evt.hits[0].title == "doc1"


def test_unknown_type_raises() -> None:
    from api.streaming.protocol import coerce_event

    with pytest.raises(Exception):  # pydantic ValidationError
        coerce_event({"type": "nope", "x": 1})
