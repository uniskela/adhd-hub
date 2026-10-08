# Clock-Off

Clock-Off is an optional schedule that helps you wind down and leave a clear
place to restart. It never stops processes, changes thread status or prevents
you from continuing. Enable it in **Settings → Appearance**; Now shows a quiet
status near the boundary, while clocked off, or during a temporary override.

## Configure the schedule

Choose your Hub timezone, active days, a local Clock-Off time and a wind-down
lead of 0–240 minutes. The defaults are weekdays, 22:00 and a 15-minute lead;
Clock-Off starts disabled. An empty list of active days schedules no windows.

Integrations can read preferences with authenticated `GET /api/prefs` and
update them with `PUT /api/prefs`:

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

Days run from Monday `0` through Sunday `6`. Schedule updates preserve omitted
fields and unrelated preferences. Invalid schedules return `400` without saving.

## Midnight, reset and daylight saving

Each active day names the local date Clock-Off starts. Friday at 22:00 stays
clocked off until Saturday at 06:00, even when Saturday is inactive. A schedule
starting at 00:15 resets at 06:00 that morning; one starting exactly at 06:00
resets the following morning.

The Hub uses your timezone's daylight-saving rules. Repeated activation times
use the first occurrence; nonexistent times move forward by the daylight-saving
gap. Wind-down and override durations measure elapsed minutes.

## Read current state

Authenticated `GET /api/clock-off` returns `schedule` and `clock_off` objects.
The overview and digest REST/MCP responses also include `clock_off`.

| State | What to expect |
| --- | --- |
| `normal` | No active boundary or Clock-Off is disabled. |
| `winding_down` | Finish a small safe step and record where to resume. |
| `clocked_off` | Park unfinished work until the next local 06:00 reset. |
| `overridden` | Your explicit temporary override is still valid. |

The state includes `timezone`, `clock_off_at`, `wind_down_at`, `resumes_at`,
`minutes_remaining`, `override_until` and advisory `guidance`. Timestamps are
UTC ISO-8601 strings ending in `Z`; display them in the supplied timezone.
Window timestamps and minutes are null when no window is scheduled. Read the
state again after settings changes or a boundary instead of storing derived state.

## Explicit temporary override

Use the dashboard override control when you choose to continue. Integrations
can send authenticated `POST /api/clock-off/override` with `{"minutes": 30}`;
valid durations are 1–1440 whole minutes. Cancel it with
`DELETE /api/clock-off/override`. Both return the current schedule and state.
Invalid durations return `422`.

Overrides survive restart and expire at the original time. They do not change
your schedule. Disabled Clock-Off stays `normal` even with a stored override.
Only the override endpoints can write the override expiry.

## Agent guidance

Connected agents receive calm wrap-up suggestions through `clock_off.guidance`.
The schedule is advisory, and your explicit override is respected. It never
automatically pauses or completes a thread.

## Verification

For implementation details, boundary cases and maintainer checks, see the
[Clock-Off implementation contract](https://github.com/uniskela/adhd-hub/blob/main/docs/internal/contracts/clock-off-api.md).
