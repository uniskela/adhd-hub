from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from adhd_hub.indexer.patterns import (
    clean_summary,
    looks_like_command,
    looks_like_question,
    matches_task,
)


def _read_jsonl(path: Path, max_bytes: int = 1024 * 1024) -> list[dict[str, Any]]:
    try:
        if path.stat().st_size > max_bytes:
            return []
    except OSError:
        return []
    lines: list[dict[str, Any]] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for line in raw.splitlines():
        t = line.strip()
        if not t:
            continue
        try:
            obj = json.loads(t)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            lines.append(obj)
    return lines


def _extract_text_blocks(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    return ""


def user_texts_claude(entries: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for entry in entries:
        if entry.get("type") != "user":
            continue
        msg = entry.get("message") or {}
        if msg.get("role") and msg.get("role") != "user":
            continue
        text = _extract_text_blocks(msg.get("content", entry.get("content", "")))
        text = text.strip()
        if text and not looks_like_command(text):
            out.append(text)
    return out


def user_texts_cursor(entries: list[dict[str, Any]]) -> list[str]:
    """Best-effort Cursor agent-transcript JSONL (role/type vary by version)."""
    out: list[str] = []
    for entry in entries:
        role = (entry.get("role") or entry.get("type") or "").lower()
        if role not in {"user", "human"}:
            # Nested message
            msg = entry.get("message")
            if isinstance(msg, dict):
                role = (msg.get("role") or "").lower()
                if role != "user":
                    continue
                text = _extract_text_blocks(msg.get("content", ""))
            else:
                continue
        else:
            text = _extract_text_blocks(
                entry.get("content") or entry.get("text") or entry.get("message") or ""
            )
        text = text.strip() if isinstance(text, str) else ""
        if text and not looks_like_command(text):
            out.append(text)
    return out


def user_texts_codex(entries: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for entry in entries:
        et = (entry.get("type") or entry.get("kind") or "").lower()
        role = (entry.get("role") or "").lower()
        if et not in {"user_message", "message"} and role != "user":
            continue
        content: Any = entry.get("content") or entry.get("text")
        if content is None:
            msg = entry.get("message")
            if isinstance(msg, dict):
                content = msg.get("content")
            elif isinstance(msg, str):
                content = msg
        text = _extract_text_blocks(content or "")
        text = text.strip()
        if text and not looks_like_command(text):
            out.append(text)
    return out


def candidates_from_texts(texts: Iterable[str]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if len(text) < 12 or len(text) > 600:
            continue
        if not matches_task(text):
            continue
        summary = clean_summary(text)
        if summary in seen:
            continue
        seen.add(summary)
        found.append(summary)
    return found


def _assistant_texts(entries: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for entry in entries:
        role = (entry.get("role") or entry.get("type") or "").lower()
        msg = entry.get("message")
        if role in {"assistant", "ai", "model"} or (
            isinstance(msg, dict) and (msg.get("role") or "").lower() == "assistant"
        ):
            if isinstance(msg, dict):
                text = _extract_text_blocks(msg.get("content", ""))
            else:
                text = _extract_text_blocks(
                    entry.get("content") or entry.get("text") or ""
                )
            text = text.strip() if isinstance(text, str) else ""
            if text and not looks_like_command(text):
                out.append(text)
        elif entry.get("type") == "assistant":
            text = _extract_text_blocks(
                (entry.get("message") or {}).get("content", entry.get("content", ""))
            )
            text = text.strip() if isinstance(text, str) else ""
            if text:
                out.append(text)
    return out


def pending_reply_from_entries(entries: list[dict[str, Any]]) -> str | None:
    """If the transcript ends on an assistant question with no user reply, capture it."""
    if not entries:
        return None
    # Walk from end: find last meaningful message role
    last_user_idx = -1
    last_asst_idx = -1
    last_asst_text = ""
    for i, entry in enumerate(entries):
        role = (entry.get("role") or entry.get("type") or "").lower()
        msg = entry.get("message") if isinstance(entry.get("message"), dict) else {}
        mrole = (msg.get("role") or "").lower() if msg else ""
        if role in {"user", "human"} or mrole == "user" or entry.get("type") == "user":
            last_user_idx = i
        if role in {"assistant", "ai", "model"} or mrole == "assistant" or entry.get(
            "type"
        ) == "assistant":
            last_asst_idx = i
            if msg:
                last_asst_text = _extract_text_blocks(msg.get("content", ""))
            else:
                last_asst_text = _extract_text_blocks(
                    entry.get("content") or entry.get("text") or ""
                )
    if last_asst_idx > last_user_idx and looks_like_question(last_asst_text or ""):
        return clean_summary(f"Pending reply: {last_asst_text}")
    return None


def walk_jsonl(root: Path) -> list[Path]:
    if not root or not root.expanduser().exists():
        return []
    root = root.expanduser()
    files: list[Path] = []
    for path in root.rglob("*.jsonl"):
        if path.is_file():
            files.append(path)
    files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return files


def parse_file_with_origins(path: Path, tool: str) -> list[dict[str, str]]:
    entries = _read_jsonl(path)
    if tool == "claude":
        texts = user_texts_claude(entries)
    elif tool == "codex":
        texts = user_texts_codex(entries)
    else:
        texts = user_texts_cursor(entries)
    items: list[dict[str, str]] = [
        {"summary": s, "origin": "indexer"} for s in candidates_from_texts(texts)
    ]
    pending = pending_reply_from_entries(entries)
    if pending:
        items.append({"summary": pending, "origin": "pending-reply"})
    # Unanswered user questions that look like open decisions
    for text in texts[-5:]:
        if looks_like_question(text) and matches_task(text):
            items.append(
                {
                    "summary": clean_summary(f"Open question: {text}"),
                    "origin": "question",
                }
            )
            break
    return items


def parse_claude_file(path: Path) -> list[str]:
    return [i["summary"] for i in parse_file_with_origins(path, "claude") if i["origin"] == "indexer"]


def parse_cursor_file(path: Path) -> list[str]:
    return [i["summary"] for i in parse_file_with_origins(path, "cursor") if i["origin"] == "indexer"]


def parse_codex_file(path: Path) -> list[str]:
    return [i["summary"] for i in parse_file_with_origins(path, "codex") if i["origin"] == "indexer"]
