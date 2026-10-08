import { $, setMsg } from './state.js';
import { api } from './api.js';
import { clockOffStatus, nextRefreshAt, normalizeSchedule } from './clock-off.mjs';

let schedule = normalizeSchedule({});
let filling = false;
let saveGen = 0;
let timer = 0;
let refreshing = false;
let staleCount = 0;

export function rememberSchedule(raw) {
  schedule = normalizeSchedule(raw);
  fillForm(schedule);
}

function fillForm(next) {
  const box = $("clock-off-enabled");
  if (!box) return;
  filling = true;
  box.checked = next.enabled;
  const fields = $("clock-off-fields");
  if (fields) fields.hidden = !next.enabled;
  document.querySelectorAll("[data-clock-day]").forEach((input) => {
    input.checked = next.active_days.includes(Number(input.value));
  });
  const time = $("clock-off-time");
  if (time) time.value = next.clock_off_time;
  const lead = $("clock-off-lead");
  if (lead) lead.value = String(next.wind_down_minutes);
  filling = false;
}

function readForm() {
  const box = $("clock-off-enabled");
  if (!box) return null;
  const days = [...document.querySelectorAll("[data-clock-day]:checked")].map((input) => Number(input.value));
  return normalizeSchedule({
    enabled: box.checked,
    active_days: days,
    clock_off_time: $("clock-off-time")?.value || "22:00",
    wind_down_minutes: Number($("clock-off-lead")?.value),
  });
}

function paint(view) {
  const root = $("clock-off-status");
  if (!root) return;
  root.hidden = !view.visible;
  const title = $("clock-off-status-title");
  const detail = $("clock-off-status-detail");
  const actions = $("clock-off-overrides");
  if (!view.visible) {
    if (title) title.textContent = "";
    if (detail) {
      detail.hidden = true;
      detail.textContent = "";
    }
    if (actions) {
      actions.hidden = true;
      actions.replaceChildren();
    }
    return;
  }
  if (title) title.textContent = view.title;
  if (detail) {
    detail.hidden = !view.detail;
    detail.textContent = view.detail || "";
  }
  if (!actions) return;
  const show = view.overrides.length > 0 || view.endOverride;
  actions.hidden = !show;
  actions.replaceChildren();
  if (!show) return;
  if (view.overrides.length) {
    const label = document.createElement("p");
    label.className = "hint";
    label.textContent = "Override temporarily";
    actions.append(label);
    view.overrides.forEach((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "ghost";
      button.dataset.minutes = String(item.minutes);
      button.textContent = item.label;
      actions.append(button);
    });
  }
  if (view.endOverride) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ghost";
    button.dataset.endOverride = "1";
    button.textContent = "End override";
    actions.append(button);
  }
}

function armTimer(clockOff, view, now) {
  clearTimeout(timer);
  if (typeof document !== "undefined" && document.hidden) return;
  if (view.stale) {
    if (staleCount < 1) {
      staleCount += 1;
      timer = setTimeout(() => { refreshClockOff(); }, 1000);
    }
    return;
  }
  staleCount = 0;
  let wait = null;
  if (view.visible) wait = 60000;
  else {
    const at = nextRefreshAt({ schedule, clock_off: clockOff }, now);
    if (!at) return;
    wait = Math.min(Math.max(at.getTime() - now.getTime(), 1000), 12 * 60 * 60 * 1000);
  }
  timer = setTimeout(() => { refreshClockOff(); }, wait);
}

export function renderClockOffFromState(clockOff, now = new Date()) {
  const view = clockOffStatus({ schedule, clock_off: clockOff || { enabled: false } }, now);
  paint(view);
  armTimer(clockOff || { enabled: false }, view, now);
  return view;
}

export async function refreshClockOff() {
  if (refreshing) return;
  refreshing = true;
  try {
    const data = await api("/clock-off");
    if (data?.schedule) schedule = normalizeSchedule(data.schedule);
    renderClockOffFromState(data?.clock_off);
  } catch {
    /* Keep the last quiet status. The next visit or boundary reads again. */
  } finally {
    refreshing = false;
  }
}

async function saveFromForm() {
  if (filling) return;
  const next = readForm();
  if (!next) return;
  const fields = $("clock-off-fields");
  if (fields) fields.hidden = !next.enabled;
  const gen = ++saveGen;
  try {
    const saved = await api("/prefs", {
      method: "PUT",
      body: JSON.stringify({ clock_off: next }),
    });
    if (gen !== saveGen) return;
    schedule = normalizeSchedule(saved?.clock_off || next);
    fillForm(schedule);
    await refreshClockOff();
  } catch (error) {
    if (gen !== saveGen) return;
    fillForm(schedule);
    setMsg(error.message || "Could not save Clock-Off");
  }
}

async function postOverride(minutes) {
  const data = await api("/clock-off/override", {
    method: "POST",
    body: JSON.stringify({ minutes }),
  });
  if (data?.schedule) schedule = normalizeSchedule(data.schedule);
  renderClockOffFromState(data?.clock_off);
  $("clock-off-status-title")?.focus();
}

async function endOverride() {
  const data = await api("/clock-off/override", { method: "DELETE" });
  if (data?.schedule) schedule = normalizeSchedule(data.schedule);
  renderClockOffFromState(data?.clock_off);
  $("clock-off-status-title")?.focus();
}

export function bindClockOff() {
  $("clock-off-enabled")?.addEventListener("change", () => { saveFromForm(); });
  $("clock-off-time")?.addEventListener("change", () => { saveFromForm(); });
  $("clock-off-lead")?.addEventListener("change", () => { saveFromForm(); });
  document.querySelectorAll("[data-clock-day]").forEach((input) => {
    input.addEventListener("change", () => { saveFromForm(); });
  });
  $("clock-off-overrides")?.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const action = button.dataset.endOverride
      ? endOverride()
      : postOverride(Number(button.dataset.minutes));
    action.catch((error) => setMsg(error.message || "Could not update Clock-Off"));
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshClockOff();
  });
}
