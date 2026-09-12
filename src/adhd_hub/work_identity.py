"""Source-aware work identity helpers (Foundation B1 / #73).

Authority is derived from resolved work_source and is never persisted.
External identity is host-scoped: (provider, host, owner, repo, number).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from adhd_hub.models import Project, Thread


class WorkSource(StrEnum):
    local = "local"
    github = "github"
    gitea = "gitea"


class WorkAuthority(StrEnum):
    hub = "hub"
    external = "external"


class ExternalIssueState(StrEnum):
    open = "open"
    closed = "closed"


# Documented for #74 — not enforced in #73.
REPO_OWNED_FIELDS = frozenset(
    {
        "title",
        "body",
        "open_closed",
        "labels",
        "milestone",
        "assignees",
        "external_identity",
    }
)
HUB_OWNED_CONTINUITY_FIELDS = frozenset(
    {
        "focus",
        "next_steps",
        "blocked_reason",
        "resume_step",
        "session_history",
        "progress_history",
    }
)

GITHUB_CANONICAL_HOST = "github.com"
WORK_IDENTITY_MIGRATED_META = "work_identity_migrated_v1"


class DuplicateExternalIdentityError(ValueError):
    """Raised when attaching an external identity already linked to another thread."""


class RepoOwnedFieldMutationError(ValueError):
    """Continuity API attempted to change a repo-owned field on external-authority work."""


REPO_OWNED_CONTINUITY_MUTATION = (
    "repo_owned_field_forbidden: use an explicit forge-aware operation "
    "(B2b mark_done/reopen/promote) to change remote-owned fields"
)


@dataclass(frozen=True, slots=True)
class ExternalIdentity:
    provider: WorkSource
    host: str
    owner: str
    repo: str
    number: int

    def __post_init__(self) -> None:
        if self.provider not in (WorkSource.github, WorkSource.gitea):
            raise ValueError("external identity provider must be github or gitea")
        if self.number < 1:
            raise ValueError("external issue number must be >= 1")


def authority_for(source: WorkSource) -> WorkAuthority:
    if source == WorkSource.local:
        return WorkAuthority.hub
    return WorkAuthority.external


def normalize_host(provider: WorkSource, host_or_url: str | None) -> str:
    """Return canonical host for uniqueness keys."""
    if provider == WorkSource.github:
        return GITHUB_CANONICAL_HOST
    raw = (host_or_url or "").strip()
    if not raw:
        raise ValueError("gitea host is required")
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("gitea host is required")
    if parsed.port and parsed.port not in (80, 443):
        return f"{host}:{parsed.port}"
    return host


def normalize_owner_repo(owner: str, repo: str) -> tuple[str, str]:
    o = owner.strip().lower()
    r = repo.strip().lower()
    if not o or not r:
        raise ValueError("owner and repo are required")
    return o, r


def normalize_external_identity(
    provider: WorkSource | str,
    host: str | None,
    owner: str,
    repo: str,
    number: int,
) -> ExternalIdentity:
    src = WorkSource(provider)
    if src == WorkSource.local:
        raise ValueError("local work has no external identity")
    host_n = normalize_host(src, host)
    owner_n, repo_n = normalize_owner_repo(owner, repo)
    return ExternalIdentity(
        provider=src,
        host=host_n,
        owner=owner_n,
        repo=repo_n,
        number=int(number),
    )


def external_identity_key(identity: ExternalIdentity) -> str:
    return (
        f"{identity.provider.value}:{identity.host}/"
        f"{identity.owner}/{identity.repo}#{identity.number}"
    )


def thread_has_external_identity(thread: Thread) -> bool:
    return bool(
        thread.external_provider
        and thread.external_host
        and thread.external_owner
        and thread.external_repo
        and thread.external_issue_number is not None
    )


def resolve_work_source(project: Project | None, thread: Thread) -> WorkSource:
    """Resolve effective work source; linked threads stay pinned to their provider."""
    if thread_has_external_identity(thread):
        pinned = thread.work_source or thread.external_provider
        if pinned in (WorkSource.github, WorkSource.gitea):
            return WorkSource(pinned)
        if thread.external_provider in (WorkSource.github, WorkSource.gitea):
            return WorkSource(thread.external_provider)
    if thread.work_source is not None:
        return WorkSource(thread.work_source)
    if project is not None and project.default_work_source is not None:
        return WorkSource(project.default_work_source)
    return WorkSource.local


def resolve_authority(project: Project | None, thread: Thread) -> WorkAuthority:
    return authority_for(resolve_work_source(project, thread))


def host_from_forge_browse_root(provider: WorkSource, browse_root: str | None) -> str | None:
    try:
        return normalize_host(provider, browse_root)
    except ValueError:
        return None
