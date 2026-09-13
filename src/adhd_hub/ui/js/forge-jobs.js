import { $, setMsg, escapeHtml } from './state.js';
import { api } from './api.js';

let _forgeJobsPoll = null;

export function renderForgeJobs(jobs) {
  const wrap = $("forge-jobs");
  const list = $("forge-jobs-list");
  if (!wrap || !list) return;
  const items = Array.isArray(jobs) ? jobs : [];
  const active = items.filter((j) => j.status === "queued" || j.status === "running");
  const recent = items.slice(0, 6);
  if (!recent.length) {
    wrap.hidden = true;
    list.innerHTML = "";
    return;
  }
  wrap.hidden = false;
  list.innerHTML = recent
    .map((j) => {
      const status = escapeHtml(j.status || "unknown");
      const pos =
        j.status === "queued" && j.queue_position
          ? ` #${j.queue_position}`
          : "";
      const msg = escapeHtml(j.message || j.label || j.kind || "");
      return `<li><span class="forge-job-status is-${status}">${status}${pos}</span><span class="forge-job-msg">${msg}</span></li>`;
    })
    .join("");
  if (active.length && !_forgeJobsPoll) {
    _forgeJobsPoll = setInterval(() => {
      refreshForgeJobs().catch(() => {});
    }, 900);
  }
  if (!active.length && _forgeJobsPoll) {
    clearInterval(_forgeJobsPoll);
    _forgeJobsPoll = null;
  }
}

export async function refreshForgeJobs() {
  const data = await api("/forge/jobs?limit=12");
  renderForgeJobs(data.jobs || []);
  return data.jobs || [];
}

export async function waitForForgeJob(jobId, { onUpdate } = {}) {
  const started = Date.now();
  while (Date.now() - started < 10 * 60 * 1000) {
    const job = await api(`/forge/jobs/${encodeURIComponent(jobId)}`);
    if (typeof onUpdate === "function") onUpdate(job);
    await refreshForgeJobs().catch(() => {});
    if (job.status === "done" || job.status === "failed") return job;
    await new Promise((r) => setTimeout(r, 450));
  }
  throw new Error("Forge job timed out — check Settings → Forge jobs.");
}

export async function enqueueForgeJob(path, body, { pendingLabel } = {}) {
  const job = await api(path, {
    method: "POST",
    body: body == null ? "{}" : JSON.stringify(body),
  });
  if (!job || !job.job_id) return { job: null, result: job };
  const pos = job.queue_position;
  const queuedMsg =
    pos && pos > 1
      ? `${pendingLabel || job.label || "Forge job"} queued (#${pos})`
      : `${pendingLabel || job.label || "Forge job"} started…`;
  setMsg(queuedMsg);
  await refreshForgeJobs().catch(() => {});
  const done = await waitForForgeJob(job.job_id, {
    onUpdate: (j) => {
      if (j.status === "queued" && j.queue_position > 1) {
        setMsg(`${j.label || pendingLabel || "Forge job"} queued (#${j.queue_position})`);
      } else if (j.status === "running") {
        setMsg(j.message || `${pendingLabel || "Forge job"} running…`);
      }
    },
  });
  if (done.status === "failed") {
    const err = new Error(done.error || done.message || "Forge job failed");
    err.job = done;
    throw err;
  }
  return { job: done, result: done.result || {} };
}
