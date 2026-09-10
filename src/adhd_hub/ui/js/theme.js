import { $ } from './state.js';

export function applyTheme() {
    const selection = $("theme-select").value;
    document.documentElement.dataset.theme = selection === "system"
      ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : selection;
  }
