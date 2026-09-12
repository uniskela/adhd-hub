# Foundation B1 — source-aware work identity & authority

Parent: [#71](https://github.com/uniskela/adhd-hub/issues/71) · Slice: [#73](https://github.com/uniskela/adhd-hub/issues/73)

## Goal

One source-aware work model for ADHD Hub continuity records (`Thread`):

- **Local work** — Hub owns task fields and continuity (`work_source=local`, derived `authority=hub`).
- **Repo-backed work** — GitHub/Gitea owns task fields; Hub owns continuity (`work_source=github|gitea`, derived `authority=external`).

Projects may set a default work source; individual threads may override. External identity is host-scoped and unique so the same owner/repo/number on two Gitea hosts cannot collide.

## State split

| Field | Meaning |
| --- | --- |
| `Thread.status` | Hub continuity/workflow only: `open` \| `blocked` \| `done` \| `dismissed` |
| `external_issue_state` | Canonical external task state when linked: `open` \| `closed` \| `null` |
| Local work | `external_issue_state` stays `null` |

`authority` is **derived only** from the resolved `work_source` (`local→hub`, else `external`). It is never persisted.

In #73, existing forge board/inbox behaviour is unchanged (including Hub status → forge open/closed). #74 enforces ownership and syncs `external_issue_state`.

## Identity

Canonical tuple: `(provider, host, owner, repo, number)`.

- GitHub host is always `github.com`.
- Gitea host is the normalised browse hostname (lowercase; no scheme/path; include non-default port when present).
- Owner and repo are trimmed and lowercased for uniqueness keys (GitHub and Gitea).
- Key form: `github:github.com/owner/repo#123`, `gitea:git.example.com/owner/repo#45`.

Partial unique index on the five normalised columns when all are non-null.

## Source resolution

1. If the thread has attached external identity → `work_source` is **pinned** to that provider; project default must not change effective source.
2. Else if `thread.work_source` is set → use it.
3. Else → `project.default_work_source` (default `local`).

Attaching external identity always sets `work_source` to `github` or `gitea` (never leave null on linked threads).

`source_tool` remains agent/mailbox provenance and is unrelated to `work_source`.

## Field ownership (for #74; documented only here)

**Repo-owned (when authority=external):** title, issue body outside Hub markers, open/closed, labels, milestone, assignees, remote identity.

**Hub-owned:** focus, next steps, blocked/waiting, resume cue, session/progress history, future focus-time and AI summaries.

## Migration

Offline, additive schema + one-shot promote of `meta["forge_issue:<thread_id>"] → number`:

- Promote only when provider, host, owner, and repo are established confidently from durable offline config (global forge.json and/or complete project forge overrides).
- On promote: set identity columns, pin `work_source`, leave `external_issue_state` null, keep legacy meta.
- Fail-safe: if identity cannot be established confidently, leave legacy meta intact, do not guess, report/log unresolved. Mark migration pass complete so it does not loop; heal later in #74.
- Never call forge APIs or mutate remote issues during migration.
- Never infer `external_issue_state` from Hub `Thread.status`.

## Surfaces in #73

- Additive serializers: resolved `work_source`, computed `authority`, external identity, `external_issue_state`; keep `forge_issue_number` / `forge_issue_url`.
- Dual-write first-class identity when existing board/inbox paths set `forge_issue:` meta.
- Internal `attach_external_identity` / lookup helpers for tests and #74.
- **No** user-facing MCP/API/UI flow that creates new external-authority work until #74 replaces Hub-status→forge open/closed.

## Non-goals

- #74 sync engine, import filters, promote UX, revision metadata (`external_updated_at`), ownership enforcement.
- #75 activity ledger / SSE / sync health.
- #72 statistics.

## Spec self-review

- No TBD placeholders; authority is derived-only; host is required; pin-on-link is explicit; migration is fail-safe; revision metadata deferred; public external-create deferred.
