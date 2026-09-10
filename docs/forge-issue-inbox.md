# Forge issue inbox (remote / cloud agents)

Agents that cannot reach a private Tailscale Hub MCP can still leave unfinished work for ADHD Hub by opening forge issues. That includes **Cursor Cloud**, **Codex / ChatGPT cloud**, **Claude Code / Claude remote**, and similar sandboxed runners.

They *can* use GitHub/Gitea. The Hub polls those issues and turns them into threads.

## Security (author allowlist)

Inbox import is **fail closed**:

1. Only issues whose **author forge login** is in **Inbox authors** are imported.
2. If the allowlist is empty, the Hub imports **nothing** (even when inbox is enabled).
3. PRs are never imported. Issues already labeled `adhd-hub-synced` are skipped.
4. After a successful import, Hub **closes** the issue and adds `adhd-hub-synced` — it never deletes forge content.

Random collaborators (or anyone who can open issues on a public repo) cannot inject Hub threads unless you add their username.

Set authors in Settings → Forge → **Inbox authors**, or via env:

```bash
export ADHD_HUB_FORGE_BOARD_INBOX_AUTHORS="your-login,automation-bot"
```

Match GitHub `user.login` / Gitea username (case-insensitive).

## Enable

1. Settings → Connections → Forge: turn on **Board / issues** and **Import cloud-agent issues (inbox)**.
2. Add your forge username(s) under **Inbox authors**.
3. Save. Optionally click **Import issue inbox** once to test.
4. The Hub also polls on `ADHD_HUB_FORGE_INBOX_CRON` (default every 15 minutes).

## Agent protocol (any tool)

1. Create an issue titled `[ADHD] <short summary>` **as an allowlisted user** (token/bot identity must be on the allowlist). The prefix is case-insensitive (`[adhd]` / `[ADHD]`); optional whitespace after `]` is fine.
2. Labels (all optional):
   - `adhd-hub` — belt-and-suspenders if the agent *can* apply labels
   - `project:<slug>`
   - `source:codex` | `source:chatgpt` | `source:cursor` | `source:claude` | `source:claude-code`
3. Body: short Now / Done / Next / Return cue (no secrets).
4. After import, Hub **closes** the issue and adds `adhd-hub-synced` (never deletes).

**Title `[ADHD]` is sufficient** for allowlisted authors. The hub label is not required. Cursor Cloud agents often cannot set labels (`Resource not accessible by integration`); they should still open a title-prefixed issue and skip the label.

An issue with the hub label but no title prefix is still imported (label-only path).

## How listing works

Hub lists open issues with the same REST Issues endpoint already used for board sync:

`GET /repos/{owner}/{repo}/issues?state=open` (100 per page, at most 10 pages), then filters **client-side**.

We do **not**:

- pass GitHub `labels=adhd-hub` (that query never returns title-only issues)
- use GitHub Search (`in:title`) — Search is eventually consistent, so a just-opened cloud-agent issue can miss an immediate **Import issue inbox** click
- use GraphQL — extra permission surface for the same list

Gitea uses the same list-then-filter path (label **or** title prefix), with `limit=50` and `type=issues` because Gitea's page size max is 50 and it always serializes `pull_request` (null on real issues). Cost is typically one REST call per poll; a busy repo may use a few more pages. Issues beyond the page cap are not scanned.

## Skills on remote agents

Install Hub skills wherever the agent runs:

```bash
# Cursor / Codex / generic
npx skills add uniskela/adhd-hub -g

# Claude Code agent adapter
npx skills add uniskela/adhd-hub -g -a claude-code
```

Also keep a project `AGENTS.md` (via `adhd-hub setup` / `connect`) so every tool sees the same continuity rules. The session skill falls back to this forge mailbox when MCP is unreachable.

## Operator API

```bash
curl -sS -X POST -H "Authorization: Bearer $ADHD_HUB_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' \
  http://127.0.0.1:8787/api/forge/inbox/import
```

## Related adapters

- [Cursor](https://github.com/uniskela/adhd-hub/blob/main/adapters/cursor-mcp.json) / [Cursor rule](https://github.com/uniskela/adhd-hub/blob/main/adapters/cursor-rule.mdc)
- [Codex](https://github.com/uniskela/adhd-hub/blob/main/adapters/codex.md)
- [Claude Code](https://github.com/uniskela/adhd-hub/blob/main/adapters/claude-code.md)
