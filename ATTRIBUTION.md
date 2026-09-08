# Attribution

## claude-adhd

ADHD Progress Hub is a new project inspired by
[shaheer-00/claude-adhd](https://github.com/shaheer-00/claude-adhd)
by shaheer.

Ideas adapted (not copied as a Claude Code plugin):

- Capturing unfinished threads from coding-agent sessions
- Session digests and gentle reminders for ADHD-friendly workflows
- Heuristic transcript patterns for “I’ll do X later” / TODO-style language
- Local-first privacy (summaries, not uploading full chats by default)

ADHD Hub reimplements these concepts as a **self-hosted MCP + REST service**
so Cursor, Codex, Claude Code, and other agents can share one source of truth,
with optional OpenClaw notifications.

claude-adhd remains the Claude Code–native plugin; this repo is intentionally
tool-agnostic.
