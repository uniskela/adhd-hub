from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx

from adhd_hub.backlog.models import Continuity, ProtectionFlag, Repository, ScanItem, ScanSummary
from adhd_hub.forge.board_sync import STATUS_END, STATUS_START, BoardForgeSync
from adhd_hub.forge.config import ForgeConfig, ForgeProvider
from adhd_hub.forge.repo_sync import (
    _headers,
    credentials_apply_to_pinned,
    is_pull_request_payload,
    issue_snapshot_from_raw,
    iter_issue_pages,
)
from adhd_hub.forge.thread_refresh import SOURCE_FIELDS, content_hash, issue_snapshot
from adhd_hub.models import Thread
from adhd_hub.overlap import normalize_goal
from adhd_hub.work_identity import ExternalIdentity, normalize_external_identity

_MAX_PAGES = 10
_DETAIL_PAGES = 3
_DETAIL_REQUEST_LIMIT = 100
_MAX_WAIT_SECONDS = 5
_RUN_SECONDS = 300
_SEGMENT = re.compile(r"[A-Za-z0-9_.-]+")
_REFERENCE = re.compile(r"(?<![\w/#])#([1-9]\d{0,17})(?!\w)")
_FOREIGN_REF = re.compile(r"(?:https?://\S+|\b[\w.-]+/[\w.-]+#\d+)")
_SECURITY_TEXT = re.compile(
    r"\b(?:cve|security disclosure|vulnerabilit\w*|auth hardening)\b", re.IGNORECASE
)
_TASK_REF = re.compile(r"^\s*[-*]\s+\[[ xX]\].*#\d+", re.MULTILINE)


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


class ScanReadError(Exception):
    def __init__(self, code: str, retry_after: int | None = None):
        self.code = code
        self.retry_after = retry_after
        super().__init__(code)


def repository_for(cfg: ForgeConfig) -> Repository:
    if not all(
        _SEGMENT.fullmatch(part) and part not in {".", ".."} for part in (cfg.owner, cfg.repo)
    ):
        raise ValueError("forge_target_unresolved")
    for url in (cfg.api_root(), cfg.web_browse_root()):
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or (parsed.username or parsed.password or parsed.query or parsed.fragment)
        ):
            raise ValueError("forge_target_unresolved")
    if cfg.provider == ForgeProvider.github and (
        urlsplit(cfg.api_root()).netloc.lower() != "api.github.com"
        or urlsplit(cfg.web_browse_root()).netloc.lower() != "github.com"
        or not all(url.startswith("https://") for url in (cfg.api_root(), cfg.web_browse_root()))
    ):
        # shortcut: Hub keys GitHub sources to github.com, expand identity before supporting GHES.
        raise ValueError("forge_target_unresolved")
    api_url, web_url = urlsplit(cfg.api_root()), urlsplit(cfg.web_browse_root())
    if cfg.provider == ForgeProvider.gitea and (
        api_url.scheme != web_url.scheme
        or api_url.netloc.casefold() != web_url.netloc.casefold()
        or api_url.path != "/api/v1"
        or web_url.path
    ):
        # shortcut: identities omit URL mounts, extend them before allowing subpath instances.
        raise ValueError("forge_target_unresolved")
    identity = normalize_external_identity(
        cfg.provider.value, cfg.web_browse_root(), cfg.owner, cfg.repo, 1
    )
    if not credentials_apply_to_pinned(cfg, identity):
        raise ValueError("forge_target_unresolved")
    return Repository(
        provider=identity.provider.value,
        host=identity.host,
        owner=identity.owner,
        repo=identity.repo,
    )


def trusted_authors(cfg: ForgeConfig) -> set[str]:
    return {login.strip().casefold() for login in cfg.board_inbox_authors if login.strip()}


def _retry_delay(response: httpx.Response) -> int | None:
    header = response.headers.get("Retry-After")
    try:
        if header:
            if header.isdecimal():
                return min(int(header[:12]), 2**31 - 1)
            return max(0, int(parsedate_to_datetime(header).timestamp() - time.time()) + 1)
        if response.headers.get("X-RateLimit-Remaining") == "0":
            reset = response.headers.get("X-RateLimit-Reset", "")
            if reset.isdecimal():
                return max(0, min(int(reset[:12] or "0") - int(time.time()) + 1, 2**31 - 1))
    except (ValueError, OverflowError):
        pass
    return None


