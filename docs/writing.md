# ADHD-friendly writing and planning

This is a lightweight, optional convention for project notes, plans, handoffs, issues, and pull requests. It makes the next useful action visible without asking a reader to reconstruct context. It is not medical advice and should be adapted to the person and project.

## The first-screen rule

Keep the top of every active note short enough to scan before you start work. It should answer these questions in order:

1. **Goal / Outcome** — what will be true when this is finished?
2. **Focus / Now** — what is the single, physical next action?
3. **Next** — at most three actions after the current one?
4. **Blocked** — who or what needs to move first? (omit when nothing is blocked)
5. **Resume / Return cue** — what should I do when I come back after a break?

Hub threads store these as structured fields (`goal`, `focus`, `next_steps`, `blocked_reason`, `resume_step`) plus a short title. Prefer updating those fields via `upsert_progress(thread_id=...)` instead of pasting a full diary every checkpoint.

Use a verb, a concrete object, and a location where useful: `Run uv run pytest`, `Open docs/authentication.md`, or `Ask Sam to confirm the DNS record`. Avoid labels such as “work on auth” that still require deciding how to begin.

## Active-work update

Hub rewrites `PROGRESS.md` with **Active threads** (current structured state), **Recent milestones** (meaningful changes only), and **History** (recoverable older detail). Do not duplicate unchanged state into history. Omit empty Blocked sections rather than writing `None`.

When writing freeform notes (issues, handoffs), keep completed history below the active section:

```markdown
## Goal
- Ship OAuth discovery + token endpoint for MCP clients.

## Focus
- Run `uv run pytest tests/test_oauth.py` and record the first failure, if any.

## Next
1. Fix the first failing OAuth test.
2. Run the full test suite.
3. Open a pull request with the deployment note.

## Resume
- When I reopen this work, start by running `uv run pytest tests/test_oauth.py`.
```

Guidelines:

- Make **Focus** exactly one action that can be started without another planning pass.
- Limit **Next** to three ordered actions. Move later ideas to a backlog or issue.
- Name the owner or unblock condition in **Blocked** only when something is waiting.
- Write the **Resume** cue as a concrete pickup instruction that works after several days away.
- One thread = one independently finishable outcome; do not append unrelated work to the same thread.

### 30-second minimum

When time or energy is low, write only this and resume the fuller format later:

```markdown
## Focus
- …

## Resume
- When I return, I will …
```

## Plans that stay usable during implementation

Put the decision-relevant parts first. A plan is a guide to the next decision, not a diary of every thought.

```markdown
# <short outcome-focused title>

## Outcome
- <observable result>

## Not doing
- <nearby work deliberately out of scope>

## Now
- <one startable action>

## Steps
1. <small observable step>
2. <small observable step>
3. <verification or delivery step>

## Decisions
- **<choice>:** <reason>; revisit when <condition>.

## Completion check
- <command, review, or user-visible confirmation>

## Return cue
- When I resume, I will <action>.
```

Keep one source of truth for a decision. Link to a detailed design, issue, or pull request rather than copying its full narrative into the plan.

## Writing patterns for shared work

| Surface | Start with | Keep it clear by |
| --- | --- | --- |
| Project description | The durable outcome or purpose | Separating it from the temporary task in the thread title |
| Issue | Observable problem and acceptance check | Listing reproduction, scope, and the next owner action |
| Pull request | What changed and how it was verified | Calling out risk, follow-up work, and screenshots/links only when needed |
| Decision note | Choice, reason, and revisit condition | Recording the consequence, not the whole discussion |
| Handoff | Current state and exact return cue | Naming paths, commands, IDs, and blockers explicitly |

Prefer short headings, one idea per bullet, plain language, and links or commands that can be opened or copied directly. Put a timestamp on a status update when recency matters. Put background material after the active section, where it remains available without competing with the next action.

## Why this pattern

The convention externalizes context, provides clear written cues, and makes re-entry an explicit action. Those choices draw on guidance and research without assuming one format works for everyone:

- NICE’s ADHD guideline discusses environmental modifications, clear written or visual instructions, and visual reminders: [NG87 recommendations](https://www.nice.org.uk/guidance/ng87/chapter/recommendations).
- “When _cue_, I will _action_” is an implementation-intention pattern supported by Gollwitzer and Sheeran’s meta-analysis: [Implementation Intentions and Goal Achievement (2006)](https://doi.org/10.1016/S0065-2601(06)38002-1).
- A meta-analysis of working-memory differences in children with ADHD supports reducing the need to hold task context in mind; this is background for externalizing context, not a claim about every adult: [Martinussen et al. (2005)](https://doi.org/10.1097/01.chi.0000153228.72591.73).
