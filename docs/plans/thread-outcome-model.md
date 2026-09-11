# Thread outcome model (foundation for Waves 6–8)

One thread = one independently finishable outcome.

## Shipped primitives

- Structured thread fields: `goal`, `focus`, `next_steps` (≤3), `blocked_reason`, `resume_step`
- `upsert_progress(thread_id=...)` / `force_new_thread` / `needs_thread_selection`
- Thread-scoped `progress_notes.thread_id` (legacy rows stay unscoped)
- `PROGRESS.md`: Active threads → Recent milestones → History (legacy log migrated)
- Overlap scoring includes goal/focus/next/resume
- Compact agent guidance (AGENTS block + session skill)

## Deliberately left for later waves

- Wave 6 (#52): AI summaries / project tags / organiser
- Wave 7 (#54): merge/dedupe UI, stale triage, Next-up ranking
- Wave 8 (#55): reversible wiki compaction, global search, energy modes
