"""Document upload + reindex stub + search stub."""

from __future__ import annotations


async def test_upload_document(client: object, auth_headers: dict[str, str]) -> None:
    r = await client.post(  # type: ignore[attr-defined]
        "/knowledge/documents",
        headers=auth_headers,
        json={
            "source": "manual://first",
            "title": "Hello",
            "content": "# Hello\n\nWorld.",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["source"] == "manual://first"


async def test_list_documents_paginates(client: object, auth_headers: dict[str, str]) -> None:
    # Upload 3 docs, fetch page 1 with size 2.
    for i in range(3):
        r = await client.post(  # type: ignore[attr-defined]
            "/knowledge/documents",
            headers=auth_headers,
            json={
                "source": f"manual://{i}",
                "title": f"doc-{i}",
                "content": "stuff",
            },
        )
        assert r.status_code == 201

    r = await client.get(  # type: ignore[attr-defined]
        "/knowledge/documents?page=1&size=2", headers=auth_headers
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


async def test_reindex_returns_202(client: object, auth_headers: dict[str, str]) -> None:
    r = await client.post(  # type: ignore[attr-defined]
        "/knowledge/documents:reindex", headers=auth_headers
    )
    assert r.status_code == 202
    assert r.json() == {"ok": True}


async def test_search_empty_until_change_9(client: object, auth_headers: dict[str, str]) -> None:
    r = await client.get(  # type: ignore[attr-defined]
        "/knowledge/search?q=anything", headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json() == []
