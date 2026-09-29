# Claude Code hooks (continuity guard)

Canonical Hub-owned Claude Code hooks are **command** hooks merged into
`.claude/settings.json`. Prefer project sync rather than hand-copying:

```bash
adhd-hub setup . --continuity-guard
# or
adhd-hub sync-project . --continuity-guard
```

That writes:

- `.claude/hooks/adhd-hub-guard.sh` — thin wrapper → `adhd-hub guard hook --adapter claude`
- `.claude/settings.json` — **merges** Hub PreToolUse / PostToolUse / Stop entries; preserves unrelated settings

Canonical reference: [claude-hooks.json](claude-hooks.json).

## Strength (honest)

| Surface | Level | What Hub manages |
|---------|-------|------------------|
| Claude Code | **medium** | PreToolUse can deny mutations; PostToolUse observes Hub/forge evidence; Stop can block-nudge up to the configured retry limit (default `max_stop_retries=2`) |
| Cursor | **strong** | Full lifecycle deny + stop loop_limit (see [cursor-hooks.md](cursor-hooks.md)) |
| Codex / OpenClaw | **advisory** | Skills + MCP + forge; no Hub-managed lifecycle deny hooks |

SessionStart / SessionEnd are **not** used for enforcement.

See [docs/continuity-guard.md](../docs/continuity-guard.md).
