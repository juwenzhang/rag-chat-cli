"""Dump the current OpenAPI schema to ``docs/openapi.json``.

Usage::

    uv run python scripts/dump_openapi.py

The resulting file is committed so front-end code generators (Change 12+)
and docs tools can consume it without standing the service up. A CI check
can compare ``docs/openapi.json`` against a fresh ``create_app().openapi()``
to catch schema drift; that wiring lands with the observability change.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "openapi.json"


def main() -> int:
    # Make sure we import the checked-in code, not a site-packages copy.
    sys.path.insert(0, str(ROOT))

    # Inject safe defaults so create_app does not hit the real .env.
    os.environ.setdefault("APP_ENV", "dev")
    os.environ.setdefault("AUTH__JWT_SECRET", "openapi-dump-placeholder")

    from api.app import create_app

    app = create_app()
    schema = app.openapi()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(schema.get('paths', {}))} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
