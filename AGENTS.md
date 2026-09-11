# AGENTS.md

Guidance for coding agents working in this repository.

## ADHD Progress Hub

- Prefer MCP tools from `adhd-hub` (`resolve_project`, `session_digest`, `check_overlap`, `upsert_progress`, `mark_done`, `set_reminder`) when starting, pausing, or finishing work that could be abandoned.
- Install skills globally when possible: `npx skills add ./skills -g` (or `uniskela/adhd-hub` once public).
- Do not invent hub state — only report what the tools return.
- Prefer summaries; never dump full chat transcripts into the hub.

## Graphify

This project keeps a knowledge graph under `graphify-out/`.

### Before exploring code

Orient with graphify **before** broad Read/Grep/Glob exploration:

```bash
graphify query "<question>"
graphify path "<A>" "<B>"
graphify explain "<concept>"
```

Use Read/Grep/Glob after orientation when you need exact lines to edit or debug. If `graphify-out/graph.json` is missing, build/update the graph first.

### After modifying code

Always refresh the graph (AST-only, no LLM / API cost):

```bash
graphify update .
```

Run this after meaningful code edits in the same session (not optional). Prefer the project root as `.`.

### Useful extras

```bash
graphify god-nodes
graphify affected "<symbol>"
graphify check-update .
```

If `graphify-out/wiki/index.md` exists, prefer it for navigation. Use `graphify-out/GRAPH_REPORT.md` for broad architecture review when query/path/explain are not enough.

See the Cursor skill [`.cursor/skills/graphify/SKILL.md`](.cursor/skills/graphify/SKILL.md) and rule [`.cursor/rules/graphify.mdc`](.cursor/rules/graphify.mdc).

<!-- adhd-hub:project-agent:start -->
<!-- adhd-hub:guidance-version:2 -->
## ADHD Hub continuity

For substantial work in this project:

- If ADHD Hub MCP tools are missing, errored, unauthorized, or otherwise
  unavailable: the **first line** of your reply on that turn (and on later
  substantial Hub-worthy turns while still down) MUST state that Hub MCP is
  not available, plus a short fix hint (MCP URL → this Hub's `/mcp`,
  `ADHD_HUB_AUTH_TOKEN`, restart the agent; skip/cancel Auth if it hangs
  until Hub OAuth is enabled). Then continue the authorized work. Never
  invent Hub state or claim a Hub write succeeded.
- Skip Hub for trivial/read-only/tiny work.
- Once per meaningful session: `resolve_project`, then `session_digest` with
  the task query. Reuse resolved context where possible.
- **One thread = one independently finishable outcome** (not the whole repo).
  Before updating a thread, compare new work to that thread's Goal; if it does
  not advance the same outcome, use another thread or create one.
- Known thread → `upsert_progress(thread_id=...)` with compact structured state
  (goal / focus / ≤3 next / blocked if any / resume). Do not silently attach
  to an unrelated open thread.
- `check_overlap` only before potentially new work; reuse only when the Goal
  matches. Different goal → separate thread (`force_new_thread` if needed).
- Pause with one concrete resume action; `mark_done` only the known completed
  thread — never close unrelated overlap results.
- If Hub guidance looks stale (session_digest guidance status, or doctor),
  mention it once, keep using the current MCP contract, and recommend
  `adhd-hub setup . --refresh` — do not nag repeatedly or hand-edit AGENTS.md.
- Summaries only; never secrets, credentials, env files, or transcripts.
<!-- adhd-hub:project-agent:end -->
