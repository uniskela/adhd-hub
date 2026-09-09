from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from adhd_hub import __version__
from adhd_hub.models import (
    EnergyLevel,
    ProgressUpsert,
    ProjectUpsert,
    ReminderCreate,
    ReminderKind,
    ThreadStatus,
    ThreadUpsert,
)
from adhd_hub.service import HubService


def build_mcp(service: HubService) -> MCPServer:
    mcp = MCPServer(
        name="adhd-hub",
        title="ADHD Progress Hub",
        description="Unfinished threads, progress wiki, overlap checks, reminders.",
        version=__version__,
        instructions=(
            "Use this hub to avoid losing half-finished work. "
            "On session start call resolve_project or register_workspace, then session_digest "
            "(or get_overview), check_overlap, and list_reminders(due_only=true). "
            "When pausing mid-task, call pause_thread with a next tiny step. "
            "When leaving work incomplete, call upsert_progress and/or upsert_thread. "
            "When finished, call mark_done; use dismiss_thread for soft close without done. "
            "upsert_progress already returns a thread_id; avoid creating a duplicate thread. "
            "Prefer project_slug from resolve_project. Never save secrets or full transcripts."
        ),
    )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def check_overlap(
        query: Annotated[str, Field(min_length=2, max_length=2000)],
        limit: Annotated[int, Field(ge=1, le=50)] = 5,
    ) -> dict[str, Any]:
        """Find open threads that overlap with what you are about to work on."""
        result = service.check_overlap(query, limit=limit)
        return result.model_dump(mode="json")

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def list_open_threads(
        energy: EnergyLevel | None = None,
        project_slug: str | None = None,
        limit: Annotated[int, Field(ge=1, le=500)] = 50,
    ) -> list[dict[str, Any]]:
        """List open (unfinished) threads in the hub."""
        e = EnergyLevel(energy) if energy else None
        threads = service.list_open_threads(energy=e, project_slug=project_slug, limit=limit)
        return [t.model_dump(mode="json") for t in threads]

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def list_projects(limit: Annotated[int, Field(ge=1, le=500)] = 100) -> list[dict[str, Any]]:
        """List registered projects with open/done counts."""
        return service.list_projects(limit=limit)

    @mcp.tool()
    def resolve_project(
        workspace_path: str | None = None,
        project_slug: str | None = None,
        create_if_missing: bool = True,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Resolve or create a project from workspace path and/or slug."""
        proj = service.resolve_project(
            workspace_path=workspace_path,
            project_slug=project_slug,
            create_if_missing=create_if_missing,
            title=title,
        )
        if not proj:
            return {"error": "not_found"}
        return proj.model_dump(mode="json")

    @mcp.tool()
    def upsert_project(
        title: str,
        slug: str | None = None,
        description: str | None = None,
        workspace_path: str | None = None,
        repo_url: str | None = None,
        forge_owner: str | None = None,
        forge_repo: str | None = None,
        forge_wiki_path: str | None = None,
        forge_project_id: str | None = None,
        energy: EnergyLevel = EnergyLevel.unknown,
    ) -> dict[str, Any]:
        """Create or update a project registry entry (paths + optional forge target)."""
        paths = [workspace_path] if workspace_path else []
        proj = service.upsert_project(
            ProjectUpsert(
                slug=slug,
                title=title,
                description=description,
                repo_url=repo_url,
                workspace_paths=paths,
                default_energy=EnergyLevel(energy),
                forge_owner=forge_owner,
                forge_repo=forge_repo,
                forge_wiki_path=forge_wiki_path,
                forge_project_id=forge_project_id,
            )
        )
        return proj.model_dump(mode="json")

    @mcp.tool()
    def rename_project(
        slug: str,
        new_slug: str,
        title: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Request a project rename — queues for confirmation in /ui (not applied yet)."""
        try:
            return service.request_rename_project(
                slug,
                new_slug,
                title=title,
                reason=reason,
                source_tool="mcp",
            )
        except KeyError:
            return {"error": "not_found"}
        except ValueError as exc:
            return {"error": str(exc)}

    @mcp.tool()
    def delete_project(
        slug: str,
        delete_progress: bool = False,
        delete_remote: bool = False,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Request project deletion — queues for confirmation in /ui (not deleted yet)."""
        try:
            return service.request_delete_project(
                slug,
                delete_progress=delete_progress,
                delete_remote=delete_remote,
                reason=reason,
                source_tool="mcp",
            )
        except KeyError:
            return {"error": "not_found"}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def list_pending_actions() -> list[dict[str, Any]]:
        """List project delete/rename requests waiting for /ui confirmation."""
        return service.list_pending_actions()

    @mcp.tool()
    def upsert_thread(
        summary: str,
        project_slug: str | None = None,
        workspace_path: str | None = None,
        source_tool: str | None = None,
        energy: EnergyLevel = EnergyLevel.unknown,
        chat_ref: str | None = None,
        transcript_ref: str | None = None,
        status: ThreadStatus = ThreadStatus.open,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Create or update an unfinished-work thread."""
        thread = service.upsert_thread(
            ThreadUpsert(
                id=thread_id,
                summary=summary,
                project_slug=project_slug,
                workspace_path=workspace_path,
                source_tool=source_tool,
                energy=EnergyLevel(energy),
                chat_ref=chat_ref,
                transcript_ref=transcript_ref,
                status=ThreadStatus(status),
                origin="manual",
            )
        )
        return thread.model_dump(mode="json")

    @mcp.tool()
    def upsert_progress(
        content: str,
        project_slug: str | None = None,
        title: str | None = None,
        workspace_path: str | None = None,
        source_tool: str | None = None,
        create_thread_if_missing: bool = True,
    ) -> dict[str, Any]:
        """Append to a project PROGRESS.md wiki page (and keep/create an open thread)."""
        return service.upsert_progress(
            ProgressUpsert(
                project_slug=project_slug,
                content=content,
                create_thread_if_missing=create_thread_if_missing,
                title=title,
                workspace_path=workspace_path,
                source_tool=source_tool,
            )
        )

    @mcp.tool()
    def mark_done(thread_id: str, note: str | None = None) -> dict[str, Any]:
        """Mark a thread done."""
        thread = service.mark_done(thread_id, note)
        if not thread:
            return {"error": "not_found", "id": thread_id}
        return thread.model_dump(mode="json")

    @mcp.tool()
    def pause_thread(
        thread_id: str,
        next_step: Annotated[str, Field(min_length=1, max_length=2000)],
    ) -> dict[str, Any]:
        """Pause a thread and leave a next tiny step for when you return."""
        try:
            thread = service.store.pause_thread(thread_id, next_step)
        except KeyError:
            return {"error": "not_found", "id": thread_id}
        except ValueError as exc:
            return {"error": str(exc), "id": thread_id}
        return service.thread_public_dict(thread)

    @mcp.tool()
    def dismiss_thread(thread_id: str, note: str | None = None) -> dict[str, Any]:
        """Dismiss a thread without marking it done (soft close)."""
        thread = service.mark_dismissed(thread_id, note)
        if not thread:
            return {"error": "not_found", "id": thread_id}
        return thread.model_dump(mode="json")

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def list_reminders(
        due_only: bool = False,
        include_handled: bool = False,
    ) -> list[dict[str, Any]]:
        """List reminders. Prefer due_only=true at session start."""
        if due_only:
            items = service.store.due_reminders()
        else:
            items = service.store.list_reminders(include_handled=include_handled)
        return [item.model_dump(mode="json") for item in items]

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def get_overview() -> dict[str, Any]:
        """Compact hub overview for agents (counts, next_up, due reminders)."""
        return service.agent_overview()

    @mcp.tool()
    def register_workspace(
        workspace_path: Annotated[str, Field(min_length=1, max_length=4000)],
        title: str | None = None,
        create_open_thread: bool = True,
        summary: str | None = None,
        source_tool: str | None = "mcp",
    ) -> dict[str, Any]:
        """One-click: register a folder as a Hub project (optional default open thread)."""
        try:
            return service.register_workspace(
                workspace_path,
                title=title,
                create_open_thread=create_open_thread,
                summary=summary,
                source_tool=source_tool,
            )
        except ValueError as exc:
            return {"error": str(exc)}

    @mcp.tool()
    def set_reminder(
        message: str,
        kind: ReminderKind = ReminderKind.once,
        due_at_iso: str | None = None,
    ) -> dict[str, Any]:
        """Set a reminder (once | session | daily | random). due_at_iso for once."""
        due = datetime.fromisoformat(due_at_iso) if due_at_iso else None
        rem = service.set_reminder(
            ReminderCreate(message=message, kind=ReminderKind(kind), due_at=due)
        )
        return rem.model_dump(mode="json")

    @mcp.tool()
    def session_digest(
        workspace_path: str | None = None,
        query: str | None = None,
        energy: EnergyLevel | None = None,
    ) -> dict[str, Any]:
        """Session-start digest: stale/open threads + due reminders + wiki snippet."""
        e = EnergyLevel(energy) if energy else None
        digest = service.session_digest(workspace_path=workspace_path, query=query, energy=e)
        return digest.model_dump(mode="json")

    @mcp.tool()
    def push_openclaw_memory(
        project_slug: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Push a short Hub digest into OpenClaw memory (no raw chats; best-effort)."""
        return service.push_openclaw_memory_sync(project_slug=project_slug, note=note)

    return mcp
