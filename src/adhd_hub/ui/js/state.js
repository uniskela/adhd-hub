/** Shared mutable UI state and helpers (ES module live bindings). */
const preferenceCache = new Map();
export const preferences = {
  getItem(key) {
    if (preferenceCache.has(key)) return preferenceCache.get(key);
    try { return localStorage.getItem(key); } catch (_) { return null; }
  },
  setItem(key, value) {
    preferenceCache.set(key, String(value));
    try { localStorage.setItem(key, value); } catch (_) { /* In-memory fallback. */ }
  },
  removeItem(key) {
    preferenceCache.set(key, null);
    try { localStorage.removeItem(key); } catch (_) { /* Storage unavailable. */ }
  },
};
preferences.removeItem("adhd_hub_token");

export let authStatus = { password_configured: false, development_mode: false };
export let loginMode = "token";
export let celebrationTimeout;
export const completing = new Set();
export let threadsCache = [];
export let threadsRequest = 0;
export let projectRequest = 0;
export const tzKey = "adhd_hub_timezone";
export let currentView = "open";
export let projectFilter = null;
export let overviewCache = null;
export let detailCache = null;
export let activeScreen = "now";
export let chosenId = preferences.getItem("adhd_hub_chosen_thread");
export let chosenThread = null;
export let focusState = preferences.getItem("adhd_hub_focus_state") || "ready";
export let focusRequest = 0;
export let pauseTarget = null;
export let nowMessage = "";
export let shareFile = null;
export let shareVersion = 0;
export let focusModeOn = preferences.getItem("adhd_hub_focus_mode") === "true";
export let focusEndsAt = Number(preferences.getItem("adhd_hub_focus_ends_at") || 0) || 0;
export let focusTimerId = null;
export let archivedProjectsCache = [];
export let currentTz =
    preferences.getItem(tzKey) ||
    Intl.DateTimeFormat().resolvedOptions().timeZone ||
    "UTC";
export const prefersReducedMotion = () =>
    typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

export const $ = (id) => document.getElementById(id);
export const setMsg = (t) => {
  $("msg").textContent = t || "";
  $("settings-msg").textContent = t || "";
};
export const escapeHtml = (s) =>
  String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

export let repoUrl = "";
export let repoDisplayUrl = "";
export function initRepoLinks() {
  repoUrl = $("repo-link").href;
  repoDisplayUrl = repoUrl.replace(/^https:\/\//, "");
}
