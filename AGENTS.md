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
