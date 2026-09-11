from __future__ import annotations

import os
import sys
from typing import TextIO

_FG = {
    "green": "32",
    "red": "31",
    "yellow": "33",
    "cyan": "36",
}

_STATUS_MARK = {
    "ok": "OK",
    "skipped": "--",
    "manual": "--",
    "warn": "!!",
    "missing": "!!",
    "error": "XX",
}

_STATUS_FG = {
    "ok": "green",
    "warn": "yellow",
    "missing": "yellow",
    "error": "red",
}


def color_enabled(stream: TextIO | None = None) -> bool:
    if os.environ.get("NO_COLOR", "").strip():
        return False
    if os.environ.get("ADHD_HUB_NO_COLOR", "").strip():
        return False
    target = stream if stream is not None else sys.stdout
    try:
        return bool(target.isatty())
    except Exception:
        return False


def style(
    text: str,
    *,
    fg: str | None = None,
    bold: bool = False,
    dim: bool = False,
    stream: TextIO | None = None,
) -> str:
    if not color_enabled(stream):
        return text
    parts: list[str] = []
    if bold:
        parts.append("1")
    if dim:
        parts.append("2")
    if fg and fg in _FG:
        parts.append(_FG[fg])
    if not parts:
        return text
    return f"\x1b[{';'.join(parts)}m{text}\x1b[0m"


def status_mark(status: str) -> str:
    return _STATUS_MARK.get(status, status)


def paint_status(
    status: str, mark: str | None = None, *, stream: TextIO | None = None
) -> str:
    label = mark if mark is not None else status_mark(status)
    fg = _STATUS_FG.get(status)
    if status in {"skipped", "manual"}:
        return style(label, dim=True, stream=stream)
    if fg:
        return style(label, fg=fg, bold=True, stream=stream)
    return label


def print_running(command: list[str], *, file: TextIO | None = None) -> None:
    target = file if file is not None else sys.stdout
    prefix = style("→ Running", dim=True, stream=target)
    print(f"{prefix}  {' '.join(command)}", file=target)
