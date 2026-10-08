/** Pure Clock-Off copy and schedule shaping. DOM wiring lives in clock-off.js. */

const WEEKDAYS = [0, 1, 2, 3, 4];

export function normalizeSchedule(input) {
  const src = input && typeof input === "object" ? input : {};
  const rawDays = Array.isArray(src.active_days) ? src.active_days : WEEKDAYS;
  const active_days = [...new Set(
    rawDays
      .map((day) => Number(day))
      .filter((day) => Number.isInteger(day) && day >= 0 && day <= 6),
  )].sort((a, b) => a - b);
  const match = /^([01]\d|2[0-3]):([0-5]\d)/.exec(String(src.clock_off_time || "22:00").trim());
  let lead = Number(src.wind_down_minutes);
  if (!Number.isInteger(lead)) lead = 15;
  return {
    enabled: src.enabled === true,
    active_days,
    clock_off_time: match ? `${match[1]}:${match[2]}` : "22:00",
    wind_down_minutes: Math.min(240, Math.max(0, lead)),
  };
}

/** Whole minutes until an ISO instant, rounded up. 0 once that instant has passed. */
export function minutesUntil(iso, now) {
  const end = Date.parse(iso);
  const start = now instanceof Date ? now.getTime() : Date.parse(now);
  if (!Number.isFinite(end) || !Number.isFinite(start)) return null;
  const ms = end - start;
  if (ms <= 0) return 0;
  return Math.ceil(ms / 60000);
}

export function formatLocalClock(iso, timeZone, locale) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const options = { hour: "numeric", minute: "2-digit", timeZone: timeZone || "UTC" };
  try {
    return new Intl.DateTimeFormat(locale, options).format(date);
  } catch {
    return new Intl.DateTimeFormat(locale, { ...options, timeZone: "UTC" }).format(date);
  }
}

function phrase(minutes) {
  const n = Math.max(0, minutes);
  return n === 1 ? "1 minute" : `${n} minutes`;
}

function presets(clock, zone, locale) {
  const items = [
    { minutes: 30, label: "30 minutes" },
    { minutes: 60, label: "1 hour" },
  ];
  const untilReset = clock.resumes_at ? minutesUntil(clock.resumes_at, clock._now) : null;
  if (untilReset >= 1 && untilReset <= 1440 && untilReset !== 30 && untilReset !== 60) {
    const when = formatLocalClock(clock.resumes_at, zone, locale);
    if (when) items.push({ minutes: untilReset, label: `Until ${when}` });
  }
  return items;
}

/**
 * Quiet Now copy. Hidden while disabled, and while enabled but still outside
 * the wind-down approach window.
 * ponytail: approach notice is capped at 60 minutes; a longer lead is already
 * the winding_down state.
 */
export function clockOffStatus(envelope, now = new Date(), locale) {
  const schedule = normalizeSchedule(envelope?.schedule);
  const clock = envelope?.clock_off && typeof envelope.clock_off === "object" ? envelope.clock_off : {};
  const enabled = clock.enabled === undefined ? schedule.enabled : clock.enabled === true;
  const hidden = {
    visible: false,
    state: "normal",
    title: "",
    detail: "",
    overrides: [],
    endOverride: false,
    stale: false,
  };
  if (!enabled) return hidden;

  const zone = clock.timezone || "UTC";
  const state = clock.state || "normal";
  if (state === "overridden") {
    const left = clock.override_until ? minutesUntil(clock.override_until, now) : 0;
    if (!clock.override_until || left <= 0) return { ...hidden, stale: true };
    return {
      visible: true,
      state: "overridden",
      title: "Clock-Off is paused",
      detail: `Until ${formatLocalClock(clock.override_until, zone, locale)}`,
      overrides: [],
      endOverride: true,
      stale: false,
    };
  }

  if (state === "normal") {
    const startIn = clock.wind_down_at ? minutesUntil(clock.wind_down_at, now) : null;
    if (clock.wind_down_at && startIn === 0) return { ...hidden, stale: true };
    const notice = Math.min(Math.max(schedule.wind_down_minutes, 0), 60);
    if (!notice || startIn == null || startIn <= 0 || startIn > notice) return hidden;
    return {
      visible: true,
      state: "approaching",
      title: `Wind-down starts in ${phrase(startIn)}`,
      detail: "",
      overrides: [],
      endOverride: false,
      stale: false,
    };
  }

  const choices = presets({ ...clock, _now: now }, zone, locale);
  if (state === "winding_down") {
    const left = Number.isInteger(clock.minutes_remaining)
      ? clock.minutes_remaining
      : (clock.clock_off_at ? minutesUntil(clock.clock_off_at, now) : null);
    return {
      visible: true,
      state: "winding_down",
      title: "Save your next step before finishing",
      detail: left > 0 ? `Clock-Off in ${phrase(left)}` : "",
      overrides: choices,
      endOverride: false,
      stale: false,
    };
  }

  if (state === "clocked_off") {
    const ends = clock.resumes_at ? formatLocalClock(clock.resumes_at, zone, locale) : "";
    return {
      visible: true,
      state: "clocked_off",
      title: "Save your next step before finishing",
      detail: ends ? `Clock-Off ends at ${ends}` : "",
      overrides: choices,
      endOverride: false,
      stale: false,
    };
  }

  return hidden;
}

/** Next UTC instant the client should read again, or null when nothing is scheduled. */
export function nextRefreshAt(envelope, now = new Date()) {
  const schedule = normalizeSchedule(envelope?.schedule);
  const clock = envelope?.clock_off || {};
  if (clock.enabled !== true && !schedule.enabled) return null;
  const times = [];
  const add = (iso) => {
    const t = Date.parse(iso);
    if (Number.isFinite(t) && t > now.getTime()) times.push(t);
  };
  add(clock.wind_down_at);
  add(clock.clock_off_at);
  add(clock.resumes_at);
  add(clock.override_until);
  if (clock.wind_down_at && schedule.wind_down_minutes > 0) {
    const notice = Math.min(schedule.wind_down_minutes, 60);
    const start = Date.parse(clock.wind_down_at) - notice * 60000;
    if (start > now.getTime()) times.push(start);
  }
  if (!times.length) return null;
  return new Date(Math.min(...times));
}

/** Run calls one after another. A call made during an active run waits, then runs once. */
export function chainCalls(start) {
  let chain = Promise.resolve();
  return function queued() {
    const run = chain.then(start, start);
    chain = run.then(() => undefined, () => undefined);
    return run;
  };
}
