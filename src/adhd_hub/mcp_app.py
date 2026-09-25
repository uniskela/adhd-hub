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
            "One thread = one independently finishable outcome (not the whole project). "
            "On session start call resolve_project, then session_digest with the task query. "
            "Before potentially new work call check_overlap and compare against thread Goal. "
            "At checkpoints call upsert_progress with the known thread_id and compact "
            "goal/focus/next_steps/blocked_reason/resume_step only — omit ritual content. "
            "If upsert_progress returns needs_thread_selection, pass thread_id or force_new_thread. "
            "When finished, mark_done only that thread. Never save secrets or full transcripts."
        ),
    )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def check_overlap(
        query: Annotated[str, Field(min_length=2, max_length=2000)],
        limit: Annotated[int, Field(ge=1, le=50)] = 5,
    ) -> dict[str, Any]:
        """Find open threads that may overlap a planned task.

        Use before starting potentially new work. The query should describe the
        intended task, and the result is read-only; compare likely matches before
        creating another thread.
        """
        result = service.check_overlap(query, limit=limit)
        return result.model_dump(mode="json")

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def list_open_threads(
        energy: EnergyLevel | None = None,
        project_slug: str | None = None,
        limit: Annotated[int, Field(ge=1, le=500)] = 50,
    ) -> list[dict[str, Any]]:
        """List unfinished threads without changing them.

        Filter by project or energy when narrowing existing work. Use
        session_digest when you want a session-start summary with reminders and
        resume context instead of the raw thread list.
        """
        e = EnergyLevel(energy) if energy else None
        threads = service.list_open_threads(energy=e, project_slug=project_slug, limit=limit)
        return [t.model_dump(mode="json") for t in threads]

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def list_projects(limit: Annotated[int, Field(ge=1, le=500)] = 100) -> list[dict[str, Any]]:
        """List registered Hub projects with open/done thread counts.

        Use for project discovery or navigation. This is read-only; use
        resolve_project or upsert_project when a project needs to be resolved or
        changed.
        """
        return service.list_projects(limit=limit)

    @mcp.tool()
    def resolve_project(
        workspace_path: str | None = None,
        project_slug: str | None = None,
        create_if_missing: bool = True,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Resolve the current Hub project from a workspace path or slug.

        Use at session start before session_digest. With create_if_missing=true,
        this may create a local project registry entry; set it false when lookup
        must be read-only. Use upsert_project for explicit metadata or forge
        configuration changes.
        """
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
        parent_slug: str | None = None,
        forge_owner: str | None = None,
        forge_repo: str | None = None,
        forge_wiki_path: str | None = None,
        forge_project_id: str | None = None,
        energy: EnergyLevel = EnergyLevel.unknown,
    ) -> dict[str, Any]:
        """Create or update a project registry entry and its explicit metadata.

        Use when setting title, workspace path, repository, energy, parent, or forge
        targeting. parent_slug nests under any project (unlimited depth; cycles rejected).
        This persists local Hub project configuration; it does not by itself create,
        rename, or delete a remote forge repository.
        """
        paths = [workspace_path] if workspace_path else []
        upsert_data: dict[str, Any] = {
            "slug": slug,
            "title": title,
            "description": description,
            "repo_url": repo_url,
            "workspace_paths": paths,
            "default_energy": EnergyLevel(energy),
            "forge_owner": forge_owner,
            "forge_repo": forge_repo,
            "forge_wiki_path": forge_wiki_path,
            "forge_project_id": forge_project_id,
        }
        # Omit parent_slug when unset so existing nesting is preserved; "" clears.
        if parent_slug is not None:
            upsert_data["parent_slug"] = parent_slug
        try:
            proj = service.upsert_project(ProjectUpsert(**upsert_data))
        except ValueError as exc:
            return {"error": str(exc)}
        return proj.model_dump(mode="json")

    @mcp.tool()
    def rename_project(
        slug: str,
        new_slug: str,
        title: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Queue a project rename for human confirmation in /ui.

        Use when the project identity should change. This request does not apply
        the rename immediately; list_pending_actions shows queued confirmations.
        """
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
        """Queue project deletion for human confirmation in /ui.

        Nothing is deleted immediately. The flags describe what the confirmed
        action should remove; use list_pending_actions to inspect the queued
        request before confirmation.
        """
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
        """List project rename/delete requests waiting for /ui confirmation.

        This is read-only and is useful after rename_project or delete_project to
        show the operator exactly what remains pending.
        """
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
        goal: str | None = None,
        focus: str | None = None,
        next_steps: list[str] | None = None,
        blocked_reason: str | None = None,
        resume_step: str | None = None,
    ) -> dict[str, Any]:
        """Create a new finishable work thread or explicitly update one.

        One thread should represent one independently finishable outcome, not a
        whole project. Pass thread_id when updating a known thread. For routine
        checkpoints on active work, prefer upsert_progress so progress notes and
        PROGRESS.md stay in sync.
        """
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
                goal=goal,
                focus=focus,
                next_steps=next_steps,
                blocked_reason=blocked_reason,
                resume_step=resume_step,
            )
        )
        return thread.model_dump(mode="json")

    @mcp.tool()
    def upsert_progress(
        content: str | None = None,
        project_slug: str | None = None,
        title: str | None = None,
        workspace_path: str | None = None,
        source_tool: str | None = None,
        create_thread_if_missing: bool = True,
        thread_id: str | None = None,
        force_new_thread: bool = False,
        goal: str | None = None,
        focus: str | None = None,
        next_steps: list[str] | None = None,
        blocked_reason: str | None = None,
        resume_step: str | None = None,
    ) -> dict[str, Any]:
        """Save a checkpoint to active thread state and project PROGRESS.md.

        Prefer a known thread_id so the checkpoint cannot land on the wrong
        thread. Update structured Goal/Focus/Next/Blocked/Resume only on routine
        checkpoints — do not pass ritual content such as "Thread upserted from …".
        Reserve content for rare human-meaningful events (decision, blocker note,
        ship note). If selection is ambiguous the tool can request a thread_id;
        force_new_thread explicitly starts another outcome. Depending on
        create_thread_if_missing, a missing thread may be created as a side effect.
        """
        try:
            return service.upsert_progress(
                ProgressUpsert(
                    project_slug=project_slug,
                    content=content,
                    create_thread_if_missing=create_thread_if_missing,
                    title=title,
                    workspace_path=workspace_path,
                    source_tool=source_tool,
                    thread_id=thread_id,
                    force_new_thread=force_new_thread,
                    goal=goal,
                    focus=focus,
                    next_steps=next_steps,
                    blocked_reason=blocked_reason,
                    resume_step=resume_step,
                )
            )
        except KeyError as exc:
            return {"error": "not_found", "detail": str(exc)}
        except ValueError as exc:
            return {"error": str(exc)}

    @mcp.tool()
    def mark_done(thread_id: str, note: str | None = None) -> dict[str, Any]:
        """Close a specific thread when its finishable outcome is complete.

        Use only with a known thread_id after the work is actually finished.
        Use pause_thread for unfinished work that will resume later, or
        dismiss_thread when intentionally abandoning it. note is an optional
        completion note.
        """
        try:
            thread = service.mark_done(thread_id, note)
        except ValueError as exc:
            return {"error": str(exc), "id": thread_id}
        if not thread:
            return {"error": "not_found", "id": thread_id}
        return thread.model_dump(mode="json")

    @mcp.tool()
    def pause_thread(
        thread_id: str,
        next_step: Annotated[str, Field(min_length=1, max_length=2000)],
    ) -> dict[str, Any]:
        """Pause unfinished work and save the concrete next action to resume it.

        Use when the thread will continue later. This updates its pause/resume
        state; use mark_done for completed work or dismiss_thread for work being
        intentionally abandoned. Requires the exact thread_id and next_step.
        """
        step = next_step.strip()
        if not step:
            return {"error": "next_step required", "id": thread_id}
        try:
            thread = service.pause_thread(thread_id, step)
        except KeyError:
            return {"error": "not_found", "id": thread_id}
        except ValueError as exc:
            return {"error": str(exc), "id": thread_id}
        return service.thread_public_dict(thread)

    @mcp.tool()
    def dismiss_thread(thread_id: str, note: str | None = None) -> dict[str, Any]:
        """Soft-close a thread that should stop without being marked complete.

        Use for abandoned, superseded, or no-longer-relevant work. Use mark_done
        when the intended outcome was completed, or pause_thread when it will be
        resumed later. Prefer confirm_thread_relevant / snooze_thread_triage for
        a calm stale-work check — never auto-dismiss from those tools.
        """
        thread = service.mark_dismissed(thread_id, note)
        if not thread:
            return {"error": "not_found", "id": thread_id}
        return service.thread_public_dict(thread)

    @mcp.tool()
    def confirm_thread_relevant(thread_id: str) -> dict[str, Any]:
        """Confirm a stale open thread is still relevant (Wave 7 soft triage).

        Quiets the “still relevant?” prompt via reminder cooldown. Does not
        change status and never dismisses. Use snooze_thread_triage to ask again
        later, or dismiss_thread only when the human intentionally abandons it.
        """
        try:
            thread = service.confirm_thread_relevant(thread_id)
        except KeyError:
            return {"error": "not_found", "id": thread_id}
        except ValueError as exc:
            return {"error": str(exc), "id": thread_id}
        return service.thread_public_dict(thread)

    @mcp.tool()
    def snooze_thread_triage(
        thread_id: str,
        days: Annotated[int, Field(ge=1, le=30)] = 7,
    ) -> dict[str, Any]:
        """Snooze stale-thread triage prompts for a few days (default 7).

        Soft only — thread stays open. Never auto-dismisses. Use
        confirm_thread_relevant when the outcome is still wanted now.
        """
        try:
            thread = service.snooze_thread_triage(thread_id, days=days)
        except KeyError:
            return {"error": "not_found", "id": thread_id}
        except ValueError as exc:
            return {"error": str(exc), "id": thread_id}
        return service.thread_public_dict(thread)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def list_reminders(
        due_only: bool = False,
        include_handled: bool = False,
    ) -> list[dict[str, Any]]:
        """List persisted Hub reminders without changing them.

        Prefer due_only=true at session start to surface only reminders that need
        attention now. Set include_handled=true only when historical handled
        reminders are relevant.
        """
        if due_only:
            items = service.store.due_reminders()
        else:
            items = service.store.list_reminders(include_handled=include_handled)
        return [item.model_dump(mode="json") for item in items]

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def get_overview() -> dict[str, Any]:
        """Return a compact, read-only Hub overview for agents.

        Includes counts, next-up work, and due reminders. Use session_digest when
        you also need project-specific resume context or the progress wiki snippet.
        """
        return service.agent_overview()

    @mcp.tool()
    def register_workspace(
        workspace_path: Annotated[str, Field(min_length=1, max_length=4000)],
        title: str | None = None,
        create_open_thread: bool = True,
        summary: str | None = None,
        source_tool: str | None = "mcp",
    ) -> dict[str, Any]:
        """Register a local folder as a Hub project in one operation.

        Side effect: this persists the workspace/project mapping and, when
        create_open_thread=true, also creates a default open thread. Use
        resolve_project when you only need to resolve an already-known workspace
        or want optional lookup-with-create behavior.
        """
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
    def report_guidance_health(
        project_slug: str | None = None,
        workspace_path: str | None = None,
        agent_guidance_version: int | None = None,
        session_skill_version: int | None = None,
        cursor_rule_version: int | None = None,
        source: str = "agent",
    ) -> dict[str, Any]:
        """Record versions of Hub guidance a local client actually verified.

        Call only after the client itself inspected managed markers or ran a
        local doctor/setup check. The Hub cannot inspect the client's checkout;
        this tool records the verification result supplied by that client.
        """
        try:
            return service.record_guidance_verification(
                project_slug=project_slug,
                workspace_path=workspace_path,
                agent_guidance_version=agent_guidance_version,
                session_skill_version=session_skill_version,
                cursor_rule_version=cursor_rule_version,
                source=source,
            )
        except ValueError as exc:
            return {"error": str(exc)}

    @mcp.tool()
    def set_reminder(
        message: str,
        kind: ReminderKind = ReminderKind.once,
        due_at_iso: str | None = None,
    ) -> dict[str, Any]:
        """Create and persist a Hub reminder.

        kind selects once, session, daily, or random scheduling. due_at_iso is an
        ISO datetime used for a once reminder when a specific due time is known.
        Use list_reminders to read existing reminders without creating one.
        """
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
        """Build the session-start resume digest for the current work context.

        Use after resolve_project. It combines relevant stale/open threads, due
        reminders, and the progress wiki snippet; query narrows overlap relevance
        and energy can filter work to the operator's current capacity.

        Includes a `guidance` object (expected versions + last local verification
        status). The Hub cannot inspect the client's checkout — run
        `adhd-hub doctor --project` locally (or call `report_guidance_health`
        after a local check) so this field becomes meaningful.
        """
        e = EnergyLevel(energy) if energy else None
        digest = service.session_digest(workspace_path=workspace_path, query=query, energy=e)
        return digest.model_dump(mode="json")

    @mcp.tool()
    def push_openclaw_memory(
        project_slug: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Best-effort push of a short Hub digest into configured OpenClaw memory.

        This has an external side effect and depends on the operator's OpenClaw
        integration being configured. It sends a compact Hub-generated digest,
        not raw chats; project_slug narrows it and note adds short context.
        """
        return service.push_openclaw_memory_sync(project_slug=project_slug, note=note)

    return mcp
