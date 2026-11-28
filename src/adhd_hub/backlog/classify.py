from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta
from itertools import combinations

from adhd_hub.backlog.models import (
    ClusterDestination,
    Disposition,
    ExistingThread,
    IssueKind,
    NewThread,
    ProtectionFlag,
    Recommendation,
    RecommendationItem,
    Relationship,
    ScanItem,
)
from adhd_hub.backlog.scanner import digest
from adhd_hub.models import Thread
from adhd_hub.overlap import check_overlap, jaccard, normalize_goal, tokenize

PROTECTED_LABELS = {"bug", "security", "enhancement", "pinned", "tracker", "release"}
SAFE_DISPOSITIONS = {Disposition.skip, Disposition.mirror, Disposition.reference}
HANDOFF = {
    IssueKind.review_checkpoint,
    IssueKind.implementation_checkpoint,
    IssueKind.continuity_handoff,
}
CHECKPOINTS = HANDOFF - {IssueKind.continuity_handoff}
_PREFIX = re.compile(r"^\[adhd\]\s*", re.IGNORECASE)
_VERSION = re.compile(r"^v?\d+\.\d+(?:\.\d+)?:\s*", re.IGNORECASE)
_REVIEW = re.compile(
    r"\b(?:ready for review|review (?:package|complete|checkpoint|round)|corrections?|r\d+)\b",
    re.IGNORECASE,
)
_IMPLEMENTATION = re.compile(
    r"\b(?:implementation|stage \d+|step \d+[a-z]?|poc ready)\b", re.IGNORECASE
)
_TRACKER = re.compile(r"\b(?:tracker|roadmap|umbrella)\b|^track\b|\b(?:migration|rollout) plan\b")
_SECURITY = re.compile(r"\b(?:cve|disclosure|vulnerabilit\w*|auth hardening|security)\b")
_RELEASE_VERSION = re.compile(r"\bv?\d+\.\d+")
_FINISHED = re.compile(r"\b(?:shipped|resolved|completed|implementation complete)\b")
_SERIES = re.compile(r"^(p\d+|(?:[\w-]+ )?finding #?\d+|isolated coordinator)\b")
_TAIL = re.compile(r"\s*\([^()]*\)\s*$")
_PUBLIC_KINDS = {
    IssueKind.security,
    IssueKind.public_bug,
    IssueKind.feature_request,
    IssueKind.canonical_tracker,
    IssueKind.release,
}


def _kind(item: ScanItem, title: str, labels: set[str], cited: int) -> IssueKind:
    if "security" in labels or _SECURITY.search(title) or item.security_mention:
        return IssueKind.security
    if "bug" in labels or re.match(r"^bug\s*:", title):
        return IssueKind.public_bug
    release_title = bool(re.search(r"\brelease\b", title))
    if (
        {"feature", "enhancement", "feature request"} & labels
        or (_VERSION.match(title) and not release_title)
        or re.match(r"^(?:feature(?: request)?|enhancement)\s*:", title)
    ):
        return IssueKind.feature_request
    if {"release", "release-please"} & labels or (release_title and _RELEASE_VERSION.search(title)):
        return IssueKind.release
    if (
        "tracker" in labels
        or _TRACKER.search(title)
        or item.tracked_tasks
        or cited >= 3
        or (ProtectionFlag.pinned in item.protection_flags)
    ):
        return IssueKind.canonical_tracker
    if (
        item.inbox_match
        and item.structured.model_dump(exclude_defaults=True)
        and item.author_role == "trusted"
        and (ProtectionFlag.external_participants not in item.protection_flags)
    ):
        if _REVIEW.search(title):
            return IssueKind.review_checkpoint
        if _IMPLEMENTATION.search(title):
            return IssueKind.implementation_checkpoint
        return IssueKind.continuity_handoff
    return IssueKind.unknown


