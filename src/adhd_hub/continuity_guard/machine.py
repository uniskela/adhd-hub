"""Explicit continuity-guard state machine (deterministic, no LLM)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adhd_hub.continuity_guard.config import GuardConfig
    from adhd_hub.continuity_guard.state import GuardState


class GuardPhase(StrEnum):
    not_required = "not_required"
    required_unestablished = "required_unestablished"
    active = "active"
    checkpoint_due = "checkpoint_due"
    paused = "paused"
    completed = "completed"
    persistence_unavailable = "persistence_unavailable"


class GuardEvent(StrEnum):
    """Deterministic events that drive transitions."""

    trivial_activity = "trivial_activity"
    meaningful_mutation = "meaningful_mutation"
    file_edit = "file_edit"
    continuity_established = "continuity_established"
    checkpoint_observed = "checkpoint_observed"
    pause_observed = "pause_observed"
    done_observed = "done_observed"
    forge_fallback_observed = "forge_fallback_observed"
    persistence_unavailable = "persistence_unavailable"
    reset = "reset"
    begin_session = "begin_session"


@dataclass(frozen=True)
class TransitionResult:
    state: GuardState
    changed: bool
    message: str | None = None


def apply_event(
    state: GuardState,
    event: GuardEvent,
    *,
    config: GuardConfig | None = None,
    conversation_id: str | None = None,
    path_hint: str | None = None,
    continuity_method: str | None = None,
    project_slug: str | None = None,
    thread_id: str | None = None,
    fallback_issue_number: int | None = None,
    fallback_issue_url: str | None = None,
) -> TransitionResult:
    """Apply one deterministic event. Mutates and returns ``state``."""
    from adhd_hub.continuity_guard.config import GuardConfig as _GC

    cfg = config or _GC(enabled=True, mode="balanced")
    before = state.phase
    if conversation_id and not state.conversation_id:
        state.conversation_id = conversation_id
    elif conversation_id and state.conversation_id != conversation_id:
        # New conversation: soft reset meaningful counters but keep enrollment
        state.conversation_id = conversation_id
        state.guard_retry_count = 0
        state.mutations_since_checkpoint = 0
        state.files_changed = 0
        state.touched_paths = []
        state.evidence_progress = False
        state.evidence_pause = False
        state.evidence_done = False
        state.meaningful_work = False
        state.set_phase(GuardPhase.not_required)

    if event == GuardEvent.reset:
        state.phase = GuardPhase.not_required.value
        state.meaningful_work = False
        state.files_changed = 0
        state.mutations_since_checkpoint = 0
        state.evidence_resolve = False
        state.evidence_digest = False
        state.evidence_overlap = False
        state.evidence_progress = False
        state.evidence_pause = False
        state.evidence_done = False
        state.evidence_forge_fallback = False
        state.continuity_method = None
        state.project_slug = None
        state.thread_id = None
        state.fallback_issue_number = None
        state.fallback_issue_url = None
        state.guard_retry_count = 0
        state.persistence_unavailable = False
        state.last_warning = None
        state.touched_paths = []
        state.set_phase(GuardPhase.not_required)
        return TransitionResult(state, True, "reset")

    if event == GuardEvent.begin_session:
        if state.phase_enum() in {
            GuardPhase.completed,
            GuardPhase.paused,
            GuardPhase.persistence_unavailable,
        }:
            # Fresh work after pause/done
            state.evidence_progress = False
            state.evidence_pause = False
            state.evidence_done = False
            state.mutations_since_checkpoint = 0
            state.meaningful_work = False
            state.set_phase(GuardPhase.not_required)
        return TransitionResult(state, state.phase != before)

    if event == GuardEvent.trivial_activity:
        return TransitionResult(state, False)

    if event == GuardEvent.meaningful_mutation:
        state.meaningful_work = True
        state.mutations_since_checkpoint += 1
        if path_hint:
            _note_path(state, path_hint)
        phase = state.phase_enum()
        if phase in {
            GuardPhase.not_required,
            GuardPhase.paused,
            GuardPhase.completed,
        }:
            if _continuity_ok(state):
                state.set_phase(GuardPhase.active)
            else:
                state.set_phase(GuardPhase.required_unestablished)
        elif phase == GuardPhase.active:
            if state.mutations_since_checkpoint >= cfg.checkpoint_after_mutations:
                state.set_phase(GuardPhase.checkpoint_due)
        elif phase == GuardPhase.persistence_unavailable:
            pass  # allow work without trapping
        return TransitionResult(state, state.phase != before)

    if event == GuardEvent.file_edit:
        state.meaningful_work = True
        state.files_changed += 1
        state.mutations_since_checkpoint += 1
        if path_hint:
            _note_path(state, path_hint)
        phase = state.phase_enum()
        if phase in {
            GuardPhase.not_required,
            GuardPhase.paused,
            GuardPhase.completed,
        }:
            if _continuity_ok(state):
                state.set_phase(GuardPhase.active)
            else:
                state.set_phase(GuardPhase.required_unestablished)
        elif (
            phase == GuardPhase.active
            and state.mutations_since_checkpoint >= cfg.checkpoint_after_mutations
        ):
            state.set_phase(GuardPhase.checkpoint_due)
        return TransitionResult(state, state.phase != before)

    if event in {
        GuardEvent.continuity_established,
        GuardEvent.forge_fallback_observed,
    }:
        if event == GuardEvent.forge_fallback_observed:
            state.evidence_forge_fallback = True
            state.continuity_method = "forge"
            if fallback_issue_number is not None:
                state.fallback_issue_number = fallback_issue_number
            if fallback_issue_url:
                state.fallback_issue_url = fallback_issue_url
        else:
            state.continuity_method = continuity_method or state.continuity_method or "mcp"
        if project_slug:
            state.project_slug = project_slug
        if thread_id:
            state.thread_id = thread_id
        state.persistence_unavailable = False
        if state.phase_enum() in {
            GuardPhase.required_unestablished,
            GuardPhase.not_required,
            GuardPhase.persistence_unavailable,
        }:
            state.set_phase(GuardPhase.active)
        elif state.phase_enum() == GuardPhase.checkpoint_due:
            # Establishing continuity mid-checkpoint stays checkpoint_due until write
            pass
        elif state.phase_enum() in {GuardPhase.paused, GuardPhase.completed}:
            state.set_phase(GuardPhase.active)
        return TransitionResult(state, True, "continuity_established")

    if event == GuardEvent.checkpoint_observed:
        state.evidence_progress = True
        state.mutations_since_checkpoint = 0
        state.evidence_pause = False
        state.evidence_done = False
        if project_slug:
            state.project_slug = project_slug
        if thread_id:
            state.thread_id = thread_id
        if not state.continuity_method:
            state.continuity_method = continuity_method or "mcp"
        state.set_phase(GuardPhase.active)
        return TransitionResult(state, True, "checkpoint")

    if event == GuardEvent.pause_observed:
        state.evidence_pause = True
        state.evidence_progress = True
        state.mutations_since_checkpoint = 0
        if thread_id:
            state.thread_id = thread_id
        state.set_phase(GuardPhase.paused)
        return TransitionResult(state, True, "paused")

    if event == GuardEvent.done_observed:
        state.evidence_done = True
        state.evidence_progress = True
        state.mutations_since_checkpoint = 0
        if thread_id:
            state.thread_id = thread_id
        state.set_phase(GuardPhase.completed)
        return TransitionResult(state, True, "completed")

    if event == GuardEvent.persistence_unavailable:
        state.persistence_unavailable = True
        state.continuity_method = "none"
        state.set_phase(GuardPhase.persistence_unavailable)
        state.last_warning = "ADHD Hub continuity persistence unavailable"
        return TransitionResult(state, True, "persistence_unavailable")

    return TransitionResult(state, False)


def _continuity_ok(state: GuardState) -> bool:
    """Single definition of established continuity (same as ``continuity_established``)."""
    return continuity_established(state)


def _note_path(state: GuardState, path_hint: str) -> None:
    clean = path_hint.replace("\\", "/").split("/")[-1]
    if clean and clean not in state.touched_paths:
        state.touched_paths.append(clean)
        if len(state.touched_paths) > 40:
            state.touched_paths = state.touched_paths[-40:]


def continuity_established(state: GuardState) -> bool:
    """True when Hub MCP or forge fallback evidence is present."""
    return bool(
        (state.evidence_resolve and state.evidence_digest)
        or state.evidence_progress
        or state.evidence_forge_fallback
        or (state.evidence_resolve and state.evidence_overlap)
        or state.persistence_unavailable
    )


MSG_ESTABLISH = (
    "ADHD Hub continuity is required before finishing substantial work.\n\n"
    "1. Resolve the current project with create_if_missing=false.\n"
    "2. Load session_digest/check_overlap as appropriate.\n"
    "3. Reuse or establish the correct finishable thread.\n"
    "4. If Hub MCP is unavailable, use the authorised [ADHD] forge fallback.\n"
    "5. Then retry stop / continue the work.\n\n"
    "Do not claim continuity was saved without a successful persistence action."
)

MSG_MUTATION_BLOCK = (
    "ADHD Hub continuity is required before substantial mutation.\n\n"
    "1. Resolve the current project with create_if_missing=false.\n"
    "2. Load session_digest/check_overlap as appropriate.\n"
    "3. Reuse or establish the correct finishable thread.\n"
    "4. If Hub MCP is unavailable, use the authorised [ADHD] forge fallback.\n"
    "5. Then retry the requested work.\n\n"
    "Do not claim continuity was saved without a successful persistence action."
)

MSG_CHECKPOINT_OR_PAUSE = (
    "Before stopping, checkpoint the current ADHD Hub thread with:\n"
    "- current Goal\n"
    "- one Focus action\n"
    "- max 3 Next steps\n"
    "- blocker only if real\n"
    "- concrete Resume cue\n\n"
    "If leaving incomplete work, also call pause_thread. "
    "If Hub MCP is unavailable, update the authorised [ADHD] forge fallback. "
    "Then stop again."
)

MSG_MARK_DONE = (
    "Meaningful work looks complete, but mark_done evidence is missing.\n\n"
    "1. Final progress/checkpoint if useful.\n"
    "2. If completion.ready (or Goal clearly done): mark_done for that thread only.\n"
    "3. If work remains: pause_thread instead — do not retry a rejected mark_done.\n"
    "4. Do NOT close unrelated overlap candidates.\n"
    "If Hub MCP is unavailable, update the [ADHD] forge fallback with completion state.\n"
    "Then stop again."
)

MSG_RETRY_CAP = (
    "ADHD Hub continuity guard: stop allowed after retry cap. "
    "Continuity may be incomplete — do not invent Hub state."
)


def stop_decision(
    state: GuardState,
    *,
    config: GuardConfig,
    loop_count: int = 0,
    work_looks_complete: bool = False,
) -> tuple[str | None, bool]:
    """Return ``(followup_message_or_None, allow_stop)``.

    Bounded by ``config.max_stop_retries`` and Cursor ``loop_count``.
    """
    phase = state.phase_enum()
    retries = max(state.guard_retry_count, loop_count)

    if phase == GuardPhase.not_required and not state.meaningful_work:
        return None, True

    if phase in {GuardPhase.paused, GuardPhase.completed}:
        return None, True

    if phase == GuardPhase.persistence_unavailable:
        return None, True

    if phase == GuardPhase.required_unestablished:
        if retries >= config.max_stop_retries:
            state.last_warning = MSG_RETRY_CAP
            return None, True
        state.guard_retry_count = retries + 1
        return MSG_ESTABLISH, False

    if phase in {GuardPhase.active, GuardPhase.checkpoint_due}:
        if work_looks_complete and not state.evidence_done:
            if retries >= config.max_stop_retries:
                state.last_warning = MSG_RETRY_CAP
                return None, True
            state.guard_retry_count = retries + 1
            return MSG_MARK_DONE, False
        # Unfinished meaningful work needs pause/checkpoint
        if not state.evidence_pause and not state.evidence_done:
            # Allow stop if recently checkpointed and not checkpoint_due
            if (
                phase == GuardPhase.active
                and state.evidence_progress
                and state.mutations_since_checkpoint == 0
            ):
                # Still prefer pause when leaving — one nudge
                if retries >= config.max_stop_retries:
                    state.last_warning = MSG_RETRY_CAP
                    return None, True
                state.guard_retry_count = retries + 1
                return MSG_CHECKPOINT_OR_PAUSE, False
            if retries >= config.max_stop_retries:
                state.last_warning = MSG_RETRY_CAP
                return None, True
            state.guard_retry_count = retries + 1
            return MSG_CHECKPOINT_OR_PAUSE, False
        return None, True

    return None, True
