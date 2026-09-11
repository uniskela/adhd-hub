# Connect report UX + coding companions expansion

**Date:** 2026-09-11  
**Status:** draft — awaiting user review  
**Scope:** ADHD-friendly connect/doctor CLI output; document four additional recommended companions.

---

## Goals

1. Make `adhd-hub connect` / `doctor` (and thus install.ps1 / install.sh) easy to scan for ADHD brains: lead with outcome + next action, color by severity, collapse OK noise, keep warn/fail fully visible.
2. Expand `docs/coding-companions.md` with Superpowers, Context7, agent-browser, and Serena — clear strength (strong vs optional), licenses/privacy notes, manual install pointers. **No new `--with-*` auto-install flags for these four in this change** (they are plugins/MCPs with agent-specific setup; Hub stays recommendation-only).

## Non-goals

- Adding `rich` / `colorama` dependencies.
- Auto-installing Superpowers, Context7, agent-browser, or Serena from connect.
- Redesigning Hub Settings companion toggles for the new four (docs + soft checklist only).
- Changing companion install behavior for i-have-adhd / Graphify / RTK beyond report formatting.

---

## Part A — Connect / doctor report UX

### Approach

Tiny stdlib ANSI helpers (e.g. `src/adhd_hub/cli_style.py`):

- Color **on** when stdout is a TTY and neither `NO_COLOR` nor `ADHD_HUB_NO_COLOR` is set.
- Color **off** when piped, CI, or those env vars are set.
- Shared helpers: `style(text, *, fg=..., bold=...)`, status marks, section headers.
- No new package dependencies.

### Live run output

Today: `Running: <command>`

Change to a quieter, shared prefix, e.g.:

```text
→ Running  uv tool install graphifyy
```

- Dim/muted when color is on.
- Same helper used from connect’s command runner (the existing `print("Running:", …)` site).
- Do **not** try to recolor third-party tool stdout (skills CLI, graphify banners stay as upstream prints them).

### Final report — default (not verbose)

Order on screen:

1. **Banner** — success: green “Connected” (keep recognizable wording, e.g. `Complete! ADHD Hub is connected.`); failure: red “Connect finished with errors…”. Hub URL on the next line.
2. **Do next** (success) or **Fix these** (failure) — numbered, short, actionable. Prefer existing next-step content; on failure, list only warn/error/missing steps that need action (name + short detail).
3. **Needs attention** — every step with status `warn` | `error` | `missing` | `manual`, full detail, colored marks.
4. **Done** — collapsed OK / skipped groups with counts only, e.g.:
   - `Hub · 3 ok`
   - `Agents · 4 ok`
   - `Companions · 5 ok`
   - `Other · 1 ok` (if any)
5. Skip empty sections (e.g. no “Needs attention” when all ok).

### Final report — verbose

When `--verbose` is passed to `connect` / `doctor` (reuse existing global `-v` / `--verbose` on the CLI parser and thread into `print_report(report, *, verbose=False)`):

- After the banner (and optional short next/fix block), print the **full flat list** as today: `[OK] name: detail` (with color on marks).
- Still keep the banner + next/fix block so ADHD defaults aren’t lost.

### Status marks and colors

| Status | Mark | Color (when enabled) |
|--------|------|----------------------|
| ok | OK | green |
| skipped | -- | dim |
| manual | -- | dim (or cyan if we need contrast; default dim) |
| warn | !! | yellow |
| missing | !! | yellow |
| error | XX | red |

### Step grouping rules

Classify by step **name** prefix / known names:

| Group | Matches |
|-------|---------|
| Hub | `hub probe`, `register`, `setup complete`, names starting with `hub ` |
| Agents | `cursor MCP`, `cursor rule`, `codex MCP`, `AGENTS.md`, `skills`, `skills CLI`, `openclaw`, agent guidance |
| Companions | `companions note`, `companions agents`, names starting with `companion `, `install i-have-adhd`, `install graphify`, `install rtk` |
| Other | everything else |

Exact name lists live in one small mapping next to `print_report` so tests can pin behavior.

### Tests

- Extend `test_print_report_*`: default output contains banner, `Do next` / `Fix these` / `Needs attention` / `Done` as appropriate; OK details collapsed unless verbose.
- Verbose: full `[OK] hub probe:` (or equivalent) lines present.
- With color forced off (env or monkeypatch), output has no ANSI escapes; structure assertions use plain text.
- Existing connect/companion tests keep passing.

### Files (expected)

- `src/adhd_hub/cli_style.py` (new)
- `src/adhd_hub/connect.py` — `print_report`, live `Running` line
- `src/adhd_hub/cli.py` — pass `verbose=args.verbose` into `print_report`
- `tests/test_connect.py` (+ small style tests if useful)

---

## Part B — Coding companions guide expansion

### Doc table (top of `docs/coding-companions.md`)

Keep existing three installable companions; add:

| Role | Tool | Recommendation |
|------|------|----------------|
| Continuity (this product) | ADHD Progress Hub | Required for Hub |
| Reply shape | [i-have-adhd](https://github.com/ayghri/i-have-adhd) | Strong add (existing `--with-i-have-adhd`) |
| Codebase map | [Graphify](https://github.com/Graphify-Labs/graphify) | Strong add (existing `--with-graphify`) |
| Quieter shell output | [RTK](https://github.com/rtk-ai/rtk) | Strong add (existing `--with-rtk`) |
| Agent workflow | [Superpowers](https://github.com/obra/superpowers) | Strong add — **docs / checklist only** |
| Current docs | [Context7](https://github.com/upstash/context7) | Strong add — **docs / checklist only** |
| Browser verification | [agent-browser](https://github.com/vercel-labs/agent-browser) | Strong add — **docs / checklist only** |
| Semantic code navigation | [Serena](https://github.com/oraios/serena) | Optional / advanced — **docs / checklist only** |

Strip tracking query params from URLs.

### New sections (same pattern as existing)

For each of Superpowers, Context7, agent-browser, Serena:

- License (link to upstream LICENSE when known; if unclear, “see upstream repo”)
- What it does (1–2 sentences)
- Privacy / network note (especially Context7 remote docs MCP; Serena local vs remote; agent-browser local browser control)
- Manual install / enable pointers (official README links; Cursor MCP / plugin style — **no Hub `--with-*`**)
- Explicit: Hub does not install or update these

### Soft recommend in connect/doctor (optional, light)

Add one `companions note` detail or a single extra step such as:

- `companion workflow pack` / status `manual` — “Also consider Superpowers, Context7, agent-browser (+ Serena advanced) — see coding-companions.md”

Do **not** detect install presence for these four in v1 (unreliable across agents).  
Do **not** add Settings toggles or install.ps1 bake-ins for them in this change.

### Ethics

Same as existing: recommendations only; no vendoring; respect licenses; no silent MCP/plugin installs.

---

## Rollout / verification

1. Unit tests for `print_report` default + verbose + no-color.
2. Manual: `uv run adhd-hub doctor …` and `connect --dry-run` (if available) in a TTY; confirm sections and colors.
3. Rebuild wheel / restart Hub only if shipping via `/install.ps1` (same as other CLI changes).
4. `graphify update .` after code edits.

## Risks

- Over-collapsing OK steps might hide a surprising “ok but weird” detail → mitigated by `--verbose`.
- Group misclassification of new step names → keep mapping explicit + tests.
- Companion docs drift if upstream install steps change → link README, don’t duplicate long recipes.

## Rollback

Revert `cli_style.py` + `print_report` / docs changes; no schema or prefs migrations.
