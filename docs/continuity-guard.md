# Continuity Guard

ADHD Hub skills and AGENTS rules tell coding agents **how** to keep continuity.
They remain advisory — agents can still finish substantial work without calling
Hub MCP or writing an authorised `[ADHD]` forge fallback.

The **Continuity Guard** adds deterministic, non-LLM enforcement using:

- ephemeral Git-local state
- Cursor lifecycle hooks
- evidence of Hub MCP / forge actions (not self-attestation)
- project-sync for opt-in installation

```text
Agent rule / skill guidance
          │
          ▼
Cursor lifecycle hooks
          │
          ▼
adhd-hub continuity guard
          │
          ├── deterministic state/evidence
          ├── project/session requirement
          ├── checkpoint requirement
          └── completion requirement
          │
          ▼
Agent performs Hub MCP action
          │
          ├── Hub available → normal Hub thread
          │
          └── Hub unavailable → authorised [ADHD] forge fallback
          │
          ▼
Guard sees sufficient evidence
          │
          ▼
Agent may continue / finish
```

The guard **never fabricates Hub state**.

## Why rules alone are not enough

Rules and skills are prompt guidance. They do not observe tool success, cannot
block mutations, and cannot force a stop follow-up. Hooks + local evidence close
that gap without introducing an AI classifier.

## Setup (opt-in)

```bash
adhd-hub setup . --continuity-guard
# or
adhd-hub sync-project . --continuity-guard
```

This does **not** run automatically with `--project-skills`. Existing repos stay
unenrolled until you opt in.

Writes / merges:

| Path | Behaviour |
|------|-----------|
| `.cursor/hooks/adhd-hub-guard.sh` | Hub-owned thin wrapper → `adhd-hub guard hook` |
| `.cursor/hooks.json` | Hub entries upserted; unrelated hooks preserved |
| `.claude/hooks/adhd-hub-guard.sh` | Thin wrapper → `adhd-hub guard hook --adapter claude` |
| `.claude/settings.json` | Hub PreToolUse / PostToolUse / Stop merged; unrelated settings preserved |
| `adhd-hub.toml` | Seeded when missing (`[continuity_guard] enabled = true`) |

**Codex** and **OpenClaw** are not given lifecycle deny hooks (no equivalent Hub-managed surface). They stay **advisory** via skills / AGENTS / MCP / forge — see the strength table below.

Uninstall Hub integration only:

```bash
# Via Python API / future CLI — sync does not delete unrelated hooks
python -c "from adhd_hub.project_sync import uninstall_continuity_guard as u; print(u('.'))"
```

## Enforcement strength by agent

| Agent | Level | Notes |
|-------|-------|-------|
| Cursor | **strong** | Deny mutations, edit counts, stop follow-ups (`loop_limit`) |
| Claude Code | **medium** | PreToolUse deny + PostToolUse evidence + Stop block-nudge; SessionStart/End unused |
| Codex | **advisory** | Skills + MCP + forge + optional `adhd-hub guard observe` — no Hub-managed deny hooks |
| OpenClaw | **advisory** | Coding continuity is skills/MCP/forge; Hub→OpenClaw reminder hooks are a separate direction |

Adapters: [cursor-hooks.md](../adapters/cursor-hooks.md), [claude-hooks.md](../adapters/claude-hooks.md), [codex.md](../adapters/codex.md), [openclaw.md](../adapters/openclaw.md).

## CLI

```bash
adhd-hub guard status .
adhd-hub guard begin .
adhd-hub guard observe . --tool resolve_project
adhd-hub guard checkpoint .
adhd-hub guard finish .
adhd-hub guard reset .
adhd-hub guard audit .
adhd-hub guard hook .                    # Cursor (auto-detect)
adhd-hub guard hook --adapter claude .   # Claude Code stdin/stdout JSON
```

## Local state

State lives at:

```text
.git/adhd-hub/continuity-guard.json
```

- Not normally committed
- Disposable / reconstructable
- No credentials, tokens, or transcripts
- Stale state (default 48h) is soft-reset so old sessions do not block new work

## State machine

```text
not_required → required_unestablished → active ⇄ checkpoint_due
                     ↓                      ↓
            persistence_unavailable      paused / completed
```

