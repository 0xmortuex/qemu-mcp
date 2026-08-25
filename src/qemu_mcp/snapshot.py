"""Snapshot tag validation and HMP command-line building.

QEMU has no native QMP savevm/loadvm - only the HMP monitor commands,
reachable over QMP via `human-monitor-command`. The tag becomes a token in
that command-line string, so instead of trying to escape/quote it safely
it's restricted to a plain identifier character set.
"""

from __future__ import annotations

import re

_TAG_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def validate_tag(tag: str) -> str:
    if not _TAG_RE.match(tag):
        raise ValueError(
            f"invalid snapshot tag {tag!r} - use only letters, digits, '.', '_', '-'"
        )
    return tag


def save_command_line(tag: str) -> str:
    return f"savevm {validate_tag(tag)}"


def load_command_line(tag: str) -> str:
    return f"loadvm {validate_tag(tag)}"


def delete_command_line(tag: str) -> str:
    return f"delvm {validate_tag(tag)}"
