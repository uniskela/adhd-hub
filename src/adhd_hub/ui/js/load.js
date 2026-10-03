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
    const openCount = overview.open || 0;
    const projectCount = (overview.projects || []).length;
    $("now-open-count").textContent = openCount;
    $("now-open-label").textContent = openCount === 1 ? "open step" : "open steps";
    $("now-done-count").textContent = overview.done_week || 0;
    $("now-project-count").textContent = projectCount;
    $("now-project-label").textContent = projectCount === 1 ? "project" : "projects";
    const caption = $("now-overview-caption");
    caption.textContent = overview.blocked
      ? `${overview.blocked} ${overview.blocked === 1 ? "step is" : "steps are"} blocked. Open My work when you’re ready.`
      : "";
    caption.hidden = !overview.blocked;
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
