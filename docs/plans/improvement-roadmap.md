# ADHD Progress Hub — roadmap

This is the **single public roadmap page** for ADHD Progress Hub. GitHub issue [#15](https://github.com/uniskela/adhd-hub/issues/15) is the canonical tracker for current status and ordering; this page mirrors it in a reader-friendly form.

Reviewed against `main` on **2026-09-24** for upcoming **v0.16.0** (Wave 6 shipped on `main` via [#159](https://github.com/uniskela/adhd-hub/pull/159), [#160](https://github.com/uniskela/adhd-hub/pull/160), [#161](https://github.com/uniskela/adhd-hub/pull/161), and [#162](https://github.com/uniskela/adhd-hub/pull/162); release PR [#163](https://github.com/uniskela/adhd-hub/pull/163) pending; package on `main` is still **v0.15.0**). Narrow reliability/documentation fixes can land without changing the sequence below; issue #15 remains authoritative when status changes.

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
- ADHD-friendly Notes & context reader (#136);
- Foundation B3 activity ledger, SSE live invalidation, and sync health (#75 / [#152](https://github.com/uniskela/adhd-hub/pull/152));
- Wave 6 heuristic and opt-in local LLM thread scan-lines, project tags/filters, last-touch cues, and organiser suggestions with confirm (#52 / [#159](https://github.com/uniskela/adhd-hub/pull/159)–[#162](https://github.com/uniskela/adhd-hub/pull/162)).

Shipped work above does **not** replace the remaining product roadmap below. **NOW** is Wave 7 [#54](https://github.com/uniskela/adhd-hub/issues/54).

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

### Foundation B3 — activity ledger, live UI & sync health ✅

[#75](https://github.com/uniskela/adhd-hub/issues/75), shipped via [#152](https://github.com/uniskela/adhd-hub/pull/152). Kickoff history: [foundation-b3-kickoff.md](foundation-b3-kickoff.md).

Durable structured activity events, authenticated SSE live invalidation (API refetch remains displayed truth), and sync/connection health are on `main`. This is the history substrate for later activity insights (#72).

### Wave 6 — AI clarity & project organisation ✅

[#52](https://github.com/uniskela/adhd-hub/issues/52), shipped on `main` for upcoming v0.16.0 via [#159](https://github.com/uniskela/adhd-hub/pull/159), [#160](https://github.com/uniskela/adhd-hub/pull/160), [#161](https://github.com/uniskela/adhd-hub/pull/161), and [#162](https://github.com/uniskela/adhd-hub/pull/162). Release PR [#163](https://github.com/uniskela/adhd-hub/pull/163) is pending.

- short AI or heuristic thread summaries;
- calmer project list with tags/categories and useful filters;
- optional human-confirmed AI organisation.

Remote AI remains opt-in and must not leak secrets, raw transcripts, private URLs or machine paths. Prefer B3 events for freshness; do not create a competing history mechanism. Keep [#117](https://github.com/uniskela/adhd-hub/issues/117) as independent maintenance.

## Current priority

### Wave 7 — continuity intelligence 🔄 **NOW**

[#54](https://github.com/uniskela/adhd-hub/issues/54) — after Wave 6.

- soft stale-thread triage;
- calm cross-project Next-up ranking;
- merge/dedupe suggestions with human confirmation;
- better return-cue guidance.

Richer stale-reminder context/direct CTAs are a narrower reminder UX improvement and do not complete this wave; Wave 7 still owns triage/snooze, ranking, merge suggestions and return-cue quality coaching.

## Next product sequence

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

[#56](https://github.com/uniskela/adhd-hub/issues/56) — later, after Waves 7–8 are stable.

- optional related-work map;
- soft household multi-profile;
- skills.sh discoverability when packaging/distribution is ready.

### Wave 5 — optional integrations

[#20](https://github.com/uniskela/adhd-hub/issues/20) remains **deferred / opt-in**. Slack/Discord/calendar work should only move forward when a concrete need justifies a tightly scoped integration.

## Independent maintenance

These can land without changing the product-wave sequence:

- [#117](https://github.com/uniskela/adhd-hub/issues/117) — improve MCP parameter descriptions, annotations, output schemas and regression coverage using Glama TDQS explanations as diagnostics. **Independent** of the Wave 7 train; land separately when capacity allows.
- [#102](https://github.com/uniskela/adhd-hub/issues/102) — finish remaining lockfile/CI install-mode cleanup (decide `--frozen` vs `--locked` after refresh). Package version on `main` is already **v0.15.0**; do not treat version-string drift as open product work.

Completed CI/security cleanup is historical and should not be treated as current roadmap work.

## Sequence summary

| Priority | Work | Status |
|---|---|---|
| Done | Waves 0–4 | Shipped |
| Done | Foundation A | Shipped |
| Done | Foundation B1 #73 | Shipped in v0.8.0 |
| Done | Foundation B2 #74 | Shipped in v0.8.0 |
| Done | Foundation B3 #75 | Event ledger / live UI / sync health (#152) |
| Done | Wave 6 #52 | Shipped on main for v0.16.0 (#159–#162); release #163 pending |
| **Now** | **Wave 7 #54** | Continuity intelligence |
| Next | Wave 8 #55 | Find & capture |
| Then | Activity insights #72 | Uses B3 history |
| Later | Wave 9 #56 | Shared surfaces / discoverability |
| Opt-in | Wave 5 #20 | Only when justified |
| Independent | MCP schema quality #117 | Land separately from Wave 7 |
| Independent | CI lockfile cleanup #102 | Remaining maintenance |

## Keeping this page from drifting

Detailed acceptance criteria belong in the linked GitHub issues. When issue #15 and this page disagree, **issue #15 wins** and this page should be refreshed rather than creating another roadmap document.
