# Return-cue agent guidance

This page explains how agents respond to return-cue coaching. Root
[AGENTS.md](../../AGENTS.md), [skills/](../../skills/) and
[adapters/](../../adapters/) remain canonical agent instructions.

See the [implementation contract](../internal/contracts/return-cue-coaching.md)
and [public guide](../public/return-cue-coaching.md) for the payload and limits.

When a checkpoint or pause returns a `return_cue` that is not `concrete`, an
agent that knows the real first action from the current session should send one
improved `resume_step`. It should not invent files or commands to pass the
check, and should not retry in a loop.
