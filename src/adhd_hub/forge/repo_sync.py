"""Repo-primary discover / fingerprint / pinned reconcile (Foundation B2a / #74)."""

from __future__ import annotations

import hashlib
import logging
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import httpx

from adhd_hub.forge.config import ForgeConfig, ForgeProvider, IssueImportPolicy
from adhd_hub.work_identity import (
    ExternalIdentity,
    ExternalIssueState,
    WorkSource,
    normalize_external_identity,
    normalize_host,
)

log = logging.getLogger(__name__)

_USER_LOGIN_CACHE: dict[str, str] = {}


@dataclass(frozen=True, slots=True)
class IssueSnapshot:
    identity: ExternalIdentity
    title: str
    state: ExternalIssueState
    labels: tuple[str, ...]
    updated_at: str
    assignee_logins: tuple[str, ...] = ()


def normalize_title(title: str) -> str:
    return unicodedata.normalize("NFC", (title or "").strip())


def normalize_labels(labels: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in labels:
        name = str(raw or "").strip().casefold()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    out.sort()
    return tuple(out)


def fingerprint_for(snapshot: IssueSnapshot) -> str:
    identity = snapshot.identity
    labels = normalize_labels(snapshot.labels)
    lines = [
        identity.provider.value,
        identity.host,
        identity.owner,
        identity.repo,
        str(identity.number),
        snapshot.state.value,
        normalize_title(snapshot.title),
        ",".join(labels),
    ]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def is_pull_request_payload(raw: dict[str, Any]) -> bool:
    """GitHub PRs include pull_request dict; Gitea issues often have pull_request: null."""
    return raw.get("pull_request") is not None


def issue_snapshot_from_raw(
    raw: dict[str, Any],
    *,
    provider: WorkSource | str,
    host: str,
    owner: str | None = None,
    repo: str | None = None,
) -> IssueSnapshot | None:
    if not isinstance(raw, dict) or is_pull_request_payload(raw):
        return None
    number = raw.get("number")
    if not isinstance(number, int) or number < 1:
        return None
    title = raw.get("title") if isinstance(raw.get("title"), str) else ""
    state_raw = str(raw.get("state") or "open").casefold()
    state = ExternalIssueState.closed if state_raw in {"closed", "close"} else ExternalIssueState.open
    label_names: list[str] = []
    for item in raw.get("labels") or []:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            label_names.append(item["name"])
        elif isinstance(item, str):
            label_names.append(item)
    assignees: list[str] = []
    for item in raw.get("assignees") or []:
        if isinstance(item, dict) and isinstance(item.get("login"), str):
            assignees.append(item["login"])
    assignee = raw.get("assignee")
    if isinstance(assignee, dict) and isinstance(assignee.get("login"), str):
        assignees.append(assignee["login"])
    own = owner
    rep = repo
    if not own or not rep:
        repo_obj = raw.get("repository")
        if isinstance(repo_obj, dict):
            full = repo_obj.get("full_name")
            if isinstance(full, str) and "/" in full:
                own, rep = full.split("/", 1)
            else:
                owner_obj = repo_obj.get("owner")
                if isinstance(owner_obj, dict) and isinstance(owner_obj.get("login"), str):
                    own = own or owner_obj["login"]
                if isinstance(repo_obj.get("name"), str):
                    rep = rep or repo_obj["name"]
    if not own or not rep:
        return None
    updated = raw.get("updated_at") or raw.get("updated") or ""
    identity = normalize_external_identity(provider, host, str(own), str(rep), number)
    return IssueSnapshot(
        identity=identity,
        title=title,
        state=state,
        labels=normalize_labels(label_names),
        updated_at=str(updated),
        assignee_logins=tuple(sorted({a.casefold() for a in assignees if a})),
    )


def credentials_apply_to_pinned(cfg: ForgeConfig, identity: ExternalIdentity) -> bool:
    if not cfg.token or cfg.provider == ForgeProvider.none:
        return False
    if identity.provider == WorkSource.github:
        return cfg.provider == ForgeProvider.github
    if identity.provider == WorkSource.gitea:
        if cfg.provider != ForgeProvider.gitea:
            return False
        cfg_host = normalize_host(WorkSource.gitea, cfg.web_browse_root() or cfg.base_url)
        return cfg_host == identity.host
    return False


def _headers(cfg: ForgeConfig) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {cfg.token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if cfg.provider == ForgeProvider.github:
        headers["Accept"] = "application/vnd.github+json"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    return headers


def fetch_pinned_issue(
    cfg: ForgeConfig,
    identity: ExternalIdentity,
    *,
    client: httpx.Client | None = None,
) -> IssueSnapshot | dict[str, Any]:
    """Fetch issue by pinned identity. Never substitutes project owner/repo."""
    if not credentials_apply_to_pinned(cfg, identity):
        return {
            "skipped": True,
            "reason": "pinned_identity_unreachable",
            "identity": {
                "provider": identity.provider.value,
                "host": identity.host,
                "owner": identity.owner,
                "repo": identity.repo,
                "number": identity.number,
            },
        }
    url = (
        f"{cfg.api_root()}/repos/{identity.owner}/{identity.repo}/issues/{identity.number}"
    )
    own_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        resp = http.get(url, headers=_headers(cfg))
        if resp.status_code >= 400:
            return {
                "skipped": True,
                "reason": "pinned_identity_unreachable",
                "status_code": resp.status_code,
                "identity": {
                    "provider": identity.provider.value,
                    "host": identity.host,
                    "owner": identity.owner,
                    "repo": identity.repo,
                    "number": identity.number,
                },
            }
        snap = issue_snapshot_from_raw(
            resp.json(),
            provider=identity.provider,
            host=identity.host,
            owner=identity.owner,
            repo=identity.repo,
        )
        if snap is None:
            return {"skipped": True, "reason": "pinned_identity_unreachable"}
        return snap
    finally:
        if own_client:
            http.close()


def resolve_assigned_to_me_login(
    cfg: ForgeConfig,
    *,
    client: httpx.Client | None = None,
) -> str | dict[str, Any]:
    explicit = (cfg.forge_account_login or "").strip()
    if explicit:
        return explicit
    if not (cfg.enabled() and cfg.token):
        return {"error": "assigned_to_me_login_unavailable"}
    cache_key = f"{cfg.provider.value}:{cfg.api_root()}:{cfg.token[-8:]}"
    cached = _USER_LOGIN_CACHE.get(cache_key)
    if cached:
        return cached
    own_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        resp = http.get(f"{cfg.api_root()}/user", headers=_headers(cfg))
        if resp.status_code >= 400:
            return {"error": "assigned_to_me_login_unavailable", "status_code": resp.status_code}
        data = resp.json()
        login = data.get("login") if isinstance(data, dict) else None
        if not isinstance(login, str) or not login.strip():
            return {"error": "assigned_to_me_login_unavailable"}
        _USER_LOGIN_CACHE[cache_key] = login.strip()
        return login.strip()
    finally:
        if own_client:
            http.close()


def discover_issue_payloads(
    cfg: ForgeConfig,
    *,
    limit: int = 50,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """List candidate issue payloads for the configured project forge target."""
    policy = cfg.issue_import_policy
    if policy == IssueImportPolicy.manual:
        return []
    if not (cfg.enabled() and cfg.board_enabled and cfg.owner and cfg.repo):
        return {"skipped": True, "reason": "forge_target_unresolved"}

    login_filter: str | None = None
    if policy == IssueImportPolicy.assigned_to_me:
        resolved = resolve_assigned_to_me_login(cfg, client=client)
        if isinstance(resolved, dict):
            return resolved
        login_filter = resolved.casefold()

    label_filter = {x.casefold() for x in (cfg.issue_import_labels or []) if x.strip()}
    hub_labels = {x.casefold() for x in (cfg.issue_labels or []) if x.strip()}
    host = normalize_host(
        WorkSource.github if cfg.provider == ForgeProvider.github else WorkSource.gitea,
        cfg.web_browse_root() or cfg.base_url,
    )
    provider = (
        WorkSource.github if cfg.provider == ForgeProvider.github else WorkSource.gitea
    )

    own_client = client is None
    http = client or httpx.Client(timeout=30.0)
    out: list[dict[str, Any]] = []
    authors_allow: set[str] | None = None
    if policy == IssueImportPolicy.adhd_inbox:
        if not cfg.board_inbox_enabled:
            return {
                "skipped": True,
                "reason": "board_inbox_disabled",
                "hint": "adhd_inbox discovery requires board_inbox_enabled.",
            }
        authors_allow = {
            name.strip().casefold()
            for name in (cfg.board_inbox_authors or [])
            if isinstance(name, str) and name.strip()
        }
        if not authors_allow:
            return {
                "skipped": True,
                "reason": "board_inbox_authors_required",
                "hint": "adhd_inbox discovery requires board_inbox_authors (fail closed).",
            }
    try:
        page_size = 50 if cfg.provider == ForgeProvider.gitea else 100
        for page in range(1, 11):
            params: dict[str, Any] = {"state": "open", "page": page}
            if cfg.provider == ForgeProvider.gitea:
                params["limit"] = page_size
                params["type"] = "issues"
            else:
                params["per_page"] = page_size
            url = f"{cfg.api_root()}/repos/{cfg.owner}/{cfg.repo}/issues"
            resp = http.get(url, headers=_headers(cfg), params=params)
            if resp.status_code >= 400:
                log.warning("discover issues failed: %s %s", resp.status_code, resp.text[:200])
                resp.raise_for_status()
            items = resp.json()
            if not isinstance(items, list) or not items:
                break
            for raw in items:
                if not isinstance(raw, dict) or is_pull_request_payload(raw):
                    continue
                names = []
                for item in raw.get("labels") or []:
                    if isinstance(item, dict) and isinstance(item.get("name"), str):
                        names.append(item["name"].casefold())
                    elif isinstance(item, str):
                        names.append(item.casefold())
                title = raw.get("title") if isinstance(raw.get("title"), str) else ""
                if policy == IssueImportPolicy.labels:
                    if not label_filter or not (label_filter & set(names)):
                        continue
                elif policy == IssueImportPolicy.adhd_inbox:
                    author = ""
                    user = raw.get("user")
                    if isinstance(user, dict) and isinstance(user.get("login"), str):
                        author = user["login"].casefold()
                    if not author or not authors_allow or author not in authors_allow:
                        continue
                    has_hub = bool(hub_labels & set(names))
                    has_prefix = title.casefold().startswith("[adhd]")
                    if not (has_hub or has_prefix):
                        continue
                elif policy == IssueImportPolicy.assigned_to_me:
                    assignees = []
                    for item in raw.get("assignees") or []:
                        if isinstance(item, dict) and isinstance(item.get("login"), str):
                            assignees.append(item["login"].casefold())
                    assignee = raw.get("assignee")
                    if isinstance(assignee, dict) and isinstance(assignee.get("login"), str):
                        assignees.append(assignee["login"].casefold())
                    if not login_filter or login_filter not in assignees:
                        continue
                # all_open: no extra filter
                snap = issue_snapshot_from_raw(
                    raw,
                    provider=provider,
                    host=host,
                    owner=cfg.owner,
                    repo=cfg.repo,
                )
                if snap is None:
                    continue
                out.append({"raw": raw, "snapshot": snap})
                if len(out) >= limit:
                    return out
            if len(items) < page_size:
                break
        return out
    finally:
        if own_client:
            http.close()


def mutate_pinned_issue_state(
    cfg: ForgeConfig,
    identity: ExternalIdentity,
    *,
    closed: bool,
    client: httpx.Client | None = None,
) -> IssueSnapshot | dict[str, Any]:
    """PATCH remote open/closed for pinned identity; return fresh snapshot or error dict."""
    if not credentials_apply_to_pinned(cfg, identity):
        return {
            "ok": False,
            "error": "pinned_identity_unreachable",
            "pending": False,
        }
    url = (
        f"{cfg.api_root()}/repos/{identity.owner}/{identity.repo}/issues/{identity.number}"
    )
    payload: dict[str, Any] = {
        "state": "closed" if closed else "open",
    }
    if closed and cfg.provider == ForgeProvider.github:
        payload["state_reason"] = "completed"
    own_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        resp = http.patch(url, headers=_headers(cfg), json=payload)
        if resp.status_code >= 400 and "state_reason" in payload:
            payload.pop("state_reason", None)
            resp = http.patch(url, headers=_headers(cfg), json=payload)
        if resp.status_code >= 400:
            return {
                "ok": False,
                "error": f"remote_patch_failed:{resp.status_code}",
                "pending": False,
                "detail": resp.text[:300],
            }
        data = resp.json() if resp.content else {}
        snap = issue_snapshot_from_raw(
            data if isinstance(data, dict) else {},
            provider=identity.provider,
            host=identity.host,
            owner=identity.owner,
            repo=identity.repo,
        )
        if snap is None:
            snap = IssueSnapshot(
                identity=identity,
                title=str(data.get("title") or "") if isinstance(data, dict) else "",
                state=ExternalIssueState.closed if closed else ExternalIssueState.open,
                labels=(),
                updated_at=str(data.get("updated_at") or "") if isinstance(data, dict) else "",
            )
        return snap
    finally:
        if own_client:
            http.close()


def create_remote_issue(
    cfg: ForgeConfig,
    *,
    title: str,
    body: str = "",
    client: httpx.Client | None = None,
) -> IssueSnapshot | dict[str, Any]:
    if not (cfg.enabled() and cfg.token and cfg.owner and cfg.repo):
        return {"ok": False, "error": "forge_target_unresolved", "pending": False}
    url = f"{cfg.api_root()}/repos/{cfg.owner}/{cfg.repo}/issues"
    own_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        resp = http.post(
            url,
            headers=_headers(cfg),
            json={"title": title[:200], "body": body or ""},
        )
        if resp.status_code >= 400:
            return {
                "ok": False,
                "error": f"remote_create_failed:{resp.status_code}",
                "pending": False,
                "detail": resp.text[:300],
            }
        host = normalize_host(
            WorkSource.github if cfg.provider == ForgeProvider.github else WorkSource.gitea,
            cfg.web_browse_root() or cfg.base_url,
        )
        provider = (
            WorkSource.github if cfg.provider == ForgeProvider.github else WorkSource.gitea
        )
        snap = issue_snapshot_from_raw(
            resp.json(),
            provider=provider,
            host=host,
            owner=cfg.owner,
            repo=cfg.repo,
        )
        if snap is None:
            return {"ok": False, "error": "remote_create_invalid_response", "pending": False}
        return snap
    finally:
        if own_client:
            http.close()
