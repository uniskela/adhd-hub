# Return-cue coaching

A return cue is your thread's `resume_step`: the first thing to do when you
come back. Coaching quietly suggests making that step specific enough to
restart from.

| Weak | Better |
| --- | --- |
| Continue later | Open service.py, finish the failing sync test, then run pytest |
| Fix the issue | Reproduce the auth error and inspect the failing OAuth callback test |

## Guarantees

Coaching is advisory: it never blocks a save, pause, completion or merge, and
does not affect `completion.ready`. It uses deterministic local rules and only
the current thread's fields. It makes no AI calls or network requests and
does not invent files, commands or facts.

## Where it appears

The dashboard shows coaching beside resume fields on Now and My work. Existing
thread, progress, pause, digest and overview REST/MCP responses include a
`return_cue` field. Finished, dismissed and merged threads have `return_cue: null`.
Older clients can ignore the field. Overlap suggestions and `mark_done` keep
their existing focused responses.

## Shape

```json
{
  "quality": "vague",
  "signals": ["no_specifics"],
  "hint": "This resume step names nothing specific yet. Add what to open, run or check first.",
  "suggestion": {"source": "focus", "text": "Rewrite the retry loop in sync_worker"},
  "advisory": true,
  "version": 1
}
```

`quality` is `missing`, `vague` or `concrete`. `signals` explains a missing or
vague cue (`empty`, `placeholder`, `no_specifics` or `repeats_goal`). Concrete
cues have empty signals and a null hint. A suggestion, when available, repeats
the thread's own concrete focus or first next step; it does not write it for you.

## Limits

The check is lenient: one specific word is enough, so “Fix the auth bug” passes.
Its generic-word lists are English; other languages are treated as specific.
It cannot verify whether a file or command exists. Use your own judgment about
what will help you restart.

## UI notes

When a suggestion appears, **Use Focus** or **Use next step** can copy it into
the resume field for you to review. Pause, Save and Done stay available. Client
integrations should use `quality` and `signals` for behavior and treat `hint` as
display copy that can change.

## Agents

Connected agents can improve a vague cue once when they know the real first
action from the current session. They should not invent facts or repeatedly
retry to satisfy the check.

For exact response locations, UI behavior and maintainer fixtures, see the
[return-cue implementation contract](https://github.com/uniskela/adhd-hub/blob/main/docs/internal/contracts/return-cue-coaching.md).
