"""Validate commit messages against the Angular/Conventional Commits shape."""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ALLOWED_TYPES = {
    "build",
    "chore",
    "ci",
    "docs",
    "feat",
    "fix",
    "perf",
    "refactor",
    "revert",
    "style",
    "test",
}

_PATTERN = re.compile(
    r"^(?P<type>[a-z]+)(?:\([a-z0-9._/-]+\))?(?P<breaking>!)?: (?P<subject>\S.{0,100})$"
)

_ALLOWED_PREFIXES = (
    "Merge ",
    "Revert ",
    "fixup! ",
    "squash! ",
)


def _first_non_comment_line(message: str) -> str:
    for line in message.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def validate_subject(subject: str) -> str | None:
    if not subject:
        return "commit message is empty"
    if subject.startswith(_ALLOWED_PREFIXES):
        return None
    match = _PATTERN.match(subject)
    if match is None:
        return "commit message must follow Angular style, e.g. feat(web): add model settings"
    commit_type = match.group("type")
    if commit_type not in _ALLOWED_TYPES:
        return f"unsupported commit type: {commit_type}"
    if subject.endswith("."):
        return "commit subject should not end with a period"
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_commit_msg.py <commit-msg-file>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    subject = _first_non_comment_line(path.read_text(encoding="utf-8"))
    error = validate_subject(subject)
    if error is None:
        return 0
    print(f"[commit-msg] {error}", file=sys.stderr)
    print("[commit-msg] allowed types: " + ", ".join(sorted(_ALLOWED_TYPES)), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
