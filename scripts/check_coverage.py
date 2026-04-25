#!/usr/bin/env python
"""Coverage gate for the project.

Reads ``coverage.xml`` (produced by ``pytest --cov --cov-report=xml``) and
enforces two thresholds:

* **total**  — overall line-rate  (default 85, per AGENTS.md §12)
* **core**   — line-rate aggregated over files under ``core/`` (default 90)

Thresholds can be tuned via environment variables to enable
"ratchet up" behaviour as the project matures::

    COV_TOTAL_MIN=80 COV_CORE_MIN=75 python scripts/check_coverage.py

In ``--soft`` mode the script only **reports** the numbers (exit 0 regardless);
used by ``make test-cov``.  The strict form (``make test-cov-strict``) omits
the flag and exits non-zero on breach.

Only the standard library is used so the script can run in any venv that has
no project dependencies installed.
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_TOTAL_MIN = float(os.environ.get("COV_TOTAL_MIN", "85"))
DEFAULT_CORE_MIN = float(os.environ.get("COV_CORE_MIN", "90"))
REPORT_PATH = Path(os.environ.get("COVERAGE_XML", "coverage.xml"))


def _parse_line_rate(elem: ET.Element) -> float:
    raw = elem.attrib.get("line-rate")
    if raw is None:
        return 0.0
    return float(raw) * 100.0


def _aggregate_prefix(root: ET.Element, prefix: str) -> float:
    """Aggregate hit/miss line counts for all ``class`` elements whose filename
    starts with *prefix*, returning a percentage."""
    hits = 0
    total = 0
    for cls in root.iter("class"):
        filename = cls.attrib.get("filename", "")
        if not filename.startswith(prefix):
            continue
        for line in cls.iter("line"):
            total += 1
            if int(line.attrib.get("hits", "0")) > 0:
                hits += 1
    if total == 0:
        return 100.0  # nothing to cover → treat as pass
    return hits / total * 100.0


def main() -> int:
    soft = "--soft" in sys.argv[1:]

    if not REPORT_PATH.exists():
        print(f"[coverage-gate] {REPORT_PATH} not found — did pytest --cov run?")
        return 0 if soft else 1

    tree = ET.parse(REPORT_PATH)
    root = tree.getroot()
    total = _parse_line_rate(root)
    core = _aggregate_prefix(root, "core/")

    print(f"[coverage-gate] total={total:.1f}%  (target ≥ {DEFAULT_TOTAL_MIN:g})")
    print(f"[coverage-gate] core/={core:.1f}%  (target ≥ {DEFAULT_CORE_MIN:g})")

    failed = []
    if total < DEFAULT_TOTAL_MIN:
        failed.append(f"total {total:.1f}% < {DEFAULT_TOTAL_MIN:g}%")
    if core < DEFAULT_CORE_MIN:
        failed.append(f"core/ {core:.1f}% < {DEFAULT_CORE_MIN:g}%")

    if not failed:
        print("[coverage-gate] OK")
        return 0

    for f in failed:
        print(f"[coverage-gate] FAIL: {f}")

    if soft:
        print("[coverage-gate] soft mode → exiting 0 (warnings only)")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
