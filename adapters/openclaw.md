# OpenClaw + ADHD Hub

Use the [OpenClaw connection and alerts guide](../docs/public/openclaw.md) for the plain-language two-service model, supported skill-install command, Gateway hook-token setup, Hub-to-OpenClaw hook configuration, HTTPS domain/reverse-proxy requirements, and an alert test. Agents should never reveal or paste the hook token; the operator or deployment secret mechanism must provision it. This guide is the canonical source for this adapter so the public wiki and repository guide stay aligned.

## Continuity guard (advisory)

OpenClaw does **not** get Hub-managed coding-agent deny hooks. Continuity for
coding sessions is **advisory** (skills / MCP / forge). Hub→OpenClaw reminder
hooks are a separate direction and are not the Continuity Guard. Opt-in
`sync-project --continuity-guard` enrolls Cursor/Claude in the repo; see
[docs/public/continuity-guard.md](../docs/public/continuity-guard.md) for the strength table.