class ForgeReader:
    """Bound GETs to the configured API and never follow forge-supplied URLs or redirects."""

    def __init__(self, cfg: ForgeConfig, client: httpx.Client, cancelled: Callable[[], bool]):
        self.cfg = cfg
        self.client = client
        self.cancelled = cancelled
        self.deadline = time.monotonic() + _RUN_SECONDS
        self.repository_url = f"{cfg.api_root()}/repos/{cfg.owner}/{cfg.repo}"
        self.last_rate_limit: ScanReadError | None = None
        self.detail_requests = 0

    def check(self):
        if self.cancelled():
            raise ScanReadError("cancelled")
        if time.monotonic() >= self.deadline:
            raise ScanReadError("deadline")

    def get(self, url, params=None, *, detail: bool = False) -> httpx.Response:
        for attempt in range(3):
            self.check()
            if detail:
                if self.detail_requests >= _DETAIL_REQUEST_LIMIT:
                    raise ScanReadError("detail_budget_exhausted")
                self.detail_requests += 1
            try:
                response = self.client.get(
                    url,
                    params=params,
                    headers=_headers(self.cfg),
                    follow_redirects=False,
                    timeout=min(10.0, max(0.001, self.deadline - time.monotonic())),
                )
            except httpx.TimeoutException:
                raise ScanReadError("timeout") from None
            except httpx.HTTPError:
                raise ScanReadError("transport_error") from None
            if response.status_code == 200:
                return response
            delay = _retry_delay(response)
            rate_limited = response.status_code == 429 or (
                response.status_code == 403
                and (
                    delay is not None
                    or response.headers.get("X-RateLimit-Remaining") == "0"
                    or "rate limit" in response.text[:1000].casefold()
                )
            )
            if not rate_limited:
                raise ScanReadError(f"http_{response.status_code}")
            delay = delay if delay is not None else 2**attempt
            error = ScanReadError("rate_limited", delay)
            if (
                attempt == 2
                or delay > _MAX_WAIT_SECONDS
                or time.monotonic() + delay >= self.deadline
            ):
                self.last_rate_limit = error
                raise error
            until = time.monotonic() + delay
            while (remaining := until - time.monotonic()) > 0:
                self.check()
                time.sleep(min(remaining, 0.1))
        raise AssertionError("unreachable")

    @staticmethod
    def json(response, expected):
        try:
            value = response.json()
        except ValueError:
            raise ScanReadError("invalid_payload") from None
        if not isinstance(value, expected):
            raise ScanReadError("invalid_payload")
        return value

    def repository(self, expected: Repository) -> tuple[bool, str | None]:
        info = self.json(self.get(self.repository_url), dict)
        name = info.get("full_name")
        if not isinstance(name, str) or name.casefold() != f"{expected.owner}/{expected.repo}":
            raise ScanReadError("repository_mismatch")
        # Missing or contradictory visibility fails closed at the AI privacy gate.
        private = info.get("private") is not False or info.get("visibility") not in {None, "public"}
        remote_id = info.get("id")
        return private, str(remote_id) if type(remote_id) in (int, str) and remote_id else None

    def account_login(self) -> str:
        user = self.json(self.get(f"{self.cfg.api_root()}/user"), dict)
        login = user.get("login") or user.get("username")
        return login.strip().casefold() if isinstance(login, str) else ""

    def issue(self, number: int) -> dict:
        return self.json(self.get(f"{self.repository_url}/issues/{number}"), dict)

    def issue_details(self, number: int, resource: str):
        gitea = self.cfg.provider == ForgeProvider.gitea
        size = 50 if gitea else 100
        for page in range(1, _DETAIL_PAGES + 1):
            response = self.get(
                f"{self.repository_url}/issues/{number}/{resource}",
                {"limit" if gitea else "per_page": size, "page": page},
                detail=True,
            )
            rows = self.json(response, list)
            if any(not isinstance(row, dict) for row in rows):
                raise ScanReadError("invalid_payload")
            yield from rows
            if not more_pages(response, len(rows), size):
                return
        raise ScanReadError("detail_truncated")


def more_pages(response: httpx.Response, count: int, size: int) -> bool:
    # Follow page numbers, never Link URLs. A full page without Link is ambiguous.
    if response.headers.get("Link"):
        return "next" in response.links
    return count >= size


def _login(raw: dict) -> str:
    user = raw.get("user")
    if not isinstance(user, dict):
        return ""
    # Display names cannot prove allowlisted account identity.
    value = user.get("login") or user.get("username")
    return value.strip().casefold() if isinstance(value, str) else ""


