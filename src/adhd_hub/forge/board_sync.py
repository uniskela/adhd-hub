from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from adhd_hub.forge.config import ForgeConfig, ForgeProvider
from adhd_hub.models import Thread, ThreadStatus

log = logging.getLogger(__name__)

# Hub-owned status block inside forge issue bodies (GitHub + Gitea markdown).
STATUS_START = "<!-- adhd-hub:status:start -->"
STATUS_END = "<!-- adhd-hub:status:end -->"

# Cloud mailbox: title prefix is enough when agents cannot apply labels.
# Optional whitespace after ``]`` so ``[ADHD] foo`` and ``[ADHD]foo`` both match.
_INBOX_TITLE_PREFIX = re.compile(r"^\[adhd\]\s*", re.IGNORECASE)

# List open issues (no ``labels=`` query) then filter locally. Avoids GitHub
# Search indexing delay and the old label-first query that dropped title-only
# issues. GitHub: 100/page. Gitea: ``limit`` (API max 50). Cap 10 pages.
_INBOX_LIST_PER_PAGE = 100
_INBOX_GITEA_PER_PAGE = 50
_INBOX_LIST_MAX_PAGES = 10


class BoardForgeSync:
    """Mirror threads to GitHub/Gitea Issues (+ optional Projects attachment)."""

    def __init__(
        self,
        config: ForgeConfig,
        meta_get,
        meta_set,
        *,
        progress_reader=None,
    ) -> None:
        self.config = config
        self._meta_get = meta_get
        self._meta_set = meta_set
        # Optional legacy hook (slug → markdown). No longer embedded into issues;
        # thread state is mirrored instead. Kept for call-site compatibility.
        self._progress_reader = progress_reader

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.config.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.config.provider == ForgeProvider.github:
            headers["Accept"] = "application/vnd.github+json"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        return headers

    def _issues_url(self) -> str:
        return (
            f"{self.config.api_root()}/repos/{self.config.owner}/{self.config.repo}/issues"
        )

    def _issue_url(self, number: int) -> str:
        return f"{self._issues_url()}/{number}"

    def _meta_key(self, thread_id: str) -> str:
        return f"forge_issue:{thread_id}"

    def sync_thread(self, thread: Thread) -> dict[str, Any]:
        if not (self.config.enabled() and self.config.board_enabled):
            return {"skipped": True, "reason": "board_sync_disabled"}
        existing = self._meta_get(self._meta_key(thread.id))
        with httpx.Client(timeout=30.0) as client:
            if existing:
                return self._update_issue(client, int(existing), thread)
            return self._create_issue(client, thread)

    def _project_label(self, thread: Thread) -> str | None:
        if not thread.project_slug:
            return None
        from adhd_hub.store import slugify

        return f"project:{slugify(thread.project_slug)}"

    def _labels_for_thread(self, thread: Thread) -> list[str]:
        labels = list(self.config.issue_labels or [])
        pl = self._project_label(thread)
        if pl and pl not in labels:
            labels.append(pl)
        return labels

    def _create_issue(self, client: httpx.Client, thread: Thread) -> dict[str, Any]:
        labels = self._labels_for_thread(thread)
        self._ensure_labels(client, labels)
        body = {
            "title": f"[ADHD] {thread.summary[:200]}",
            "body": self._issue_body(thread),
            "labels": labels,
        }
        resp = client.post(self._issues_url(), headers=self._headers(), json=body)
        if resp.status_code >= 400 and labels:
            log.warning(
                "create issue with labels failed (%s); retrying without labels",
                resp.status_code,
            )
            body = {
                "title": f"[ADHD] {thread.summary[:200]}",
                "body": self._issue_body(thread),
            }
            resp = client.post(self._issues_url(), headers=self._headers(), json=body)
        if resp.status_code >= 400:
            log.warning("create issue failed: %s %s", resp.status_code, resp.text[:300])
            resp.raise_for_status()
        data = resp.json()
        number = int(data["number"])
        self._meta_set(self._meta_key(thread.id), str(number))
        if thread.status in (ThreadStatus.done, ThreadStatus.dismissed):
            self._set_issue_state(client, number, closed=True)
        self._maybe_add_to_project(client, data)
        return {
            "created": True,
            "number": number,
            "url": data.get("html_url") or data.get("url"),
        }

    def _labels_url(self) -> str:
        return (
            f"{self.config.api_root()}/repos/{self.config.owner}/{self.config.repo}/labels"
        )

    def _ensure_labels(self, client: httpx.Client, labels: list[str] | None = None) -> None:
        for name in labels if labels is not None else self.config.issue_labels:
            get = client.get(
                f"{self._labels_url()}/{name}",
                headers=self._headers(),
            )
            if get.status_code == 200:
                continue
            create = client.post(
                self._labels_url(),
                headers=self._headers(),
                json={
                    "name": name,
                    "color": "0f766e",
                    "description": "ADHD Progress Hub",
                },
            )
            if create.status_code >= 400 and create.status_code not in (409, 422):
                log.warning(
                    "ensure label %s failed: %s %s",
                    name,
                    create.status_code,
                    create.text[:200],
                )

    def _update_issue(
        self, client: httpx.Client, number: int, thread: Thread
    ) -> dict[str, Any]:
        labels = self._labels_for_thread(thread)
        self._ensure_labels(client, labels)
        current_body = ""
        get = client.get(self._issue_url(number), headers=self._headers())
        if get.status_code < 400:
            current_body = get.json().get("body") or ""
        hub_owns = self.is_wholly_hub_owned_body(current_body)
        payload: dict[str, Any] = {
            "body": self.merge_issue_body(current_body, thread),
            "state": "closed"
            if thread.status in (ThreadStatus.done, ThreadStatus.dismissed)
            else "open",
            "labels": labels,
        }
        # Only Hub-owned mirrors may rewrite the issue title.
        if hub_owns or not current_body.strip():
            payload["title"] = f"[ADHD] {thread.summary[:200]}"
        resp = client.patch(self._issue_url(number), headers=self._headers(), json=payload)
        if resp.status_code >= 400:
            # Retry without labels if forge rejects
            payload.pop("labels", None)
            resp = client.patch(
                self._issue_url(number), headers=self._headers(), json=payload
            )
        if resp.status_code >= 400:
            log.warning("update issue failed: %s %s", resp.status_code, resp.text[:300])
            resp.raise_for_status()
        data = resp.json()
        return {
            "updated": True,
            "number": number,
            "url": data.get("html_url") or data.get("url"),
            "hub_owned_body": hub_owns or not current_body.strip(),
        }

    def _set_issue_state(self, client: httpx.Client, number: int, *, closed: bool) -> None:
        resp = client.patch(
            self._issue_url(number),
            headers=self._headers(),
            json={"state": "closed" if closed else "open"},
        )
        if resp.status_code >= 400:
            log.warning("set issue state failed: %s", resp.text[:200])

    @staticmethod
    def is_wholly_hub_owned_body(body: str | None) -> bool:
        """True when the issue body is entirely Hub-generated (safe to replace)."""
        text = (body or "").strip()
        if not text:
            return True
        if STATUS_START in text and STATUS_END in text:
            before, rest = text.split(STATUS_START, 1)
            _mid, after = rest.split(STATUS_END, 1)
            return not before.strip() and not after.strip()
        # Legacy Hub-created bodies (pre-status markers).
        return text.startswith(("**ADHD Hub thread**", "### ADHD Hub"))

    @classmethod
    def upsert_status_block(cls, existing: str | None, block: str) -> str:
        """Replace or insert the Hub-managed status block; preserve other content."""
        text = existing or ""
        block = block.strip()
        if STATUS_START in text and STATUS_END in text:
            before, remainder = text.split(STATUS_START, 1)
            _old, after = remainder.split(STATUS_END, 1)
            return f"{before}{block}{after}"
        if cls.is_wholly_hub_owned_body(text):
            return block + "\n"
        # External / inbox-authored: keep user text; Hub status at the top.
        user = text.strip()
        if not user:
            return block + "\n"
        return f"{block}\n\n{user}\n"

    def render_status_block(self, thread: Thread) -> str:
        """Thread-scoped Hub status (not project-wide PROGRESS.md)."""
        lines = [
            STATUS_START,
            "### ADHD Hub",
            "",
            f"**Title:** {thread.summary.strip() or '(untitled)'}",
            "",
        ]
        if thread.goal:
            lines.extend(["**Goal**", "", thread.goal.strip(), ""])
        if thread.focus:
            lines.extend(["**Focus**", "", thread.focus.strip(), ""])
        next_steps = list(thread.next_steps or [])[:3]
        if next_steps:
            lines.append("**Next**")
            lines.append("")
            for i, step in enumerate(next_steps, start=1):
                lines.append(f"{i}. {step}")
            lines.append("")
        if thread.blocked_reason and thread.blocked_reason.strip():
            lines.extend(["**Blocked**", "", thread.blocked_reason.strip(), ""])
        if thread.resume_step and thread.resume_step.strip():
            lines.extend(["**Resume**", "", thread.resume_step.strip(), ""])
        lines.extend(
            [
                f"- status: `{thread.status.value}`",
                f"- Hub thread: `{thread.id}`",
                f"- Project: `{thread.project_slug or '-'}`",
                f"- Updated: `{thread.updated_at.isoformat()}`",
            ]
        )
        if thread.source_tool or thread.origin:
            lines.append(f"- source: `{thread.source_tool or thread.origin}`")
        if thread.project_slug:
            prog_url = self.config.file_web_url(
                f"projects/{thread.project_slug}/PROGRESS.md"
            )
            if prog_url:
                lines.append(f"- Project progress (optional): [{prog_url}]({prog_url})")
        lines.extend(["", STATUS_END])
        return "\n".join(lines)

    def _issue_body(self, thread: Thread) -> str:
        """Full body for Hub-created issues (wholly Hub-owned)."""
        return self.render_status_block(thread).rstrip() + "\n"

    def merge_issue_body(self, existing: str | None, thread: Thread) -> str:
        block = self.render_status_block(thread)
        if self.is_wholly_hub_owned_body(existing):
            return block.rstrip() + "\n"
        return self.upsert_status_block(existing, block)

    def _maybe_add_to_project(self, client: httpx.Client, issue: dict[str, Any]) -> None:
        try:
            if self.config.provider == ForgeProvider.github and self.config.project_number:
                self._github_add_project_v2(client, issue)
            elif self.config.provider == ForgeProvider.gitea and self.config.project_id:
                self._gitea_add_project(client, issue)
        except Exception:
            log.exception("project attach failed (issue still synced)")

    def _github_add_project_v2(self, client: httpx.Client, issue: dict[str, Any]) -> None:
        node_id = issue.get("node_id")
        if not node_id:
            return
        q = """
        query($login:String!, $number:Int!) {
          user(login:$login) { projectV2(number:$number) { id } }
          organization(login:$login) { projectV2(number:$number) { id } }
        }
        """
        resp = client.post(
            "https://api.github.com/graphql",
            headers=self._headers(),
            json={
                "query": q,
                "variables": {
                    "login": self.config.owner,
                    "number": self.config.project_number,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        project = (data.get("user") or {}).get("projectV2") or (
            (data.get("organization") or {}).get("projectV2")
        )
        if not project:
            log.warning(
                "GitHub project #%s not found for %s",
                self.config.project_number,
                self.config.owner,
            )
            return
        mutation = """
        mutation($project:ID!, $content:ID!) {
          addProjectV2ItemById(input:{projectId:$project, contentId:$content}) {
            item { id }
          }
        }
        """
        m = client.post(
            "https://api.github.com/graphql",
            headers=self._headers(),
            json={
                "query": mutation,
                "variables": {"project": project["id"], "content": node_id},
            },
        )
        if m.status_code >= 400:
            log.warning("addProjectV2ItemById failed: %s", m.text[:300])

    def _gitea_add_project(self, client: httpx.Client, issue: dict[str, Any]) -> None:
        number = issue.get("number")
        pid = self.config.project_id
        if not number or not pid:
            return
        urls = [
            f"{self.config.api_root()}/repos/{self.config.owner}/{self.config.repo}/issues/{number}/projects/{pid}",
            f"{self.config.api_root()}/projects/{pid}/issues",
        ]
        for url in urls:
            resp = client.post(
                url,
                headers=self._headers(),
                json={
                    "index": number,
                    "owner": self.config.owner,
                    "repo": self.config.repo,
                },
            )
            if resp.status_code < 400:
                return
        log.warning("Gitea project attach failed for issue %s", number)

    # --- Cloud-agent inbox: forge issues → Hub threads ---

    def _hub_label(self) -> str:
        labels = self.config.issue_labels or ["adhd-hub"]
        return labels[0]

    def _synced_label(self) -> str:
        return (self.config.board_inbox_synced_label or "adhd-hub-synced").strip()

    def _allowed_authors(self) -> set[str]:
        return {
            name.casefold()
            for name in (self.config.board_inbox_authors or [])
            if isinstance(name, str) and name.strip()
        }

    @staticmethod
    def _issue_author_login(raw: dict[str, Any]) -> str | None:
        user = raw.get("user")
        if not isinstance(user, dict):
            return None
        for key in ("login", "username", "name"):
            value = user.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def title_matches_inbox_prefix(title: str | None) -> bool:
        """True when the issue title starts with ``[ADHD]`` (case-insensitive)."""
        if not isinstance(title, str):
            return False
        return bool(_INBOX_TITLE_PREFIX.match(title))

    @staticmethod
    def _issue_label_names(raw: dict[str, Any]) -> set[str]:
        names: set[str] = set()
        for lab in raw.get("labels") or []:
            name = lab.get("name") if isinstance(lab, dict) else str(lab)
            if isinstance(name, str) and name:
                names.add(name)
        return names

    def _matches_inbox_selector(
        self, raw: dict[str, Any], *, hub_label: str, names: set[str]
    ) -> bool:
        """Hub label OR ``[ADHD]`` title prefix (label is optional)."""
        if hub_label and hub_label in names:
            return True
        title = raw.get("title")
        return self.title_matches_inbox_prefix(title if isinstance(title, str) else None)

    def list_inbox_issues(self, *, state: str = "open", limit: int = 50) -> list[dict[str, Any]]:
        """List open forge issues for the cloud mailbox.

        An issue matches when the author is allowlisted **and** either:

        - it has the configured hub label (``adhd-hub`` by default), or
        - its title starts with ``[ADHD]`` (case-insensitive; optional
          whitespace after ``]``).

        Listing strategy: ``GET /repos/{owner}/{repo}/issues?state=open`` with
        pagination, then filter locally. GitHub uses ``per_page=100`` (max 10
        pages). Gitea uses ``limit=50`` and ``type=issues`` (Gitea's page-size
        max). We do **not** pass GitHub's ``labels=`` query (that hid
        title-only issues) and we do **not** use Search/GraphQL (Search is
        eventually consistent; GraphQL needs extra scope).

        Fail closed: empty ``board_inbox_authors`` yields no candidates.
        """
        if not (self.config.enabled() and self.config.board_enabled):
            return []
        allowed = self._allowed_authors()
        if not allowed:
            log.info("forge inbox: skipping list — board_inbox_authors is empty (fail closed)")
            return []
        hub_label = self._hub_label()
        synced = self._synced_label()
        out: list[dict[str, Any]] = []
        with httpx.Client(timeout=30.0) as client:
            for page in range(1, _INBOX_LIST_MAX_PAGES + 1):
                params: dict[str, Any] = {"state": state, "page": page}
                if self.config.provider == ForgeProvider.gitea:
                    page_size = _INBOX_GITEA_PER_PAGE
                    params["limit"] = page_size
                    params["type"] = "issues"
                else:
                    page_size = _INBOX_LIST_PER_PAGE
                    params["per_page"] = page_size
                resp = client.get(self._issues_url(), headers=self._headers(), params=params)
                if resp.status_code >= 400:
                    log.warning(
                        "list inbox issues failed: %s %s", resp.status_code, resp.text[:300]
                    )
                    resp.raise_for_status()
                items = resp.json()
                if not isinstance(items, list) or not items:
                    break
                for raw in items:
                    if not isinstance(raw, dict):
                        continue
                    # GitHub PRs include a dict; Gitea issues serialize pull_request: null.
                    if raw.get("pull_request") is not None:
                        continue
                    author = self._issue_author_login(raw)
                    if not author or author.casefold() not in allowed:
                        continue
                    names = self._issue_label_names(raw)
                    if synced and synced in names:
                        continue
                    if not self._matches_inbox_selector(raw, hub_label=hub_label, names=names):
                        continue
                    out.append(raw)
                    if len(out) >= limit:
                        return out
                if len(items) < page_size:
                    break
        return out

    def mark_issue_imported(
        self,
        number: int,
        *,
        thread_id: str,
        thread: Thread | None = None,
    ) -> dict[str, Any]:
        """Close the forge issue and stamp the synced label — never delete."""
        synced = self._synced_label()
        with httpx.Client(timeout=30.0) as client:
            self._ensure_labels(client, [synced] if synced else None)
            labels = list(self.config.issue_labels or [])
            if synced and synced not in labels:
                labels.append(synced)
            payload: dict[str, Any] = {
                "state": "closed",
                "state_reason": "completed",
            }
            # Fetch current labels so we preserve project:* etc.
            get = client.get(self._issue_url(number), headers=self._headers())
            if get.status_code < 400:
                current = {
                    (lab.get("name") if isinstance(lab, dict) else str(lab))
                    for lab in (get.json().get("labels") or [])
                }
                labels = sorted({*current, *labels})
            if labels:
                payload["labels"] = labels
            # Upsert Hub status block; preserve user-authored content outside markers.
            if get.status_code < 400:
                body = get.json().get("body") or ""
                if thread is not None:
                    payload["body"] = self.merge_issue_body(body, thread)
                else:
                    from datetime import UTC, datetime

                    from adhd_hub.models import EnergyLevel

                    stub = Thread(
                        id=thread_id,
                        summary=f"Hub thread `{thread_id}`",
                        status=ThreadStatus.done,
                        energy=EnergyLevel.unknown,
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                    payload["body"] = self.merge_issue_body(body, stub)
            resp = client.patch(self._issue_url(number), headers=self._headers(), json=payload)
            if resp.status_code >= 400 and "state_reason" in payload:
                payload.pop("state_reason", None)
                resp = client.patch(self._issue_url(number), headers=self._headers(), json=payload)
            if resp.status_code >= 400:
                log.warning(
                    "mark issue imported failed: %s %s",
                    resp.status_code,
                    resp.text[:300],
                )
                resp.raise_for_status()
        return {"closed": True, "number": number, "thread_id": thread_id, "label": synced}
