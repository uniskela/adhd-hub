from __future__ import annotations

import re
import shutil
from pathlib import Path

from adhd_hub.models import Thread
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

    def upsert_progress(
        self,
        slug: str,
        content: str,
        *,
        title: str | None = None,
        thread: Thread | None = None,
    ) -> Path:
        path = self.progress_path(slug)
        now = self._stamp()
        heading = title or (thread.summary if thread else slug)
        if not path.exists():
            body = (
                f"# {heading}\n\n"
                f"_slug:_ `{slugify(slug)}`\n\n"
                f"## Status\n\n- status: {(thread.status.value if thread else 'open')}\n"
                f"- updated: {now}\n\n"
                f"## Progress log\n\n"
                f"### {now}\n\n{content.strip()}\n"
            )
            path.write_text(body, encoding="utf-8")
        else:
            existing = path.read_text(encoding="utf-8")
            existing = re.sub(
                r"- updated:.*",
                f"- updated: {now}",
                existing,
                count=1,
            )
            if thread:
                existing = re.sub(
                    r"- status:.*",
                    f"- status: {thread.status.value}",
                    existing,
                    count=1,
                )
            addition = f"\n### {now}\n\n{content.strip()}\n"
            if "## Progress log" in existing:
                existing = existing.replace(
                    "## Progress log\n", f"## Progress log\n{addition}", 1
                )
            else:
                existing += f"\n## Progress log\n{addition}"
            path.write_text(existing, encoding="utf-8")
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
            if "## Progress log" in text:
                text = text.replace("## Progress log", block + "## Progress log", 1)
            else:
                text = text.rstrip() + "\n\n" + block
        path.write_text(text, encoding="utf-8")
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

    def write_progress_raw(self, slug: str, content: str) -> Path:
        """Replace PROGRESS.md wholesale (used by forge import)."""
        path = self.progress_path(slug)
        path.write_text(content, encoding="utf-8")
        return path

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
                lines.append(
                    f"- [{t.status.value}] **{t.summary}** "
                    f"`{t.project_slug or ''}`{meta} — id `{t.id}`"
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
