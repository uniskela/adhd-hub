import { projectFilter, overviewCache, activeScreen, archivedProjectsCache } from './state.js';
import { api } from './api.js';
import { loadChosenThread, renderDriftBanner, renderReminders } from './now.js';
import { renderStats } from './progress.js';
import { loadPrefs } from './settings.js';
import { renderPending, renderProjects, selectProject } from './work.js';

export async function loadOverview() {
    overviewCache = await api("/overview");
    try {
      archivedProjectsCache = (await api("/projects?include_archived=true")).filter((p) => p.archived);
    } catch (_) {
      archivedProjectsCache = [];
    }
    renderStats(overviewCache);
    renderProjects(overviewCache.projects || []);
    renderPending(overviewCache.pending_actions || []);
    renderReminders(overviewCache.due_reminders || [], overviewCache.reminders || []);
    renderDriftBanner();
  }
export async function loadAll() {
    await loadPrefs();
    await loadOverview();
    await loadChosenThread();
    if (activeScreen === "work") await selectProject(projectFilter);
  }
