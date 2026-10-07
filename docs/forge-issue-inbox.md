# Forge issue inbox (remote / cloud agents)

Use the forge issue inbox when a remote/cloud agent can reach GitHub or Gitea but **cannot reach Hub MCP**. This covers Cursor Cloud, Codex/ChatGPT cloud, Claude remote environments, and similar sandboxes.

If live MCP is possible, prefer a private mesh or controlled HTTPS tunnel. See [Remote MCP access](https://uniskela.com/docs/adhd-hub/remote-mcp-access/). Do not expose anonymous `/mcp` just to make cloud agents work.

## Agent fallback decision

1. Check the actual Hub MCP tool surface.
2. If tools are missing, erroring, or unauthorised, treat Hub persistence as unavailable.
3. If forge issue-write access is available, write a short `[ADHD] ...` handoff issue.
4. If neither Hub nor forge persistence is available, continue carefully and state that continuity was **not** saved.

Environment hints such as `CURSOR_AGENT` or remote-sandbox markers can support the decision, but they do not replace checking MCP. Use `env-check` for CLOUD_AGENT vs LOCAL_WORKSPACE. Cloud agents must not assume local helper CLIs such as `graphify` are installed.

Never invent Hub, thread, or graph state, and never claim a Hub write succeeded when MCP was unreachable.

GitHub/Gitea issues are the durable mailbox. The Hub polls eligible issues and turns them into threads.

## Security (author allowlist)

Inbox import is **fail closed**:

1. Only issues whose **author forge login** is in **Inbox authors** are imported.
2. If the allowlist is empty, the Hub imports **nothing** (even when inbox is enabled).
3. PRs are never imported. Open issues labeled `adhd-hub-synced` are still checked when
   they are linked to an existing imported thread, so a reopened and edited issue can refresh it.
4. When close-on-import is enabled, Hub **closes** the issue and adds `adhd-hub-synced` — it never deletes forge content.

Random collaborators (or anyone who can open issues on a public repo) cannot inject Hub threads unless you add their username.

Set authors in Settings → Issue sync → Advanced → **Inbox authors**, or via env:

```bash
export ADHD_HUB_FORGE_BOARD_INBOX_AUTHORS="your-login,automation-bot"
```

Match GitHub `user.login` / Gitea username (case-insensitive).

## Enable

1. Settings → Issue sync: turn on **Board and issues** and **Import agent issues**.
2. Add your forge username(s) under **Inbox authors**.
3. Save. Optionally click **Import issue inbox** once to test.
4. The Hub also polls on `ADHD_HUB_FORGE_INBOX_CRON` (default every 15 minutes).

## Agent protocol (any tool)

1. Create an issue titled `[ADHD] <short summary>` **as an allowlisted user** (token/bot identity must be on the allowlist). The prefix is case-insensitive (`[adhd]` / `[ADHD]`); optional whitespace after `]` is fine.
2. Labels (all optional):
   - `adhd-hub` — belt-and-suspenders if the agent *can* apply labels
   - `project:<slug>`
   - `source:codex` | `source:chatgpt` | `source:cursor` | `source:claude` | `source:claude-code`
3. Body: use the structured Goal / Focus / Next / Resume format below (no secrets).
4. Recommended (optional): append a short Made-with footer after the continuity headings
   (see below) so readers can find ADHD Progress Hub. Skip if the issue already has one.
5. Depending on the operator's close-on-import setting, Hub may close the issue and add
   `adhd-hub-synced` after import (it never deletes the issue).

**Title `[ADHD]` is sufficient** for allowlisted authors. The hub label is not required. Cursor Cloud agents often cannot set labels (`Resource not accessible by integration`); they should still open a title-prefixed issue and skip the label.

An issue with the hub label but no title prefix is still imported (label-only path).

## Structured source and refresh

The forge issue is the editable source for imported task structure:

```md
## Goal
Ship the outcome

## Focus
Do the next concrete action

## Next
- [ ] First follow-up
- [ ] Second follow-up

## Resume
Open the relevant file and continue here

## Attribution
Made with [ADHD Progress Hub](https://github.com/uniskela/adhd-hub)
```

`## Resume cue` and `## Return cue` are also accepted (same field as bare `## Resume`).
The legacy `## Current state` / `## Tasks` headings are also accepted as Focus / Next.
Unstructured bodies are retained as source notes; the Hub does not infer structured fields from
arbitrary prose.

**Made-with footer (recommended):** keep Goal / Focus / Next / Resume as the only
importable continuity headings. Put attribution under a **non-imported** heading such as
`## Attribution` (or after those sections under any heading Hub does not map) so the line
does not bleed into Resume. One short line is enough — do not paste full `PROGRESS.md`,
secrets, private Hub URLs, internal hosts/IPs, or absolute machine paths. Wording:

`Made with [ADHD Progress Hub](https://github.com/uniskela/adhd-hub)`

### Two uses of `[ADHD]` titles

The same title prefix covers two different jobs — keep them distinct:

1. **Short mailbox cue (importable)** — one finishable outcome with Goal / Focus / Next / Resume only.
   Prefer this for cloud-agent handoffs when Hub MCP is down. Import maps those headings into thread
   fields; comments are **not** merged into Goal/Focus.
2. **Long living tracker / PRD** — a durable issue that accumulates design notes, discussion, and
   comments. Still use the `[ADHD]` title if you want Hub discoverability, but **pin a continuity
   header** (Goal / Focus / Next / Resume) at the top of the body above longer sections so import and
   the Hub Notes continuity card stay useful. Do not paste full `PROGRESS.md` into the issue; Hub
   mirrors structured status via the `<!-- adhd-hub:status -->` block when configured.

Each import stores the provider, host/repository identity, issue number and canonical URL, body
hash, successful-import timestamp, and the structured values used as the three-way merge base.
Running **Import issue inbox** again reports imported, refreshed, unchanged, and needs-review
counts. A changed linked issue updates only Goal, Focus, Next, Resume, and a title still derived
from the issue. Thread status, Hub progress notes, reminders, links, completion notes, and operator
annotations are preserved. Issue comments stay display-only in [Notes & context](notes.md) (Forge activity).

When both the Hub and forge changed a source-controlled field from its previously imported value,
the thread enters **Source conflict** instead of overwriting either side. Use **Refresh from source
issue** on the thread to preview the previous, Hub, and forge values and choose **Use forge
version**, **Keep Hub version**, or **Merge/edit manually**.

Initial import may still close the issue and add `adhd-hub-synced`, depending on configuration.
Routine polling considers open issues only. A closed linked issue is not polled, but the per-thread
refresh action can fetch and refresh it explicitly. Refresh never deletes, reopens, or closes the
source issue, and source edits never reopen or close the Hub thread.

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
