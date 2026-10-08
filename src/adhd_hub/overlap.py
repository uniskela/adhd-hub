from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from adhd_hub.models import OverlapHit, OverlapResult, Project, Thread, ThreadStatus
from adhd_hub.work_identity import WorkSource, resolve_work_source

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


def normalize_goal(text: str | None) -> str:
    """Compare outcome identity without dropping punctuation, order or negation."""
    return " ".join(unicodedata.normalize("NFC", text or "").casefold().split())


def merge_blocked_reason(
    source: Thread,
    target: Thread,
    source_project: Project | None,
    target_project: Project | None,
) -> str | None:
    """Shared non-destructive policy; callers also check legacy forge mappings."""
    if source.id == target.id:
        return "same_thread"
    if source.merged_into or target.merged_into:
        return "already_merged"
    unfinished = {ThreadStatus.open, ThreadStatus.blocked}
    if source.status not in unfinished or target.status not in unfinished:
        return "unfinished_required"
    if not source.project_slug or source.project_slug != target.project_slug:
        return "different_projects"
    source_goal = normalize_goal(source.goal)
    target_goal = normalize_goal(target.goal)
    if not source_goal or not target_goal:
        return "goal_required"
    if source_goal != target_goal:
        return "distinct_outcomes"
    for thread, project in ((source, source_project), (target, target_project)):
        if resolve_work_source(project, thread) != WorkSource.local or any(
            (
                thread.external_provider,
                thread.external_host,
                thread.external_owner,
                thread.external_repo,
                thread.external_issue_number is not None,
                thread.external_updated_at,
                thread.external_fingerprint,
                thread.external_labels,
                thread.source_issue_url,
                thread.source_imported_at,
                thread.source_content_hash,
                thread.source_snapshot,
                thread.source_sync_state,
                thread.source_conflicts,
                thread.source_title_derived,
                thread.origin in {"forge-import", "forge-inbox"},
            )
        ):
            return "forge_authoritative"
    return None


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
                thread.goal or "",
                thread.focus or "",
                " ".join(thread.next_steps or []),
                thread.resume_step or "",
                thread.blocked_reason or "",
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

    # Substring / phrase hints — slug helps project routing but should not collapse
    # distinct outcomes inside the same project.
    q_l = query.lower()
    if thread.goal and thread.goal.lower() in q_l:
        score += 0.4
        reasons.append("goal_in_query")
    if thread.summary and thread.summary.lower() in q_l:
        score += 0.25
        reasons.append("title_in_query")
    if thread.project_slug and thread.project_slug.lower() in q_l:
        score += 0.2
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
            goal = normalize_goal(thread.goal)
            if goal and goal == normalize_goal(query):
                outcome = "same_outcome"
                evidence = ["goal_exact_match"]
            elif goal:
                outcome = "related"
                evidence = ["distinct_known_goal"]
            else:
                outcome = "uncertain"
                evidence = ["no_recorded_goal"]
            scored.append(
                OverlapHit(
                    thread=thread,
                    score=round(score, 4),
                    reason=reason,
                    outcome=outcome,
                    evidence=evidence,
                )
            )
    scored.sort(key=lambda h: (-h.score, h.thread.id))
    return OverlapResult(query=query, hits=scored[:limit])
