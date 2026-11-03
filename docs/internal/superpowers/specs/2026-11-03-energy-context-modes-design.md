# Energy / context modes (Wave 8) — design

Parent: [#55](https://github.com/uniskela/adhd-hub/issues/55) · Continuity: [#337](https://github.com/uniskela/adhd-hub/issues/337)

## Goal

Ship **Short vs Deep return views** as a local preference so coming back to Now can stay minimal or show fuller context. No capacity scoring, no gamified energy guilt. Thread `EnergyLevel` / Next-up ranking stay unchanged.

## Non-goals

- Soft “capacity today” filter chips on Now
- MCP / server prefs for density
- Changing Focus mode or Clock-Off
- Reworking My work detail density (can follow later)

## Approach

One local preference: `adhd_hub_return_density` = `short` | `deep` (default **deep** = current behaviour).

### Short

On Now, with a chosen thread: show stage, title, resume (“Where you left off” or start cue), and primary actions only. Hide project-notes `<details>`, focus meta (project · last touched), and the overview stats strip. Gentle checks (`#now-checks`) stay — they are actionable, not decorative.

### Deep

Current Now layout unchanged.

### Settings

Under Appearance: **Return view** control — Short (“Just the next step”) / Deep (“Full context”). Neutral copy; no energy/guilt language.

### Persistence

`localStorage` via existing `preferences` helper (same pattern as focus mode / theme).

## Verify

- Preference round-trips; default deep matches today’s DOM
- Short omits notes/meta/overview; actions + resume remain
- Pytest / UI string asserts; SW cache bump
