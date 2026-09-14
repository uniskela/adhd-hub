# Next waves

Current sequencing for ADHD Progress Hub. Detailed notes live in [`improvement-roadmap.md`](improvement-roadmap.md); GitHub issue [#15](https://github.com/uniskela/adhd-hub/issues/15) is the tracking parent.

Reviewed against **current `main` on 2026-09-14** (package version v0.10.0; v0.10.1 fixes are merged but not yet released).

## GitHub tracking

| Item | Issue | Status |
|------|-------|--------|
| Parent roadmap | [#15](https://github.com/uniskela/adhd-hub/issues/15) | Active |
| Foundation B umbrella | [#71](https://github.com/uniskela/adhd-hub/issues/71) | B1/B2 shipped; B3 remains |
| Foundation B1 — source identity | [#73](https://github.com/uniskela/adhd-hub/issues/73) | ✅ Shipped in v0.8.0 |
| Foundation B2 — repo-primary reconciliation | [#74](https://github.com/uniskela/adhd-hub/issues/74) | ✅ Shipped in v0.8.0 |
| Foundation B3 — event ledger/live UI/sync health | [#75](https://github.com/uniskela/adhd-hub/issues/75) | **Now** |
| Wave 5 — optional integrations | [#20](https://github.com/uniskela/adhd-hub/issues/20) | Deferred / opt-in |
| Wave 6 — AI clarity | [#52](https://github.com/uniskela/adhd-hub/issues/52) | Next after B3 |
| Wave 7 — continuity intelligence | [#54](https://github.com/uniskela/adhd-hub/issues/54) | After Wave 6 |
| Wave 8 — find & capture | [#55](https://github.com/uniskela/adhd-hub/issues/55) | After Wave 7 |
| Activity insights/statistics | [#72](https://github.com/uniskela/adhd-hub/issues/72) | After core Waves 6–8 |
| Wave 9 — shared surfaces | [#56](https://github.com/uniskela/adhd-hub/issues/56) | Later |

Independent repository maintenance is tracked separately so it can land without distorting the product sequence: CI/security in [#101](https://github.com/uniskela/adhd-hub/issues/101) and the clean pytest/Ruff quality gate in [#102](https://github.com/uniskela/adhd-hub/issues/102).

## Current order

1. **Foundation B3 — #75**
   - durable structured activity/event history;
   - authenticated SSE-first browser invalidation;
   - sync/connection health and compact history;
   - reliable history substrate for #72.
2. **Wave 6 — #52**
   - short AI/heuristic thread summaries;
   - cleaner project list with tags/categories;
   - optional human-confirmed AI organisation.
3. **Wave 7 — #54**
   - stale-thread triage;
   - cross-project Next-up ranking;
   - merge/dedupe suggestions;
   - better return cues.
4. **Wave 8 — #55**
   - reversible progress compaction;
   - local-first global search;
   - mobile/share capture;
   - energy/context modes.
5. **Activity insights — #72**
   - daily/weekly/monthly completion/activity views;
   - persisted focus time;
   - contribution-style heatmap built on #75 history.
6. **Wave 9 — #56**
   - related-work map;
   - soft household multi-profile;
   - skills.sh discoverability.

Wave 5 remains opt-in/deferred unless a concrete Slack/Discord/calendar need justifies pulling one tightly scoped integration forward.

## Shipped foundation

### Foundation A — thread/outcome model ✅

PR #65 established one thread = one independently finishable outcome, explicit thread targeting, structured Goal / Focus / Next / Blocked / Resume state, guidance drift detection, and thread-scoped continuity.

### Foundation B1 — source-aware identity ✅

Shipped in v0.8.0. Local work remains Hub-owned; repo-backed work has durable GitHub/Gitea identity and explicit task-vs-continuity authority boundaries.

### Foundation B2 — repo-primary reconciliation ✅

Shipped in v0.8.0. GitHub/Gitea is authoritative for repo-backed task fields; Hub keeps private continuity. Ordinary issues can be imported safely, explicit close/reopen is remote-first, local work can be promoted/linked, and periodic reconciliation heals missed updates.

### Foundation B3 — live/history layer 🔄

The v0.10.0 Forge job queue provides useful queued/running/done/failed operation visibility, but it does **not** replace #75. B3 still owns the durable event ledger, live browser invalidation, broader sync health/history, and the trusted history source for #72.

## Security and ownership baseline

- Local/non-repo work remains first-class and needs no forge.
- Repo-backed task fields are forge-authoritative; Hub continuity fields are Hub-authoritative.
- Do not use generic last-write-wins.
- Do not close imported repo issues merely because Hub discovered them.
- Never automatically publish private Hub continuity/session history to public issues.
- Periodic reconciliation remains the correctness fallback even if faster event paths are added.
- Public/committed artifacts must not embed secrets, private Hub URLs, or machine-specific paths.

## Verification

- `uv run pytest`
- `uv run ruff check src tests`
- UI waves: `scripts/browser_smoke.py`
- MCP waves: `scripts/probe_mcp.py`
