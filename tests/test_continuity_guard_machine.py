"""State-machine tests for the continuity guard."""

from __future__ import annotations

from adhd_hub.continuity_guard.config import GuardConfig
from adhd_hub.continuity_guard.machine import (
    GuardEvent,
    GuardPhase,
    apply_event,
    stop_decision,
)
from adhd_hub.continuity_guard.state import GuardState

CFG = GuardConfig(enabled=True, mode="balanced", max_stop_retries=2, checkpoint_after_mutations=5)


def test_trivial_session_stays_not_required() -> None:
    state = GuardState()
    apply_event(state, GuardEvent.trivial_activity, config=CFG)
    assert state.phase_enum() == GuardPhase.not_required
    followup, allow = stop_decision(state, config=CFG, loop_count=0)
    assert allow and followup is None


def test_meaningful_mutation_requires_continuity() -> None:
    state = GuardState()
    apply_event(state, GuardEvent.meaningful_mutation, config=CFG, path_hint="src/app.py")
    assert state.phase_enum() == GuardPhase.required_unestablished
    assert state.meaningful_work is True


def test_continuity_evidence_moves_to_active() -> None:
    state = GuardState()
    apply_event(state, GuardEvent.meaningful_mutation, config=CFG)
    state.evidence_resolve = True
    state.evidence_digest = True
    apply_event(state, GuardEvent.continuity_established, config=CFG, continuity_method="mcp")
    assert state.phase_enum() == GuardPhase.active
    assert state.continuity_method == "mcp"


def test_edits_eventually_checkpoint_due() -> None:
    state = GuardState()
    state.evidence_resolve = True
    state.evidence_digest = True
    apply_event(state, GuardEvent.continuity_established, config=CFG)
    for i in range(5):
        apply_event(state, GuardEvent.file_edit, config=CFG, path_hint=f"f{i}.py")
    assert state.phase_enum() == GuardPhase.checkpoint_due


def test_checkpoint_clears_due() -> None:
    state = GuardState()
    state.set_phase(GuardPhase.checkpoint_due)
    state.meaningful_work = True
    state.mutations_since_checkpoint = 9
    apply_event(state, GuardEvent.checkpoint_observed, config=CFG)
    assert state.phase_enum() == GuardPhase.active
    assert state.mutations_since_checkpoint == 0
    assert state.evidence_progress is True


def test_pause_evidence_permits_stop() -> None:
    state = GuardState()
    state.meaningful_work = True
    state.set_phase(GuardPhase.active)
    apply_event(state, GuardEvent.pause_observed, config=CFG, thread_id="abc")
    assert state.phase_enum() == GuardPhase.paused
    followup, allow = stop_decision(state, config=CFG)
    assert allow and followup is None


def test_done_evidence_permits_stop() -> None:
    state = GuardState()
    state.meaningful_work = True
    apply_event(state, GuardEvent.done_observed, config=CFG)
    assert state.phase_enum() == GuardPhase.completed
    followup, allow = stop_decision(state, config=CFG)
    assert allow and followup is None


def test_stop_requires_establish_then_retry_cap() -> None:
    state = GuardState()
    apply_event(state, GuardEvent.meaningful_mutation, config=CFG)
    assert state.phase_enum() == GuardPhase.required_unestablished
    msg1, allow1 = stop_decision(state, config=CFG, loop_count=0)
    assert not allow1 and msg1
    msg2, allow2 = stop_decision(state, config=CFG, loop_count=1)
    assert not allow2 and msg2
    msg3, allow3 = stop_decision(state, config=CFG, loop_count=2)
    assert allow3 and msg3 is None
    assert state.last_warning


def test_persistence_unavailable_does_not_loop() -> None:
    state = GuardState()
    apply_event(state, GuardEvent.meaningful_mutation, config=CFG)
    apply_event(state, GuardEvent.persistence_unavailable, config=CFG)
    assert state.phase_enum() == GuardPhase.persistence_unavailable
    followup, allow = stop_decision(state, config=CFG, loop_count=0)
    assert allow and followup is None


def test_forge_fallback_establishes_active() -> None:
    state = GuardState()
    apply_event(state, GuardEvent.meaningful_mutation, config=CFG)
    apply_event(
        state,
        GuardEvent.forge_fallback_observed,
        config=CFG,
        fallback_issue_number=265,
        fallback_issue_url="https://github.com/uniskela/adhd-hub/issues/265",
    )
    assert state.phase_enum() == GuardPhase.active
    assert state.continuity_method == "forge"
    assert state.fallback_issue_number == 265
