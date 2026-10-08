# ADHD Progress Hub — roadmap

This is the **single public roadmap page** for ADHD Progress Hub. GitHub issue [#15](https://github.com/uniskela/adhd-hub/issues/15) is the canonical tracker for current status and ordering.

## At a glance

| Position | Work | Status |
| --- | --- | --- |
| **Now** | Wave 7 — continuity intelligence | All four slices merged on `main`; merge/dedupe and return-cue coaching ship in **v0.21.0** (release PR [#309](https://github.com/uniskela/adhd-hub/pull/309), not yet published) |
| **Next** | Wave 8 — find & capture | Planned |
| **Then** | Activity insights | Planned after core clarity/findability work |
| **Later** | Wave 9 — shared surfaces & discoverability | Deferred until Waves 7–8 are stable |
| **Opt-in** | Wave 5 integrations | Only when a concrete need justifies them |

Reviewed against `main` on **2026-10-08** (Sydney). Latest published package and tag is **v0.20.2**; release PR [#309](https://github.com/uniskela/adhd-hub/pull/309) proposes **v0.21.0** and is waiting for a manual merge. **v0.20.0**–**v0.20.2** shipped opt-in Ponytail and Humanizer companions, Settings skills scope with Select all, and the calm UI wave (My work, Now, Progress, Settings, and sign-in). Wave 7 triage [#236](https://github.com/uniskela/adhd-hub/pull/236) and Next-up [#240](https://github.com/uniskela/adhd-hub/pull/240) shipped in **v0.18.0**. The remaining Wave 7 slices are now merged on `main`: merge/dedupe suggestions ([#312](https://github.com/uniskela/adhd-hub/pull/312) backend, [#315](https://github.com/uniskela/adhd-hub/pull/315) UI) and return-cue coaching ([#317](https://github.com/uniskela/adhd-hub/pull/317) backend, [#320](https://github.com/uniskela/adhd-hub/pull/320) UI). [#54](https://github.com/uniskela/adhd-hub/issues/54) stays open until v0.21.0 is published. Narrow documentation stamps can land without changing the sequence below; issue #15 remains authoritative when status changes.

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
- Wave 6 heuristic and opt-in local LLM thread scan-lines, project tags/filters, last-touch cues, and organiser suggestions with confirm (#52 / [#159](https://github.com/uniskela/adhd-hub/pull/159)–[#162](https://github.com/uniskela/adhd-hub/pull/162));
- organisation / no-repository projects, notes Summarise, rewrite-all scan lines, and the mobile Projects rail (see [dashboard](../dashboard.md) and [notes](../notes.md));
- opt-in Ponytail and Humanizer companions, Settings skills scope with Select all, and the calm UI wave, published in **v0.20.0**–**v0.20.2** (see [Connect](../connect.md), [companions](../coding-companions.md), and [dashboard](../dashboard.md)).

Merged on `main` for **v0.21.0** (release PR [#309](https://github.com/uniskela/adhd-hub/pull/309), not yet published):

- Wave 7 duplicate review with human-confirmed local merges; forge-backed pairs stay review-only ([#312](https://github.com/uniskela/adhd-hub/pull/312), [#315](https://github.com/uniskela/adhd-hub/pull/315); see [merge API](../merge-dedupe-api.md));
- Wave 7 advisory return-cue coaching that never blocks a save, pause or completion ([#317](https://github.com/uniskela/adhd-hub/pull/317), [#320](https://github.com/uniskela/adhd-hub/pull/320); see [return-cue coaching](../return-cue-coaching.md));
- opt-in Clock-Off wind-down schedule, temporary override and quiet Now status ([#310](https://github.com/uniskela/adhd-hub/issues/310) via [#322](https://github.com/uniskela/adhd-hub/pull/322) and [#323](https://github.com/uniskela/adhd-hub/pull/323); see [Clock-Off](../clock-off-api.md));
- MCP parameter descriptions, annotations and typed outputs ([#117](https://github.com/uniskela/adhd-hub/issues/117) via [#318](https://github.com/uniskela/adhd-hub/pull/318); see [MCP tool contract](../mcp-tool-contract.md));
- locked CI installs and Release Please–managed `uv.lock` versions ([#102](https://github.com/uniskela/adhd-hub/issues/102) via [#311](https://github.com/uniskela/adhd-hub/pull/311));
- non-destructive sample data ([#305](https://github.com/uniskela/adhd-hub/pull/305)) and the `completion.ready` end-of-task guidance fixes ([#307](https://github.com/uniskela/adhd-hub/pull/307), [#321](https://github.com/uniskela/adhd-hub/pull/321)).

Shipped work above does **not** replace the remaining product roadmap below. **NOW** is Wave 7 [#54](https://github.com/uniskela/adhd-hub/issues/54) until v0.21.0 is published; Wave 8 is next.

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

[#52](https://github.com/uniskela/adhd-hub/issues/52), published in **v0.16.0** via [#159](https://github.com/uniskela/adhd-hub/pull/159), [#160](https://github.com/uniskela/adhd-hub/pull/160), [#161](https://github.com/uniskela/adhd-hub/pull/161), and [#162](https://github.com/uniskela/adhd-hub/pull/162). Release PR [#163](https://github.com/uniskela/adhd-hub/pull/163) merged. Latest published tag is **v0.20.2** (v0.20.0–v0.20.2: opt-in companions, Settings skills scope, and the calm UI wave; continuity guard and deterministic project-sync shipped in v0.19.0; post–v0.16.2 Docker `/data` persistence [#222](https://github.com/uniskela/adhd-hub/pull/222) and later reliability work).

- short AI or heuristic thread summaries;
- calmer project list with tags/categories and useful filters;
- optional human-confirmed AI organisation.

Remote AI remains opt-in and must not leak secrets, raw transcripts, private URLs or machine paths. Prefer B3 events for freshness; do not create a competing history mechanism. MCP schema quality [#117](https://github.com/uniskela/adhd-hub/issues/117) landed separately as independent maintenance ([#318](https://github.com/uniskela/adhd-hub/pull/318)).

## Current priority

### Wave 7 — continuity intelligence 🔄 **NOW**

[#54](https://github.com/uniskela/adhd-hub/issues/54) — after Wave 6.

- soft stale-thread triage (**first slice**: confirm / snooze; never auto-dismiss) — shipped in **v0.18.0** ([#236](https://github.com/uniskela/adhd-hub/pull/236));
- calm cross-project Next-up ranking (**second slice**) — shipped in **v0.18.0** ([#240](https://github.com/uniskela/adhd-hub/pull/240));
- merge/dedupe suggestions with human confirmation (**third slice**) — merged on `main` for **v0.21.0**: deterministic duplicate review, MCP `suggest_duplicate_threads` / `request_thread_merge` / `thread_merge_history`, and a **Possible overlap** review in the dashboard ([#312](https://github.com/uniskela/adhd-hub/pull/312), [#315](https://github.com/uniskela/adhd-hub/pull/315)). Merges only queue a pending action; a person approves in the UI. Forge-backed or source-imported threads are refused (`forge_authoritative`) and stay review-only;
- better return-cue guidance (**fourth slice**) — merged on `main` for **v0.21.0**: an advisory `return_cue` on checkpoint, pause, list, digest and overview payloads, shown quietly by the Now pause field and as the **Left off** cue on My work. It never blocks Pause, Save or Done ([#317](https://github.com/uniskela/adhd-hub/pull/317), [#320](https://github.com/uniskela/adhd-hub/pull/320)).

All four slices are on `main`. Close [#54](https://github.com/uniskela/adhd-hub/issues/54) and move **Now** to Wave 8 in issue #15 once v0.21.0 is published.

Clock-Off ([#310](https://github.com/uniskela/adhd-hub/issues/310), [#322](https://github.com/uniskela/adhd-hub/pull/322) backend/MCP, [#323](https://github.com/uniskela/adhd-hub/pull/323) UI) also merged for v0.21.0. It is an opt-in, advisory wind-down boundary that agents read through `get_overview` and `session_digest`. Only the person can set an override, from the dashboard or REST; MCP has no override tool. It supports Wave 7 return cues without pulling Wave 8 energy/context modes forward.

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

- [#117](https://github.com/uniskela/adhd-hub/issues/117) — ✅ closed via [#318](https://github.com/uniskela/adhd-hub/pull/318) (merged for v0.21.0). All 26 current tools describe every input parameter and declare all four annotation hints. Local tests guard both. Typed output schemas cover `resolve_project`, `upsert_progress`, `mark_done`, `session_digest` and `report_guidance_health`. **Remaining follow-up:** after v0.21.0 is published and Glama rebuilds, record the per-tool TDQS rescore against the 2026-09-22 baseline (issue scope item 6). Only then consider typed outputs for other mutation results with selection/error states, such as `pause_thread` and `request_thread_merge`.
- [#102](https://github.com/uniskela/adhd-hub/issues/102) — ✅ closed via [#311](https://github.com/uniskela/adhd-hub/pull/311). CI installs with `--locked` (`UV_LOCKED=true`). Release Please bumps the `adhd-hub` version in `uv.lock` together with `pyproject.toml` (`release-please-config.json` `extra-files`). Do not hand-edit either version.
- [#300](https://github.com/uniskela/adhd-hub/issues/300) — verification only: confirm the Docker Hub README and short description sync after the v0.21.0 image publishes, then close.

Completed CI/security cleanup is historical and should not be treated as current roadmap work.

## Sequence summary

| Priority | Work | Status |
|---|---|---|
| Done | Waves 0–4 | Shipped |
| Done | Foundation A | Shipped |
| Done | Foundation B1 #73 | Shipped in v0.8.0 |
| Done | Foundation B2 #74 | Shipped in v0.8.0 |
| Done | Foundation B3 #75 | Event ledger / live UI / sync health (#152) |
| Done | Wave 6 #52 | Published in v0.16.0 (#159–#162); release #163 merged; latest published tag v0.20.2 |
| **Now** | **Wave 7 #54** | Continuity intelligence — triage + Next-up published in v0.18.0; merge/dedupe (#312/#315) + return cues (#317/#320) merged for v0.21.0 (#309 pending) |
| Next | Wave 8 #55 | Find & capture |
| Then | Activity insights #72 | Uses B3 history |
| Later | Wave 9 #56 | Shared surfaces / discoverability |
| Opt-in | Wave 5 #20 | Only when justified |
| Done | Clock-Off #310 | Backend/MCP #322 + UI #323 merged for v0.21.0 |
| Done | MCP schema quality #117 | #318 merged for v0.21.0; Glama rescore after publish |
| Done | CI lockfile cleanup #102 | #311 merged for v0.21.0 |
| Verify | Docker Hub description #300 | Check after the v0.21.0 image publish |

## Keeping this page from drifting

Detailed acceptance criteria belong in the linked GitHub issues. When issue #15 and this page disagree, **issue #15 wins** and this page should be refreshed rather than creating another roadmap document.
