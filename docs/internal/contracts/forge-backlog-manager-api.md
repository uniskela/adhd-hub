# Forge Backlog Manager API v1

FBM-01 and FBM-02 implement the scanner and draft recommendations described in
[architecture PR #371](https://github.com/uniskela/adhd-hub/pull/371/files).
The response envelopes use `schema_version: 1`. The enabled Hub's
`/openapi.json` describes the request and response schemas. The endpoints use
existing Hub bearer or browser-session authentication.

## Configure

Set `ADHD_HUB_BACKLOG_ENABLED=true` and restart the Hub. Bind the project to a
GitHub or Gitea connection with a complete repository target and a token with
repository metadata and issue read access. GitHub scanning uses github.com
because the Hub's existing GitHub identity is scoped to that host. The Gitea
API and browser URLs must use the same origin and repository mount. A scan
targets the project binding. Issue
or repository URLs from a request or forge response cannot change the target.

For requested AI recommendations, enable the configured provider and **Backlog
suggestions** under Settings → AI helpers. Set
`ADHD_HUB_BACKLOG_AI_PROJECTS='["project-slug"]'` at startup. Also include the
project in `ADHD_HUB_BACKLOG_AI_PRIVATE_PROJECTS` to permit sending issue
excerpts from its private repository. Both lists are empty by default.
Unknown visibility requires the private opt-in. Project policy editing is
scheduled for FBM-06.

## Scans and items

| Method and path | Input and result |
| --- | --- |
| `POST /api/backlog/scans` | `{project_slug, selector?, include_closed?}` → 202 with `scan_id`, `job_id`. |
| `GET /api/backlog/scans/{id}` | Repository identity, scan status, page count, truncation, kind and protection counts, and a machine-readable error when applicable. |
| `GET /api/backlog/scans/{id}/items` | `limit` 1–200 (default 50), opaque `cursor`, optional `kind` and `cluster`. Returns `items` and `next_cursor`. |
| `GET /api/forge/jobs/{id}` | Existing queue status and compact progress or result. |
| `POST /api/backlog/jobs/{id}/cancel` | 202 for a backlog job. Cancellation is cooperative between HTTP requests or AI batches. |

`all_open` is the default selector. `adhd_inbox` requires the enabled Inbox
selector and the existing author allowlist. `labels` uses the project's import
label configuration. `assigned_to_me` uses the configured forge account or the
authenticated forge user. `include_closed` includes both issue states with any
selector. A repository with an active scan returns `409 scan_running`.

Scanning uses up to ten issue pages, at 100 per page for GitHub or 50 per page
for Gitea. Pull requests are excluded. The scan retains completed reads when a
later page fails. For eligible items, comment or timeline reads that fail or
exceed three pages add `incomplete_read`. This also covers installations that
do not provide a usable timeline API. Rate limiting retries up to twice when
the wait is at most five seconds. Longer waits return a retry hint and the
scan retains completed reads.

Each item contains the canonical provider, host, owner, repository and issue
number, an identity-derived URL, labels, milestone, role, comment count,
limited structured continuity, a source body hash and a source revision. The
revision covers the source body and issue metadata used for classification.
A linked primary thread and its import status are resolved by the full pinned
identity. Scans store
structured fields and hashes. AI jobs re-read issue bodies on demand. Scans
age out after 90 days unless a plan references them. Hub backups include the
SQLite tables.

## Recommendations and drafts

Identical normalized Goals provide `same_outcome` evidence. Checkpoints need
a matching title stem and a checkpoint marker. Explicit, different Goals
keep related work in separate consolidation clusters. Candidate destinations
come from overlap against unfinished local threads in the project. Protection
flags control the default disposition. Completion and staleness signals are
advisory. An issue with no activity for at least 90 days gets a staleness hint.

| Method and path | Input and result |
| --- | --- |
| `POST /api/backlog/scans/{id}/ai-suggestions` | Optional `{issue_numbers: [...]}` → 202 with `job_id`, or 403 `ai_not_opted_in`. Poll the scan items for per-item `ai_status`. |
| `POST /api/backlog/plans` | `{scan_id}` → 201 with a versioned local draft. |
| `GET /api/backlog/plans/{id}` | Draft, version, item revisions, protection and attached advice. |
| `PATCH /api/backlog/plans/{id}` | `{expected_version, items: [...]}` → updated draft or `409 version_conflict`. Each item can supply a disposition, destination, proposed fields, explicit `accept_ai`, or an operator protection override with a reason. |

For example, set an item to `reference` with
`{"expected_version":1,"items":[{"issue_number":12,"disposition":"reference"}]}`.
Protected items default to `skip`. An explicit operator draft edit needs a
reason to choose `migrate` or `consolidate` for a protected issue. AI advice
that conflicts with protection stays advisory. Protection suggested by AI is
additive for the scan and survives provider failures or retries. Drafts and
updates compare the
stored repository binding and policy against the current configuration and
return `409 stale_snapshot` if a newer scan proves an issue changed or is
missing from an equivalent complete listing.

AI uses serial batches of up to ten allowlisted-author issues, with up to
twenty batches and a ten-minute deadline per job. Each chat request uses the
configured timeout. The provider receives bounded, scrubbed issue text and
opaque references. It receives neither comment text nor Hub thread text.
An issue's freshly fetched revision must match the scan to be sent. An
unchanged batch may reuse validated results for up to 30 days. Job results
record the provider host, model, field names, and payload hashes. Provider
failures, cancellation, malformed data and invalid refs leave deterministic
recommendations available. Drafts perform no forge operations.

## Contract fixtures

[`fragmented-80.json`](../../../tests/fixtures/backlog/fragmented-80.json)
contains synthetic multi-agent issue data.
[`deterministic-v1.json`](../../../tests/fixtures/backlog/deterministic-v1.json)
records the expected deterministic output. Each row contains the issue
number, kind, completed and stale hints, outcome relationship, disposition,
cluster key, workstream key and protection flags.
