# Clock-Off agent guidance

This page explains Clock-Off coaching. Root [AGENTS.md](../../AGENTS.md),
[skills/](../../skills/) and [adapters/](../../adapters/) remain the canonical
agent instructions; this page does not replace them.

See the [implementation contract](../internal/contracts/clock-off-api.md)
and [public guide](../public/clock-off-api.md) for the state and override rules.

Treat `clock_off.guidance` as calm, advisory coaching. During wind-down, avoid
broad tasks, new PRs, refactors, audits and unrelated debugging. Finish only the
current small safe step where practical; use `upsert_progress` for a compact
checkpoint and `pause_thread` with a concrete next pickup action. Once clocked
off, prefer necessary wrap-up and a short safely parked summary. Mention the
boundary once rather than repeatedly nagging. Respect the explicit override.
Clock-Off never marks work done, auto-pauses it, or rejects a user action.
