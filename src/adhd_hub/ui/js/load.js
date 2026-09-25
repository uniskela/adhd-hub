import { state, $ } from './state.js';
import { api } from './api.js';
import { loadChosenThread, renderDriftBanner, renderReminders, renderTriage } from './now.js';
import { renderStats } from './progress.js';
import { loadPrefs } from './settings.js';
import { renderPending, renderProjects, selectProject } from './work.js';

export async function loadOverview() {
    state.overviewCache = await api("/overview");
    try {
      state.archivedProjectsCache = (await api("/projects?include_archived=true")).filter((p) => p.archived);
    } catch (_) {
      state.archivedProjectsCache = [];
    }
    renderStats(state.overviewCache);
    const overview = state.overviewCache;
    $("now-open-count").textContent = overview.open || 0;
    $("now-done-count").textContent = overview.done_week || 0;
    $("now-project-count").textContent = (overview.projects || []).length;
    $("now-overview-caption").textContent = overview.blocked
      ? `${overview.blocked} ${overview.blocked === 1 ? "step needs" : "steps need"} a nudge. Open My work when you’re ready.`
      : "No need to do it all today. Focus mode keeps just your chosen step in view.";
    renderProjects(state.overviewCache.projects || []);
    renderPending(state.overviewCache.pending_actions || []);
    renderReminders(state.overviewCache.due_reminders || [], state.overviewCache.reminders || []);
    renderTriage(state.overviewCache.triage_candidates || []);
    renderDriftBanner();
  }
export async function loadAll() {
    await loadPrefs();
    await loadOverview();
    await loadChosenThread();
    const wantWork =
      state.activeScreen === "work" || state.settingsReturnScreen === "work";
    if (wantWork) await selectProject(state.projectFilter);
  }
