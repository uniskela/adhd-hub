---
name: graphify
description: >-
  Use the graphify knowledge graph to explore architecture, dependencies, and
  impact before reading or grepping the codebase; keep the graph current with
  graphify update . after code changes. Use when exploring this repo, answering
  architecture questions, tracing dependencies, assessing blast radius, or after
  editing code while graphify-out/ exists.
---

# Graphify

Local knowledge graph for this repo lives in `graphify-out/`.

CLI (Windows): `%USERPROFILE%\.local\bin\graphify.exe` — ensure that dir is on `PATH`, or invoke it by full path.

## When to use

| Situation | Command |
|-----------|---------|
| Any architecture / “how does X work?” question | `graphify query "<question>"` |
| Dependency between two symbols | `graphify path "<A>" "<B>"` |
| Everything related to a concept | `graphify explain "<concept>"` |
| Blast radius of a change | `graphify affected "<symbol>"` |
| Core hubs | `graphify god-nodes` |
| After editing code | `graphify update .` |

**Before** broad exploration with Read/Grep/Glob/Bash, run `query` / `path` / `explain` first (same rule as `.cursor/rules/graphify.mdc`). Pass this requirement into subagent prompts that explore code.

**After** modifying code files, always run:

```bash
graphify update .
```

AST-only refresh — no API key / LLM cost. Use `--force` (or `GRAPHIFY_FORCE=1`) if a refactor deleted a lot of code and the rebuild looks smaller than the old graph.

## Workflow

1. `graphify query "..."` (or `path` / `explain`) to get a scoped subgraph.
2. Open only the files/symbols the graph points to.
3. Edit.
4. `graphify update .`
5. Optionally `graphify affected "<changed-symbol>"` to check fallout.

## Navigation artifacts

- `graphify-out/GRAPH_REPORT.md` — communities, god nodes, broad review
- `graphify-out/wiki/index.md` — if present, prefer over raw file walks
- Default graph: `graphify-out/graph.json`

## Do not

- Skip graphify because the area “feels familiar”
- Dump the whole `graph.json` into chat — use query/path/explain
- Forget `graphify update .` after code changes (required by `AGENTS.md`)