def _dt(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(UTC) if parsed.tzinfo is not None else None
    except ValueError:
        return None


def forge_authored_body(body: str) -> str:
    """Exclude Hub-owned continuity even when it has been mirrored to the issue."""
    if BoardForgeSync.is_wholly_hub_owned_body(body):
        return ""
    before, marker, after = body.partition(STATUS_START)
    while marker:
        _, end, tail = after.partition(STATUS_END)
        if not end:
            return before
        segment, marker, after = tail.partition(STATUS_START)
        before = f"{before}\n{segment}"
    return before


def issue_data(raw: dict, cfg: ForgeConfig, repo: Repository):
    if type(raw.get("number")) is not int or not 0 < raw["number"] < 2**63:
        raise ScanReadError("invalid_payload")
    embedded = raw.get("repository")
    if (
        isinstance(embedded, dict)
        and embedded.get("full_name")
        and (str(embedded["full_name"]).casefold() != f"{repo.owner}/{repo.repo}")
    ):
        raise ScanReadError("repository_mismatch")
    snap = issue_snapshot_from_raw(
        raw, provider=repo.provider, host=repo.host, owner=repo.owner, repo=repo.repo
    )
    if snap is None:
        raise ScanReadError("invalid_payload")
    milestone_raw = raw.get("milestone")
    milestone = (
        str(milestone_raw.get("title") or "")[:200] if isinstance(milestone_raw, dict) else None
    )
    comment_count = raw.get("comments")
    comments_known = type(comment_count) is int and comment_count >= 0
    comment_count = comment_count if comments_known else 0
    revision = digest(
        {
            "repository": repo.model_dump(),
            "issue": snap.identity.number,
            "id": raw.get("id"),
            "updated_at": snap.updated_at,
            "title": snap.title,
            "body": snap.body,
            "state": snap.state,
            "labels": snap.labels,
            "comments": raw.get("comments"),
            "milestone": milestone_raw,
            "assignees": snap.assignee_logins,
            "locked": raw.get("locked"),
            "author": _login(raw),
            "pinned": raw.get("pinned"),
            "reactions": raw.get("reactions"),
            "state_reason": raw.get("state_reason"),
        }
    )
    body = forge_authored_body(snap.body)
    structured = issue_snapshot({"title": snap.title, "body": body})
    normalized_goal = normalize_goal(structured.get("goal"))
    continuity = Continuity(
        **{
            k: [s[:200] for s in v] if isinstance(v, list) else v[:300] if isinstance(v, str) else v
            for k, v in structured.items()
            if k in SOURCE_FIELDS
        }
    )
    author = _login(raw)
    trusted = author in trusted_authors(cfg)
    title = snap.title[:500]
    hub_labels = {label.casefold() for label in cfg.issue_labels}
    inbox_match = BoardForgeSync.title_matches_inbox_prefix(title) or bool(
        hub_labels.intersection(snap.labels)
    )
    flags = []
    if not trusted:
        flags.append(ProtectionFlag.external_author)
    if milestone_raw:
        flags.append(ProtectionFlag.milestone)
    if raw.get("locked"):
        flags.append(ProtectionFlag.locked)
    if raw.get("pinned") or "pinned" in snap.labels:
        flags.append(ProtectionFlag.pinned)
    if not comments_known or _dt(snap.updated_at) is None:
        flags.append(ProtectionFlag.incomplete_read)
    refs = sorted({int(number) for number in _REFERENCE.findall(_FOREIGN_REF.sub("", body))})[:100]
    item = ScanItem(
        identity={**repo.model_dump(), "number": snap.identity.number},
        canonical_url=(
            f"{cfg.web_browse_root()}/{repo.owner}/{repo.repo}/issues/{snap.identity.number}"
        ),
        title=title,
        state=snap.state.value,
        updated_at=_dt(snap.updated_at),
        body_hash=content_hash(snap.body),
        source_revision=revision,
        labels=list(snap.labels),
        milestone=milestone,
        author_role="trusted" if trusted else "external",
        comment_count=comment_count,
        structured=continuity,
        goal_key=digest(normalized_goal) if normalized_goal else None,
        security_mention=bool(_SECURITY_TEXT.search(body)),
        inbox_match=inbox_match,
        references=refs,
        tracked_tasks=bool(_TASK_REF.search(body)),
        protection_flags=flags,
    )
    return item, snap


def _pr_event(row: dict) -> bool:
    source = row.get("source")
    source_issue = source.get("issue") if isinstance(source, dict) else None
    if isinstance(source_issue, dict) and is_pull_request_payload(source_issue):
        return True
    if row.get("pull_request") or row.get("ref_pull_request"):
        return True
    linked = row.get("ref_issue")
    return isinstance(linked, dict) and (
        is_pull_request_payload(linked) or "/pulls/" in str(linked.get("html_url", ""))
    )


def _enrich(reader: ForgeReader, item: ScanItem, trusted: set[str]):
    flags = set(item.protection_flags)
    number = item.identity.number
    if item.comment_count:
        comments = list(reader.issue_details(number, "comments"))
        if any(_login(row) not in trusted for row in comments):
            flags.add(ProtectionFlag.external_participants)
        count = len({str(row["id"]) for row in comments if row.get("id") is not None})
        if count != item.comment_count or count != len(comments):
            flags.add(ProtectionFlag.incomplete_read)
        item.protection_flags = sorted(flags)
    for event in reader.issue_details(number, "timeline"):
        if (event.get("event") or event.get("type")) == "pinned":
            flags.add(ProtectionFlag.pinned)
        if _pr_event(event):
            flags.add(ProtectionFlag.linked_pull_request)
        item.protection_flags = sorted(flags)


@dataclass
class ScanResult:
    items: list[ScanItem] = field(default_factory=list)
    pages_read: int = 0
    listing_complete: bool = False
    detail_limited_count: int = 0
    truncated: bool = False
    error: ScanReadError | None = None
    private: bool = True
    repository_id: str | None = None


def scan_repository(
    reader: ForgeReader,
    scan: ScanSummary,
    find_thread: Callable[[ExternalIdentity], Thread | None],
) -> ScanResult:
    found = ScanResult()
    cfg = reader.cfg
    trusted = trusted_authors(cfg)
    login = cfg.forge_account_login.strip().casefold()
    assignees: dict[int, tuple[str, ...]] = {}
    terminal_errors = {"cancelled", "deadline", "rate_limited"}
    try:
        found.private, found.repository_id = reader.repository(scan.repository)
        if scan.selector == "assigned_to_me" and not login:
            login = reader.account_login()
            if not login:
                raise ScanReadError("assigned_to_me_login_unavailable")
        if scan.selector == "adhd_inbox" and (not cfg.board_inbox_enabled or not trusted):
            raise ScanReadError("board_inbox_authors_required")
        selected_labels = {value.strip().casefold() for value in cfg.issue_import_labels}
        items = {}
        for response, size in iter_issue_pages(
            cfg, reader.get, state="all" if scan.include_closed else "open"
        ):
            raw_page = reader.json(response, list)
            found.pages_read += 1
            for raw in raw_page:
                if isinstance(raw, dict) and is_pull_request_payload(raw):
                    continue
                try:
                    if not isinstance(raw, dict):
                        raise ScanReadError("invalid_payload")
                    item, snap = issue_data(raw, cfg, scan.repository)
                except (ScanReadError, TypeError, ValueError, OverflowError):
                    found.error = found.error or ScanReadError("invalid_issue_payload")
                    continue
                if (
                    (not scan.include_closed and item.state == "closed")
                    or (
                        scan.selector == "adhd_inbox"
                        and (not item.inbox_match or item.author_role != "trusted")
                    )
                    or (scan.selector == "labels" and not selected_labels.intersection(item.labels))
                    or (scan.selector == "assigned_to_me" and login not in snap.assignee_logins)
                ):
                    continue
                assignees[item.identity.number] = snap.assignee_logins
                linked = find_thread(snap.identity)
                if linked:
                    item.linked_thread_id = linked.id
                    item.linked_role = "primary"
                    item.linked_import = bool(
                        linked.source_imported_at
                        or linked.origin in {"forge-inbox", "forge-import"}
                    )
                    item.source_conflict = linked.source_sync_state == "conflicted"
                previous = items.get(item.identity.number)
                if previous and previous.source_revision != item.source_revision:
                    item.protection_flags.append(ProtectionFlag.incomplete_read)
                    found.error = found.error or ScanReadError("source_changed_during_scan")
                items[item.identity.number] = item
            found.items = sorted(items.values(), key=lambda issue: issue.identity.number)
            if not more_pages(response, len(raw_page), size):
                found.listing_complete = found.error is None
                break
            if found.pages_read == _MAX_PAGES:
                found.truncated = True
    except ScanReadError as exc:
        found.error = exc

    if (
        not login
        and any(assignees.values())
        and not (found.error and found.error.code in terminal_errors)
    ):
        try:
            login = reader.account_login()
        except ScanReadError as exc:
            if exc.code in terminal_errors:
                found.error = exc
    for item in found.items:
        if set(assignees[item.identity.number]) - {login}:
            item.protection_flags.append(ProtectionFlag.assigned_other)

    # Spend the limited reads first on issues that could become migration candidates.
    detail_order = sorted(
        found.items,
        key=lambda item: (
            not item.inbox_match
            or bool(item.protection_flags)
            or bool(item.linked_thread_id)
            or item.security_mention,
            item.identity.number,
        ),
    )
    for item in detail_order:
        if item.author_role != "trusted":
            continue  # Already protected by author.
        try:
            if found.error and found.error.code in terminal_errors:
                raise found.error
            _enrich(reader, item, trusted)
        except ScanReadError as exc:
            item.protection_flags = sorted({*item.protection_flags, ProtectionFlag.incomplete_read})
            if exc.code == "detail_budget_exhausted":
                found.detail_limited_count += 1
            if exc.code in terminal_errors or found.error is None:
                found.error = exc
    return found
