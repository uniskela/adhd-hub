from __future__ import annotations

import base64
import hashlib
import logging
from pathlib import Path
from typing import Any

import httpx

from adhd_hub.forge.config import ForgeConfig, ForgeProvider

log = logging.getLogger(__name__)


class WikiForgeSync:
    """Push/pull markdown wiki files via GitHub or Gitea Contents / Git Data APIs."""

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

    def _repo_api(self, suffix: str) -> str:
        owner, repo = self.config.owner, self.config.repo
        return f"{self.config.api_root()}/repos/{owner}/{repo}/{suffix.lstrip('/')}"

    def _full_path(self, rel_path: str, *, at_repo_root: bool = False) -> str:
        rel = rel_path.lstrip("/")
        if at_repo_root:
            return rel
        prefix = self.config.wiki_path.strip("/")
        return f"{prefix}/{rel}" if prefix else rel

    def _contents_url(self, rel_path: str, *, at_repo_root: bool = False) -> str:
        full = self._full_path(rel_path, at_repo_root=at_repo_root)
        return self._repo_api(f"contents/{full}")

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
        if not isinstance(data, dict):
            raise TypeError(f"unexpected Contents API payload for {rel_path}")
        return data

    def _decode_content(self, existing: dict[str, Any] | None) -> str | None:
        if not existing or existing.get("type") != "file":
            return None
        encoded = existing.get("content")
        if not isinstance(encoded, str):
            return None
        encoding = existing.get("encoding")
        if isinstance(encoding, str) and encoding.lower() != "base64":
            return None
        raw = "".join(encoded.split())
        try:
            return base64.b64decode(raw, validate=True).decode("utf-8")
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _git_blob_sha(content: str, length: int) -> str | None:
        raw = content.encode("utf-8")
        blob = f"blob {len(raw)}\0".encode() + raw
        if length == 40:
            return hashlib.sha1(blob).hexdigest()
        if length == 64:
            return hashlib.sha256(blob).hexdigest()
        return None

    def _remote_matches(
        self, existing: dict[str, Any], content: str, rel_path: str
    ) -> bool:
        if existing.get("type") != "file":
            raise RuntimeError(f"cannot compare non-file Contents API payload for {rel_path}")
        remote = self._decode_content(existing)
        if remote is not None:
            return remote == content

        sha = existing.get("sha")
        if isinstance(sha, str):
            normalized = sha.strip().lower()
            try:
                int(normalized, 16)
            except ValueError:
                normalized = ""
            expected = self._git_blob_sha(content, len(normalized))
            if expected is not None:
                return normalized == expected
        raise RuntimeError(f"cannot determine remote content for {rel_path}")

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
            if existing is not None and self._remote_matches(existing, content, rel_path):
                return {"skipped": True, "reason": "unchanged", "path": rel_path}
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
        uploaded = [] if put.get("skipped") else [new_rel]
        unchanged_files = [new_rel] if put.get("reason") == "unchanged" else []
        wrote = bool(uploaded or deleted.get("deleted"))
        return {
            "put": put,
            "deleted": deleted,
            "from": old_rel,
            "to": new_rel,
            "uploaded": uploaded,
            "unchanged_files": unchanged_files,
            "unchanged": not wrote,
        }

    def _collect_wiki_files(self, wiki_dir: Path) -> list[tuple[str, str]]:
        files: list[tuple[str, str]] = []
        index = wiki_dir / "INDEX.md"
        if index.is_file():
            files.append(("INDEX.md", index.read_text(encoding="utf-8")))
        projects = wiki_dir / "projects"
        if projects.is_dir():
            for progress in sorted(projects.glob("*/PROGRESS.md")):
                slug = progress.parent.name
                rel = f"projects/{slug}/PROGRESS.md"
                files.append((rel, progress.read_text(encoding="utf-8")))
        return files

    def _changed_files(
        self, client: httpx.Client, files: list[tuple[str, str]]
    ) -> tuple[list[tuple[str, str]], list[str]]:
        changed: list[tuple[str, str]] = []
        unchanged: list[str] = []
        for rel, content in files:
            existing = self._get_file(client, rel, at_repo_root=False)
            if existing is not None and self._remote_matches(existing, content, rel):
                unchanged.append(rel)
                continue
            changed.append((rel, content))
        return changed, unchanged

    def _branch_head(self, client: httpx.Client) -> tuple[str, str]:
        """Return (commit_sha, tree_sha) for wiki_branch."""
        branch = self.config.wiki_branch or "main"
        resp = client.get(
            self._repo_api(f"branches/{branch}"),
            headers=self._headers(),
        )
        if resp.status_code == 404:
            for suffix in (f"git/ref/heads/{branch}", f"git/refs/heads/{branch}"):
                alt = client.get(self._repo_api(suffix), headers=self._headers())
                if alt.status_code >= 400:
                    continue
                data = alt.json()
                if isinstance(data, list) and data:
                    data = data[0]
                if isinstance(data, dict):
                    obj = data.get("object") if isinstance(data.get("object"), dict) else data
                    sha = (obj or {}).get("sha")
                    if isinstance(sha, str) and sha:
                        commit = client.get(
                            self._repo_api(f"git/commits/{sha}"),
                            headers=self._headers(),
                        )
                        commit.raise_for_status()
                        cdata = commit.json()
                        tree = (cdata.get("tree") or {}).get("sha")
                        if isinstance(tree, str) and tree:
                            return sha, tree
            resp.raise_for_status()
        resp.raise_for_status()
        data = resp.json()
        commit = data.get("commit") if isinstance(data, dict) else None
        if not isinstance(commit, dict):
            raise TypeError(f"unexpected branch payload for {branch}")
        commit_sha = commit.get("sha")
        nested = commit.get("commit") if isinstance(commit.get("commit"), dict) else {}
        tree = nested.get("tree") if isinstance(nested, dict) else None
        if tree is None:
            tree = commit.get("tree")
        tree_sha = tree.get("sha") if isinstance(tree, dict) else None
        if not (isinstance(commit_sha, str) and isinstance(tree_sha, str)):
            detail = client.get(
                self._repo_api(f"git/commits/{commit_sha}"),
                headers=self._headers(),
            )
            detail.raise_for_status()
            cdata = detail.json()
            tree_sha = (cdata.get("tree") or {}).get("sha")
            commit_sha = cdata.get("sha") or commit_sha
        if not (isinstance(commit_sha, str) and isinstance(tree_sha, str)):
            raise TypeError(f"could not resolve head for branch {branch}")
        return commit_sha, tree_sha

    def _commit_files_batch(
        self,
        client: httpx.Client,
        files: list[tuple[str, str]],
        message: str,
    ) -> dict[str, Any]:
        """One Git commit for many wiki files (Git Data API — GitHub + Gitea)."""
        parent_sha, base_tree = self._branch_head(client)
        tree_items: list[dict[str, Any]] = []
        for rel, content in files:
            blob_resp = client.post(
                self._repo_api("git/blobs"),
                headers=self._headers(),
                json={
                    "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                    "encoding": "base64",
                },
            )
            if blob_resp.status_code >= 400:
                log.warning(
                    "wiki blob create failed %s: %s",
                    blob_resp.status_code,
                    blob_resp.text[:300],
                )
                blob_resp.raise_for_status()
            blob = blob_resp.json()
            blob_sha = blob.get("sha")
            if not isinstance(blob_sha, str):
                raise TypeError(f"blob create missing sha for {rel}")
            tree_items.append(
                {
                    "path": self._full_path(rel, at_repo_root=False),
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_sha,
                }
            )

        tree_resp = client.post(
            self._repo_api("git/trees"),
            headers=self._headers(),
            json={"base_tree": base_tree, "tree": tree_items},
        )
        if tree_resp.status_code >= 400:
            log.warning(
                "wiki tree create failed %s: %s",
                tree_resp.status_code,
                tree_resp.text[:300],
            )
            tree_resp.raise_for_status()
        new_tree = tree_resp.json().get("sha")
        if not isinstance(new_tree, str):
            raise TypeError("tree create missing sha")

        commit_resp = client.post(
            self._repo_api("git/commits"),
            headers=self._headers(),
            json={
                "message": message,
                "tree": new_tree,
                "parents": [parent_sha],
            },
        )
        if commit_resp.status_code >= 400:
            log.warning(
                "wiki commit create failed %s: %s",
                commit_resp.status_code,
                commit_resp.text[:300],
            )
            commit_resp.raise_for_status()
        new_commit = commit_resp.json().get("sha")
        if not isinstance(new_commit, str):
            raise TypeError("commit create missing sha")

        branch = self.config.wiki_branch or "main"
        ref_payload = {"sha": new_commit, "force": False}
        ref_resp = client.patch(
            self._repo_api(f"git/refs/heads/{branch}"),
            headers=self._headers(),
            json=ref_payload,
        )
        if ref_resp.status_code == 404:
            ref_resp = client.post(
                self._repo_api("git/refs"),
                headers=self._headers(),
                json={"ref": f"refs/heads/{branch}", "sha": new_commit},
            )
        if ref_resp.status_code >= 400:
            log.warning(
                "wiki ref update failed %s: %s",
                ref_resp.status_code,
                ref_resp.text[:300],
            )
            ref_resp.raise_for_status()
        return {
            "commit_sha": new_commit,
            "uploaded": [rel for rel, _ in files],
            "batched": True,
            "message": message,
        }

    def _push_files_sequential(
        self, files: list[tuple[str, str]]
    ) -> dict[str, Any]:
        uploaded: list[str] = []
        unchanged_files: list[str] = []
        errors: list[str] = []
        for rel, content in files:
            try:
                result = self.put_file(rel, content, f"adhd-hub: update {rel}")
                if result.get("reason") == "unchanged":
                    unchanged_files.append(rel)
                else:
                    uploaded.append(rel)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{rel}: {exc}")
        return {
            "uploaded": uploaded,
            "unchanged_files": unchanged_files,
            "errors": errors,
            "batched": False,
            "unchanged": not uploaded and not errors,
        }

    def push_wiki_tree(self, wiki_dir: Path) -> dict[str, Any]:
        """Push INDEX.md + projects/*/PROGRESS.md in one forge commit when possible."""
        if not (self.config.enabled() and self.config.wiki_enabled):
            return {"skipped": True, "reason": "wiki_sync_disabled"}
        files = self._collect_wiki_files(wiki_dir)
        if not files:
            return {
                "uploaded": [],
                "unchanged_files": [],
                "errors": [],
                "batched": True,
                "unchanged": True,
            }

        with httpx.Client(timeout=60.0) as client:
            try:
                changed, unchanged_files = self._changed_files(client, files)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "wiki change detection failed (%s); falling back to per-file Contents API",
                    exc,
                )
                sequential = self._push_files_sequential(files)
                sequential["fallback_reason"] = "change_detection_failed"
                sequential["checked"] = len(files)
                return sequential

            if not changed:
                return {
                    "uploaded": [],
                    "unchanged_files": unchanged_files,
                    "errors": [],
                    "batched": True,
                    "unchanged": True,
                    "checked": len(files),
                }

            n_progress = sum(1 for rel, _ in changed if rel.endswith("/PROGRESS.md"))
            has_index = any(rel == "INDEX.md" for rel, _ in changed)
            parts: list[str] = []
            if has_index:
                parts.append("INDEX.md")
            if n_progress:
                parts.append(
                    f"{n_progress} PROGRESS.md"
                    if n_progress != 1
                    else "1 PROGRESS.md"
                )
            if not parts:
                parts.append(f"{len(changed)} file(s)")
            message = f"adhd-hub: sync wiki ({', '.join(parts)})"

            try:
                result = self._commit_files_batch(client, changed, message)
                result["errors"] = []
                result["unchanged_files"] = unchanged_files
                result["unchanged"] = False
                result["checked"] = len(files)
                return result
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "batched wiki commit failed (%s); falling back to per-file Contents API",
                    exc,
                )

        sequential = self._push_files_sequential(changed)
        sequential["unchanged_files"] = unchanged_files + sequential["unchanged_files"]
        sequential["fallback_reason"] = "batch_commit_failed"
        sequential["checked"] = len(files)
        return sequential

    def _list_dir(
        self, client: httpx.Client, rel_path: str
    ) -> list[dict[str, Any]]:
        """List a directory via Contents API (wiki_path-aware)."""
        owner, repo = self.config.owner, self.config.repo
        prefix = self.config.wiki_path.strip("/")
        rel = rel_path.strip("/")
        if prefix and rel:
            full = f"{prefix}/{rel}"
        elif prefix:
            full = prefix
        else:
            full = rel
        if full:
            url = f"{self.config.api_root()}/repos/{owner}/{repo}/contents/{full}"
        else:
            url = f"{self.config.api_root()}/repos/{owner}/{repo}/contents"
        resp = client.get(
            url, headers=self._headers(), params={"ref": self.config.wiki_branch}
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        return []

    def read_file_text(self, rel_path: str) -> str | None:
        """Fetch a single markdown file from the forge wiki tree."""
        if not (self.config.enabled() and self.config.wiki_enabled):
            return None
        with httpx.Client(timeout=30.0) as client:
            existing = self._get_file(client, rel_path, at_repo_root=False)
            return self._decode_content(existing)

    def list_remote_project_slugs(self) -> dict[str, Any]:
        """Scan forge for projects/*/ directories that look like hub wiki pages."""
        if not (self.config.enabled() and self.config.wiki_enabled):
            return {"skipped": True, "reason": "wiki_sync_disabled", "projects": []}
        projects: list[dict[str, Any]] = []
        errors: list[str] = []
        with httpx.Client(timeout=30.0) as client:
            try:
                entries = self._list_dir(client, "projects")
            except Exception as exc:  # noqa: BLE001
                return {
                    "skipped": False,
                    "projects": [],
                    "errors": [f"projects/: {exc}"],
                }
            for entry in entries:
                if entry.get("type") != "dir":
                    continue
                slug = str(entry.get("name") or "").strip()
                if not slug or slug.startswith("."):
                    continue
                rel = f"projects/{slug}/PROGRESS.md"
                has_progress = False
                try:
                    progress = self._get_file(client, rel, at_repo_root=False)
                    has_progress = bool(
                        progress and progress.get("type") == "file"
                    )
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{rel}: {exc}")
                projects.append(
                    {
                        "slug": slug,
                        "has_progress": has_progress,
                        "path": rel if has_progress else f"projects/{slug}/",
                    }
                )
        return {"skipped": False, "projects": projects, "errors": errors}
