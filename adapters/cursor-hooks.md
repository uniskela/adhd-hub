# Cursor hooks (continuity guard)

Canonical Hub-owned Cursor hooks are **command-based** (Cloud Agents do not
run prompt-based hooks). Prefer installing them through project sync rather
than hand-copying:

```bash
adhd-hub setup . --continuity-guard
# or
adhd-hub sync-project . --continuity-guard
```

That writes:

- `.cursor/hooks/adhd-hub-guard.sh` — thin wrapper calling `adhd-hub guard hook`
- `.cursor/hooks.json` — **merges** Hub entries; preserves unrelated hooks

Canonical reference: [cursor-hooks.json](cursor-hooks.json).

## Lifecycle

| Event | Role |
|-------|------|
| `preToolUse` | Deny meaningful mutations when continuity is required but unestablished |
| `postToolUse` | Observe Hub MCP / forge / mutations (Cloud-safe) |
| `afterFileEdit` | Count meaningful edits toward checkpoint |
| `preCompact` | Observational reminder only (cannot block compaction) |
| `stop` | Follow-up for pause/done/fallback; `loop_limit: 2` |
| `beforeMCPExecution` / `afterMCPExecution` | Local enrichment (not available on Cloud Agents) |

See [docs/public/continuity-guard.md](../docs/public/continuity-guard.md).

Legacy prompt-based sample (local IDE only, not Cloud-safe) remains in
[cursor-hooks.sample.json](cursor-hooks.sample.json) for reference — do not use
it for new installs.
