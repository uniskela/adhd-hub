"""Local-first global search across threads, projects, and wiki progress."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from adhd_hub.clarity import scrub_scan_text
from adhd_hub.models import Project, Thread, ThreadStatus

SearchKind = Literal["thread", "project", "wiki"]

MIN_QUERY_LEN = 2
MAX_QUERY_LEN = 200
DEFAULT_LIMIT = 25
MAX_LIMIT = 50
SNIPPET_RADIUS = 80
WIKI_READ_CAP = 200_000


@dataclass(slots=True)
class SearchHit:
    kind: SearchKind
    id: str
    title: str
    snippet: str | None
    project_slug: str | None
    status: str | None
    score: float
    updated_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.id,
            "title": self.title,
            "snippet": self.snippet or None,
            "project_slug": self.project_slug,
            "status": self.status,
            "score": round(self.score, 3),
        }


def normalize_query(raw: str | None) -> str:
    text = " ".join(str(raw or "").split()).strip()
    if len(text) > MAX_QUERY_LEN:
        text = text[:MAX_QUERY_LEN].rstrip()
    return text


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(MAX_LIMIT, int(limit)))


def _snippet(haystack: str, needle: str) -> str | None:
    """Window around the match on the original string (case-insensitive)."""
    if not haystack:
        return None
    match = re.search(re.escape(needle), haystack, flags=re.IGNORECASE)
    if match is None:
        return scrub_scan_text(haystack[: SNIPPET_RADIUS * 2])
    start = max(0, match.start() - SNIPPET_RADIUS)
    end = min(len(haystack), match.end() + SNIPPET_RADIUS)
    chunk = haystack[start:end].strip()
    if start > 0:
        chunk = "…" + chunk
    if end < len(haystack):
        chunk = chunk + "…"
    return scrub_scan_text(chunk)


def _field_score(query: str, value: str | None, *, exact: float, prefix: float, sub: float) -> float:
    text = (value or "").strip()
    if not text:
        return 0.0
    q = query.casefold()
    t = text.casefold()
    if t == q:
        return exact
    if t.startswith(q):
        return prefix
    if q in t:
        return sub
    return 0.0


def score_thread(query: str, thread: Thread) -> tuple[float, str | None]:
    parts: list[tuple[float, str | None]] = [
        (_field_score(query, thread.summary, exact=100, prefix=55, sub=40), thread.summary),
        (_field_score(query, thread.goal, exact=95, prefix=50, sub=35), thread.goal),
        (_field_score(query, thread.focus, exact=90, prefix=45, sub=30), thread.focus),
        (_field_score(query, thread.resume_step, exact=85, prefix=40, sub=28), thread.resume_step),
        (_field_score(query, thread.blocked_reason, exact=70, prefix=35, sub=22), thread.blocked_reason),
        (_field_score(query, thread.project_slug, exact=90, prefix=50, sub=25), thread.project_slug),
        (_field_score(query, thread.id, exact=80, prefix=40, sub=15), thread.id),
    ]
    for step in thread.next_steps or []:
        parts.append((_field_score(query, step, exact=80, prefix=40, sub=25), step))
    best = max(parts, key=lambda p: p[0])
    if best[0] <= 0:
        return 0.0, None
    # Open/blocked slightly ahead of done when include_done mixes them.
    status_boost = 2.0 if thread.status in (ThreadStatus.open, ThreadStatus.blocked) else 0.0
    return best[0] + status_boost, _snippet(best[1] or thread.summary, query)


def score_project(query: str, project: Project) -> tuple[float, str | None]:
    parts: list[tuple[float, str | None]] = [
        (_field_score(query, project.title, exact=100, prefix=55, sub=40), project.title),
        (_field_score(query, project.slug, exact=95, prefix=50, sub=30), project.slug),
        (_field_score(query, project.description, exact=70, prefix=35, sub=25), project.description),
    ]
    for tag in project.tags or []:
        parts.append((_field_score(query, tag, exact=85, prefix=45, sub=30), tag))
    best = max(parts, key=lambda p: p[0])
    if best[0] <= 0:
        return 0.0, None
    return best[0], _snippet(best[1] or project.title, query)


def score_wiki(query: str, body: str) -> tuple[float, str | None]:
    if not body or query.casefold() not in body.casefold():
        return 0.0, None
    return 18.0, _snippet(body, query)


def _recency_key(hit: SearchHit) -> float:
    if hit.updated_at is None:
        return 0.0
    return hit.updated_at.timestamp()


def rank_hits(hits: Iterable[SearchHit], *, limit: int) -> list[SearchHit]:
    ordered = sorted(
        (h for h in hits if h.score > 0),
        key=lambda h: (-h.score, -_recency_key(h), h.kind, h.title.casefold()),
    )
    return ordered[:limit]


def search_threads(
    query: str,
    threads: Iterable[Thread],
    *,
    include_done: bool,
) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for thread in threads:
        if thread.merged_into:
            continue
        if not include_done and thread.status not in (ThreadStatus.open, ThreadStatus.blocked):
            continue
        score, snippet = score_thread(query, thread)
        if score <= 0:
            continue
        hits.append(
            SearchHit(
                kind="thread",
                id=thread.id,
                title=thread.summary,
                snippet=snippet,
                project_slug=thread.project_slug,
                status=thread.status.value,
                score=score,
                updated_at=thread.updated_at,
            )
        )
    return hits


def search_projects(query: str, projects: Iterable[Project]) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for project in projects:
        score, snippet = score_project(query, project)
        if score <= 0:
            continue
        hits.append(
            SearchHit(
                kind="project",
                id=project.slug,
                title=project.title,
                snippet=snippet,
                project_slug=project.slug,
                status="archived" if project.archived_at else "active",
                score=score,
                updated_at=project.updated_at,
            )
        )
    return hits


def search_wiki_bodies(
    query: str, bodies: Iterable[tuple[str, str, datetime | None]]
) -> list[SearchHit]:
    """bodies: (slug, markdown, updated_at hint)."""
    hits: list[SearchHit] = []
    for slug, body, updated_at in bodies:
        capped = body if len(body) <= WIKI_READ_CAP else body[:WIKI_READ_CAP]
        score, snippet = score_wiki(query, capped)
        if score <= 0:
            continue
        hits.append(
            SearchHit(
                kind="wiki",
                id=slug,
                title=f"{slug} progress",
                snippet=snippet,
                project_slug=slug,
                status=None,
                score=score,
                updated_at=updated_at,
            )
        )
    return hits
