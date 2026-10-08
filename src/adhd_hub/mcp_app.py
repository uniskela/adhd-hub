from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from adhd_hub import __version__
from adhd_hub.mcp_results import (
    GuidanceHealthResult,
    ProgressResult,
    ProjectResult,
    SessionDigestResult,
    ThreadResult,
)
from adhd_hub.models import (
    EnergyLevel,
    ProgressUpsert,
    ProjectUpsert,
    ReminderCreate,
    ReminderKind,
    Thread,
    ThreadStatus,
    ThreadUpsert,
)
from adhd_hub.return_cue import thread_return_cue
from adhd_hub.service import HubService


def _thread_dump(thread: Thread) -> dict[str, Any]:
    """Raw thread dump plus advisory ``return_cue`` (no extra store reads)."""
    data = thread.model_dump(mode="json")
    data["return_cue"] = thread_return_cue(thread)
    return data


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
            "End of task: if completion.ready (or Goal truly done) mark_done that thread only; "
            "if work remains, upsert_progress then pause_thread — never mark_done. "
            "If mark_done is rejected for unfinished work, do not retry; checkpoint + pause. "
            "Thread payloads include advisory return_cue coaching for resume_step "
            "(missing/vague/concrete); it never blocks. Improve a weak cue once when you know "
            "the real first action — never invent files or commands. "
            "Never save secrets or full transcripts."
        ),
    )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def check_overlap(
        query: Annotated[
            str,
            Field(
                description="Plain-language intended outcome or task keywords; searches unfinished Hub threads without creating work.",
                min_length=2,
                max_length=2000,
            ),
        ],
        limit: Annotated[
            int,
            Field(description="Maximum overlap hits to return (1–50); defaults to 5.", ge=1, le=50),
        ] = 5,
    ) -> dict[str, Any]:
        """Find open threads that may overlap a planned task.

        Use before starting potentially new work. The query should describe the
        intended task, and the result is read-only; compare likely matches before
        creating another thread.
        """
        result = service.check_overlap(query, limit=limit)
        return result.model_dump(mode="json")

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def suggest_duplicate_threads(
        thread_id: Annotated[
            str,
            Field(
                description="Exact existing thread ID to compare against unfinished outcomes; related work alone is not a duplicate.",
                min_length=1,
                max_length=128,
            ),
        ],
        limit: Annotated[
            int,
            Field(description="Maximum suggestions to return (1–50); defaults to 5.", ge=1, le=50),
        ] = 5,
    ) -> dict[str, Any]:
        """Review overlap suggestions for an existing thread's finishable outcome.

        Same-goal evidence is conservative; related work is not a merge candidate.
        Forge-backed work stays separate and forge-authoritative. No writes.
        """
        return service.suggest_duplicate_threads(thread_id, limit=limit)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def request_thread_merge(
        source_thread_id: Annotated[
            str,
            Field(
                description="Exact local thread ID to retain as merged history after human approval; cannot be forge-backed.",
                min_length=1,
                max_length=128,
            ),
        ],
        target_thread_id: Annotated[
            str,
            Field(
                description="Exact distinct local thread ID whose current state is kept after approval; must represent the same outcome.",
                min_length=1,
                max_length=128,
            ),
        ],
    ) -> dict[str, Any]:
        """Queue a local duplicate-thread merge for explicit human approval.

        This only creates a pending action, never executes a merge. A human must
        review both states and approve through authenticated REST pending-actions.
        The target state is kept, the source and all its history are retained.
        Forge-backed threads cannot be merged. Never approve on the human's behalf.
        """
        return service.request_thread_merge(source_thread_id, target_thread_id)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def thread_merge_history(
        thread_id: Annotated[
            str,
            Field(
                description="Exact thread ID whose retained merge sources, progress notes and events should be read.",
                min_length=1,
                max_length=128,
            ),
        ],
        limit: Annotated[
            int,
            Field(
                description="Maximum notes and events per original thread (1–500); defaults to 50.",
                ge=1,
                le=500,
            ),
        ] = 50,
    ) -> dict[str, Any]:
        """Read retained merged threads, progress notes and events with original IDs.

        Limit applies per original thread. All source and resume information is
        retained; this does not fetch or change remote issues.
        """
        return service.thread_merge_history(thread_id, limit=limit)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def list_open_threads(
        energy: Annotated[
            EnergyLevel | None,
            Field(
                description="Exact energy filter: low, medium, high or unknown; null includes all energy levels."
            ),
        ] = None,
        project_slug: Annotated[
            str | None,
            Field(
                description="Registered project slug; includes descendants. Null lists open threads across projects."
            ),
        ] = None,
        limit: Annotated[
            int,
            Field(
                description="Maximum open threads to return (1–500); defaults to 50.", ge=1, le=500
            ),
        ] = 50,
    ) -> list[dict[str, Any]]:
        """List unfinished threads without changing them.

        Filter by project or energy when narrowing existing work. Use
        session_digest when you want a session-start summary with reminders and
        resume context instead of the raw thread list. Each thread carries
        advisory return_cue coaching for its resume_step.
        """
        e = EnergyLevel(energy) if energy else None
        threads = service.list_open_threads(energy=e, project_slug=project_slug, limit=limit)
        return [_thread_dump(t) for t in threads]

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def list_projects(
        limit: Annotated[
            int,
            Field(
                description="Maximum registered projects to return (1–500); defaults to 100.",
                ge=1,
                le=500,
            ),
        ] = 100,
    ) -> list[dict[str, Any]]:
        """List registered Hub projects with open/done thread counts.

        Use for project discovery or navigation. This is read-only; use
        resolve_project or upsert_project when a project needs to be resolved or
        changed.
        """
        return service.list_projects(limit=limit)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def resolve_project(
        workspace_path: Annotated[
            str | None,
            Field(
                description="Client workspace folder path, matched to registered paths or basename; may be registered when project_slug resolves."
            ),
        ] = None,
        project_slug: Annotated[
            str | None,
            Field(
                description="Project identifier, checked before workspace_path; missing slugs are normalized on creation."
            ),
        ] = None,
        create_if_missing: Annotated[
            bool,
            Field(
                description="Defaults to true: create a missing registry entry. False prevents creation, but an existing slug may gain workspace_path."
            ),
        ] = True,
        title: Annotated[
            str | None,
            Field(
                description="Display title for a newly created project; defaults to slug or workspace basename. Does not rename an existing project."
            ),
        ] = None,
    ) -> ProjectResult:
        """Resolve the current Hub project from a workspace path or slug.

        Use at session start before session_digest. With create_if_missing=true,
        this may create a local project registry entry; false prevents creation.
        An existing project_slug with workspace_path still registers that path.
        Use upsert_project for explicit metadata or forge configuration changes.
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

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def upsert_project(
        title: Annotated[
            str,
            Field(
                description="Required project display title; replaces the existing title when updating."
            ),
        ],
        slug: Annotated[
            str | None,
            Field(
                description="Project identifier, normalized to a slug; null derives it from title. Reuse the existing slug to update."
            ),
        ] = None,
        description: Annotated[
            str | None,
            Field(
                description="Optional project description; null preserves an existing description."
            ),
        ] = None,
        workspace_path: Annotated[
            str | None,
            Field(
                description="Optional client workspace folder path to add to the project mapping; existing paths are retained."
            ),
        ] = None,
        repo_url: Annotated[
            str | None,
            Field(
                description="Complete HTTP(S) repository URL; null clears an existing URL. Never include credentials."
            ),
        ] = None,
        parent_slug: Annotated[
            str | None,
            Field(
                description="Existing parent project slug; null preserves nesting, empty string clears it. Cycles and missing parents are rejected."
            ),
        ] = None,
        forge_owner: Annotated[
            str | None,
            Field(
                description="Forge repository owner or organization; null preserves existing configuration."
            ),
        ] = None,
        forge_repo: Annotated[
            str | None,
            Field(
                description="Forge repository name; null preserves existing configuration. Used with forge_owner for sync targeting."
            ),
        ] = None,
        forge_wiki_path: Annotated[
            str | None,
            Field(
                description="Optional wiki checkout path used by forge sync; null preserves existing configuration."
            ),
        ] = None,
        forge_project_id: Annotated[
            str | None,
            Field(
                description="Optional forge project-board identifier as a string; null preserves existing configuration."
            ),
        ] = None,
        energy: Annotated[
            EnergyLevel,
            Field(
                description="Project default energy: low, medium, high or unknown; defaults to unknown and replaces the existing default."
            ),
        ] = EnergyLevel.unknown,
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

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def rename_project(
        slug: Annotated[
            str,
            Field(
                description="Existing project slug to rename; this call only queues a confirmation request."
            ),
        ],
        new_slug: Annotated[
            str,
            Field(
                description="Desired project identifier, normalized to a slug; must not conflict with another project."
            ),
        ],
        title: Annotated[
            str | None,
            Field(
                description="Optional replacement display title to apply after human confirmation; null keeps the title."
            ),
        ] = None,
        reason: Annotated[
            str | None,
            Field(description="Optional short explanation shown with the pending rename request."),
        ] = None,
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

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def delete_project(
        slug: Annotated[
            str,
            Field(
                description="Existing project slug; this call queues deletion for human confirmation without deleting immediately."
            ),
        ],
        delete_progress: Annotated[
            bool,
            Field(
                description="Defaults to false; request removal of local progress files when deletion is confirmed."
            ),
        ] = False,
        delete_remote: Annotated[
            bool,
            Field(
                description="Defaults to false; request removal of the remote project PROGRESS.md from the configured wiki after confirmation."
            ),
        ] = False,
        reason: Annotated[
            str | None,
            Field(
                description="Optional short explanation shown with the pending deletion request."
            ),
        ] = None,
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

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def list_pending_actions() -> list[dict[str, Any]]:
        """List project rename/delete requests waiting for /ui confirmation.

        This is read-only and is useful after rename_project or delete_project to
        show the operator exactly what remains pending.
        """
        return service.list_pending_actions()

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=True,
        )
    )
    def upsert_thread(
        summary: Annotated[
            str,
            Field(
                description="Required short title for one independently finishable outcome; replaces the title on update."
            ),
        ],
        project_slug: Annotated[
            str | None,
            Field(
                description="Project identifier; takes precedence over workspace_path and may create a registry entry. Null resolves from path or summary."
            ),
        ] = None,
        workspace_path: Annotated[
            str | None,
            Field(
                description="Optional client workspace folder path used for project resolution and thread identity; retained on update when null."
            ),
        ] = None,
        source_tool: Annotated[
            str | None,
            Field(
                description="Optional originating client/tool name for attribution; null preserves the existing source."
            ),
        ] = None,
        energy: Annotated[
            EnergyLevel,
            Field(
                description="Thread energy: low, medium, high or unknown; defaults to unknown, also when updating."
            ),
        ] = EnergyLevel.unknown,
        chat_ref: Annotated[
            str | None,
            Field(
                description="Optional chat/session reference, not transcript contents; null preserves the existing reference."
            ),
        ] = None,
        transcript_ref: Annotated[
            str | None,
            Field(
                description="Optional transcript reference, not contents; used in generated thread identity and preserved when null."
            ),
        ] = None,
        status: Annotated[
            ThreadStatus,
            Field(
                description="Thread state: open, blocked, done or dismissed; defaults to open, also when updating. Prefer lifecycle tools for closure."
            ),
        ] = ThreadStatus.open,
        thread_id: Annotated[
            str | None,
            Field(
                description="Exact ID to update (or create if absent); null derives a stable ID from summary and transcript/path/project, which may match existing work."
            ),
        ] = None,
        goal: Annotated[
            str | None,
            Field(
                description="Finishable outcome; null preserves it on update, empty string clears it."
            ),
        ] = None,
        focus: Annotated[
            str | None,
            Field(
                description="Current focus, whitespace collapsed and truncated to 500 characters; null or blank preserves existing focus."
            ),
        ] = None,
        next_steps: Annotated[
            list[str] | None,
            Field(
                description="Ordered actions; retains the first 3 nonblank entries, each at most 500 characters. Null preserves; [] clears."
            ),
        ] = None,
        blocked_reason: Annotated[
            str | None,
            Field(
                description="Current blocker; null preserves it on update, empty string clears it. Does not set status automatically."
            ),
        ] = None,
        resume_step: Annotated[
            str | None,
            Field(
                description="Concrete first action to open, run or check on return; null preserves it, empty string clears it. Coaching is advisory."
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Create a new finishable work thread or explicitly update one.

        One thread should represent one independently finishable outcome, not a
        whole project. Pass thread_id when updating a known thread. For routine
        checkpoints on active work, prefer upsert_progress so progress notes and
        PROGRESS.md stay in sync. Without thread_id, a generated ID may match and
        update an existing thread. Updates apply the status and energy defaults;
        supplied progress fields clear paused_at. Writes update progress/wiki
        files and may sync to a configured forge or refresh scan-line AI.
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
        return _thread_dump(thread)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=True,
        )
    )
    def upsert_progress(
        content: Annotated[
            str | None,
            Field(
                description="Optional meaningful history note (decision, blocker or ship note); omit for routine structured checkpoints. Boilerplate is dropped; exclude secrets."
            ),
        ] = None,
        project_slug: Annotated[
            str | None,
            Field(
                description="Project identifier; takes precedence over workspace_path. Either this or workspace_path is required, even with thread_id."
            ),
        ] = None,
        title: Annotated[
            str | None,
            Field(
                description="Optional thread title and new-project title; also used for outcome matching. Null preserves an existing thread title."
            ),
        ] = None,
        workspace_path: Annotated[
            str | None,
            Field(
                description="Client workspace folder path for project resolution; required when project_slug is absent and may register a missing project."
            ),
        ] = None,
        source_tool: Annotated[
            str | None,
            Field(
                description="Optional originating client/tool name for attribution; null preserves an existing thread source."
            ),
        ] = None,
        create_thread_if_missing: Annotated[
            bool,
            Field(
                description="Defaults to true: select or create a thread when thread_id is absent. False saves project notes only unless thread_id is supplied."
            ),
        ] = True,
        thread_id: Annotated[
            str | None,
            Field(
                description="Exact existing thread ID in the resolved project; preferred for checkpoints. Takes precedence over force_new_thread."
            ),
        ] = None,
        force_new_thread: Annotated[
            bool,
            Field(
                description="Defaults to false. True bypasses outcome matching when thread_id is absent; requires create_thread_if_missing=true."
            ),
        ] = False,
        goal: Annotated[
            str | None,
            Field(
                description="Finishable outcome; null preserves it on update, empty string clears it."
            ),
        ] = None,
        focus: Annotated[
            str | None,
            Field(
                description="Current focus, whitespace collapsed and truncated to 500 characters; null or blank preserves existing focus."
            ),
        ] = None,
        next_steps: Annotated[
            list[str] | None,
            Field(
                description="Ordered actions; retains the first 3 nonblank entries, each at most 500 characters. Null preserves; [] clears."
            ),
        ] = None,
        blocked_reason: Annotated[
            str | None,
            Field(
                description="Current blocker; null preserves it, empty string clears it. Does not change thread status."
            ),
        ] = None,
        resume_step: Annotated[
            str | None,
            Field(
                description="Concrete first action on return; null preserves it, empty string clears it. Updating thread progress clears paused_at."
            ),
        ] = None,
    ) -> ProgressResult:
        """Save a checkpoint to active thread state and project PROGRESS.md.

        Prefer a known thread_id so the checkpoint cannot land on the wrong
        thread. Update structured Goal/Focus/Next/Blocked/Resume only on routine
        checkpoints — do not pass ritual content such as "Thread upserted from …".
        Reserve content for rare human-meaningful events (decision, blocker note,
        ship note). If selection is ambiguous the tool can request a thread_id;
        force_new_thread explicitly starts another outcome. Depending on
        create_thread_if_missing, a missing thread may be created as a side effect.
        When completion.ready is false, prefer this plus pause_thread over mark_done.
        Saving thread progress clears paused_at and may sync to a configured
        forge/wiki or refresh scan-line AI. The returned thread.return_cue is
        advisory coaching on resume_step (missing / vague / concrete); weak cues
        do not reject a save. Name the first action using only facts you know.
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

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            # Linked issues are PATCHed again on retry; remote projections may change.
            openWorldHint=True,
        )
    )
    def mark_done(
        thread_id: Annotated[
            str,
            Field(
                description="Exact thread ID whose outcome is complete; may close its linked forge issue. Missing IDs return not_found."
            ),
        ],
        note: Annotated[
            str | None,
            Field(description="Optional short completion note saved when the status changes."),
        ] = None,
    ) -> ThreadResult:
        """Close a specific thread when its finishable outcome is complete.

        Prefer completion.ready == true (or clear Goal completion) before calling.
        Use pause_thread for unfinished work that will resume later, or
        dismiss_thread when intentionally abandoning it. note is an optional
        completion note. If this call is denied/rejected because work remains,
        do not retry unchanged — checkpoint with upsert_progress and pause_thread.
        """
        try:
            thread = service.mark_done(thread_id, note)
        except ValueError as exc:
            return {"error": str(exc), "id": thread_id}
        if not thread:
            return {"error": "not_found", "id": thread_id}
        return thread.model_dump(mode="json")

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            # Overwrites the resume cue and refreshes pause time on every call.
            openWorldHint=False,
        )
    )
    def pause_thread(
        thread_id: Annotated[
            str,
            Field(
                description="Exact unfinished thread ID to pause; finished or dismissed threads are rejected."
            ),
        ],
        next_step: Annotated[
            str,
            Field(
                description="Concrete first action on return (1–2000 characters); whitespace-only values are rejected. Saves resume_step and pause time.",
                min_length=1,
                max_length=2000,
            ),
        ],
    ) -> dict[str, Any]:
        """Pause unfinished work and save the concrete next action to resume it.

        Use when the thread will continue later (including when completion.ready
        is false). This updates its pause/resume state; use mark_done for
        completed work or dismiss_thread for work being intentionally abandoned.
        Requires the exact thread_id and next_step. Weak wording never blocks the
        pause; the response's advisory return_cue says whether next_step names
        something specific to open, run or check first.
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

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=True,
        )
    )
    def dismiss_thread(
        thread_id: Annotated[
            str,
            Field(
                description="Exact thread ID to soft-close as abandoned or superseded; retains its history."
            ),
        ],
        note: Annotated[
            str | None,
            Field(
                description="Optional short dismissal explanation saved when the status changes."
            ),
        ] = None,
    ) -> dict[str, Any]:
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

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def confirm_thread_relevant(
        thread_id: Annotated[
            str,
            Field(
                description="Exact open or blocked thread ID still worth pursuing; refreshes reminder cooldown and clears triage snooze."
            ),
        ],
    ) -> dict[str, Any]:
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

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def snooze_thread_triage(
        thread_id: Annotated[
            str,
            Field(
                description="Exact open or blocked thread ID whose stale-work prompts should be delayed; status is retained."
            ),
        ],
        days: Annotated[
            int,
            Field(
                description="Days to suppress stale-thread triage prompts (1–30); defaults to 7, measured from this call.",
                ge=1,
                le=30,
            ),
        ] = 7,
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

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def list_reminders(
        due_only: Annotated[
            bool,
            Field(
                description="Defaults to false. True returns currently due, unhandled reminders using their schedule and ignores include_handled."
            ),
        ] = False,
        include_handled: Annotated[
            bool,
            Field(
                description="Defaults to false. True includes handled reminders only when due_only=false."
            ),
        ] = False,
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

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def get_overview() -> dict[str, Any]:
        """Return a compact, read-only Hub overview for agents.

        Includes counts, next-up work, and due reminders. Use session_digest when
        you also need project-specific resume context or the progress wiki snippet.
        next_up and triage_candidates carry advisory return_cue coaching.
        """
        return service.agent_overview()

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            # Keeps existing mapping/unfinished work; creation can sync forge/AI.
            openWorldHint=True,
        )
    )
    def register_workspace(
        workspace_path: Annotated[
            str,
            Field(
                description="Nonblank client workspace folder path (1–4000 characters) to resolve or register; the Hub need not access that folder.",
                min_length=1,
                max_length=4000,
            ),
        ],
        title: Annotated[
            str | None,
            Field(
                description="Optional title for a new project; defaults to the workspace basename. Does not rename an existing project."
            ),
        ] = None,
        create_open_thread: Annotated[
            bool,
            Field(
                description="Defaults to true: create a default thread only if the project has no unfinished threads; never adopts an arbitrary existing thread."
            ),
        ] = True,
        summary: Annotated[
            str | None,
            Field(
                description="Optional title for the default new thread; defaults to Continue <project title>, truncated to 500 characters."
            ),
        ] = None,
        source_tool: Annotated[
            str | None,
            Field(
                description="Originating client/tool name for the default thread; defaults to mcp (also used when null)."
            ),
        ] = "mcp",
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

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def report_guidance_health(
        project_slug: Annotated[
            str | None,
            Field(
                description="Project identifier for the verified guidance; takes precedence over workspace_path and may create a registry entry."
            ),
        ] = None,
        workspace_path: Annotated[
            str | None,
            Field(
                description="Client workspace folder path for project resolution when project_slug is absent; supply a slug or path for correct attribution."
            ),
        ] = None,
        agent_guidance_version: Annotated[
            int | None,
            Field(
                description="Integer from the managed AGENTS.md guidance-version marker actually inspected locally; null means unavailable, not verified current."
            ),
        ] = None,
        session_skill_version: Annotated[
            int | None,
            Field(
                description="Integer hub_skill_version from the locally inspected session skill; null means unavailable."
            ),
        ] = None,
        cursor_rule_version: Annotated[
            int | None,
            Field(
                description="Integer hub_guidance_version from the locally inspected Cursor rule; null means unavailable."
            ),
        ] = None,
        source: Annotated[
            str,
            Field(
                description="Client/check attribution string, such as agent or doctor; defaults to agent. Recorded with a new verification timestamp."
            ),
        ] = "agent",
    ) -> GuidanceHealthResult:
        """Record versions of Hub guidance a local client actually verified.

        Call only after inspecting managed markers or running a local doctor/setup
        check. The Hub cannot inspect the client's checkout; it replaces the
        project's last verification record and timestamp with the supplied
        versions. Null versions mean unavailable, not verified current. Project
        resolution may create a local registry entry; no guidance files are edited.
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

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def set_reminder(
        message: Annotated[
            str,
            Field(
                description="Reminder text to persist; each call creates a new reminder. Keep it short and exclude secrets."
            ),
        ],
        kind: Annotated[
            ReminderKind,
            Field(
                description="Schedule: once (default), session, daily or random. Session repeats in digests; random reminders appear probabilistically."
            ),
        ] = ReminderKind.once,
        due_at_iso: Annotated[
            str | None,
            Field(
                description="Optional ISO 8601 datetime, preferably with UTC offset (e.g. 2026-10-08T12:00:00+00:00); required for once to become due; other kinds may omit it."
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Create and persist a Hub reminder.

        kind selects once, session, daily, or random scheduling. A once reminder
        requires due_at_iso to become due; future times delay any kind. Use an
        ISO datetime with a UTC offset. Each call creates a separate reminder.
        Use list_reminders to read existing reminders without creating one.
        """
        due = datetime.fromisoformat(due_at_iso) if due_at_iso else None
        rem = service.set_reminder(
            ReminderCreate(message=message, kind=ReminderKind(kind), due_at=due)
        )
        return rem.model_dump(mode="json")

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def suggest_next_up(
        energy: Annotated[
            EnergyLevel | None,
            Field(
                description="Preferred energy: low, medium, high or unknown; affects ranking without excluding other levels. Null adds no energy preference."
            ),
        ] = None,
        project_slug: Annotated[
            str | None,
            Field(
                description="Restrict candidates to a registered project and descendants; null considers all projects."
            ),
        ] = None,
        focus_project_slug: Annotated[
            str | None,
            Field(
                description="Prefer this project during ranking while retaining other candidates; null adds no focus preference."
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Calm cross-project Next-up pick (Wave 7 continuity intelligence).

        Soft ranking only — prefers quiet/stale open work with a resume cue,
        optional energy match, and optional focus_project_slug to honour focus
        mode / drift (stay near the chosen project). Never starts or dismisses
        work. Prefer this when focus is off and the human asks “what now?”.
        """
        e = EnergyLevel(energy) if energy else None
        pick = service.pick_next_up(
            energy=e,
            project_slug=project_slug,
            focus_project_slug=focus_project_slug,
        )
        if not pick:
            return {"next_up": None}
        return {"next_up": service.thread_public_dict(pick)}

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            # Advances nudge cooldowns/reminders and may rebuild the local wiki.
            openWorldHint=False,
        )
    )
    def session_digest(
        workspace_path: Annotated[
            str | None,
            Field(
                description="Client workspace folder path to resolve the current project without creating it; null or unresolved path considers all projects."
            ),
        ] = None,
        query: Annotated[
            str | None,
            Field(
                description="Optional intended outcome or keywords to rank relevant open work; no overlap falls back to the Next-up ranking."
            ),
        ] = None,
        energy: Annotated[
            EnergyLevel | None,
            Field(
                description="Exact energy filter: low, medium, high or unknown; null includes all levels. An empty project pool falls back to all projects."
            ),
        ] = None,
    ) -> SessionDigestResult:
        """Build the session-start resume digest for the current work context.

        Use after resolve_project. It combines relevant stale/open threads, due
        reminders, and the progress wiki snippet; query narrows overlap relevance
        and energy can filter work to the operator's current capacity. Each item
        carries completion readiness and advisory return_cue coaching for its
        resume_step (deterministic, local, never blocking). This is a mutating
        session action: it refreshes nudged threads' reminder cooldowns, marks
        surfaced non-session reminders fired, and builds a missing wiki index.
        Random reminders are sampled, so repeat calls may produce different results.

        Includes a `guidance` object (expected versions + last local verification
        status). The Hub cannot inspect the client's checkout — run
        `adhd-hub doctor --project` locally (or call `report_guidance_health`
        after a local check) so this field becomes meaningful.
        """
        e = EnergyLevel(energy) if energy else None
        digest = service.session_digest(workspace_path=workspace_path, query=query, energy=e)
        return digest.model_dump(mode="json")

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        )
    )
    def push_openclaw_memory(
        project_slug: Annotated[
            str | None,
            Field(
                description="Optional project identifier to scope the compact Hub digest sent to OpenClaw memory; null uses all projects."
            ),
        ] = None,
        note: Annotated[
            str | None,
            Field(
                description="Optional short context added to the memory digest; exclude secrets and transcripts."
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Best-effort push of a short Hub digest into configured OpenClaw memory.

        This has an external side effect and depends on the operator's OpenClaw
        integration being configured. It sends a compact Hub-generated digest,
        not raw chats; project_slug narrows it and note adds short context.
        """
        return service.push_openclaw_memory_sync(project_slug=project_slug, note=note)

    return mcp