def _stem(title: str) -> str:
    normalized = _TAIL.sub("", _VERSION.sub("", _PREFIX.sub("", title.casefold()).strip()))
    normalized = _REVIEW.sub("", normalized)
    normalized = re.sub(
        r"\b(?:implementation (?=stage|step)|stage \d+|step \d+[a-z]?|poc ready)\b", "", normalized
    )
    return re.sub(r"[^\w#]+", " ", normalized).strip()


def _protect(item: ScanItem, now: datetime, cited: int):
    title = _PREFIX.sub("", item.title).strip().casefold()
    labels = {label.casefold() for label in item.labels}
    item.kind = _kind(item, title, labels, cited)
    flags = set(item.protection_flags)
    if item.kind in _PUBLIC_KINDS:
        flags.add(ProtectionFlag(item.kind.value))
    if labels & PROTECTED_LABELS:
        flags.add(ProtectionFlag.protected_label)
    if item.source_conflict:
        flags.add(ProtectionFlag.source_conflict)
    if item.updated_at and now - item.updated_at <= timedelta(days=7):
        flags.add(ProtectionFlag.recently_active)
    item.protection_flags = sorted(flags)
    item.stale = bool(item.updated_at and now - item.updated_at >= timedelta(days=90))
    # Review-complete is a checkpoint marker, not evidence the outcome shipped.
    item.completed = item.state == "closed" or bool(_FINISHED.search(title))


def _thread_candidates(
    item: ScanItem,
    threads: list[Thread],
    exact_by_goal: dict[str, str],
) -> tuple[list[str], str | None]:
    query = item.structured.goal or item.title
    if not query.strip():
        return [], None
    result = check_overlap(query, threads, min_score=0.08, limit=5)
    exact = exact_by_goal.get(item.goal_key) if item.goal_key else None
    candidates = [hit.thread.id for hit in result.hits if hit.thread.id != exact]
    return (([exact] if exact else []) + candidates)[:5], exact


class _Groups:
    def __init__(self, numbers):
        self.parents = {number: number for number in numbers}

    def root(self, number):
        while self.parents[number] != number:
            self.parents[number] = self.parents[self.parents[number]]
            number = self.parents[number]
        return number

    def union(self, left, right):
        first, second = sorted((self.root(left), self.root(right)))
        self.parents[second] = first
        return first


