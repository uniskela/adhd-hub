from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import httpx

from adhd_hub.forge.config import ForgeConfig, ForgeProvider

log = logging.getLogger(__name__)


class WikiForgeSync:
    """Push/pull markdown wiki files via GitHub or Gitea Contents API."""

    def __init__(self, config: ForgeConfig) -> None:
        self.config = config

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

    def _contents_url(self, rel_path: str, *, at_repo_root: bool = False) -> str:
        owner, repo = self.config.owner, self.config.repo
        if at_repo_root:
            full = rel_path.lstrip("/")
        else:
            prefix = self.config.wiki_path.strip("/")
            full = f"{prefix}/{rel_path.lstrip('/')}" if prefix else rel_path.lstrip("/")
        return f"{self.config.api_root()}/repos/{owner}/{repo}/contents/{full}"

    def _get_file(
        self, client: httpx.Client, rel_path: str, *, at_repo_root: bool = False
    ) -> dict[str, Any] | None:
        url = self._contents_url(rel_path, at_repo_root=at_repo_root)
        resp = client.get(
            url, headers=self._headers(), params={"ref": self.config.wiki_branch}
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else None

    def _put_contents(
        self,
        rel_path: str,
        content: str,
        message: str,
        *,
        at_repo_root: bool = False,
    ) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            existing = self._get_file(client, rel_path, at_repo_root=at_repo_root)
            payload: dict[str, Any] = {
                "message": message,
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "branch": self.config.wiki_branch,
            }
            if existing and existing.get("sha"):
                payload["sha"] = existing["sha"]
            resp = client.put(
                self._contents_url(rel_path, at_repo_root=at_repo_root),
                headers=self._headers(),
                json=payload,
            )
            if resp.status_code >= 400:
                log.warning("wiki put failed %s: %s", resp.status_code, resp.text[:300])
                resp.raise_for_status()
            return resp.json()

    def put_file(self, rel_path: str, content: str, message: str) -> dict[str, Any]:
        if not (self.config.enabled() and self.config.wiki_enabled):
            return {"skipped": True, "reason": "wiki_sync_disabled"}
        return self._put_contents(rel_path, content, message, at_repo_root=False)

    def put_file_at_repo_root(
        self, rel_path: str, content: str, message: str
    ) -> dict[str, Any]:
        """Write under repo root (ignores wiki_path). Used for primary-memory README etc."""
        if not (self.config.enabled() and self.config.wiki_enabled):
            return {"skipped": True, "reason": "wiki_sync_disabled"}
        return self._put_contents(rel_path, content, message, at_repo_root=True)

    def delete_file(self, rel_path: str, *, message: str | None = None) -> dict[str, Any]:
        if not (self.config.enabled() and self.config.wiki_enabled):
            return {"skipped": True, "reason": "wiki_sync_disabled"}
        with httpx.Client(timeout=30.0) as client:
            existing = self._get_file(client, rel_path, at_repo_root=False)
            if not existing or not existing.get("sha"):
                return {"deleted": False, "missing": True, "path": rel_path}
            payload = {
                "message": message or f"adhd-hub: delete {rel_path}",
                "sha": existing["sha"],
                "branch": self.config.wiki_branch,
            }
            resp = client.request(
                "DELETE",
                self._contents_url(rel_path, at_repo_root=False),
                headers=self._headers(),
                json=payload,
            )
            if resp.status_code >= 400:
                log.warning("wiki delete failed %s: %s", resp.status_code, resp.text[:300])
                resp.raise_for_status()
            return {"deleted": True, "path": rel_path}

    def move_file(
        self,
        old_rel: str,
        new_rel: str,
        content: str,
        *,
        message: str | None = None,
    ) -> dict[str, Any]:
        """PUT new path, verify, then DELETE old (retry-safe)."""
        if not (self.config.enabled() and self.config.wiki_enabled):
            return {"skipped": True, "reason": "wiki_sync_disabled"}
        put = self.put_file(
            new_rel,
            content,
            message or f"adhd-hub: move {old_rel} → {new_rel}",
        )
        deleted = self.delete_file(
            old_rel,
            message=message or f"adhd-hub: remove old path {old_rel}",
        )
        return {"put": put, "deleted": deleted, "from": old_rel, "to": new_rel}

    def push_wiki_tree(self, wiki_dir: Path) -> dict[str, Any]:
        if not (self.config.enabled() and self.config.wiki_enabled):
            return {"skipped": True, "reason": "wiki_sync_disabled"}
        uploaded: list[str] = []
        errors: list[str] = []
        index = wiki_dir / "INDEX.md"
        if index.is_file():
            try:
                self.put_file(
                    "INDEX.md",
                    index.read_text(encoding="utf-8"),
                    "adhd-hub: update INDEX.md",
                )
                uploaded.append("INDEX.md")
            except Exception as exc:  # noqa: BLE001 — collect per-file sync errors
                errors.append(f"INDEX.md: {exc}")
        projects = wiki_dir / "projects"
        if projects.is_dir():
            for progress in projects.glob("*/PROGRESS.md"):
                slug = progress.parent.name
                rel = f"projects/{slug}/PROGRESS.md"
                try:
                    self.put_file(
                        rel,
                        progress.read_text(encoding="utf-8"),
                        f"adhd-hub: update {rel}",
                    )
                    uploaded.append(rel)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{rel}: {exc}")
        return {"uploaded": uploaded, "errors": errors}
