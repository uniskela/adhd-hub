import { state, preferences, $ } from './state.js';
import { selectProject } from './work.js';

const SCREEN_KEY = "adhd_hub_active_screen";

export function savedScreen() {
    const raw = preferences.getItem(SCREEN_KEY);
    return raw === "work" || raw === "progress" || raw === "now" ? raw : "now";
  }
export function showScreen(screen, { focusHeading = true, persist = true } = {}) {
    const next = screen === "work" || screen === "progress" || screen === "now" ? screen : "now";
    state.activeScreen = next;
    ["now", "work", "progress"].forEach((name) => { $(name + "-view").hidden = name !== next; });
    document.querySelectorAll("[data-screen]").forEach((button) => {
      if (button.dataset.screen === next) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    if (next !== "work") { ++state.projectRequest; ++state.threadsRequest; }
    if (persist) preferences.setItem(SCREEN_KEY, next);
    if (!focusHeading) return;
    const heading = $(next + "-view")?.querySelector("h1");
    if (heading) {
      if (!heading.hasAttribute("tabindex")) heading.setAttribute("tabindex", "-1");
      try { heading.focus({ preventScroll: true }); } catch (_) { heading.focus(); }
    }
  }
export async function openWork() {
    showScreen("work");
    await selectProject(state.projectFilter);
  }
