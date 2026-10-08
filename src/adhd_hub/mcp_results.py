"""Output-only MCP schemas for existing JSON dictionaries.

TypedDict keeps absent keys absent and does not add model defaults. Extra keys
are retained so schema publication cannot discard service enrichments. Dates
stay strings to preserve each endpoint's existing timestamp representation.
Result envelopes describe success and error fields together: a union return
annotation would make the MCP SDK wrap the existing payload in ``result``.
"""

from typing import Annotated, Any, Literal, Required

from pydantic import ConfigDict, Field
from typing_extensions import TypedDict

from adhd_hub.clock_off import ClockOffState
from adhd_hub.models import EnergyLevel, ReminderKind, ThreadStatus
from adhd_hub.work_identity import ExternalIssueState, WorkAuthority, WorkSource

Timestamp = Annotated[str, Field(json_schema_extra={"format": "date-time"})]


class OutputDict(TypedDict):
    __pydantic_config__ = ConfigDict(extra="allow")


class CompletionResult(OutputDict):
    """Readiness based on stored thread state, without checking a forge or PR."""

    ready: Annotated[bool, Field(description="True when stored state has no completion blockers.")]
    reasons: Annotated[list[str], Field(description="Stored blockers; empty when ready is true.")]


class ReturnCueSuggestion(OutputDict):
    source: Literal["focus", "next_steps"]
    text: str


class ReturnCueResult(OutputDict):
    """Advisory resume coaching; never rejects a save, pause or completion."""

    quality: Literal["missing", "vague", "concrete"]
    signals: list[str]
    hint: str | None
    suggestion: ReturnCueSuggestion | None
    advisory: Literal[True]
    version: int


class ThreadFields(OutputDict, total=False):
    """Raw thread fields, also shared by success/error lifecycle envelopes."""

    id: str
    summary: str
    status: ThreadStatus
    energy: EnergyLevel
    source_tool: str | None
    workspace_path: str | None
    project_slug: str | None
    chat_ref: str | None
    transcript_ref: str | None
    origin: str
    created_at: Timestamp
    updated_at: Timestamp
    resume_step: str | None
    paused_at: Timestamp | None
    last_reminded_at: Timestamp | None
    triage_snooze_until: Timestamp | None
    goal: str | None
    focus: str | None
    next_steps: list[str]
    blocked_reason: str | None
    work_source: WorkSource | None
    external_provider: WorkSource | None
    external_host: str | None
    external_owner: str | None
    external_repo: str | None
    external_issue_number: int | None
    external_issue_state: ExternalIssueState | None
    external_updated_at: str | None
    external_fingerprint: str | None
    external_labels: list[str]
    source_issue_url: str | None
    source_imported_at: str | None
    source_content_hash: str | None
    source_snapshot: dict[str, Any]
    source_sync_state: str | None
    source_conflicts: dict[str, Any]
    source_title_derived: bool
    merged_into: str | None
    completion: CompletionResult
    return_cue: ReturnCueResult | None


class ThreadResult(ThreadFields, total=False):
    """Thread on success; only error and the requested id on rejection/not-found."""

    id: Required[str]
    error: Annotated[str, Field(description="Present only when the operation fails.")]


class DigestThreadResult(ThreadFields):
    """Raw session thread with completion readiness and resume coaching."""

    id: str
    summary: str
    status: ThreadStatus
    energy: EnergyLevel
    created_at: Timestamp
    updated_at: Timestamp
    next_steps: list[str]
    completion: CompletionResult
    return_cue: ReturnCueResult | None


class CompactThreadResult(OutputDict):
    """Checkpoint state and candidate selection; timestamps retain wire format."""

    id: str
    title: str
    summary: str
    goal: str | None
    status: ThreadStatus
    focus: str | None
    next_steps: list[str]
    blocked_reason: str | None
    resume_step: str | None
    updated_at: Timestamp
    project_slug: str | None
    completion: CompletionResult
    return_cue: ReturnCueResult | None
    work_source: WorkSource
    authority: WorkAuthority
    external_provider: WorkSource | None
    external_host: str | None
    external_owner: str | None
    external_repo: str | None
    external_issue_number: int | None
    external_issue_state: ExternalIssueState | None


class ReminderResult(OutputDict):
    id: str
    message: str
    kind: ReminderKind
    due_at: Timestamp | None
    created_at: Timestamp
    handled: bool
    last_fired_at: Timestamp | None


class GuidanceDigestResult(OutputDict):
    """Expected guidance versions and the client's last reported local check."""

    expected_version: int
    expected_session_skill_version: int
    last_verified_version: int | None
    last_verified_at: Timestamp | None
    status: Literal[
        "local_verification_required", "verification_recommended", "last_verified_current"
    ]
    hint: str


class SessionDigestResult(OutputDict):
    """Session summary after reminder cooldown/firing bookkeeping."""

    open_count: Annotated[int, Field(description="Unfinished threads in the selected pool.")]
    stale_count: Annotated[int, Field(description="Stale threads excluding active triage snoozes.")]
    items: list[DigestThreadResult]
    due_reminders: list[ReminderResult]
    wiki_index_snippet: str | None
    guidance: GuidanceDigestResult | None
    clock_off: Annotated[
        ClockOffState, Field(description="Global opt-in advisory boundary and wrap-up guidance.")
    ]


class ProgressResult(OutputDict, total=False):
    """Saved checkpoint, ambiguous selection, or error; absent keys stay absent."""

    project_slug: str
    progress_path: Annotated[
        str | None, Field(description="Written PROGRESS.md path; null while selection is required.")
    ]
    thread_id: Annotated[
        str | None, Field(description="Selected thread; null for notes-only or selection-required.")
    ]
    created_thread: Annotated[
        bool, Field(description="Present on success; whether a thread was created.")
    ]
    needs_thread_selection: Annotated[
        bool,
        Field(
            description="If true, choose a candidate thread_id or explicitly force a new thread."
        ),
    ]
    forge: Annotated[
        dict[str, Any],
        Field(description="Configured forge/wiki sync outcomes; may contain sync errors."),
    ]
    thread: Annotated[
        CompactThreadResult | None,
        Field(description="Saved state on success; null for notes-only."),
    ]
    candidates: Annotated[
        list[CompactThreadResult],
        Field(description="Present when explicit thread selection is required."),
    ]
    hint: str
    error: Annotated[str, Field(description="Present only when the checkpoint fails.")]
    detail: Annotated[str, Field(description="Additional detail for a missing thread.")]


class ProjectResult(OutputDict, total=False):
    """Resolved registry project on success; only error on lookup failure."""

    slug: str
    title: str
    description: str | None
    repo_url: str | None
    workspace_paths: list[str]
    tags: list[str]
    parent_slug: str | None
    sort_order: int
    default_energy: EnergyLevel
    default_work_source: WorkSource
    forge_owner: str | None
    forge_repo: str | None
    forge_wiki_path: str | None
    forge_project_id: str | None
    forge_connection_profile_id: str | None
    archived_at: Timestamp | None
    created_at: Timestamp
    updated_at: Timestamp
    error: Annotated[str, Field(description="Present only when no project was resolved.")]


class GuidanceHealthResult(OutputDict, total=False):
    """Stored client verification record, or error; no client filesystem inspection."""

    project_slug: str
    recorded: Literal[True]
    guidance: Annotated[
        str,
        Field(
            description="Existing JSON-encoded verification record, including verified_at and source."
        ),
    ]
    error: str
