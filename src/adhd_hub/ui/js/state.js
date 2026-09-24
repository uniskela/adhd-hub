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

const TOAST_DEFAULT_MS = { success: 4500, info: 4500, warning: 7000, error: 0 };
let _toastSeq = 0;

function _toastVariant(text, opts) {
  if (opts && opts.variant) return opts.variant;
  if (opts && opts.error) return "error";
  const t = String(text || "");
  if (/^error\b|failed|could not|unavailable/i.test(t)) return "error";
  if (/^warning\b|skipped/i.test(t)) return "warning";
  if (/saved|done|imported|copied|up to date|approved|restored|downloaded/i.test(t))
    return "success";
  return "info";
}

function _toastApplyTimer(el, variant, opts = {}) {
  clearTimeout(Number(el.dataset.timer || 0) || undefined);
  el.dataset.timer = "";
  const sticky = Boolean(opts.sticky || opts.persist);
  const ms = sticky
    ? 0
    : (opts.duration ?? TOAST_DEFAULT_MS[variant] ?? TOAST_DEFAULT_MS.info);
  if (ms > 0) {
    el.dataset.timer = String(setTimeout(() => el.remove(), ms));
  }
}

export const setMsg = (t, opts = {}) => {
  const host = $("toast-host");
  const legacyMsg = $("msg");
  const legacySettings = $("settings-msg");
  if (legacyMsg) {
    legacyMsg.textContent = "";
    legacyMsg.hidden = true;
  }
  if (legacySettings) {
    legacySettings.textContent = "";
    legacySettings.hidden = true;
  }
  if (!host) return;
  const key = opts.key ? String(opts.key) : "";
  if (!t) {
    if (key && opts.dismiss) {
      [...host.querySelectorAll(".toast")].forEach((el) => {
        if (el.dataset.key === key) {
          clearTimeout(Number(el.dataset.timer || 0) || undefined);
          el.remove();
        }
      });
    }
    return;
  }

  const variant = _toastVariant(t, opts);
  const text = String(t);
  const existing = key
    ? [...host.querySelectorAll(".toast")].find((el) => el.dataset.key === key)
    : [...host.querySelectorAll(".toast")].find(
        (el) => el.dataset.variant === variant && el.dataset.text === text
      );
  if (existing) {
    existing.className = `toast toast-${variant}`;
    existing.dataset.variant = variant;
    existing.dataset.text = text;
    if (key) existing.dataset.key = key;
    existing.setAttribute("role", variant === "error" ? "alert" : "status");
    existing.setAttribute("aria-live", variant === "error" ? "assertive" : "polite");
    const body = existing.querySelector(".toast-body");
    if (body) body.textContent = text;
    existing.classList.add("toast-bump");
    _toastApplyTimer(existing, variant, opts);
    return;
  }

  const id = `toast-${++_toastSeq}`;
  const el = document.createElement("div");
  el.className = `toast toast-${variant}`;
  el.id = id;
  el.dataset.variant = variant;
  el.dataset.text = text;
  if (key) el.dataset.key = key;
  el.setAttribute("role", variant === "error" ? "alert" : "status");
  el.setAttribute("aria-live", variant === "error" ? "assertive" : "polite");

  const body = document.createElement("p");
  body.className = "toast-body";
  body.textContent = text;

  const close = document.createElement("button");
  close.type = "button";
  close.className = "toast-close";
  close.setAttribute("aria-label", "Dismiss notification");
  close.textContent = "×";
  close.addEventListener("click", () => {
    clearTimeout(Number(el.dataset.timer || 0) || undefined);
    el.remove();
  });

  el.append(body, close);
  host.append(el);

  _toastApplyTimer(el, variant, opts);
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
  tagFilter: null,
  overviewCache: null,
  detailCache: null,
  activeScreen: "now",
  settingsReturnScreen: "now",
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
  forgeConfigCache: null,
  aiConfigCache: null,
  /** Project slug with an in-flight rewrite-all, or null. */
  rewriteAllInFlight: null,
};

export function initRepoLinks() {
  state.repoUrl = $("repo-link").href;
  state.repoDisplayUrl = state.repoUrl.replace(/^https:\/\//, "");
}
