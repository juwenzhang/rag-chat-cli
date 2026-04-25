"""AccessLog query-string sanitization.

Keeps the public ``AccessLogMiddleware`` unit-level testable: no ASGI
client, no DB — just feeds ``_sanitize_query`` a few URLs and asserts the
scrubbing shape.
"""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("", ""),
        ("a=1&b=2", "a=1&b=2"),
        ("token=abc123", "token=%2A%2A%2A"),  # %2A%2A%2A == "***"
        ("foo=bar&access_token=abc", "foo=bar&access_token=%2A%2A%2A"),
        ("TOKEN=ABC", "TOKEN=%2A%2A%2A"),  # case-insensitive
        ("refresh_token=abc&x=y", "refresh_token=%2A%2A%2A&x=y"),
        ("password=p%40ss", "password=%2A%2A%2A"),
    ],
)
def test_sanitize_query(raw: str, want: str) -> None:
    from api.middleware.logging import _sanitize_query

    assert _sanitize_query(raw) == want


def test_sanitize_keeps_empty_values() -> None:
    from api.middleware.logging import _sanitize_query

    # keep_blank_values is on → "token=" still gets redacted.
    assert _sanitize_query("token=") == "token=%2A%2A%2A"