| Phase | Meaning |
|-------|---------|
| `not_required` | Trivial / read-only session |
| `required_unestablished` | Meaningful work started; no Hub/forge evidence yet |
| `active` | Continuity established |
| `checkpoint_due` | Enough mutations since last checkpoint |
| `paused` | `pause_thread` (or equivalent) observed |
| `completed` | `mark_done` observed |
| `persistence_unavailable` | Hub + forge unavailable; coding still allowed |

## Meaningful-work heuristics

Conservative signals only (no LLM classification):

**Usually skip:** read-only tools, single tiny comment/typo, formatting-only.

**Usually require:** Write/multi-file edits, migrations, `gh pr create`,
substantial shell mutators, edit counts past threshold, explicit begin.

Thresholds live in `adhd-hub.toml`:

```toml
[continuity_guard]
enabled = true
mode = "balanced"
max_stop_retries = 2
checkpoint_after_mutations = 5
```

## Cursor hooks

Verified against current Cursor docs (`hooks.json` version 1, command hooks).

### Cloud-safe (required path)

| Hook | Guard behaviour |
|------|-----------------|
| `preToolUse` | Deny meaningful mutations when `required_unestablished` |
| `postToolUse` | Record Hub MCP (`MCP:<tool>`) / forge / mutation evidence |
| `afterFileEdit` | Count meaningful edits |
| `preCompact` | **Observational only** — emits `user_message`; cannot block compaction |
| `stop` | Strongest enforcement via `followup_message`; `loop_limit: 2` |

### Local-only enrichment

`beforeMCPExecution` / `afterMCPExecution` improve MCP evidence when available.
**Cloud Agents do not support these hooks** — Cloud must rely on `preToolUse` /
`postToolUse`.

Do not depend on `sessionStart` / `sessionEnd` for Cloud Agents.

Hooks fail-open: if `adhd-hub` is missing from PATH, the wrapper prints `{}` and
exits 0 so coding is never bricked.

## MCP-first and forge fallback

1. Hub MCP available → resolve / digest / progress / pause / done as usual.
2. Hub unavailable → authorised `[ADHD]` forge issue (Inbox authors allowlist).
3. Neither available → record `persistence_unavailable`, warn once, allow work.

Optional machine marker in forge bodies (ignored by inbox section import):

```html
<!-- adhd-hub:continuity-fallback:v1 -->
```

Do not claim Hub imported a forge issue until inbox sync does.

## Stop / preCompact behaviour

- **Stop** with unfinished meaningful work → follow-up asking for checkpoint +
  `pause_thread` (or forge update).
- **Stop** with completed work but no `mark_done` evidence → follow-up for done.
- After **2** automatic follow-ups (`loop_limit` + local counter), stop is allowed
  with a continuity warning — never trap Cursor forever.
- **preCompact** cannot delay compaction under current Cursor schema; it only
  surfaces a user-visible reminder. Checkpoint enforcement also relies on stop /
  preToolUse.

## Doctor / audit

```bash
adhd-hub doctor --project .
adhd-hub guard audit .
```

Doctor reports `continuity guard installed` or `not enabled` (informational —
unenrolled projects do not fail doctor for missing guard).

`guard audit` is CI-safe: checks hooks/script/config only, never private
`.git/adhd-hub` runtime state. Do **not** require an `[ADHD]` issue on every PR.

## Privacy / security

- Never log bearer tokens or persist credentials in guard state
- Treat hook stdin as untrusted data; parse with a real JSON parser
- Never `eval` or shell-interpolate payload strings
- Never copy transcripts or absolute private paths into forge issues
- Preserve HTTPS / encrypted-overlay bearer policy from Hub skills

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Hooks never fire | Ensure workspace trusted; `.cursor/hooks.json` present; Cloud needs writable env |
| Mutations not blocked | Confirm enrollment + meaningful mutation (reads are never blocked) |
| `adhd-hub: command not found` | Install package / ensure PATH; wrapper fails open |
| Stuck stop loops | Cap is 2; `adhd-hub guard reset .` clears local state |
| Unrelated hooks missing | Report a bug — merge should preserve non-Hub entries |

## Related

- [project-sync.md](project-sync.md)
- [forge-issue-inbox.md](forge-issue-inbox.md)
- [project-agent-setup.md](project-agent-setup.md)
- [adapters/cursor-hooks.md](../adapters/cursor-hooks.md)
