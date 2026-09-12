"""Forge orchestration extracted from HubService."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from adhd_hub.forge.board_sync import BoardForgeSync
from adhd_hub.forge.config import (
    ForgeConfig,
    ForgeProvider,
    config_from_profile,
    forge_from_settings,
    load_forge_config,
    profile_matches_identity_host,
)
from adhd_hub.forge.config import (
    save_forge_config as persist_forge_config,
)
from adhd_hub.forge.wiki_sync import WikiForgeSync
from adhd_hub.models import Thread, ThreadStatus, ThreadUpsert
from adhd_hub.store import item_id
from adhd_hub.work_identity import thread_has_external_identity

if TYPE_CHECKING:
    from adhd_hub.service import HubService

log = logging.getLogger(__name__)


class ForgeFacade:
    def __init__(self, hub: HubService) -> None:
        self._hub = hub

    def forge_config(self, project_slug: str | None = None) -> ForgeConfig:
        base = load_forge_config(
            self._hub.settings.data_dir, env_defaults=forge_from_settings(self._hub.settings)
        )
        data = base.model_dump()
        # Primary memory repos mirror at repo root (projects/<slug>/…)
        if data.get("primary_memory_repo") and str(data.get("wiki_path") or "").strip("/") in (
            "",
            "adhd-hub/wiki",
        ):
            data["wiki_path"] = ""
            base = ForgeConfig.model_validate(data)
        else:
            base = ForgeConfig.model_validate(data)
        if not project_slug:
            return base
        proj = self._hub.store.get_project(project_slug)
        if not proj:
            return base
        profile = base.profile_by_id(proj.forge_connection_profile_id)
        if profile is None:
            # Local-only / unbound: never leak default-profile credentials.
            return base.model_copy(
                update={
                    "provider": ForgeProvider.none,
                    "token": "",
                    "owner": proj.forge_owner or "",
                    "repo": proj.forge_repo or "",
                    "project_id": proj.forge_project_id,
                    "wiki_path": (
                        proj.forge_wiki_path
                        if proj.forge_wiki_path is not None
                        else base.wiki_path
                    ),
                }
            )
        cfg = config_from_profile(base, profile)
        updates: dict = {}
        if proj.forge_owner:
            updates["owner"] = proj.forge_owner
        if proj.forge_repo:
            updates["repo"] = proj.forge_repo
        if proj.forge_wiki_path is not None:
            updates["wiki_path"] = proj.forge_wiki_path
        if proj.forge_project_id:
            updates["project_id"] = proj.forge_project_id
        return cfg.model_copy(update=updates) if updates else cfg

    def resolve_credentials_for_identity(self, identity) -> ForgeConfig | None:
        """Return forge config whose token applies to the pinned identity host."""
        from adhd_hub.work_identity import ExternalIdentity

        if not isinstance(identity, ExternalIdentity):
            return None
        base = load_forge_config(
            self._hub.settings.data_dir, env_defaults=forge_from_settings(self._hub.settings)
        )
        for profile in base.connection_profiles:
            if profile_matches_identity_host(profile, identity):
                return config_from_profile(base, profile)
        return None

    def operational_forge_config(self, project_slug: str | None = None) -> ForgeConfig:
        """Config for intentional forge ops (link/promote/wiki board).

        Bound projects use their profile. Unbound projects fall back to the
        default Hub connection so explicit operator actions still work; discovery
        remains gated on forge_connection_profile_id via forge_config().
        """
        if not project_slug:
            return self.forge_config()
        pcfg = self.forge_config(project_slug)
        if pcfg.provider != ForgeProvider.none and pcfg.token:
            return pcfg
        return self.forge_config()

    def save_forge_config(self, config: ForgeConfig) -> ForgeConfig:
        # Persist empty wiki_path for primary memory instead of re-defaulting
        if config.primary_memory_repo and config.wiki_path.strip("/") == "adhd-hub/wiki":
            config = config.model_copy(update={"wiki_path": ""})
        persist_forge_config(self._hub.settings.data_dir, config)
        return config

    def confident_forge_target(self, project_slug: str | None) -> dict[str, str] | None:
        """Return provider/host/owner/repo only when offline evidence is unambiguous."""
        from adhd_hub.work_identity import WorkSource, host_from_forge_browse_root

        base = load_forge_config(
            self._hub.settings.data_dir, env_defaults=forge_from_settings(self._hub.settings)
        )
        if base.provider not in (ForgeProvider.github, ForgeProvider.gitea):
            return None
        proj = self._hub.store.get_project(project_slug) if project_slug else None
        if proj:
            has_o = bool((proj.forge_owner or "").strip())
            has_r = bool((proj.forge_repo or "").strip())
            if has_o ^ has_r:
                return None
            # Prefer bound profile host when set; else default (legacy global) profile.
            bound = base.profile_by_id(proj.forge_connection_profile_id)
            if bound is not None:
                cfg = config_from_profile(base, bound)
                owner = (proj.forge_owner or "").strip() or cfg.owner
                repo = (proj.forge_repo or "").strip() or cfg.repo
                provider = WorkSource(cfg.provider.value)
                host = host_from_forge_browse_root(provider, cfg.web_browse_root())
            else:
                owner = (proj.forge_owner or "").strip() or base.owner
                repo = (proj.forge_repo or "").strip() or base.repo
                provider = WorkSource(base.provider.value)
                host = host_from_forge_browse_root(provider, base.web_browse_root())
        else:
            owner, repo = base.owner, base.repo
            provider = WorkSource(base.provider.value)
            host = host_from_forge_browse_root(provider, base.web_browse_root())
        if not (owner and repo and host):
            return None
        return {
            "provider": provider.value,
            "host": host,
            "owner": owner,
            "repo": repo,
        }

    def _meta_set_with_identity(self, cfg: ForgeConfig):
        def meta_set(key: str, value: str | dict) -> None:
            if not (
                isinstance(key, str)
                and key.startswith("forge_issue:")
                and str(value).isdigit()
            ):
                self._hub.store.set_meta(key, value)
                return
            thread_id = key.removeprefix("forge_issue:")
            number = int(value)
            thread = self._hub.store.get_thread(thread_id)
            if thread is not None and thread_has_external_identity(thread):
                if thread.external_issue_number == number:
                    # Idempotent: keep first-class identity; refresh legacy meta.
                    self._hub.store.set_meta(key, value)
                else:
                    log.warning(
                        "refuse forge remapping for thread %s: pinned #%s vs requested #%s",
                        thread_id,
                        thread.external_issue_number,
                        number,
                    )
                return
            attached = self._hub.store.try_attach_from_forge_config(
                thread_id,
                number,
                provider=cfg.provider.value,
                browse_root=cfg.web_browse_root(),
                owner=cfg.owner,
                repo=cfg.repo,
            )
            if attached is not None:
                return
            try:
                other = self._hub.store.get_thread_by_external_identity(
                    cfg.provider.value,
                    cfg.web_browse_root(),
                    cfg.owner,
                    cfg.repo,
                    number,
                )
            except ValueError:
                other = None
            if other is not None:
                log.warning(
                    "refuse forge_issue meta for thread %s: identity owned by %s",
                    thread_id,
                    other.id,
                )
                return
            # Not confident enough for first-class identity — legacy meta only.
            self._hub.store.set_meta(key, value)

        return meta_set

    def _board(self, cfg: ForgeConfig) -> BoardForgeSync:
        return BoardForgeSync(
            cfg,
            self._hub.store.get_meta,
            self._meta_set_with_identity(cfg),
            progress_reader=self._hub.wiki.read_progress,
        )

    def _refresh_forge_section(self, slug: str) -> None:
        cfg = self.forge_config(slug)
        progress_url = cfg.file_web_url(f"projects/{slug}/PROGRESS.md")
        issue_links: list[tuple[str, str]] = []
        for t in self._hub.store.list_threads(
            status=ThreadStatus.open, project_slug=slug, limit=50
        ):
            pub = self._hub.thread_public_dict(t)
            url = pub.get("forge_issue_url")
            num = pub.get("forge_issue_number")
            if url and num:
                issue_links.append((f"#{num} {t.summary[:60]}", url))
        self._hub.wiki.ensure_forge_section(
            slug, progress_url=progress_url, issue_links=issue_links
        )

    def _forge_after_thread(self, thread: Thread) -> dict:
        cfg = self.forge_config(thread.project_slug)
        out: dict = {}
        try:
            out["board"] = self._board(cfg).sync_thread(thread)
        except Exception as exc:
            log.exception("board sync failed")
            out["board"] = {"error": str(exc)}
        if thread.project_slug:
            try:
                self._refresh_forge_section(thread.project_slug)
            except Exception:
                log.exception("forge section refresh failed")
        try:
            # Global wiki tree still primary; per-project forge may point elsewhere
            # for board, while wiki uses configured wiki_path on that forge target.
            out["wiki"] = WikiForgeSync(cfg).push_wiki_tree(self._hub.settings.wiki_dir)
        except Exception as exc:
            log.exception("wiki sync failed")
            out["wiki"] = {"error": str(exc)}
        return out

    def sync_forge_now(self) -> dict:
        cfg = self.forge_config()
        from adhd_hub.forge.repo_sync import (
            credentials_apply_to_pinned,
            discover_issue_payloads,
            fetch_pinned_issue,
            fingerprint_for,
        )
        from adhd_hub.forge.scaffold import push_primary_scaffold
        from adhd_hub.work_identity import (
            WorkSource,
            normalize_external_identity,
            thread_has_external_identity,
        )

        scaffold = push_primary_scaffold(
            cfg, hub_ui_url=self._hub.settings.resolve_public_url()
        )
        wiki = WikiForgeSync(cfg).push_wiki_tree(self._hub.settings.wiki_dir)

        # 1) Reconcile all linked threads from pinned identity (not project forge gate).
        reconcile_results: list[dict] = []
        for thread in self._hub.store.list_externally_linked_threads(limit=500):
            if not thread_has_external_identity(thread):
                continue
            try:
                identity = normalize_external_identity(
                    thread.external_provider or WorkSource.github,
                    thread.external_host,
                    thread.external_owner or "",
                    thread.external_repo or "",
                    int(thread.external_issue_number or 0),
                )
            except ValueError as exc:
                reconcile_results.append(
                    {
                        "thread_id": thread.id,
                        "skipped": True,
                        "reason": "pinned_identity_unreachable",
                        "error": str(exc),
                    }
                )
                continue
            # Prefer host-matched profile credentials; never send wrong-host tokens.
            cred_cfg = self.resolve_credentials_for_identity(identity)
            if cred_cfg is None or not credentials_apply_to_pinned(cred_cfg, identity):
                reconcile_results.append(
                    {
                        "thread_id": thread.id,
                        "skipped": True,
                        "reason": "pinned_identity_unreachable",
                    }
                )
                continue
            fetched = fetch_pinned_issue(cred_cfg, identity)
            if isinstance(fetched, dict):
                reconcile_results.append({"thread_id": thread.id, **fetched})
                continue
            fp = fingerprint_for(fetched)
            applied = self._hub.store.apply_external_projection(
                thread.id,
                summary=fetched.title,
                external_issue_state=fetched.state,
                external_updated_at=fetched.updated_at,
                external_fingerprint=fp,
                external_labels=list(fetched.labels),
            )
            reconcile_results.append(
                {"thread_id": thread.id, "identity": identity.number, **applied}
            )

        # 2) Discovery for projects with a connection profile (plus default hub target).
        discovery_results: list[dict] = []
        seen_targets: set[tuple[str, str, str]] = set()
        projects = list(self._hub.store.list_projects())
        targets: list[tuple[str | None, ForgeConfig]] = [(None, cfg)]
        for proj in projects:
            if not proj.forge_connection_profile_id:
                continue
            pcfg = self.forge_config(proj.slug)
            targets.append((proj.slug, pcfg))
        for slug, tcfg in targets:
            if not (tcfg.enabled() and tcfg.board_enabled and tcfg.owner and tcfg.repo):
                continue
            key = (tcfg.provider.value, tcfg.owner.casefold(), tcfg.repo.casefold())
            if key in seen_targets:
                continue
            seen_targets.add(key)
            discovered = discover_issue_payloads(tcfg, limit=50)
            if isinstance(discovered, dict):
                discovery_results.append({"project_slug": slug, **discovered})
                continue
            imported: list[dict] = []
            skipped: list[dict] = []
            # Legacy forge_issue: meta is number-only; scoped to this discovery target.
            legacy_by_number = {
                str(value): key.removeprefix("forge_issue:")
                for key, value in self._hub.store.list_meta_prefix("forge_issue:").items()
            }
            for item in discovered:
                snap = item["snapshot"]
                # Multi-project claim check when creating new
                existing = self._hub.store.get_thread_by_external_identity(
                    snap.identity.provider,
                    snap.identity.host,
                    snap.identity.owner,
                    snap.identity.repo,
                    snap.identity.number,
                )
                if existing is None:
                    legacy_tid = legacy_by_number.get(str(snap.identity.number))
                    if legacy_tid:
                        legacy_thread = self._hub.store.get_thread(legacy_tid)
                        if legacy_thread is not None:
                            same_identity = False
                            if thread_has_external_identity(legacy_thread):
                                try:
                                    legacy_identity = normalize_external_identity(
                                        legacy_thread.external_provider or WorkSource.github,
                                        legacy_thread.external_host,
                                        legacy_thread.external_owner or "",
                                        legacy_thread.external_repo or "",
                                        int(legacy_thread.external_issue_number or 0),
                                    )
                                    same_identity = (
                                        legacy_identity.provider == snap.identity.provider
                                        and legacy_identity.host == snap.identity.host
                                        and legacy_identity.owner.casefold()
                                        == snap.identity.owner.casefold()
                                        and legacy_identity.repo.casefold()
                                        == snap.identity.repo.casefold()
                                        and legacy_identity.number == snap.identity.number
                                    )
                                except ValueError:
                                    same_identity = False
                                if same_identity:
                                    existing = legacy_thread
                            else:
                                # Heal only when this discovery target matches the
                                # legacy thread's resolvable forge target (not number alone).
                                lcfg = self.forge_config(legacy_thread.project_slug)
                                target_matches = (
                                    lcfg.enabled()
                                    and lcfg.owner
                                    and lcfg.repo
                                    and lcfg.owner.casefold() == snap.identity.owner.casefold()
                                    and lcfg.repo.casefold() == snap.identity.repo.casefold()
                                )
                                if target_matches:
                                    try:
                                        self._hub.store.attach_external_identity(
                                            legacy_tid, snap.identity, dual_write_meta=True
                                        )
                                        existing = self._hub.store.get_thread(legacy_tid)
                                    except (ValueError, KeyError) as exc:
                                        log.warning(
                                            "legacy forge_issue heal skipped for %s: %s",
                                            legacy_tid,
                                            exc,
                                        )
                if existing:
                    skipped.append(
                        {
                            "number": snap.identity.number,
                            "reason": "already_mapped",
                            "thread_id": existing.id,
                        }
                    )
                    continue
                claimants = [
                    p
                    for p in projects
                    if (p.forge_owner or tcfg.owner).casefold() == snap.identity.owner
                    and (p.forge_repo or tcfg.repo).casefold() == snap.identity.repo
                ]
                # Also count projects using global owner/repo without override
                if slug is None and not claimants:
                    claimants = [
                        p
                        for p in projects
                        if not (p.forge_owner and p.forge_repo)
                    ]
                project_slug = slug
                if project_slug is None:
                    if len(claimants) == 1:
                        project_slug = claimants[0].slug
                    elif len(claimants) > 1:
                        skipped.append(
                            {
                                "number": snap.identity.number,
                                "reason": "needs_project_disambiguation",
                            }
                        )
                        self.record_sync_review(
                            reason="needs_project_disambiguation",
                            payload={
                                "number": snap.identity.number,
                                "owner": snap.identity.owner,
                                "repo": snap.identity.repo,
                                "claimants": [p.slug for p in claimants],
                            },
                        )
                        continue
                    else:
                        project_slug = "inbox"
                assert project_slug is not None
                self._hub.store.ensure_project_for_slug(project_slug, title=project_slug)
                thread, created = self._hub.store.get_or_create_thread_for_external_identity(
                    identity=snap.identity,
                    project_slug=project_slug,
                    summary=snap.title or f"Issue #{snap.identity.number}",
                    external_issue_state=snap.state,
                )
                fp = fingerprint_for(snap)
                self._hub.store.apply_external_projection(
                    thread.id,
                    summary=snap.title or thread.summary,
                    external_issue_state=snap.state,
                    external_updated_at=snap.updated_at,
                    external_fingerprint=fp,
                    external_labels=list(snap.labels),
                )
                imported.append(
                    {
                        "number": snap.identity.number,
                        "thread_id": thread.id,
                        "created": created,
                    }
                )
            discovery_results.append(
                {
                    "project_slug": slug,
                    "owner": tcfg.owner,
                    "repo": tcfg.repo,
                    "imported": imported,
                    "skipped": skipped,
                }
            )

        # Preserve-existing local mirrors only (no new creates) — optional legacy.
        board_results = []
        if cfg.board_mirror_local:
            for thread in self._hub.list_open_threads(limit=200):
                if thread_has_external_identity(thread):
                    continue
                try:
                    tcfg = self.forge_config(thread.project_slug)
                    board_results.append(self._board(tcfg).sync_thread(thread))
                except Exception as exc:  # noqa: BLE001
                    board_results.append({"error": str(exc), "thread_id": thread.id})

        per_project_wiki: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        for proj in self._hub.store.list_projects():
            if not (proj.forge_owner and proj.forge_repo):
                continue
            key = (proj.forge_owner, proj.forge_repo, proj.forge_wiki_path or "")
            if key in seen:
                continue
            seen.add(key)
            pcfg = self.forge_config(proj.slug)
            try:
                per_project_wiki.append(
                    {
                        "slug": proj.slug,
                        "result": WikiForgeSync(pcfg).push_wiki_tree(
                            self._hub.settings.wiki_dir
                        ),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                per_project_wiki.append({"slug": proj.slug, "error": str(exc)})
        return {
            "scaffold": scaffold,
            "wiki": wiki,
            "reconcile": reconcile_results,
            "discovery": discovery_results,
            "board": board_results,
            "per_project_wiki": per_project_wiki,
            "config": cfg.public_dict(),
            "import_preview": self.preview_forge_import(),
        }

    def import_forge_inbox(self, *, limit: int = 50, close_imported: bool | None = None) -> dict:
        """Pull cloud-agent forge issues into Hub threads (never deletes remote issues)."""
        cfg = self.forge_config()
        if close_imported is None:
            close_imported = bool(cfg.board_inbox_close_imported)
        if not (cfg.enabled() and cfg.board_enabled and cfg.board_inbox_enabled):
            return {
                "skipped": True,
                "reason": "board_inbox_disabled",
                "imported": [],
                "skipped_issues": [],
            }
        authors = [
            name.strip()
            for name in (cfg.board_inbox_authors or [])
            if isinstance(name, str) and name.strip()
        ]
        if not authors:
            return {
                "skipped": True,
                "reason": "board_inbox_authors_required",
                "imported": [],
                "skipped_issues": [],
                "hint": "Add allowed forge usernames under Settings → Forge → Inbox authors.",
            }
        board = self._board(cfg)
        mapped_numbers = {
            value: key.removeprefix("forge_issue:")
            for key, value in self._hub.store.list_meta_prefix("forge_issue:").items()
        }
        imported: list[dict] = []
        skipped: list[dict] = []
        try:
            issues = board.list_inbox_issues(limit=limit)
        except Exception as exc:
            log.exception("forge inbox list failed")
            return {"error": str(exc), "imported": [], "skipped_issues": []}

        for issue in issues:
            number = int(issue.get("number") or 0)
            if not number:
                continue
            linked = None
            try:
                linked = self._hub.store.get_thread_by_external_identity(
                    cfg.provider.value,
                    cfg.web_browse_root(),
                    cfg.owner,
                    cfg.repo,
                    number,
                )
            except ValueError:
                linked = None
            if linked:
                skipped.append(
                    {
                        "number": number,
                        "reason": "already_mapped",
                        "thread_id": linked.id,
                    }
                )
                continue
            if str(number) in mapped_numbers:
                skipped.append(
                    {
                        "number": number,
                        "reason": "already_mapped",
                        "thread_id": mapped_numbers[str(number)],
                    }
                )
                continue
            body = issue.get("body") or ""
            existing = re.search(r"\*\*ADHD Hub thread\*\*\s+`([^`]+)`", body)
            if existing:
                thread_id = existing.group(1).strip()
                self._meta_set_with_identity(cfg)(f"forge_issue:{thread_id}", str(number))
                if close_imported:
                    try:
                        board.mark_issue_imported(
                            number,
                            thread_id=thread_id,
                            close_remote=True,
                            stamp_synced_label=True,
                        )
                    except Exception as exc:  # noqa: BLE001
                        skipped.append(
                            {"number": number, "reason": f"link_close_failed:{exc}"}
                        )
                        continue
                skipped.append(
                    {
                        "number": number,
                        "reason": "linked_existing_marker",
                        "thread_id": thread_id,
                    }
                )
                continue

            title = (issue.get("title") or "").strip()
            summary = re.sub(r"^\[ADHD\]\s*", "", title, flags=re.IGNORECASE).strip() or title
            if not summary:
                skipped.append({"number": number, "reason": "empty_title"})
                continue

            project_slug = None
            source_tool = "forge-inbox"
            for lab in issue.get("labels") or []:
                name = lab.get("name") if isinstance(lab, dict) else str(lab)
                if not isinstance(name, str):
                    continue
                if name.startswith("project:"):
                    project_slug = name.split(":", 1)[1].strip() or None
                elif name.startswith("source:"):
                    raw_source = name.split(":", 1)[1].strip().lower()
                    allowed = {
                        "codex",
                        "chatgpt",
                        "cursor",
                        "claude",
                        "claude-code",
                        "openclaw",
                    }
                    if raw_source in allowed:
                        source_tool = raw_source

            payload = ThreadUpsert(
                # Stable per forge issue so same titles do not collide into one thread.
                id=item_id(
                    f"forge-issue:{number}",
                    f"{cfg.owner}/{cfg.repo}",
                ),
                summary=summary[:500],
                project_slug=project_slug,
                source_tool=source_tool,
                origin="forge-inbox",
                chat_ref=f"forge-issue:{number}",
            )
            slug = self._hub._resolve_slug_for_write(
                project_slug=payload.project_slug,
                workspace_path=payload.workspace_path,
                summary_or_title=payload.summary,
            )
            payload = payload.model_copy(update={"project_slug": slug})
            self._hub.store.ensure_project_for_slug(
                slug, title=payload.summary[:80], workspace_path=payload.workspace_path
            )
            thread = self._hub.store.upsert_thread(payload)
            # Map before any outbound board sync so we update issue #N instead of creating another.
            self._meta_set_with_identity(cfg)(f"forge_issue:{thread.id}", str(number))
            note_import = f"Imported from forge issue #{number}: {thread.summary}"
            self._hub.store.add_progress_note(
                thread.project_slug or slug, note_import, thread_id=thread.id
            )
            self._hub._sync_project_progress(
                thread.project_slug or slug,
                title=thread.summary,
                history_note=note_import,
                thread=thread,
            )
            self._hub.wiki.rebuild_index(
                self._hub.store.list_threads(status=ThreadStatus.open, limit=500)
            )

            note = body.strip()
            if note:
                if len(note) > 8000:
                    note = note[:8000].rstrip() + "\n\n…(truncated from forge issue)"
                self._hub.store.add_progress_note(
                    thread.project_slug or slug, note, thread_id=thread.id
                )
                self._hub._sync_project_progress(
                    thread.project_slug or slug,
                    title=thread.summary,
                    history_note=note,
                    thread=thread,
                )

            close_result = None
            if close_imported:
                try:
                    close_result = board.mark_issue_imported(
                        number,
                        thread_id=thread.id,
                        thread=thread,
                        close_remote=True,
                        stamp_synced_label=True,
                    )
                except Exception as exc:  # noqa: BLE001
                    close_result = {"error": str(exc)}
            imported.append(
                {
                    "number": number,
                    "thread_id": thread.id,
                    "project_slug": thread.project_slug,
                    "title": summary,
                    "url": issue.get("html_url") or issue.get("url"),
                    "closed": close_result,
                }
            )
        return {
            "imported": imported,
            "skipped_issues": skipped,
            "count": len(imported),
            "config": {
                "board_inbox_enabled": cfg.board_inbox_enabled,
                "synced_label": cfg.board_inbox_synced_label,
                "authors": authors,
            },
        }

    def preview_forge_import(self) -> dict:
        """Compare remote forge projects/* with local registry + wiki."""
        cfg = self.forge_config()
        if not (cfg.enabled() and cfg.wiki_enabled):
            return {
                "skipped": True,
                "reason": "wiki_sync_disabled",
                "candidates": [],
                "importable_count": 0,
            }
        scan = WikiForgeSync(cfg).list_remote_project_slugs()
        if scan.get("skipped"):
            return {
                "skipped": True,
                "reason": scan.get("reason"),
                "candidates": [],
                "importable_count": 0,
                "errors": scan.get("errors") or [],
            }
        local_slugs = {p.slug for p in self._hub.store.list_projects()}
        candidates: list[dict] = []
        for item in scan.get("projects") or []:
            slug = item["slug"]
            local_progress = self._hub.wiki.read_progress(slug)
            status = "new"
            if slug in local_slugs:
                status = "registered"
            elif local_progress:
                status = "local_wiki_only"
            candidates.append(
                {
                    "slug": slug,
                    "status": status,
                    "has_remote_progress": bool(item.get("has_progress")),
                    "has_local_progress": local_progress is not None,
                    "path": item.get("path"),
                }
            )
        importable = [
            c
            for c in candidates
            if c["status"] in {"new", "local_wiki_only"} and c["has_remote_progress"]
        ]
        return {
            "skipped": False,
            "candidates": candidates,
            "importable_count": len(importable),
            "errors": scan.get("errors") or [],
        }

    def _credentials_for_identity(self, identity, project_slug: str | None):
        from adhd_hub.forge.repo_sync import credentials_apply_to_pinned

        matched = self.resolve_credentials_for_identity(identity)
        if matched is not None and credentials_apply_to_pinned(matched, identity):
            return matched
        tcfg = self.forge_config(project_slug)
        if credentials_apply_to_pinned(tcfg, identity):
            return tcfg
        cfg = self.forge_config()
        if credentials_apply_to_pinned(cfg, identity):
            return cfg
        return None

    def record_sync_review(
        self,
        *,
        reason: str,
        payload: dict,
        project_slug: str | None = None,
    ):
        from adhd_hub.models import PendingActionKind

        data = dict(payload)
        if project_slug:
            data["project_slug"] = project_slug
        return self._hub.store.create_pending_action(
            kind=PendingActionKind.sync_review,
            payload=data,
            reason=reason,
            source_tool="forge-sync",
        )

    def close_external_thread(self, thread: Thread) -> dict:
        from adhd_hub.forge.repo_sync import (
            fingerprint_for,
            mutate_pinned_issue_state,
        )
        from adhd_hub.work_identity import WorkSource, normalize_external_identity

        try:
            identity = normalize_external_identity(
                thread.external_provider or WorkSource.github,
                thread.external_host,
                thread.external_owner or "",
                thread.external_repo or "",
                int(thread.external_issue_number or 0),
            )
        except ValueError:
            return {"ok": False, "error": "pinned_identity_unreachable", "pending": False}
        cfg = self._credentials_for_identity(identity, thread.project_slug)
        if cfg is None:
            return {"ok": False, "error": "pinned_identity_unreachable", "pending": False}
        result = mutate_pinned_issue_state(cfg, identity, closed=True)
        if isinstance(result, dict):
            return result
        title = result.title or thread.summary
        fp = fingerprint_for(result)
        self._hub.store.apply_external_projection(
            thread.id,
            summary=title,
            external_issue_state=result.state,
            external_updated_at=result.updated_at,
            external_fingerprint=fp,
            external_labels=list(result.labels),
        )
        return {"ok": True, "number": identity.number}

    def reopen_external_thread(self, thread: Thread) -> dict:
        from adhd_hub.forge.repo_sync import (
            fingerprint_for,
            mutate_pinned_issue_state,
        )
        from adhd_hub.work_identity import WorkSource, normalize_external_identity

        try:
            identity = normalize_external_identity(
                thread.external_provider or WorkSource.github,
                thread.external_host,
                thread.external_owner or "",
                thread.external_repo or "",
                int(thread.external_issue_number or 0),
            )
        except ValueError:
            return {"ok": False, "error": "pinned_identity_unreachable", "pending": False}
        cfg = self._credentials_for_identity(identity, thread.project_slug)
        if cfg is None:
            return {"ok": False, "error": "pinned_identity_unreachable", "pending": False}
        result = mutate_pinned_issue_state(cfg, identity, closed=False)
        if isinstance(result, dict):
            return result
        title = result.title or thread.summary
        fp = fingerprint_for(result)
        self._hub.store.apply_external_projection(
            thread.id,
            summary=title,
            external_issue_state=result.state,
            external_updated_at=result.updated_at,
            external_fingerprint=fp,
            external_labels=list(result.labels),
        )
        return {"ok": True, "number": identity.number}

    def promote_thread_to_issue(self, thread_id: str) -> dict:
        from adhd_hub.forge.repo_sync import create_remote_issue, fingerprint_for
        from adhd_hub.work_identity import (
            DuplicateExternalIdentityError,
            thread_has_external_identity,
        )

        thread = self._hub.store.get_thread(thread_id)
        if not thread:
            raise KeyError(f"thread not found: {thread_id}")
        if thread_has_external_identity(thread):
            return {"ok": False, "error": "already_linked"}
        cfg = self.operational_forge_config(thread.project_slug)
        body = ""
        if cfg.publish_hub_status_block:
            body = self._board(cfg).render_status_block(thread)
        created = create_remote_issue(cfg, title=thread.summary[:200], body=body)
        if isinstance(created, dict):
            return created
        try:
            self._hub.store.attach_external_identity(
                thread.id,
                created.identity,
                external_issue_state=created.state,
            )
        except DuplicateExternalIdentityError as exc:
            self.record_sync_review(
                reason="identity_collision",
                payload={
                    "thread_id": thread.id,
                    "number": created.identity.number,
                    "owner": created.identity.owner,
                    "repo": created.identity.repo,
                },
                project_slug=thread.project_slug,
            )
            return {"ok": False, "error": str(exc), "needs_review": True}
        fp = fingerprint_for(created)
        self._hub.store.apply_external_projection(
            thread.id,
            summary=created.title or thread.summary,
            external_issue_state=created.state,
            external_updated_at=created.updated_at,
            external_fingerprint=fp,
            external_labels=list(created.labels),
        )
        return {
            "ok": True,
            "thread_id": thread.id,
            "number": created.identity.number,
            "identity": {
                "provider": created.identity.provider.value,
                "host": created.identity.host,
                "owner": created.identity.owner,
                "repo": created.identity.repo,
                "number": created.identity.number,
            },
        }

    def link_thread_to_issue(
        self,
        thread_id: str,
        *,
        owner: str,
        repo: str,
        number: int,
        host: str | None = None,
        provider: str | None = None,
    ) -> dict:
        from adhd_hub.forge.repo_sync import fetch_pinned_issue, fingerprint_for
        from adhd_hub.work_identity import (
            DuplicateExternalIdentityError,
            WorkSource,
            normalize_external_identity,
            thread_has_external_identity,
        )

        thread = self._hub.store.get_thread(thread_id)
        if not thread:
            raise KeyError(f"thread not found: {thread_id}")
        if thread_has_external_identity(thread):
            return {"ok": False, "error": "already_linked"}
        cfg = self.operational_forge_config(thread.project_slug)
        src = WorkSource(provider or cfg.provider.value)
        if src not in (WorkSource.github, WorkSource.gitea):
            return {"ok": False, "error": "invalid_provider"}
        identity = normalize_external_identity(
            src,
            host or cfg.web_browse_root() or cfg.base_url,
            owner,
            repo,
            number,
        )
        existing = self._hub.store.get_thread_by_external_identity(
            identity.provider,
            identity.host,
            identity.owner,
            identity.repo,
            identity.number,
        )
        if existing and existing.id != thread.id:
            self.record_sync_review(
                reason="identity_collision",
                payload={
                    "thread_id": thread.id,
                    "existing_thread_id": existing.id,
                    "number": identity.number,
                },
                project_slug=thread.project_slug,
            )
            return {"ok": False, "error": "identity_collision", "needs_review": True}
        cred = self._credentials_for_identity(identity, thread.project_slug) or cfg
        fetched = fetch_pinned_issue(cred, identity)
        if isinstance(fetched, dict):
            return {"ok": False, **fetched}
        try:
            self._hub.store.attach_external_identity(
                thread.id,
                identity,
                external_issue_state=fetched.state,
            )
        except DuplicateExternalIdentityError as exc:
            self.record_sync_review(
                reason="identity_collision",
                payload={"thread_id": thread.id, "number": identity.number},
                project_slug=thread.project_slug,
            )
            return {"ok": False, "error": str(exc), "needs_review": True}
        fp = fingerprint_for(fetched)
        self._hub.store.apply_external_projection(
            thread.id,
            summary=fetched.title or thread.summary,
            external_issue_state=fetched.state,
            external_updated_at=fetched.updated_at,
            external_fingerprint=fp,
            external_labels=list(fetched.labels),
        )
        return {"ok": True, "thread_id": thread.id, "number": identity.number}
