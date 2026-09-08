from __future__ import annotations

import logging
from typing import Any

import httpx

from adhd_hub.forge.config import ForgeConfig, ForgeProvider
from adhd_hub.models import Thread, ThreadStatus

log = logging.getLogger(__name__)


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
        # Optional: callable(project_slug) -> progress markdown | None
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
        payload: dict[str, Any] = {
            "title": f"[ADHD] {thread.summary[:200]}",
            "body": self._issue_body(thread),
            "state": "closed"
            if thread.status in (ThreadStatus.done, ThreadStatus.dismissed)
            else "open",
            "labels": labels,
        }
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
        }

    def _set_issue_state(self, client: httpx.Client, number: int, *, closed: bool) -> None:
        resp = client.patch(
            self._issue_url(number),
            headers=self._headers(),
            json={"state": "closed" if closed else "open"},
        )
        if resp.status_code >= 400:
            log.warning("set issue state failed: %s", resp.text[:200])

    def _issue_body(self, thread: Thread) -> str:
        parts = [
            f"**ADHD Hub thread** `{thread.id}`",
            "",
            f"- status: `{thread.status.value}`",
            f"- project: `{thread.project_slug or '-'}`",
            f"- source: `{thread.source_tool or thread.origin}`",
            f"- workspace: `{thread.workspace_path or '-'}`",
            "",
        ]
        if thread.project_slug:
            prog_url = self.config.file_web_url(
                f"projects/{thread.project_slug}/PROGRESS.md"
            )
            if prog_url:
                parts.extend(
                    [
                        f"- progress: [{prog_url}]({prog_url})",
                        "",
                    ]
                )
        parts.extend(
            [
                "### Summary",
                "",
                thread.summary.strip() or "(no summary)",
                "",
            ]
        )
        progress = None
        if self._progress_reader and thread.project_slug:
            try:
                progress = self._progress_reader(thread.project_slug)
            except Exception:
                log.exception("progress read failed for %s", thread.project_slug)
        if progress and progress.strip():
            # Keep issue bodies bounded for forge APIs
            text = progress.strip()
            if len(text) > 12000:
                text = text[:12000].rstrip() + "\n\n…(truncated; see hub wiki PROGRESS.md)"
            parts.extend(
                [
                    "### Progress log",
                    "",
                    text,
                    "",
                ]
            )
        else:
            parts.extend(
                [
                    "### Progress log",
                    "",
                    "_No PROGRESS.md yet — call `upsert_progress` from an agent or edit in hub `/ui`._",
                    "",
                ]
            )
        return "\n".join(parts)

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
