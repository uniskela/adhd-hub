import { state } from './state.js';
import { api } from './api.js';
import { loadChosenThread, renderDriftBanner, renderReminders } from './now.js';
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
    renderProjects(state.overviewCache.projects || []);
    renderPending(state.overviewCache.pending_actions || []);
    renderReminders(state.overviewCache.due_reminders || [], state.overviewCache.reminders || []);
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
