# ADHD Progress Hub — roadmap

This is the **single public roadmap page** for ADHD Progress Hub. GitHub issue [#15](https://github.com/uniskela/adhd-hub/issues/15) is the canonical tracker for current status and ordering; this page mirrors it in a reader-friendly form.

Reviewed against `main` on **2026-09-22** at package **v0.13.0** (Notes & context reader via PR [#136](https://github.com/uniskela/adhd-hub/pull/136)). Narrow reliability/documentation fixes can land without changing the sequence below; issue #15 remains authoritative when status changes.

## Current state

The Hub already includes:

- Waves 0–4;
- the one-thread-one-outcome continuity model (Foundation A / PR #65);
- source-aware local/external work identity (Foundation B1 / #73);
- repo-primary GitHub/Gitea reconciliation (Foundation B2 / #74);
- queued/running/done/failed Forge job visibility;
- MCP over Streamable HTTP plus optional local stdio (#109);
- remote OAuth loopback callback support (#110);
- richer structured progress import from forge issues (#111);
- OpenClaw HTTPS/hook-token guidance (#112/#116);
- Glama metadata/release support (#114);
- clearer MCP tool guidance and real stdio tool-call coverage (#115);
- OpenClaw multi-agent hook targeting (#118);
- canonical public-roadmap/docs cleanup (#120);
- docs-sync notification wiring for the Uniskela site (#121);
- ADHD-friendly Notes & context reader (#136).

Those newer integration/reliability/documentation changes do **not** replace the remaining product roadmap below. **NOW** remains Foundation B3 [#75](https://github.com/uniskela/adhd-hub/issues/75) — kickoff plan: [foundation-b3-kickoff.md](foundation-b3-kickoff.md).

## Product principles

- Calm, resumable, non-punitive ADHD UX.
- Local/non-repo work remains first-class and does not require a forge.
- Repo-backed task fields are forge-authoritative; Hub continuity fields are Hub-authoritative.
- No generic last-write-wins and no automatic publication of private continuity/session history.
- Destructive or externally visible actions require explicit, reviewable behavior.
- Summaries only where possible; do not put raw transcripts, secrets, private Hub URLs, or machine-specific paths into generated/public artifacts.
- Prefer one shared history/state model over parallel feature-specific stores.

## Shipped foundations

### Waves 0–4 ✅

The installation/connect flow, ADHD-focused UX, MCP parity, homelab/trust work, maintainability and accessibility foundations are shipped. See issues [#16](https://github.com/uniskela/adhd-hub/issues/16)–[#19](https://github.com/uniskela/adhd-hub/issues/19) for the historical wave details.

### Foundation A — deterministic continuity ✅

PR #65 established one thread = one independently finishable outcome, explicit thread targeting, structured Goal / Focus / Next / Blocked / Resume state, thread-scoped history, and guidance drift detection.

### Foundation B1 — source-aware identity ✅

[#73](https://github.com/uniskela/adhd-hub/issues/73), shipped in v0.8.0.

Local work remains Hub-owned. Repo-backed work has durable provider/host/repository/issue identity, while external issue state stays distinct from Hub continuity state.

### Foundation B2 — repo-primary reconciliation ✅

[#74](https://github.com/uniskela/adhd-hub/issues/74), shipped in v0.8.0.

GitHub/Gitea can remain authoritative for repo-backed task state while the Hub keeps private continuity. Import/reconciliation is safe, close/reopen is remote-first for linked issues, and local work can be deliberately promoted/linked.

## Current priority

### Foundation B3 — activity ledger, live UI & sync health 🔄 **NOW**

[#75](https://github.com/uniskela/adhd-hub/issues/75) · kickoff: [foundation-b3-kickoff.md](foundation-b3-kickoff.md)

B3 is the remaining Foundation B slice (train started after Notes #136):

1. **Durable structured event ledger** for meaningful thread/work/session/forge changes (**first implementation slice**).
2. **Authenticated live UI invalidation**, SSE-first, with normal API refetch remaining the displayed truth.
3. **Sync/connection health** including last success/failure, conflicts and useful job state.
4. **Trustworthy history substrate** for later activity insights instead of reconstructing history from current rows or Git timestamps.

The existing Forge job queue is useful operational state but is not a substitute for this durable history/live-state layer.

## Next product sequence

### Wave 6 — AI clarity & project organisation

[#52](https://github.com/uniskela/adhd-hub/issues/52) — **after B3**.

- short AI or heuristic thread summaries;
- calmer project list with tags/categories and useful filters;
- optional human-confirmed AI organisation.

Remote AI remains opt-in and must not leak secrets, raw transcripts, private URLs or machine paths.

### Wave 7 — continuity intelligence

[#54](https://github.com/uniskela/adhd-hub/issues/54) — after Wave 6.

- soft stale-thread triage;
- calm cross-project Next-up ranking;
- merge/dedupe suggestions with human confirmation;
- better return-cue guidance.

Richer stale-reminder context/direct CTAs are a narrower reminder UX improvement and do not complete this wave; Wave 7 still owns triage/snooze, ranking, merge suggestions and return-cue quality coaching.

### Wave 8 — find & capture

[#55](https://github.com/uniskela/adhd-hub/issues/55) — after Wave 7.

- reversible progress compaction;
- local-first global search;
- mobile/share capture;
- energy/context modes without productivity guilt.

### Activity insights & statistics

[#72](https://github.com/uniskela/adhd-hub/issues/72) — after the core clarity/findability work, consuming B3 history.

- daily/weekly/monthly completion/activity views;
- persisted focus time;
- project/activity trends;
- optional contribution-style heatmap;
- timezone-correct aggregation.

This is reflection tooling, not employee surveillance or productivity scoring.

### Wave 9 — shared surfaces & discoverability

[#56](https://github.com/uniskela/adhd-hub/issues/56) — later, after Waves 6–8 are stable.

- optional related-work map;
- soft household multi-profile;
- skills.sh discoverability when packaging/distribution is ready.

### Wave 5 — optional integrations

[#20](https://github.com/uniskela/adhd-hub/issues/20) remains **deferred / opt-in**. Slack/Discord/calendar work should only move forward when a concrete need justifies a tightly scoped integration.

## Independent maintenance

These can land without changing the product-wave sequence:

- [#117](https://github.com/uniskela/adhd-hub/issues/117) — improve MCP parameter descriptions, annotations, output schemas and regression coverage using Glama TDQS explanations as diagnostics. **Deferred** relative to the B3 train; land independently when capacity allows.
- [#102](https://github.com/uniskela/adhd-hub/issues/102) — finish remaining lockfile/CI install-mode cleanup (decide `--frozen` vs `--locked` after refresh). Package version on `main` is already **v0.13.0**; do not treat version-string drift as open product work.

Completed CI/security cleanup is historical and should not be treated as current roadmap work.

## Sequence summary

| Priority | Work | Status |
|---|---|---|
| Done | Waves 0–4 | Shipped |
| Done | Foundation A | Shipped |
| Done | Foundation B1 #73 | Shipped in v0.8.0 |
| Done | Foundation B2 #74 | Shipped in v0.8.0 |
| **Now** | **Foundation B3 #75** | Event ledger / live UI / sync health (kickoff underway) |
| Next | Wave 6 #52 | AI clarity + project organisation |
| Then | Wave 7 #54 | Continuity intelligence |
| Then | Wave 8 #55 | Find & capture |
| Later | Activity insights #72 | Uses B3 history |
| Later | Wave 9 #56 | Shared surfaces / discoverability |
| Opt-in | Wave 5 #20 | Only when justified |
| Independent | MCP schema quality #117 | Deferred vs B3; land separately |
| Independent | CI lockfile cleanup #102 | Remaining maintenance |

## Keeping this page from drifting

Detailed acceptance criteria belong in the linked GitHub issues. When issue #15 and this page disagree, **issue #15 wins** and this page should be refreshed rather than creating another roadmap document.
