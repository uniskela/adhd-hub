# Activity insights Slice A — design

Parent: [#72](https://github.com/uniskela/adhd-hub/issues/72) · QA: [#343](https://github.com/uniskela/adhd-hub/issues/343) · Continuity: [#337](https://github.com/uniskela/adhd-hub/issues/337)

## Goal

Ledger-backed **completions & activity totals** on Progress (today / 7d / 30d / month + 14-day chart), timezone-correct, no forge-reconcile double counting. Reflection copy only.

## Non-goals

- Persisted focus sessions (Slice B)
- Heatmap (Slice C)
- Trends/breakdowns UI beyond period totals + existing chart (Slice D)
- Hide-toggle for insights (add later if needed)
- Changing rewards / day_streak scoring

## Approach

Aggregate from `activity_events` only:

| Event | Count bucket |
| --- | --- |
| `thread.created` | created |
| `thread.completed` | completed |
| `thread.progress_updated` | progress |
| `thread.paused` | paused |

Exclude `forge.reconcile_*` (and any other forge.*). Distinct `project_slug` values in-window → `projects_touched`.

Periods use Hub prefs timezone: **today**, **last_7**, **last_30**, **calendar month**.

Overview gains `insights` object; `added_vs_finished` chart series switches to event-backed created/completed (calm empty if none). Thread-row `done_counts` remain for rewards/open inventory.

## UI

Progress: short period summary above the existing chart (plain language). Chart still “added / finished” from events.
