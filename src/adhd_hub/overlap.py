from __future__ import annotations

import re
from pathlib import Path

from adhd_hub.models import OverlapHit, OverlapResult, Thread

_STOP = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "have",
    "will",
    "just",
    "into",
    "about",
    "your",
    "what",
    "when",
    "where",
    "which",
    "while",
    "there",
    "their",
    "then",
    "than",
    "them",
    "they",
    "been",
    "were",
    "was",
    "are",
    "but",
    "not",
    "you",
    "all",
    "can",
    "her",
    "his",
    "she",
    "him",
    "our",
    "out",
    "get",
    "got",
    "has",
    "had",
    "how",
    "who",
    "why",
    "any",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "only",
    "own",
    "same",
    "too",
    "very",
    "also",
    "like",
    "need",
    "want",
    "make",
    "made",
    "using",
    "use",
    "used",
}


def tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9][a-z0-9\-_/]{2,}", text.lower())
    return {w for w in words if w not in _STOP}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def path_boost(query: str, workspace_path: str | None) -> float:
    if not workspace_path:
        return 0.0
    q = tokenize(query)
    p = tokenize(workspace_path.replace("\\", "/").split("/")[-1])
    # Also compare full path tokens
    p |= tokenize(workspace_path.replace("\\", "/"))
    return 0.25 * jaccard(q, p)


def score_thread(query: str, thread: Thread) -> tuple[float, str]:
    q_tokens = tokenize(query)
    blob = " ".join(
        filter(
            None,
            [
                thread.summary,
                thread.project_slug or "",
                thread.workspace_path or "",
                thread.source_tool or "",
            ],
        )
    )
    t_tokens = tokenize(blob)
    score = jaccard(q_tokens, t_tokens)
    reasons: list[str] = []
    if score > 0:
        reasons.append(f"token_overlap={score:.2f}")

    # Substring / phrase hints
    q_l = query.lower()
    if thread.project_slug and thread.project_slug.lower() in q_l:
        score += 0.35
        reasons.append("slug_in_query")
    if thread.workspace_path:
        name = Path(thread.workspace_path).name.lower()
        if name and name in q_l:
            score += 0.3
            reasons.append("workspace_name")
    boost = path_boost(query, thread.workspace_path)
    if boost:
        score += boost
        reasons.append(f"path_boost={boost:.2f}")

    # Shared distinctive tokens (length > 4)
    shared = {t for t in (q_tokens & t_tokens) if len(t) > 4}
    if len(shared) >= 2:
        score += 0.15
        reasons.append(f"shared={','.join(sorted(shared)[:5])}")

    return score, "; ".join(reasons) if reasons else "weak"


def check_overlap(
    query: str,
    threads: list[Thread],
    *,
    limit: int = 5,
    min_score: float = 0.08,
) -> OverlapResult:
    scored: list[OverlapHit] = []
    for thread in threads:
        score, reason = score_thread(query, thread)
        if score >= min_score:
            scored.append(OverlapHit(thread=thread, score=round(score, 4), reason=reason))
    scored.sort(key=lambda h: h.score, reverse=True)
    return OverlapResult(query=query, hits=scored[:limit])
