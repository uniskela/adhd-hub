/** Shared mutable UI state and helpers (plain object so modules can assign). */
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

export const completing = new Set();
export const tzKey = "adhd_hub_timezone";
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

export const state = {
  authStatus: { password_configured: false, development_mode: false },
  loginMode: "token",
  celebrationTimeout: undefined,
  threadsCache: [],
  threadsRequest: 0,
  projectRequest: 0,
  currentView: "open",
  projectFilter: null,
  overviewCache: null,
  detailCache: null,
  activeScreen: "now",
  chosenId: preferences.getItem("adhd_hub_chosen_thread"),
  chosenThread: null,
  focusState: preferences.getItem("adhd_hub_focus_state") || "ready",
  focusRequest: 0,
  pauseTarget: null,
  nowMessage: "",
  shareFile: null,
  shareVersion: 0,
  focusModeOn: preferences.getItem("adhd_hub_focus_mode") === "true",
  focusEndsAt: Number(preferences.getItem("adhd_hub_focus_ends_at") || 0) || 0,
  focusTimerId: null,
  archivedProjectsCache: [],
  currentTz:
    preferences.getItem(tzKey) ||
    Intl.DateTimeFormat().resolvedOptions().timeZone ||
    "UTC",
  repoUrl: "",
  repoDisplayUrl: "",
};

export function initRepoLinks() {
  state.repoUrl = $("repo-link").href;
  state.repoDisplayUrl = state.repoUrl.replace(/^https:\/\//, "");
}
