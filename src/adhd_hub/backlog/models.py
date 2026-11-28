from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

VERSION = 1
IssueNumber = Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)]
ShortText = Annotated[str, Field(max_length=160)]
ContinuityText = Annotated[str, Field(max_length=300)]
NextStep = Annotated[str, Field(max_length=200)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IssueKind(StrEnum):
    security = "security"
    public_bug = "public_bug"
    feature_request = "feature_request"
    release = "release"
    canonical_tracker = "canonical_tracker"
    review_checkpoint = "review_checkpoint"
    implementation_checkpoint = "implementation_checkpoint"
    continuity_handoff = "continuity_handoff"
    unknown = "unknown"


class ProtectionFlag(StrEnum):
    external_author = "external_author"
    external_participants = "external_participants"
    linked_pull_request = "linked_pull_request"
    pinned = "pinned"
    milestone = "milestone"
    assigned_other = "assigned_other"
    security = "security"
    public_bug = "public_bug"
    feature_request = "feature_request"
    release = "release"
    canonical_tracker = "canonical_tracker"
    recently_active = "recently_active"
    locked = "locked"
    protected_label = "protected_label"
    protected_issue = "protected_issue"
    source_conflict = "source_conflict"
    incomplete_read = "incomplete_read"


class Disposition(StrEnum):
    mirror = "mirror"
    migrate = "migrate"
    consolidate = "consolidate"
    reference = "reference"
    skip = "skip"


class Relationship(StrEnum):
    same_outcome = "same_outcome"
    checkpoint_of = "checkpoint_of"
    related_workstream = "related_workstream"
    distinct = "distinct"
    uncertain = "uncertain"


class ScanRequest(Contract):
    project_slug: Annotated[str, Field(min_length=1, max_length=128)]
    selector: Literal["all_open", "adhd_inbox", "labels", "assigned_to_me"] = "all_open"
    include_closed: bool = False


class Repository(Contract):
    provider: Literal["github", "gitea"]
    host: str
    owner: str
    repo: str


class SourceIdentity(Repository):
    number: IssueNumber


class Continuity(Contract):
    goal: ContinuityText | None = None
    focus: ContinuityText | None = None
    next_steps: Annotated[list[NextStep], Field(max_length=3)] = Field(default_factory=list)
    blocked_reason: ContinuityText | None = None
    resume_step: ContinuityText | None = None


class ScanItem(Contract):
    identity: SourceIdentity
    canonical_url: str
    title: str
    state: Literal["open", "closed"]
    updated_at: datetime | None = None
    body_hash: str
    source_revision: str
    labels: list[str]
    milestone: str | None = None
    author_role: Literal["trusted", "external"]
    comment_count: int
    structured: Continuity
    goal_key: str | None = None
    security_mention: bool = False
    linked_thread_id: str | None = None
    linked_role: Literal["primary"] | None = None
    linked_import: bool = False
    source_conflict: bool = False
    inbox_match: bool = False
    references: list[int] = Field(default_factory=list)
    tracked_tasks: bool = False
    protection_flags: list[ProtectionFlag] = Field(default_factory=list)
    kind: IssueKind = IssueKind.unknown
    completed: bool = False
    stale: bool = False


class ScanSummary(Contract):
    schema_version: Literal[1] = VERSION
    scan_id: str
    project_slug: str
    repository: Repository
    private: bool = True
    repository_id: str | None = None
    selector: str
    include_closed: bool
    status: Literal["queued", "running", "completed", "partial", "failed", "cancelled"]
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    issue_count: int = 0
    pages_read: int = 0
    listing_complete: bool | None = None
    detail_limited_count: int = 0
    truncated: bool = False
    error_code: str | None = None
    retry_after_seconds: int | None = None
    counts_by_kind: dict[IssueKind, int] = Field(default_factory=dict)
    protected_count: int = 0
    cluster_count: int = 0
    policy_hash: str


class NewThread(Contract):
    kind: Literal["new_thread"]


class ExistingThread(Contract):
    kind: Literal["existing_thread"]
    thread_id: Annotated[str, Field(min_length=1, max_length=64)]


class ClusterDestination(Contract):
    kind: Literal["cluster"]
    issue_number: IssueNumber


Destination = Annotated[
    NewThread | ExistingThread | ClusterDestination, Field(discriminator="kind")
]


class Recommendation(Contract):
    disposition: Disposition = Disposition.skip
    destination: Destination | None = None
    relationship: Relationship = Relationship.uncertain
    evidence: list[str] = Field(default_factory=list)
    cluster_key: IssueNumber | None = None
    workstream_key: IssueNumber | None = None
    candidate_thread_ids: list[str] = Field(default_factory=list)


class AiRequest(Contract):
    issue_numbers: Annotated[list[IssueNumber], Field(max_length=1000)] | None = None


class CandidateThreadRef(Contract):
    kind: Literal["candidate_thread"]
    ref: ShortText


class ClusterRef(Contract):
    kind: Literal["cluster"]
    ref: ShortText


AiDestination = Annotated[NewThread | CandidateThreadRef | ClusterRef, Field(discriminator="kind")]


class AiSuggestion(Contract):
    ref: ShortText
    disposition: Disposition
    destination: AiDestination | None = None
    outcome_relationship: Relationship
    related_refs: Annotated[list[ShortText], Field(max_length=10)] = Field(default_factory=list)
    evidence: Annotated[list[ShortText], Field(max_length=5)] = Field(default_factory=list)
    reasoning_summary: ContinuityText = ""
    proposed_labels: Annotated[list[ShortText], Field(max_length=5)] = Field(default_factory=list)
    suggested_title: Annotated[str, Field(max_length=120)] | None = None
    suggested_continuity: Continuity | None = None
    uncertainty: Literal["low", "medium", "high"]
    missing_prerequisites: Annotated[list[ShortText], Field(max_length=5)] = Field(
        default_factory=list
    )
    protection_flags: Annotated[list[ProtectionFlag], Field(max_length=len(ProtectionFlag))] = (
        Field(default_factory=list)
    )
    workstream: ShortText | None = None
    source_status: Literal["possibly_stale", "possibly_superseded", "current", "unknown"] = (
        "unknown"
    )


class Advisory(Contract):
    suggestion: AiSuggestion
    destination: Destination | None
    related_issues: list[IssueNumber]
    conflicts_with_protection: bool


class RecommendationItem(Contract):
    issue: ScanItem
    deterministic: Recommendation
    ai_status: str = "skipped"
    ai: Advisory | None = None
    ai_protection_flags: list[ProtectionFlag] = Field(default_factory=list)


class ScanPage(Contract):
    schema_version: Literal[1] = VERSION
    items: list[RecommendationItem]
    next_cursor: str | None


class JobReceipt(Contract):
    schema_version: Literal[1] = VERSION
    job_id: str


class ScanReceipt(JobReceipt):
    scan_id: str


class CancelReceipt(Contract):
    schema_version: Literal[1] = VERSION
    cancel_requested: Literal[True] = True


class DraftFields(Continuity):
    title: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    labels: Annotated[list[ShortText], Field(max_length=5)] = Field(default_factory=list)
    workstream: ShortText | None = None


class DraftItem(Contract):
    issue_number: IssueNumber
    source_revision: str
    disposition: Disposition
    disposition_source: Literal["deterministic", "ai_accepted", "operator"] = "deterministic"
    destination: Destination | None = None
    proposed_fields: DraftFields = Field(default_factory=DraftFields)
    protection_flags: list[ProtectionFlag]
    protection_override: str | None = None
    ai_status: str = "skipped"
    ai: Advisory | None = None


class DraftPlan(Contract):
    schema_version: Literal[1] = VERSION
    plan_id: str
    scan_id: str
    project_slug: str
    policy_hash: str
    state: Literal["draft"] = "draft"
    version: int = 1
    items: list[DraftItem]


class DraftRequest(Contract):
    scan_id: Annotated[str, Field(min_length=1, max_length=64)]


class Override(Contract):
    reason: Annotated[str, Field(min_length=1, max_length=300)]


class DraftEdit(Contract):
    issue_number: IssueNumber
    disposition: Disposition | None = None
    destination: Destination | None = None
    proposed_fields: DraftFields | None = None
    protection_override: Override | None = None
    accept_ai: bool = False


class DraftPatch(Contract):
    expected_version: Annotated[int, Field(ge=1)]
    items: Annotated[list[DraftEdit], Field(min_length=1, max_length=1000)]
