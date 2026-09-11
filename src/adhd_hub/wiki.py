from __future__ import annotations

import re
import shutil
from pathlib import Path

from adhd_hub.models import Thread, ThreadStatus
from adhd_hub.store import slugify


class Wiki:
    def __init__(self, wiki_dir: Path, *, timezone: str = "UTC") -> None:
        self.wiki_dir = wiki_dir
        self.timezone = timezone or "UTC"
        self.projects_dir = wiki_dir / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def set_timezone(self, timezone: str) -> None:
        self.timezone = timezone or "UTC"

    def _stamp(self) -> str:
        from adhd_hub.timeutil import format_timestamp

        return format_timestamp(timezone=self.timezone)

    def project_dir(self, slug: str) -> Path:
        safe = slugify(slug)
        path = self.projects_dir / safe
        path.mkdir(parents=True, exist_ok=True)
        return path

    def progress_path(self, slug: str) -> Path:
        return self.project_dir(slug) / "PROGRESS.md"

    def rename_project(self, old_slug: str, new_slug: str) -> dict[str, str | bool]:
        """Staged directory rename under wiki/projects/. Idempotent if already moved."""
        old = slugify(old_slug)
        new = slugify(new_slug)
        src = self.projects_dir / old
        dst = self.projects_dir / new
        if old == new:
            return {"renamed": False, "slug": new}
        if not src.is_dir():
            if dst.is_dir():
                return {"renamed": False, "slug": new, "already": True}
            return {"renamed": False, "slug": new, "missing": True}
        if dst.exists():
            raise FileExistsError(f"wiki project dir already exists: {new}")
        staging = self.projects_dir / f".rename-{old}-to-{new}"
        if staging.exists():
            shutil.rmtree(staging)
        shutil.move(str(src), str(staging))
        try:
            shutil.move(str(staging), str(dst))
        except Exception:
            if staging.exists() and not src.exists():
                shutil.move(str(staging), str(src))
            raise
        progress = dst / "PROGRESS.md"
        if progress.is_file():
            text = progress.read_text(encoding="utf-8")
            text = re.sub(
                r"(_slug:_\s*`)[^`]+(`)",
                rf"\g<1>{new}\2",
                text,
                count=1,
            )
            progress.write_text(text, encoding="utf-8")
        return {"renamed": True, "from": old, "to": new}

    def delete_project(self, slug: str) -> dict[str, str | bool]:
        safe = slugify(slug)
        path = self.projects_dir / safe
        if not path.is_dir():
            return {"deleted": False, "slug": safe, "missing": True}
        shutil.rmtree(path)
        return {"deleted": True, "slug": safe}

    _MANAGED_HEADINGS = (
        "Status",
        "Forge",
        "Active threads",
        "Recent milestones",
        "History",
        "Progress log",
    )

    @classmethod
    def _extract_section(cls, text: str, heading: str) -> str | None:
        managed = "|".join(re.escape(h) for h in cls._MANAGED_HEADINGS)
        pattern = rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## (?:{managed})\s*$|\Z)"
        match = re.search(pattern, text, flags=re.MULTILINE | re.DOTALL)
        return match.group(1).strip("\n") if match else None

    def extract_preserved_sections(self, text: str) -> tuple[str | None, str]:
        """Return (forge_block_without_heading, history_body) from an existing file."""
        forge = self._extract_section(text, "Forge")
        history = self._extract_section(text, "History")
        legacy_migrate = False
        if history is None:
            # Legacy: fold Progress log plus any other non-managed body into History.
            progress_log = self._extract_section(text, "Progress log")
            stripped = re.sub(r"^# .*\n+", "", text, count=1)
            stripped = re.sub(r"^_slug:_.*\n+", "", stripped, count=1)
            for heading in self._MANAGED_HEADINGS:
                stripped = re.sub(
                    rf"^## {re.escape(heading)}\s*\n(?:.*?\n)*?(?=^## (?:Status|Forge|Active threads|Recent milestones|History|Progress log)\s*$|\Z)",
                    "",
                    stripped,
                    count=1,
                    flags=re.MULTILINE,
                )
            extra = stripped.strip()
            parts: list[str] = []
            if progress_log and progress_log.strip():
                parts.append(progress_log.strip())
            if extra and extra not in (progress_log or ""):
                parts.append(extra)
            history = "\n\n".join(parts).strip()
            legacy_migrate = bool(history)
        if legacy_migrate and history and "Legacy project-level history" not in history:
            history = (
                "### Legacy project-level history\n\n"
                "_Unscoped entries from before thread-targeted progress._\n\n"
                + history
            )
        return forge, history or ""

    @staticmethod
    def _format_thread_block(thread: Thread) -> str:
        lines = [f"### {thread.summary}", ""]
        if thread.goal:
            lines.append(f"Goal: {thread.goal}")
            lines.append("")
        if thread.focus:
            lines.append("Focus:")
            lines.append(f"- {thread.focus}")
            lines.append("")
        if thread.next_steps:
            lines.append("Next:")
            for i, step in enumerate(thread.next_steps[:3], start=1):
                lines.append(f"{i}. {step}")
            lines.append("")
        if thread.blocked_reason:
            lines.append("Blocked:")
            lines.append(f"- {thread.blocked_reason}")
            lines.append("")
        if thread.resume_step:
            lines.append("Resume:")
            lines.append(f"- {thread.resume_step}")
            lines.append("")
        lines.append(f"Updated: {thread.updated_at.isoformat()}")
        lines.append("")
        lines.append(f"_thread_id:_ `{thread.id}`")
        lines.append("")
        return "\n".join(lines)

    def render_progress(
        self,
        slug: str,
        *,
        title: str,
        active_threads: list[Thread],
        milestones: list[dict[str, str]],
        forge_body: str | None = None,
        history_body: str = "",
    ) -> str:
        safe = slugify(slug)
        now = self._stamp()
        lines = [
            f"# {title}",
            "",
            f"_slug:_ `{safe}`",
            "",
            "## Status",
            "",
            f"- active_threads: {len(active_threads)}",
            f"- updated: {now}",
            "",
        ]
        if forge_body is not None:
            lines.append("## Forge")
            lines.append("")
            lines.append(forge_body.rstrip() or "_No forge links yet._")
            lines.append("")
        lines.append("## Active threads")
        lines.append("")
        unfinished = [
            t
            for t in active_threads
            if t.status in (ThreadStatus.open, ThreadStatus.blocked)
        ]
        if unfinished:
            for thread in unfinished:
                lines.append(self._format_thread_block(thread).rstrip())
                lines.append("")
        else:
            lines.append("_No active threads._")
            lines.append("")
        lines.append("## Recent milestones")
        lines.append("")
        if milestones:
            for item in milestones[:30]:
                stamp = item.get("created_at") or now
                label = item.get("thread_title") or item.get("thread_id") or "project"
                content = (item.get("content") or "").strip().replace("\n", " ")
                if content:
                    lines.append(f"- {stamp} — {label}: {content}")
            lines.append("")
        else:
            lines.append("_No milestones yet._")
            lines.append("")
        lines.append("## History")
        lines.append("")
        lines.append(history_body.strip() if history_body.strip() else "_No older history._")
        lines.append("")
        return "\n".join(lines)

    def sync_progress(
        self,
        slug: str,
        *,
        title: str,
        active_threads: list[Thread],
        milestones: list[dict[str, str]],
    ) -> Path:
        """Rewrite PROGRESS.md from structured state; preserve Forge + History."""
        path = self.progress_path(slug)
        forge_body: str | None = None
        history_body = ""
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            forge_body, history_body = self.extract_preserved_sections(existing)
        body = self.render_progress(
            slug,
            title=title,
            active_threads=active_threads,
            milestones=milestones,
            forge_body=forge_body,
            history_body=history_body,
        )
        path.write_text(body, encoding="utf-8")
        return path

    def upsert_progress(
        self,
        slug: str,
        content: str,
        *,
        title: str | None = None,
        thread: Thread | None = None,
        active_threads: list[Thread] | None = None,
        milestones: list[dict[str, str]] | None = None,
    ) -> Path:
        """Compatibility entry: sync structured doc; fold freeform content into History."""
        path = self.progress_path(slug)
        forge_body: str | None = None
        history_body = ""
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            forge_body, history_body = self.extract_preserved_sections(existing)
        note = (content or "").strip()
        if note:
            stamp = self._stamp()
            label = thread.summary if thread else (title or slug)
            addition = f"### {stamp}\n\n**{label}**\n\n{note}\n"
            history_body = (addition + "\n" + history_body).strip() if history_body else addition.strip()
        heading = title or (thread.summary if thread else slug)
        threads = active_threads
        if threads is None:
            threads = [thread] if thread and thread.status in (
                ThreadStatus.open,
                ThreadStatus.blocked,
            ) else []
        body = self.render_progress(
            slug,
            title=heading,
            active_threads=threads,
            milestones=milestones or [],
            forge_body=forge_body,
            history_body=history_body,
        )
        path.write_text(body, encoding="utf-8")
        return path

    def ensure_forge_section(
        self,
        slug: str,
        *,
        progress_url: str | None = None,
        issue_links: list[tuple[str, str]] | None = None,
    ) -> Path | None:
        """Upsert a ## Forge section with folder + issue links (does not append log)."""
        path = self.progress_path(slug)
        if not path.is_file():
            return None
        lines = ["## Forge", ""]
        if progress_url:
            lines.append(f"- Progress on forge: [{progress_url}]({progress_url})")
        for label, url in issue_links or []:
            lines.append(f"- Issue: [{label}]({url})")
        if len(lines) <= 2:
            lines.append("_No forge links yet._")
        lines.append("")
        block = "\n".join(lines)
        text = path.read_text(encoding="utf-8")
        if re.search(r"^## Forge\s*$", text, re.MULTILINE):
            text = re.sub(
                r"^## Forge\s*\n(?:.*?\n)*?(?=^## |\Z)",
                block,
                text,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            if "## Active threads" in text:
                text = text.replace("## Active threads", block + "## Active threads", 1)
            elif "## Progress log" in text:
                text = text.replace("## Progress log", block + "## Progress log", 1)
            else:
                text = text.rstrip() + "\n\n" + block
        path.write_text(text, encoding="utf-8")
        return path

    def write_progress_raw(self, slug: str, content: str) -> Path:
        """Replace PROGRESS.md wholesale (used by forge import)."""
        path = self.progress_path(slug)
        path.write_text(content, encoding="utf-8")
        return path

    def list_project_slugs(self) -> list[str]:
        if not self.projects_dir.is_dir():
            return []
        return sorted(
            p.name
            for p in self.projects_dir.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )

    def read_progress(self, slug: str) -> str | None:
        path = self.progress_path(slug)
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def rebuild_index(self, open_threads: list[Thread]) -> Path:
        """Rewrite wiki/INDEX.md from open threads + project folders."""
        index_path = self.wiki_dir / "INDEX.md"
        by_slug: dict[str, list[Thread]] = {}
        for t in open_threads:
            slug = t.project_slug or slugify(t.summary)
            by_slug.setdefault(slug, []).append(t)

        lines = [
            "# ADHD Hub — open work index",
            "",
            f"_Generated {self._stamp()}_",
            "",
            "## Open threads",
            "",
        ]
        if not open_threads:
            lines.append("_No open threads._")
            lines.append("")
        else:
            for t in open_threads:
                age_bits = []
                if t.source_tool:
                    age_bits.append(t.source_tool)
                if t.workspace_path:
                    age_bits.append(t.workspace_path)
                meta = f" ({', '.join(age_bits)})" if age_bits else ""
                goal = f" — goal: {t.goal}" if t.goal else ""
                lines.append(
                    f"- [{t.status.value}] **{t.summary}** "
                    f"`{t.project_slug or ''}`{meta}{goal} — id `{t.id}`"
                )
            lines.append("")

        lines.extend(["## Wiki projects", ""])
        slugs = sorted(set(self.list_project_slugs()) | set(by_slug.keys()))
        if not slugs:
            lines.append("_No project pages yet._")
        else:
            for slug in slugs:
                rel = f"projects/{slug}/PROGRESS.md"
                n = len(by_slug.get(slug, []))
                lines.append(f"- [{slug}]({rel}) — {n} open thread(s)")
        lines.append("")
        index_path.write_text("\n".join(lines), encoding="utf-8")
        return index_path

    def index_snippet(self, max_chars: int = 1200) -> str | None:
        path = self.wiki_dir / "INDEX.md"
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
        return text[:max_chars]
