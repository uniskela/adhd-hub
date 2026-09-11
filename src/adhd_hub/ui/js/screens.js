import { state, preferences, $ } from './state.js';
import { selectProject } from './work.js';

const SCREEN_KEY = "adhd_hub_active_screen";
const SCREENS = new Set(["now", "work", "progress", "settings"]);

export function savedScreen() {
  const raw = preferences.getItem(SCREEN_KEY);
  return raw === "work" || raw === "progress" || raw === "now" ? raw : "now";
}

export function showScreen(screen, { focusHeading = true, persist = true } = {}) {
  const next = SCREENS.has(screen) ? screen : "now";
  if (next === "settings" && state.activeScreen && state.activeScreen !== "settings") {
    state.settingsReturnScreen = state.activeScreen;
  }
  state.activeScreen = next;
  ["now", "work", "progress", "settings"].forEach((name) => {
    const el = $(name + "-view");
    if (el) el.hidden = name !== next;
  });
  document.querySelectorAll("[data-screen]").forEach((button) => {
    if (button.dataset.screen === next) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  const settingsBtn = $("btn-settings");
  if (settingsBtn) {
    if (next === "settings") settingsBtn.setAttribute("aria-current", "page");
    else settingsBtn.removeAttribute("aria-current");
  }
  document.body.classList.toggle("settings-open", next === "settings");
  if (next !== "work") {
    ++state.projectRequest;
    ++state.threadsRequest;
  }
  if (persist && next !== "settings") preferences.setItem(SCREEN_KEY, next);
  if (!focusHeading) return;
  const heading = $(next + "-view")?.querySelector("h1");
  if (heading) {
    if (!heading.hasAttribute("tabindex")) heading.setAttribute("tabindex", "-1");
    try {
      heading.focus({ preventScroll: true });
    } catch (_) {
      heading.focus();
    }
  }
}

export function closeSettings() {
  const back = state.settingsReturnScreen === "work" || state.settingsReturnScreen === "progress"
    ? state.settingsReturnScreen
    : "now";
  showScreen(back);
}

export async function openWork() {
  showScreen("work");
  await selectProject(state.projectFilter);
}
