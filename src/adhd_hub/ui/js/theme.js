import { $, preferences } from './state.js';

const THEME_KEY = "adhd_hub_theme";

export function getThemePreference() {
  const value = preferences.getItem(THEME_KEY) || "system";
  return value === "light" || value === "dark" || value === "system" ? value : "system";
}

export function syncThemeToggles(selection = getThemePreference()) {
  document.querySelectorAll("[data-theme-toggle]").forEach((group) => {
    group.querySelectorAll("[data-theme-value]").forEach((button) => {
      const selected = button.dataset.themeValue === selection;
      button.setAttribute("aria-checked", String(selected));
      button.classList.toggle("is-active", selected);
    });
  });
}

export function applyTheme(selection = getThemePreference()) {
  const resolved = selection === "system"
    ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
    : selection;
  document.documentElement.dataset.theme = resolved;
  syncThemeToggles(selection);
}

export function setThemePreference(selection) {
  const next = selection === "light" || selection === "dark" || selection === "system"
    ? selection
    : "system";
  preferences.setItem(THEME_KEY, next);
  applyTheme(next);
}

export function bindThemeControls() {
  document.querySelectorAll("[data-theme-toggle]").forEach((group) => {
    group.querySelectorAll("[data-theme-value]").forEach((button) => {
      button.addEventListener("click", () => setThemePreference(button.dataset.themeValue));
    });
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (getThemePreference() === "system") applyTheme("system");
  });
  applyTheme(getThemePreference());
}
