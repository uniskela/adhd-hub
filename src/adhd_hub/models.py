from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

from adhd_hub.work_identity import ExternalIssueState, WorkSource


def _validated_repo_url(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    cleaned = value.strip().rstrip("/")
    parsed = urlsplit(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("repository URL must be a complete http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("repository URL must not contain credentials")
    return cleaned


class ThreadStatus(StrEnum):
    open = "open"
    blocked = "blocked"
    done = "done"
    dismissed = "dismissed"


class EnergyLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    unknown = "unknown"


class ReminderKind(StrEnum):
    once = "once"
    session = "session"
    daily = "daily"
    random = "random"


class Thread(BaseModel):
    id: str
    summary: str
    status: ThreadStatus = ThreadStatus.open
    energy: EnergyLevel = EnergyLevel.unknown
    source_tool: str | None = None
    workspace_path: str | None = None
    project_slug: str | None = None
    chat_ref: str | None = None
    transcript_ref: str | None = None
    origin: str = "manual"  # manual | indexer | progress | pending-reply
    created_at: datetime
    updated_at: datetime
    resume_step: str | None = None
    paused_at: datetime | None = None
    last_reminded_at: datetime | None = None
    goal: str | None = None
    focus: str | None = None
    next_steps: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None
    # Work source: None inherits project.default_work_source unless externally linked.
    work_source: WorkSource | None = None
    external_provider: WorkSource | None = None
    external_host: str | None = None
    external_owner: str | None = None
    external_repo: str | None = None
    external_issue_number: int | None = None
    external_issue_state: ExternalIssueState | None = None
    external_updated_at: str | None = None
    external_fingerprint: str | None = None
    external_labels: list[str] = Field(default_factory=list)


class ThreadUpsert(BaseModel):
    summary: str
    id: str | None = None
    status: ThreadStatus = ThreadStatus.open
    energy: EnergyLevel = EnergyLevel.unknown
    source_tool: str | None = None
    workspace_path: str | None = None
    project_slug: str | None = None
    chat_ref: str | None = None
    transcript_ref: str | None = None
    origin: str = "manual"
    goal: str | None = None
    focus: str | None = None
    next_steps: list[str] | None = None
    blocked_reason: str | None = None
    resume_step: str | None = None
    work_source: WorkSource | None = None

    @field_validator("next_steps")
    @classmethod
    def _limit_next_steps(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        from adhd_hub.thread_state import normalize_next_steps

        return normalize_next_steps(value)

    @field_validator("focus")
    @classmethod
    def _one_focus(cls, value: str | None) -> str | None:
        from adhd_hub.thread_state import normalize_focus

        return normalize_focus(value)


class ProgressUpsert(BaseModel):
    project_slug: str | None = None
    content: str | None = None
    title: str | None = None
    workspace_path: str | None = None
    source_tool: str | None = None
    create_thread_if_missing: bool = True
    thread_id: str | None = None
    force_new_thread: bool = False
    goal: str | None = None
    focus: str | None = None
    next_steps: list[str] | None = None
    blocked_reason: str | None = None
    resume_step: str | None = None

    @field_validator("next_steps")
    @classmethod
    def _limit_next_steps(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        from adhd_hub.thread_state import normalize_next_steps

        return normalize_next_steps(value)

    @field_validator("focus")
    @classmethod
    def _one_focus(cls, value: str | None) -> str | None:
        from adhd_hub.thread_state import normalize_focus

        return normalize_focus(value)

    @model_validator(mode="after")
    def _require_signal(self) -> ProgressUpsert:
        has_structured = any(
            [
                self.goal,
                self.focus,
                self.next_steps,
                self.blocked_reason,
                self.resume_step,
                self.title,
                self.thread_id,
                self.force_new_thread,
            ]
        )
        if not (self.content and self.content.strip()) and not has_structured:
            raise ValueError(
                "progress requires content or structured fields "
                "(title/goal/focus/next_steps/blocked_reason/resume_step/thread_id)"
            )
        return self


class Project(BaseModel):
    slug: str
    title: str
    description: str | None = None
    repo_url: str | None = None
    workspace_paths: list[str] = Field(default_factory=list)
    default_energy: EnergyLevel = EnergyLevel.unknown
    default_work_source: WorkSource = WorkSource.local
    # Optional per-project forge override (empty = use global forge config)
    forge_owner: str | None = None
    forge_repo: str | None = None
    forge_wiki_path: str | None = None
    forge_project_id: str | None = None  # Gitea/GitHub project board id override
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, value: str | None) -> str | None:
        return _validated_repo_url(value)


class ProjectUpsert(BaseModel):
    slug: str | None = None
    title: str
    description: str | None = None
    repo_url: str | None = None
    workspace_paths: list[str] = Field(default_factory=list)
    default_energy: EnergyLevel = EnergyLevel.unknown
    default_work_source: WorkSource | None = None
    forge_owner: str | None = None
    forge_repo: str | None = None
    forge_wiki_path: str | None = None
    forge_project_id: str | None = None

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, value: str | None) -> str | None:
        return _validated_repo_url(value)


class ProjectRename(BaseModel):
    new_slug: str
    title: str | None = None


class PendingActionKind(StrEnum):
    delete_project = "delete_project"
    rename_project = "rename_project"


class PendingActionStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class PendingAction(BaseModel):
    id: str
    kind: PendingActionKind
    status: PendingActionStatus = PendingActionStatus.pending
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    source_tool: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class Reminder(BaseModel):
    id: str
    message: str
    kind: ReminderKind = ReminderKind.once
    due_at: datetime | None = None
    created_at: datetime
    handled: bool = False
    last_fired_at: datetime | None = None


class ReminderCreate(BaseModel):
    message: str
    kind: ReminderKind = ReminderKind.once
    due_at: datetime | None = None


class ReminderSnooze(BaseModel):
    minutes: int = Field(default=60, ge=5, le=60 * 24 * 14)


class OverlapHit(BaseModel):
    thread: Thread
    score: float
    reason: str


class OverlapResult(BaseModel):
    query: str
    hits: list[OverlapHit]


class SessionDigest(BaseModel):
    open_count: int
    stale_count: int
    items: list[Thread]
    due_reminders: list[Reminder]
    wiki_index_snippet: str | None = None
    guidance: dict[str, Any] | None = None


class MarkDoneRequest(BaseModel):
    id: str
    note: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    open_threads: int
    wiki_projects: int


class IndexerPostItem(BaseModel):
    summary: str
    source_tool: str
    workspace_path: str | None = None
    project_slug: str | None = None
    transcript_ref: str | None = None
    origin: str = "indexer"
    energy: EnergyLevel = EnergyLevel.unknown


class IndexerBatch(BaseModel):
    items: list[IndexerPostItem] = Field(default_factory=list)


class JsonDict(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


class PauseRequest(BaseModel):
    next_step: str = Field(min_length=1, max_length=2000)

    @field_validator("next_step", mode="before")
    @classmethod
    def strip_next_step(cls, value):
        return value.strip() if isinstance(value, str) else value
