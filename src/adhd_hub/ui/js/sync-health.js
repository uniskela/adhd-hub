import { api } from './api.js';
import { $ } from './state.js';
import { formatWhen } from './dom.js';
import { enqueueForgeJob } from './forge-jobs.js';

function text(value, fallback = "—") {
  if (value == null || value === "") return fallback;
  return String(value);
}

export async function refreshSyncHealth() {
  const panel = $("sync-health");
  if (!panel) return null;
  let data;
  try {
    data = await api("/sync-health");
  } catch (err) {
    panel.hidden = false;
    const status = $("sync-health-status");
    if (status) status.textContent = "Sync health unavailable.";
    return null;
  }
  panel.hidden = false;

  const forge = data.forge || {};
  const conflicts = data.conflicts || {};
  const status = $("sync-health-status");
  const detail = $("sync-health-detail");
  const history = $("sync-health-history");
  const conflictEl = $("sync-health-conflicts");

  const successAt = forge.last_success?.at;
  const failureAt = forge.last_failure?.at;
  const configured = forge.configured;

  let headline = "Forge not configured.";
  if (configured) {
    if (failureAt && (!successAt || failureAt > successAt)) {
      headline = `Last sync failed${failureAt ? ` · ${formatWhen(failureAt)}` : ""}.`;
    } else if (successAt) {
      headline = `Last sync ok · ${formatWhen(successAt)}.`;
    } else {
      headline = "No forge sync recorded yet.";
    }
  }
  if (status) status.textContent = headline;

  const bits = [];
  if (configured && forge.provider) bits.push(`Provider: ${forge.provider}`);
  if (forge.last_failure?.error) bits.push(`Error: ${text(forge.last_failure.error)}`);
  if (detail) detail.textContent = bits.join(" · ");

  if (conflictEl) {
    const count = conflicts.count || 0;
    if (count > 0) {
      const names = (conflicts.threads || [])
        .map((t) => t.summary || t.id)
        .filter(Boolean)
        .slice(0, 3)
        .join(", ");
      conflictEl.hidden = false;
      conflictEl.textContent = `Needs review: ${count}${names ? ` — ${names}` : ""}`;
    } else {
      conflictEl.hidden = true;
      conflictEl.textContent = "";
    }
  }

  if (history) {
    const items = data.recent_changes || [];
    history.innerHTML = items.length
      ? items
          .map((item) => {
            const when = item.created_at ? formatWhen(item.created_at) : "";
            return `<li><span class="sync-health-when">${escapeHtml(when)}</span> ${escapeHtml(item.summary || item.type || "")}</li>`;
          })
          .join("")
      : "<li class=\"hint\">No recent Hub changes yet.</li>";
  }
  return data;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export async function retryForgeSync() {
  await enqueueForgeJob("/forge/sync", {}, { pendingLabel: "Retry sync" });
  await refreshSyncHealth();
}
