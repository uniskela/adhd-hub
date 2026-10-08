# Return-cue coaching

Wave 7 backend contract for [#54](https://github.com/uniskela/adhd-hub/issues/54).
The dashboard treatment is a separate UI task; this page is the contract it builds on.

A return cue is the thread's `resume_step`: the first thing to do when you come
back. Coaching tells people and coding agents whether that cue names something
specific enough to restart from.

| Weak | Better |
|---|---|
| Continue later | Open service.py, finish the failing sync test, then run pytest |
| Fix the issue | Reproduce the auth error and inspect the failing OAuth callback test |

## Guarantees

- **Advisory.** No save, pause, completion or merge is refused, delayed or
  altered because of cue wording. `completion.ready` ignores it.
- **Deterministic and local.** Word and pattern rules only. No AI call, no
  network, no forge lookup, nothing stored. The same fields always give the
  same result.
- **No invented facts.** Hints are fixed generic sentences. A suggestion only
  repeats text already stored on the same thread.
- **One thread at a time.** Only that thread's resume, goal, title, focus and
  next steps are read. Other threads and projects never contribute.

## Where it appears

No new tools or routes. The thread payloads listed below gain one `return_cue` key.

| Surface | Location |
|---|---|
| MCP `upsert_progress` / `POST /api/progress` | `thread.return_cue`, `candidates[].return_cue` |
| MCP `pause_thread` / `POST /api/threads/{id}/pause` | `return_cue` |
| MCP `session_digest` / `GET /api/digest` | `items[].return_cue` |
| MCP `get_overview` | `next_up.return_cue`, `triage_candidates[].return_cue` |
| `GET /api/overview` (`next_up`, `triage_candidates[]`), `GET /api/threads`, `GET /api/threads/{id}` | `return_cue` |

`return_cue` is `null` for done, dismissed and merged threads. Existing fields
are unchanged, so older clients can ignore the key.

Raw thread dumps do not carry the key, the same as `completion`: MCP
`list_open_threads`, `upsert_thread`, `mark_done`, and the thread objects inside
`check_overlap` / `suggest_duplicate_threads` hits. Use `session_digest` or
`get_overview` when coaching is wanted on a read.

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

| Field | Meaning |
|---|---|
| `quality` | `missing`, `vague` or `concrete` |
| `signals` | Stable reason codes (below); empty when `concrete` |
| `hint` | One short sentence, or `null` when `concrete` |
| `suggestion` | `null`, or `{source, text}` where `source` is `focus` or `next_steps` and `text` is that field's stored value (whitespace-normalised) |
| `advisory` | Always `true` |
| `version` | Contract version, currently `1` |

| `quality` | `signals` | When |
|---|---|---|
| `missing` | `empty` | No resume step, or whitespace only |
| `vague` | `placeholder` | Only a placeholder such as `TBD`, `n/a`, `todo` |
| `vague` | `no_specifics` | Every word is generic ("continue", "fix", "the issue", "later") and there is no file, path, identifier, inline code or `#123` reference |
| `vague` | `repeats_goal` | Same text as the thread's goal or title |
| `concrete` | — | Names at least one specific thing |

A suggestion is offered only when the cue is not `concrete` and the thread's own
Focus (or, failing that, its first Next step) is itself `concrete` and differs
from the cue.

## Limits

The rules lean lenient: one specific word is enough, so "Fix the auth bug"
passes. The generic-word lists are English; text in other languages is treated
as specific rather than flagged. The check cannot tell whether a named file or
command exists, and does not try.

## UI notes

- Show the hint quietly beside the Resume field or pause dialog, only when
  `quality` is not `concrete`. No badge counts, streaks, scores or red states.
- When `suggestion` is present, a single "Use Focus" / "Use next step" action
  can copy `suggestion.text` into the resume field for the person to confirm.
  Never write it automatically.
- Never disable Pause, Save or Done on `quality`.
- Key on `quality` and `signals`; treat `hint` as display copy that may be
  reworded without a version bump.
- Shared cases for UI tests: `tests/fixtures/return_cue/cases.json`.

## Agents

When a checkpoint or pause returns a `return_cue` that is not `concrete`, an
agent that knows the real first action from the current session should send one
improved `resume_step`. It should not invent files or commands to pass the
check, and should not retry in a loop.
