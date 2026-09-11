# Thread outcome model + guidance drift (foundation for Waves 6–8)

One thread = one independently finishable outcome.

## Shipped primitives

- Structured thread fields: `goal`, `focus`, `next_steps` (≤3), `blocked_reason`, `resume_step`
- `upsert_progress(thread_id=...)` / `force_new_thread` / `needs_thread_selection`
- Thread-scoped `progress_notes.thread_id` (legacy rows stay unscoped)
- `PROGRESS.md`: Active threads → Recent milestones → History (legacy log migrated)
- Overlap scoring includes goal/focus/next/resume
- Compact agent guidance (AGENTS block + session skill)
- Independent Hub guidance schema versions (`AGENT_GUIDANCE_VERSION`, skill `hub_skill_version`)
- `adhd-hub doctor --project` / `setup --check` drift detection; repair only via explicit setup/connect
- **Forge board sync mirrors thread state** into a Hub-managed `<!-- adhd-hub:status:* -->` block per issue — not the whole project `PROGRESS.md`

## Forge issue ownership

| Issue kind | Body ownership |
|---|---|
| Hub-created / wholly Hub-owned body | Hub may replace the status block (usually the whole body) |
| Inbox / user-authored issue | Preserve content outside markers; upsert only the Hub status block |

Association storage remains `forge_issue:<thread_id>` → issue number (opaque meta). A later **forge work graph** may promote this to a first-class link without requiring hierarchy tables in this change.

## Deliberately deferred (separate finishable outcomes)

- GitHub/Gitea sub-issue / parent-child hierarchy import
- Epic/umbrella issues that are not themselves Hub threads
- Roadmap/epic UI, full bidirectional reconciliation, PR↔issue graph UI
- Automatic dependency sequencing; merge/dedupe UI (Wave 7)
- Issue #15 child Wave issues as a hierarchical work graph in Hub

## Waves 6–8

- Wave 6 (#52): AI summaries / project tags / organiser
- Wave 7 (#54): merge/dedupe UI, stale triage, Next-up ranking
- Wave 8 (#55): reversible wiki compaction, global search, energy modes
