# ADHD Progress Hub — roadmap

This is the **single public roadmap page** for ADHD Progress Hub. GitHub issue [#15](https://github.com/uniskela/adhd-hub/issues/15) is the canonical tracker for current status and ordering.

## At a glance

| Position | Work | Status |
| --- | --- | --- |
| **Now** | Activity insights #72 | Slice A ([#345](https://github.com/uniskela/adhd-hub/pull/345)) and completion calendar ([#349](https://github.com/uniskela/adhd-hub/pull/349), [#352](https://github.com/uniskela/adhd-hub/pull/352)) shipped in **v0.22.x** ([#340](https://github.com/uniskela/adhd-hub/pull/340)); focus sessions and remaining metrics next |
| **Next** | Insights remaining | Focus sessions, then trends and remaining metrics |
| **Then** | Wave 9 | Shared surfaces / discoverability |
| **Opt-in** | Wave 5 integrations | Only when a concrete need justifies them |

Reviewed against `main` on **2026-11-08**. Latest published package and tag is **v0.22.1**. **Wave 7 [#54](https://github.com/uniskela/adhd-hub/issues/54) shipped in v0.21.x** (triage + Next-up earlier; merge/dedupe + return-cue coaching in v0.21.0). Wave 8 [#55](https://github.com/uniskela/adhd-hub/issues/55) ([#338](https://github.com/uniskela/adhd-hub/pull/338), [#339](https://github.com/uniskela/adhd-hub/pull/339), [#341](https://github.com/uniskela/adhd-hub/pull/341), [#342](https://github.com/uniskela/adhd-hub/pull/342)) and Activity insights Slice A ([#345](https://github.com/uniskela/adhd-hub/pull/345)), including the 12-week completion calendar ([#349](https://github.com/uniskela/adhd-hub/pull/349), [#352](https://github.com/uniskela/adhd-hub/pull/352)), shipped in **v0.22.x** ([#340](https://github.com/uniskela/adhd-hub/pull/340)). **NOW** remains Activity insights [#72](https://github.com/uniskela/adhd-hub/issues/72); focus sessions and remaining metrics are next. Narrow documentation stamps can land without changing the sequence below; issue #15 remains authoritative when status changes.

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
- opt-in Ponytail and Humanizer companions, Settings skills scope with Select all, and the calm UI wave, published in **v0.20.0**–**v0.20.2**;
- Wave 7 continuity intelligence published through **v0.21.0** (see below);
- docs layout separation for public / internal / agent docs in **v0.21.1**.

Shipped in **v0.21.0**:

- Wave 7 duplicate review with human-confirmed local merges; forge-backed pairs stay review-only ([#312](https://github.com/uniskela/adhd-hub/pull/312), [#315](https://github.com/uniskela/adhd-hub/pull/315); see [merge API](../merge-dedupe-api.md));
- Wave 7 advisory return-cue coaching that never blocks a save, pause or completion ([#317](https://github.com/uniskela/adhd-hub/pull/317), [#320](https://github.com/uniskela/adhd-hub/pull/320); see [return-cue coaching](../return-cue-coaching.md));
- opt-in Clock-Off wind-down schedule, temporary override and quiet Now status ([#310](https://github.com/uniskela/adhd-hub/issues/310) via [#322](https://github.com/uniskela/adhd-hub/pull/322) and [#323](https://github.com/uniskela/adhd-hub/pull/323); see [Clock-Off](../clock-off-api.md));
- MCP parameter descriptions, annotations and typed outputs ([#117](https://github.com/uniskela/adhd-hub/issues/117) via [#318](https://github.com/uniskela/adhd-hub/pull/318); see [MCP tool contract](../mcp-tool-contract.md));
- locked CI installs and Release Please–managed `uv.lock` versions ([#102](https://github.com/uniskela/adhd-hub/issues/102) via [#311](https://github.com/uniskela/adhd-hub/pull/311));
- non-destructive sample data ([#305](https://github.com/uniskela/adhd-hub/pull/305)) and the `completion.ready` end-of-task guidance fixes ([#307](https://github.com/uniskela/adhd-hub/pull/307), [#321](https://github.com/uniskela/adhd-hub/pull/321)).

Wave 8 [#55](https://github.com/uniskela/adhd-hub/issues/55) ([#338](https://github.com/uniskela/adhd-hub/pull/338), [#339](https://github.com/uniskela/adhd-hub/pull/339), [#341](https://github.com/uniskela/adhd-hub/pull/341), [#342](https://github.com/uniskela/adhd-hub/pull/342)) and Activity insights Slice A ([#345](https://github.com/uniskela/adhd-hub/pull/345)), including the 12-week completion calendar ([#349](https://github.com/uniskela/adhd-hub/pull/349), [#352](https://github.com/uniskela/adhd-hub/pull/352)), shipped in **v0.22.x** ([#340](https://github.com/uniskela/adhd-hub/pull/340)). **NOW** is Activity insights [#72](https://github.com/uniskela/adhd-hub/issues/72); focus sessions and remaining metrics are next. Testing checklist [#343](https://github.com/uniskela/adhd-hub/issues/343).

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

[#75](https://github.com/uniskela/adhd-hub/issues/75), shipped via [#152](https://github.com/uniskela/adhd-hub/pull/152). Kickoff history: [foundation-b3-kickoff.md](https://github.com/uniskela/adhd-hub/blob/main/docs/internal/plans/foundation-b3-kickoff.md).

Durable structured activity events, authenticated SSE live invalidation (API refetch remains displayed truth), and sync/connection health are on `main`. This is the history substrate for later activity insights (#72).

### Wave 6 — AI clarity & project organisation ✅

[#52](https://github.com/uniskela/adhd-hub/issues/52), published in **v0.16.0** via [#159](https://github.com/uniskela/adhd-hub/pull/159), [#160](https://github.com/uniskela/adhd-hub/pull/160), [#161](https://github.com/uniskela/adhd-hub/pull/161), and [#162](https://github.com/uniskela/adhd-hub/pull/162).

### Wave 7 — continuity intelligence ✅

[#54](https://github.com/uniskela/adhd-hub/issues/54), completed in **v0.21.0**.

- soft stale-thread triage — **v0.18.0** ([#236](https://github.com/uniskela/adhd-hub/pull/236));
- calm cross-project Next-up ranking — **v0.18.0** ([#240](https://github.com/uniskela/adhd-hub/pull/240));
- merge/dedupe suggestions with human confirmation — **v0.21.0** ([#312](https://github.com/uniskela/adhd-hub/pull/312), [#315](https://github.com/uniskela/adhd-hub/pull/315));
- advisory return-cue coaching — **v0.21.0** ([#317](https://github.com/uniskela/adhd-hub/pull/317), [#320](https://github.com/uniskela/adhd-hub/pull/320)).

Clock-Off ([#310](https://github.com/uniskela/adhd-hub/issues/310)) also shipped in v0.21.0. It supports Wave 7 return cues without pulling Wave 8 energy/context modes forward.

## Current priority

### Wave 8 — find & capture ✅

[#55](https://github.com/uniskela/adhd-hub/issues/55) — shipped in **v0.22.x** ([#340](https://github.com/uniskela/adhd-hub/pull/340)):

- global search ([#338](https://github.com/uniskela/adhd-hub/pull/338));
- reversible progress compaction ([#339](https://github.com/uniskela/adhd-hub/pull/339));
- Web Share Target into Save a thought ([#341](https://github.com/uniskela/adhd-hub/pull/341));
- Short/Deep Now return view ([#342](https://github.com/uniskela/adhd-hub/pull/342)).

### Activity insights & statistics 🔄 **NOW**

[#72](https://github.com/uniskela/adhd-hub/issues/72) — consuming B3 history. QA: [#343](https://github.com/uniskela/adhd-hub/issues/343).

- Slice A: ledger-backed period totals + chart shipped in **v0.22.x** ([#345](https://github.com/uniskela/adhd-hub/pull/345)); separate resumed/note counts and project lists remain;
- Slice B: persisted focus sessions;
- Slice C: 12-week completion calendar with day details, month-paged table fallback and remembered visibility shipped in **v0.22.x** ([#349](https://github.com/uniskela/adhd-hub/pull/349), [#352](https://github.com/uniskela/adhd-hub/pull/352)); focus/note calendar metrics remain;
- Slice D: trends / project breakdowns.

## Next product sequence

### Activity insights (remaining)

Focus sessions and the remaining metrics of [#72](https://github.com/uniskela/adhd-hub/issues/72).

### Wave 9 — shared surfaces & discoverability

[#56](https://github.com/uniskela/adhd-hub/issues/56) — later, after Waves 7–8 are stable.

### Wave 5 — optional integrations

[#20](https://github.com/uniskela/adhd-hub/issues/20) remains **deferred / opt-in**.

## Independent maintenance

- [#117](https://github.com/uniskela/adhd-hub/issues/117) — ✅ closed via [#318](https://github.com/uniskela/adhd-hub/pull/318). Catalog grows with new tools (for example `search_work`); local tests guard parameter descriptions and annotation hints. **Remaining follow-up:** Glama TDQS rescore after publish.
- [#102](https://github.com/uniskela/adhd-hub/issues/102) — ✅ closed via [#311](https://github.com/uniskela/adhd-hub/pull/311).
- [#300](https://github.com/uniskela/adhd-hub/issues/300) — verification only: Docker Hub README/short description after image publish.

## Sequence summary

| Priority | Work | Status |
|---|---|---|
| Done | Waves 0–4 | Shipped |
| Done | Foundation A / B1 / B2 / B3 | Shipped |
| Done | Wave 6 #52 | Published in v0.16.0 |
| Done | Wave 7 #54 | Completed in v0.21.0 |
| Done | Wave 8 #55 | Shipped in v0.22.x (#338, #339, #341, #342; [#340](https://github.com/uniskela/adhd-hub/pull/340)) |
| **Now** | **Activity insights #72** | Slice A (#345) and completion calendar (#349, #352) shipped in v0.22.x; focus sessions and remaining metrics next |
| Later | Wave 9 #56 | Shared surfaces / discoverability |
| Opt-in | Wave 5 #20 | Only when justified |
| Verify | Docker Hub description #300 | Check after image publish |

## Keeping this page from drifting

Detailed acceptance criteria belong in the linked GitHub issues. When issue #15 and this page disagree, **issue #15 wins** and this page should be refreshed rather than creating another roadmap document.
