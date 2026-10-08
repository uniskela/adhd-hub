# Clock-Off backend and UI contract

This first backend/MCP slice of [#310](https://github.com/uniskela/adhd-hub/issues/310)
adds a global, opt-in advisory schedule. It uses the existing `prefs.json` and
Hub timezone preference (`ADHD_HUB_TIMEZONE` supplies the initial default).
It never kills processes, changes thread status, or requires strict Continuity
Guard. The user remains in control. Settings → Appearance saves the schedule
on change. Now shows a quiet status only while Clock-Off is enabled and a
boundary is near, in progress, or overridden. The endpoints below are that
contract.

## Configure the schedule

Authenticated `GET /api/prefs` includes `timezone`, `clock_off` and the stored
`clock_off_override_until`. Update the schedule with `PUT /api/prefs`:

```json
{
  "timezone": "Australia/Sydney",
  "clock_off": {
    "enabled": true,
    "active_days": [0, 1, 2, 3, 4],
    "clock_off_time": "22:00",
    "wind_down_minutes": 15
  }
}
```

| Field | Contract |
| --- | --- |
| `enabled` | Boolean, default `false`. Disabled returns `normal` and no guidance. |
| `active_days` | Integers Monday `0` through Sunday `6`; defaults to weekdays. Duplicates are removed and days sorted. Empty means no scheduled windows. |
| `clock_off_time` | Local 24-hour `HH:MM`, default `22:00`. |
| `wind_down_minutes` | Integer elapsed minutes before Clock-Off, `0`–`240`, default `15`. |

Schedule updates merge supplied fields with the current schedule. Omitted
fields and unrelated preferences are preserved. Null schedules, unknown schedule
fields and invalid types/ranges return `400` without saving. Timezones use the
existing IANA validation. The schedule has no per-project settings or separate
timezone.

## Midnight, reset and daylight saving

Active days identify the **local date Clock-Off begins**, rather than its reset
date or the date wind-down begins. Friday at 22:00 remains clocked off through
Saturday at 05:59, even if Saturday is inactive. Each window ends at the **next
06:00 local occurrence strictly after activation**. A Saturday 00:15 schedule
resets that Saturday at 06:00; an exact 06:00 activation resets the following
morning. Wind-down may begin on the preceding local date.

Local wall times resolve through the configured timezone. For a repeated time
at a DST fallback, activation uses its **first occurrence** and stays active
through the repeated hour. A nonexistent time at a DST jump moves forward by
the gap (02:30 becomes 03:30 for a one-hour jump). Reset resolves separately in
local time, so overnight windows can be shorter or longer across DST changes.
Wind-down lead and overrides measure elapsed time using UTC instants.

Activation and wind-down are inclusive; reset and override expiry are exclusive.
An existing clocked-off window takes precedence if the next window's wind-down
overlaps it. The state is derived on each read; no scheduler job or background
agent-state store is required.

## Read current state

Authenticated `GET /api/clock-off` returns the current schedule and state:

```json
{
  "schedule": {
    "enabled": true,
    "active_days": [0, 1, 2, 3, 4],
    "clock_off_time": "22:00",
    "wind_down_minutes": 15
  },
  "clock_off": {
    "enabled": true,
    "state": "winding_down",
    "timezone": "Australia/Sydney",
    "clock_off_at": "2026-10-09T11:00:00Z",
    "wind_down_at": "2026-10-09T10:45:00Z",
    "resumes_at": "2026-10-09T19:00:00Z",
    "minutes_remaining": 12,
    "override_until": null,
    "guidance": ["Advisory wrap-up instructions for the connected agent."]
  }
}
```

`GET /api/overview`, `GET /api/digest` and MCP `get_overview` /
`session_digest` include the same top-level `clock_off` object. The session MCP
output schema publishes its fields and state enum. Existing next-up ranking,
progress writes, reminders, pause and completion behavior continue unchanged.

| State | Meaning |
| --- | --- |
| `normal` | Disabled, no active schedule days, or before wind-down. No added guidance. |
| `winding_down` | Within the lead before activation. Finish a small safe step, avoid substantial new work, checkpoint and pause. |
| `clocked_off` | Activation reached, before the next local 06:00 reset. Park unfinished work with a concrete resume step; keep wrap-up trivial or necessary. |
| `overridden` | Enabled and an explicit temporary override is still valid. Respect the user's choice until expiry. |

All state timestamps are UTC ISO-8601 strings ending in `Z`. Display them in
`clock_off.timezone`. `clock_off_at`, `wind_down_at` and `resumes_at` describe
the current clocked-off window or the next scheduled activation. They are null
when disabled or there are no active days. `minutes_remaining` rounds up to the
next whole minute before activation, stays zero afterward, and is null without
a window. `override_until` is null when expired, canceled or disabled, even
though the expired timestamp may remain stored in preferences.

The frontend can display **“Clock-Off ends at 06:00”** using `resumes_at`, or
**“Wind-down starts at …”** using `wind_down_at`. Read again after settings
changes or a displayed boundary; clients should not persist derived state.

## Explicit temporary override

Authenticated `POST /api/clock-off/override` accepts `{"minutes": 30}` for a
duration of `1`–`1440` whole minutes. There is no inferred urgency or unbounded
session override. `DELETE /api/clock-off/override` cancels it immediately.
Both return the same schedule/state envelope as `GET /api/clock-off`.
Invalid durations, extra fields or missing duration return `422`.

An override is persisted as an absolute UTC expiry and survives restart without
extending its duration. It never changes the schedule; when it expires the
then-current schedule state applies automatically. It can cover midnight, DST
or the 06:00 reset. Disabled Clock-Off remains `normal` even with a stored
override. `PUT /api/prefs` rejects any `clock_off_override_until` write with
`400`; only the explicit override endpoints create or cancel it.

All configuration, state and override endpoints use existing API authentication
(bearer credentials or browser session with existing request/origin checks).

## Agent guidance

Treat `clock_off.guidance` as calm, advisory coaching. During wind-down, avoid
broad tasks, new PRs, refactors, audits and unrelated debugging. Finish only the
current small safe step where practical; use `upsert_progress` for a compact
checkpoint and `pause_thread` with a concrete next pickup action. Once clocked
off, prefer necessary wrap-up and a short safely parked summary. Mention the
boundary once rather than repeatedly nagging. Respect the explicit override.
Clock-Off never marks work done, auto-pauses it, or rejects a user action.

## Verification

`tests/test_clock_off.py` covers schedule boundaries, active days, midnight,
IANA offsets, DST gaps/folds, persistence, expiry and actual MCP tool responses.
`tests/test_clock_off_api.py` covers authenticated configuration/override calls,
validation, partial updates, restart persistence and expiry.
`tests/test_clock_off_ui.py` covers settings payload shaping, wind-down copy,
override expiry and the narrow layout rules. Run the full pytest suite, Ruff
and the existing browser smoke, including the Clock-Off settings and Now path.
