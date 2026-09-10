import { $, state } from './state.js';
import { selectProject } from './work.js';

export function showScreen(screen) {
    state.activeScreen = screen;
    ["now", "work", "progress"].forEach((name) => { $(name + "-view").hidden = name !== screen; });
    document.querySelectorAll("[data-screen]").forEach((button) => {
      if (button.dataset.screen === screen) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    if (screen !== "work") { ++state.projectRequest; ++state.threadsRequest; }
    const heading = $(screen + "-view")?.querySelector("h1");
    if (heading) {
      if (!heading.hasAttribute("tabindex")) heading.setAttribute("tabindex", "-1");
      try { heading.focus({ preventScroll: true }); } catch (_) { heading.focus(); }
    }
  }
export async function openWork() {
    showScreen("work");
    await selectProject(state.projectFilter);
  }
