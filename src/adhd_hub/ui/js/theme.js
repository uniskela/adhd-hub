import { preferences } from './state.js';
import { accentPalette, normalizeAccent } from './accent.js';

const ACCENT_KEY = 'adhd_hub_accent';

const THEME_KEY = "adhd_hub_theme";
const THEME_ORDER = ["system", "light", "dark"];
const THEME_LABELS = { system: "System", light: "Light", dark: "Dark" };
const THEME_ICONS = {
  system:
    "M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v9A2.5 2.5 0 0 1 17.5 17H13v2h2.5a.75.75 0 0 1 0 1.5h-7a.75.75 0 0 1 0-1.5H11v-2H6.5A2.5 2.5 0 0 1 4 14.5v-9Zm1.5 0v9A1 1 0 0 0 6.5 15.5h11a1 1 0 0 0 1-1v-9a1 1 0 0 0-1-1h-11a1 1 0 0 0-1 1Z",
  light:
    "M12 7.25a4.75 4.75 0 1 1 0 9.5 4.75 4.75 0 0 1 0-9.5Zm0-4.5a.75.75 0 0 1 .75.75v1.2a.75.75 0 0 1-1.5 0V3.5A.75.75 0 0 1 12 2.75Zm0 15.3a.75.75 0 0 1 .75.75v1.2a.75.75 0 0 1-1.5 0v-1.2a.75.75 0 0 1 .75-.75Zm9.25-6.3a.75.75 0 0 1-.75.75h-1.2a.75.75 0 0 1 0-1.5H20.5a.75.75 0 0 1 .75.75ZM5.7 12a.75.75 0 0 1-.75.75H3.75a.75.75 0 0 1 0-1.5H4.95A.75.75 0 0 1 5.7 12Zm12.43-6.13a.75.75 0 0 1 0 1.06l-.85.85a.75.75 0 1 1-1.06-1.06l.85-.85a.75.75 0 0 1 1.06 0ZM8.78 16.28a.75.75 0 0 1 0 1.06l-.85.85a.75.75 0 0 1-1.06-1.06l.85-.85a.75.75 0 0 1 1.06 0Zm9.56 1.06a.75.75 0 0 1-1.06 0l-.85-.85a.75.75 0 1 1 1.06-1.06l.85.85a.75.75 0 0 1 0 1.06ZM7.93 6.93a.75.75 0 0 1-1.06 0l-.85-.85A.75.75 0 0 1 7.08 5l.85.85a.75.75 0 0 1 0 1.06Z",
  dark:
    "M12.4 3.1a.75.75 0 0 1 .78.98 7.5 7.5 0 1 0 6.74 6.74.75.75 0 0 1 .98.78A8.75 8.75 0 1 1 12.4 3.1Z",
};

export function getThemePreference() {
  const value = preferences.getItem(THEME_KEY) || "system";
  return value === "light" || value === "dark" || value === "system" ? value : "system";
}

function nextThemePreference(selection = getThemePreference()) {
  const index = THEME_ORDER.indexOf(selection);
  return THEME_ORDER[(index + 1) % THEME_ORDER.length];
}

export function syncThemeCycleButton(selection = getThemePreference()) {
  const button = document.querySelector("[data-theme-cycle]");
  if (!button) return;
  const label = THEME_LABELS[selection] || THEME_LABELS.system;
  const upcoming = THEME_LABELS[nextThemePreference(selection)] || THEME_LABELS.light;
  const labelEl = button.querySelector("[data-theme-cycle-label]");
  const iconEl = button.querySelector("[data-theme-cycle-icon]");
  if (labelEl) labelEl.textContent = label;
  if (iconEl) {
    const path = iconEl.querySelector("path") || iconEl.appendChild(document.createElementNS("http://www.w3.org/2000/svg", "path"));
    path.setAttribute("fill", "currentColor");
    path.setAttribute("d", THEME_ICONS[selection] || THEME_ICONS.system);
  }
  button.dataset.themeValue = selection;
  button.setAttribute("aria-label", `Theme: ${label}. Click to switch to ${upcoming}`);
  button.title = `Theme: ${label} — click to cycle`;
}

export function syncThemeToggles(selection = getThemePreference()) {
  document.querySelectorAll("[data-theme-toggle]").forEach((group) => {
    group.querySelectorAll("[data-theme-value]").forEach((button) => {
      const selected = button.dataset.themeValue === selection;
      button.setAttribute("aria-checked", String(selected));
      button.classList.toggle("is-active", selected);
    });
  });
  syncThemeCycleButton(selection);
}

export function applyTheme(selection = getThemePreference()) {
  const resolved = selection === "system"
    ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
    : selection;
  document.documentElement.dataset.theme = resolved;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", resolved === "dark" ? "#14141c" : "#f7f7fa");
  syncThemeToggles(selection);
  applyAccent();
}

export function setThemePreference(selection) {
  const next = selection === "light" || selection === "dark" || selection === "system"
    ? selection
    : "system";
  preferences.setItem(THEME_KEY, next);
  applyTheme(next);
}

export function cycleThemePreference() {
  setThemePreference(nextThemePreference());
}

export function bindThemeControls() {
  document.getElementById("accent-colour")?.addEventListener("input", (event) => setAccent(event.target.value));
  document.querySelectorAll("[data-accent]").forEach((button) => {
    button.addEventListener("click", () => setAccent(button.dataset.accent));
  });
  document.querySelectorAll("[data-theme-toggle]").forEach((group) => {
    group.querySelectorAll("[data-theme-value]").forEach((button) => {
      button.addEventListener("click", () => setThemePreference(button.dataset.themeValue));
    });
  });
  document.querySelectorAll("[data-theme-cycle]").forEach((button) => {
    button.addEventListener("click", () => cycleThemePreference());
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (getThemePreference() === "system") applyTheme("system");
  });
  applyTheme(getThemePreference());
}

function applyAccent() {
  const root = document.documentElement;
  const chosen = normalizeAccent(preferences.getItem(ACCENT_KEY));
  const palette = accentPalette(chosen, root.dataset.theme === "dark");
  const tokens = { "--accent": "accent", "--accent-soft": "soft", "--accent-ink": "ink", "--accent-hover": "hover" };
  for (const [token, key] of Object.entries(tokens)) {
    if (palette) root.style.setProperty(token, palette[key]);
    else root.style.removeProperty(token);
  }
  const picker = document.getElementById("accent-colour");
  if (picker) picker.value = chosen || "#4f46c8";
  const label = document.getElementById("accent-value");
  if (label) label.textContent = chosen ? chosen.toUpperCase() : "Default palette";
  document.querySelectorAll("[data-accent]").forEach((button) => {
    button.setAttribute("aria-pressed", String((button.dataset.accent || null) === chosen));
  });
}

function setAccent(value) {
  const colour = normalizeAccent(value);
  if (colour) preferences.setItem(ACCENT_KEY, colour);
  else preferences.removeItem(ACCENT_KEY);
  applyAccent();
}