def classify(
    items: list[ScanItem],
    *,
    now: datetime,
    local_threads: list[Thread] | None = None,
) -> list[RecommendationItem]:
    by_number = {item.identity.number: item.model_copy(deep=True) for item in items}
    if (
        len(
            {
                (i.identity.provider, i.identity.host, i.identity.owner, i.identity.repo)
                for i in items
            }
        )
        > 1
    ):
        raise ValueError("mixed_scan_repositories")
    numbers = sorted(by_number)
    cited = Counter(
        ref for number, item in by_number.items() for ref in item.references if ref != number
    )
    for number in numbers:
        _protect(by_number[number], now, cited[number])
    stems = {number: _stem(item.title) for number, item in by_number.items()}
    keys = {number: _SERIES.match(stem) for number, stem in stems.items()}
    tokens = {number: tokenize(stem) for number, stem in stems.items()}
    goals = {number: item.goal_key for number, item in by_number.items()}
    refs = {number: set(item.references) for number, item in by_number.items()}
    consolidation = _Groups(numbers)
    workstreams = _Groups(numbers)
    relationship = {}
    evidence = {}
    related = set()
    goal_groups = {}
    for n in numbers:
        if goals[n] and by_number[n].kind in HANDOFF:
            first = goal_groups.setdefault(goals[n], n)
            consolidation.union(first, n)
            if n != first:
                for member in (first, n):
                    relationship[member] = Relationship.same_outcome
                    evidence[member] = ["goal_exact_match"]

    cluster_goals = {consolidation.root(n): goals[n] for n in numbers}
    for left, right in combinations(numbers, 2):
        a, b = by_number[left], by_number[right]
        same_key = keys[left] and keys[right] and keys[left][0] == keys[right][0]
        score = jaccard(tokens[left], tokens[right])
        if not (same_key or score >= 0.6 or right in refs[left] or left in refs[right]):
            continue
        left_root, right_root = consolidation.root(left), consolidation.root(right)
        left_goal, right_goal = cluster_goals[left_root], cluster_goals[right_root]
        if (
            a.kind in HANDOFF
            and b.kind in HANDOFF
            and (a.kind in CHECKPOINTS or b.kind in CHECKPOINTS)
            and stems[left]
            and stems[left] == stems[right]
            and (not left_goal or not right_goal or left_goal == right_goal)
        ):
            root = consolidation.union(left, right)
            cluster_goals[root] = left_goal or right_goal
            for number in (left, right):
                if by_number[number].kind in CHECKPOINTS and number not in relationship:
                    relationship[number] = Relationship.checkpoint_of
                    evidence[number] = ["title_series_match", "checkpoint_marker"]
        elif left_root != right_root:
            workstreams.union(left, right)
            related.update((left, right))
            for number in (left, right):
                evidence.setdefault(
                    number,
                    [
                        "reference_edge"
                        if right in refs[left] or left in refs[right]
                        else f"series:{keys[left][0]}"
                        if same_key
                        else f"token_overlap={score:.2f}",
                    ],
                )

    groups = {}
    for number in numbers:
        groups.setdefault(consolidation.root(number), []).append(number)
        if consolidation.root(number) != number:
            workstreams.union(consolidation.root(number), number)
    threads = local_threads or []
    exact_by_goal = {}
    for thread in sorted(threads, key=lambda thread: thread.id):
        goal = normalize_goal(thread.goal)
        if goal:
            exact_by_goal.setdefault(digest(goal), thread.id)
    recommended = {}
    for group, members in groups.items():
        holder = max(
            members,
            key=lambda n: (
                not by_number[n].protection_flags and not by_number[n].linked_thread_id,
                by_number[n].kind not in CHECKPOINTS,
                by_number[n].updated_at.timestamp() if by_number[n].updated_at else 0,
                n,
            ),
        )
        goal_member = holder if goals[holder] else next((n for n in members if goals[n]), holder)
        candidates, exact = _thread_candidates(by_number[goal_member], threads, exact_by_goal)
        cluster_key = holder if len(members) > 1 else None
        group_related = any(n in related for n in members)
        for n in members:
            item = by_number[n]
            relation = relationship.get(
                n,
                Relationship.related_workstream
                if group_related
                else Relationship.distinct
                if goals[n] and item.kind in HANDOFF
                else Relationship.uncertain,
            )
            reasons = list(evidence.get(n, []))
            disposition = Disposition.skip
            destination = None
            if item.protection_flags:
                reasons.append("protected")
            elif item.linked_thread_id:
                reasons.append("already_mirrored")
            elif cluster_key:
                disposition = Disposition.consolidate
                destination = (
                    ExistingThread(kind="existing_thread", thread_id=exact)
                    if exact
                    else NewThread(kind="new_thread")
                    if n == holder
                    else ClusterDestination(kind="cluster", issue_number=holder)
                )
            elif exact and item.kind in HANDOFF:
                disposition = Disposition.consolidate
                destination = ExistingThread(kind="existing_thread", thread_id=exact)
                relation = Relationship.same_outcome
                reasons.append("thread_goal_exact_match")
            elif group_related:
                disposition = Disposition.reference
            elif item.kind in HANDOFF:
                disposition = Disposition.migrate
                destination = NewThread(kind="new_thread")
            else:
                reasons.append("insufficient_evidence")
            if item.completed:
                reasons.append("possibly_completed")
            if item.stale:
                reasons.append("stale_activity")
            recommended[n] = RecommendationItem(
                issue=item,
                deterministic=Recommendation(
                    disposition=disposition,
                    destination=destination,
                    relationship=relation,
                    evidence=reasons,
                    cluster_key=cluster_key,
                    workstream_key=workstreams.root(group) if group_related else None,
                    candidate_thread_ids=candidates,
                ),
            )
    return [recommended[n] for n in numbers]
