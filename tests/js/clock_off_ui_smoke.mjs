/**
 * Clock-Off settings payload, Now copy, override expiry, and narrow layout.
 * Run: node tests/js/clock_off_ui_smoke.mjs
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  chainCalls,
  clockOffStatus,
  formatLocalClock,
  nextRefreshAt,
  normalizeSchedule,
} from "../../src/adhd_hub/ui/js/clock-off.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const html = readFileSync(join(root, "src/adhd_hub/ui/index.html"), "utf8");
const css = readFileSync(join(root, "src/adhd_hub/ui/app.css"), "utf8");
const locale = "en-US";

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const schedule = normalizeSchedule({
  enabled: true,
  active_days: [4, 4, 0, 9],
  clock_off_time: "22:00:00",
  wind_down_minutes: 15,
});
assert(schedule.enabled === true, "enabled persists");
assert(JSON.stringify(schedule.active_days) === JSON.stringify([0, 4]), "days are unique and sorted");
assert(schedule.clock_off_time === "22:00", "time drops seconds");
assert(normalizeSchedule({ wind_down_minutes: 400 }).wind_down_minutes === 240, "lead clamps");
assert(normalizeSchedule({ active_days: [] }).active_days.length === 0, "empty days stay empty");
assert(normalizeSchedule({}).enabled === false, "default stays off");

const zone = "Australia/Sydney";
const off = "2026-10-09T11:00:00Z";
const wind = "2026-10-09T10:45:00Z";
const resumes = "2026-10-09T19:00:00Z";
const base = {
  schedule: { enabled: true, active_days: [0, 1, 2, 3, 4], clock_off_time: "22:00", wind_down_minutes: 15 },
  clock_off: {
    enabled: true,
    state: "normal",
    timezone: zone,
    clock_off_at: off,
    wind_down_at: wind,
    resumes_at: resumes,
    minutes_remaining: 75,
    override_until: null,
  },
};

const early = clockOffStatus(base, new Date("2026-10-09T09:00:00Z"), locale);
assert(early.visible === false, "enabled but early stays quiet");

const approaching = clockOffStatus(base, new Date("2026-10-09T10:30:00Z"), locale);
assert(approaching.visible && approaching.title === "Wind-down starts in 15 minutes", approaching.title);

const winding = clockOffStatus({
  ...base,
  clock_off: { ...base.clock_off, state: "winding_down", minutes_remaining: 12 },
}, new Date("2026-10-09T10:48:00Z"), locale);
assert(winding.title === "Save your next step before finishing", winding.title);
assert(winding.detail === "Clock-Off in 12 minutes", winding.detail);
assert(winding.overrides.map((item) => item.minutes).join(",") === "30,60," + winding.overrides.at(-1).minutes, "override choices");
assert(winding.overrides.at(-1).label.startsWith("Until "), winding.overrides.at(-1).label);
assert(!/streak|alarm|guilt|failed|overdue/i.test(`${winding.title} ${winding.detail}`), "calm copy");

const clocked = clockOffStatus({
  ...base,
  clock_off: { ...base.clock_off, state: "clocked_off", minutes_remaining: 0 },
}, new Date("2026-10-09T11:05:00Z"), locale);
const ends = formatLocalClock(resumes, zone, locale);
assert(clocked.detail === `Clock-Off ends at ${ends}`, clocked.detail);
assert(ends.includes("6:00"), ends);

const paused = clockOffStatus({
  ...base,
  clock_off: { ...base.clock_off, state: "overridden", override_until: "2026-10-09T12:00:00Z" },
}, new Date("2026-10-09T11:10:00Z"), locale);
assert(paused.endOverride && paused.overrides.length === 0, "override shows expiry only");
assert(paused.detail.startsWith("Until "), paused.detail);

const expired = clockOffStatus({
  ...base,
  clock_off: { ...base.clock_off, state: "overridden", override_until: "2026-10-09T11:00:00Z" },
}, new Date("2026-10-09T11:00:00Z"), locale);
assert(expired.visible === false && expired.stale === true, "expired override is not shown");

const offState = clockOffStatus({
  schedule: { enabled: false },
  clock_off: { enabled: false, state: "normal" },
}, new Date("2026-10-09T10:48:00Z"), locale);
assert(offState.visible === false, "disabled adds no status");

const refresh = nextRefreshAt(base, new Date("2026-10-09T09:00:00Z"));
assert(refresh.toISOString() === "2026-10-09T10:30:00.000Z", refresh.toISOString());

assert(html.includes('id="clock-off-status" class="clock-off-status" hidden'), "status starts hidden");
assert(html.includes('id="clock-off-fields" class="clock-off-fields" hidden'), "settings details start hidden");
assert(html.includes('id="clock-off-enabled"'), "opt-in control");
assert(html.includes('type="time" id="clock-off-time"'), "native time input");
assert(!html.includes("role=\"alert\"" ) || !html.slice(html.indexOf("clock-off-status"), html.indexOf("next-card")).includes("alert"), "no alert dialog");

const block = css.slice(css.indexOf(".clock-off-status"));
assert(block.includes("flex-wrap: wrap"), "days and actions wrap");
assert(block.includes("@media (max-width: 480px)"), "narrow layout");
assert(block.includes(".clock-off-overrides > button { flex: 1 1 calc(50% - .5rem); }"), "narrow override buttons");
assert(!/\.clock-off-status[^{]*\{[^}]*animation/.test(css), "no status animation");

let active = 0;
let maxActive = 0;
let reads = 0;
const queued = chainCalls(async () => {
  active += 1;
  maxActive = Math.max(maxActive, active);
  await Promise.resolve();
  active -= 1;
  return ++reads;
});
const results = await Promise.all([queued(), queued(), queued()]);
assert(maxActive === 1, "status reads do not overlap");
assert(results.join(",") === "1,2,3", "a refresh during a refresh still runs");

console.log("clock_off_ui_smoke: ok");
