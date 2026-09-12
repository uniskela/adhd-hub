import { state, $, setMsg, escapeHtml } from './state.js';
import { api } from './api.js';
import { confirmDialog, copyReference, formatWhen, safeHttpUrl, safeLink } from './dom.js';
import { loadAll } from './load.js';
import { chooseThread, wireNotes } from './now.js';

export function renderProjects(projects) {
    const list = $("project-list");
    const active = (projects || []).filter((p) => !p.archived);
    list.innerHTML = active
      .map((p) => {
        const open = (p.counts && p.counts.open) || 0;
        const isActive = state.projectFilter === p.slug ? "active" : "";
        return `<button type="button" class="proj ${isActive}" data-slug="${escapeHtml(p.slug)}" aria-pressed="${state.projectFilter === p.slug}">
          <div>${escapeHtml(p.slug === "unclassified" ? "Inbox" : p.title || p.slug)}</div>
          <div class="meta">${open} open ${open === 1 ? "step" : "steps"}</div>
        </button>`;
      })
      .join("");
    $("proj-all").classList.toggle("active", !state.projectFilter);
    $("proj-all").setAttribute("aria-pressed", String(!state.projectFilter));
    list.querySelectorAll(".proj").forEach((el) => {
      el.addEventListener("click", () => selectProject(el.dataset.slug || null).catch((e) => setMsg(e.message)));
    });
    renderArchivedProjects();
  }
export function renderArchivedProjects() {
    const wrap = $("archived-projects-wrap");
    const list = $("archived-project-list");
    const archived = state.archivedProjectsCache || [];
    if (!archived.length) {
      wrap.hidden = true;
      list.innerHTML = "";
      return;
    }
    wrap.hidden = false;
    list.innerHTML = archived
      .map((p) => {
        const open = (p.counts && p.counts.open) || 0;
        return `<button type="button" class="proj archived" data-slug="${escapeHtml(p.slug)}">
          <div>${escapeHtml(p.title || p.slug)}</div>
          <div class="meta">${open} open · archived</div>
        </button>`;
      })
      .join("");
    list.querySelectorAll(".proj").forEach((el) => {
      el.addEventListener("click", () => selectProject(el.dataset.slug || null).catch((e) => setMsg(e.message)));
    });
  }
export function fillProjectForm(p) {
    if (!p) return;
    $("edit-heading").textContent = p.unregistered
      ? `Register ${p.slug}`
      : `Edit ${p.title || p.slug}`;
    $("p_title").value = p.title || "";
    $("p_slug").value = p.slug || "";
    $("p_slug").readOnly = !p.unregistered;
    $("p_path").value = (p.workspace_paths && p.workspace_paths[0]) || "";
    $("p_desc").value = p.description || "";
    $("p_repo_url").value = p.repo_url || "";
    $("p_forge_owner").value = p.forge_owner || "";
    $("p_forge_repo").value = p.forge_repo || "";
    $("p_forge_wiki").value = p.forge_wiki_path || "";
    $("p_forge_project_id").value = p.forge_project_id || "";
    fillForgeConnectionSelect(p.forge_connection_profile_id || "");
    const archived = !!(p.archived || p.archived_at);
    $("btn-rename-project").hidden = !!p.unregistered;
    $("btn-delete-project").hidden = !!p.unregistered;
    $("btn-archive-project").hidden = !!p.unregistered || archived || p.slug === "unclassified";
    $("btn-restore-project").hidden = !!p.unregistered || !archived;
    const syncBtn = $("btn-sync-project");
    if (syncBtn) {
      syncBtn.hidden = !!p.unregistered || p.slug === "unclassified";
      syncBtn.disabled = false;
    }
  }

function fillForgeConnectionSelect(selectedId) {
    const sel = $("p_forge_connection_profile_id");
    if (!sel) return;
    const profiles = state.forgeConfigCache?.connection_profiles || [];
    sel.innerHTML =
      `<option value="">None (local-only)</option>` +
      profiles
        .map(
          (p) =>
            `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name || p.id)}</option>`
        )
        .join("");
    sel.value = selectedId || "";
  }

export async function suggestProjectForgeConnection() {
    const sel = $("p_forge_connection_profile_id");
    const repo = $("p_repo_url");
    if (!sel || !repo) return;
    if (sel.value) return; // never overwrite saved/current selection
    if (!state.forgeConfigCache) {
      try {
        state.forgeConfigCache = await api("/forge/config");
        fillForgeConnectionSelect("");
      } catch (_e) {
        return;
      }
    }
    const url = repo.value.trim();
    if (!url) return;
    const profiles = state.forgeConfigCache.connection_profiles || [];
    const host = (() => {
      try {
        return new URL(url).hostname.toLowerCase();
      } catch (_e) {
        return "";
      }
    })();
    if (!host) return;
    const matches = profiles.filter((p) => {
      if (p.provider === "github") {
        return host === "github.com" || host === "www.github.com";
      }
      if (p.provider === "gitea") {
        try {
          const web = (p.web_base_url || p.base_url || "").replace(/\/api\/v1\/?$/, "");
          return web && new URL(web).hostname.toLowerCase() === host;
        } catch (_e) {
          return false;
        }
      }
      return false;
    });
    if (matches.length === 1) {
      sel.value = matches[0].id;
    }
  }
export function renderProjectHeader(p) {
    const edit = $("btn-edit-project");
    const repo = $("btn-open-project-repo");
    if (!p) {
      edit.hidden = true;
      repo.hidden = true;
      repo.removeAttribute("href");
      return;
    }
    edit.hidden = false;
    edit.setAttribute("aria-label", p.unregistered ? "Register project" : `Edit ${p.title || p.slug}`);
    edit.title = p.unregistered ? "Register project" : "Edit project";
    const href = safeHttpUrl(p.repo_url);
    repo.hidden = !href;
    if (href) repo.href = href;
    else repo.removeAttribute("href");
  }
export function openProjectDialog(project) {
    if (!project) return;
    const open = async () => {
      if (!state.forgeConfigCache) {
        try {
          state.forgeConfigCache = await api("/forge/config");
        } catch (_e) {
          state.forgeConfigCache = { connection_profiles: [] };
        }
      }
      fillProjectForm(project);
      $("project-dialog").showModal();
      $("p_title").focus();
    };
    open().catch((e) => setMsg(String(e)));
  }
export function renderThreads(threads) {
    const query = $("thread-search").value.trim().toLowerCase();
    const total = threads.length;
    threads = threads.filter((thread) =>
      [thread.summary, thread.project_slug, thread.progress_snippet].some((value) =>
        String(value || "").toLowerCase().includes(query)
      )
    );
    $("thread-count").textContent = `${threads.length} of ${total} loaded threads${total === 100 ? " (latest 100)" : ""}`;
    const root = $("threads");
    if (!threads.length) {
      const message = query ? "No matches. Try a different search." :
        state.currentView === "done" ? "Finished work will appear here when you mark a thread done." :
        state.currentView === "stale" ? "Nothing waiting here. Return whenever you’re ready." :
        "No open threads here. Save progress from your connected assistant to pick it up later.";
      root.innerHTML = `<p class="hint">${message}</p>`;
      return;
    }
    const projectName = (slug) => {
      if (!slug || slug === "unclassified") return "Inbox";
      const project = (state.overviewCache?.projects || []).find((item) => item.slug === slug);
      return project?.title || slug;
    };
    const sourceName = (source) => ({
      web: "Quick capture",
      codex: "Codex",
      cursor: "Cursor",
      openclaw: "OpenClaw",
    }[String(source || "").toLowerCase()] || source || "Saved work");
    root.innerHTML = threads
      .map((t, index) => {
        const isChosen = t.id === state.chosenId;
        const statusLabel = t.status === "done" ? "Finished" : state.currentView === "stale" ? "Waiting" : "Ready";
        return `<article class="thread${isChosen ? " chosen" : ""}" aria-labelledby="thread-title-${index}">
          <div class="thread-topline">
            <span class="thread-number">${index + 1}</span>
            <span class="thread-project">${escapeHtml(projectName(t.project_slug))}</span>
            <span class="thread-status">${escapeHtml(statusLabel)}</span>
          </div>
          <h3 id="thread-title-${index}">${escapeHtml(t.summary)}</h3>
          <div class="thread-meta"><span>${escapeHtml(sourceName(t.source_tool || t.origin))}</span><span>Updated ${escapeHtml(formatWhen(t.updated_at))}</span></div>
          <details class="progress-details" data-notes="${escapeHtml(t.id)}"><summary>Notes &amp; context</summary><div class="notes-scroll"></div></details>
          <div class="actions thread-actions">
            ${
              t.status !== "done"
                ? `<button type="button" class="thread-primary compact" data-choose="${escapeHtml(t.id)}">${isChosen ? "Return to Now" : "Choose this step"}</button>`
                : ""
            }
            ${
              t.forge_issue_url
                ? `<a class="btn ghost compact" href="${safeLink(t.forge_issue_url)}" target="_blank" rel="noopener">Issue #${escapeHtml(t.forge_issue_number)}</a>`
                : ""
            }
            <button type="button" class="ghost compact thread-secondary" data-copy="${escapeHtml(t.id)}">Copy link</button>
          </div>
        </article>`;
      })
      .join("");
    wireNotes(root);
    root.querySelectorAll("[data-choose]").forEach((btn) =>
      btn.addEventListener("click", () => chooseThread(btn.dataset.choose))
    );
    root.querySelectorAll("[data-copy]").forEach((btn) =>
      btn.addEventListener("click", () => copyReference(btn.dataset.copy))
    );
  }
export async function loadThreads() {
    const request = ++state.threadsRequest;
    const params = new URLSearchParams();
    if (state.currentView === "stale") params.set("stale", "true");
    else params.set("status", state.currentView === "done" ? "done" : "open");
    if (state.projectFilter) params.set("project_slug", state.projectFilter);
    params.set("limit", "100");
    const threads = await api("/threads?" + params.toString());
    if (request !== state.threadsRequest) return;
    state.threadsCache = threads;
    renderThreads(state.threadsCache);
  }
export async function selectProject(slug) {
    const request = ++state.projectRequest;
    ++state.threadsRequest;
    state.projectFilter = slug || null;
    state.detailCache = null;
    state.threadsCache = [];

    renderProjects(state.overviewCache?.projects || []);
    renderProjectHeader(null);
    $("threads").textContent = "Loading your steps…";
    $("thread-count").textContent = "";
    $("focus-links").replaceChildren();
    if (!state.projectFilter) {
      $("work-title").textContent = "All projects";
      await loadThreads();
      return;
    }
    $("work-title").textContent = "Loading project…";
    try {
      const detail = await api("/projects/" + encodeURIComponent(state.projectFilter));
      if (request !== state.projectRequest) return;
      state.detailCache = detail;
      fillProjectForm(state.detailCache);
      $("work-title").textContent = state.detailCache.slug === "unclassified" ? "Inbox" : state.detailCache.title || state.detailCache.slug;
      renderProjectHeader(state.detailCache);
    } catch (e) {
      if (request !== state.projectRequest) return;
      $("work-title").textContent = "Project unavailable";
      setMsg("Could not load project: " + e.message);
    }
    if (request === state.projectRequest) await loadThreads();
  }
export function renderPending(actions) {
    const banner = $("pending-banner");
    const list = actions || [];
    if (!list.length) {
      banner.hidden = true;
      banner.innerHTML = "";
      return;
    }
    banner.hidden = false;
    banner.innerHTML = `
      <h2>Pending agent requests</h2>
      <p class="hint">Confirm or reject destructive project changes requested via MCP.</p>
      ${list
        .map((a) => {
          const p = a.payload || {};
          let summary = a.kind;
          if (a.kind === "delete_project") {
            summary = `Delete project <strong>${escapeHtml(p.slug)}</strong>`;
            if (p.delete_progress || p.delete_remote) {
              summary += ` <span class="meta">(${[
                p.delete_progress ? "local wiki" : null,
                p.delete_remote ? "remote file" : null,
              ]
                .filter(Boolean)
                .join(" + ")})</span>`;
            }
          } else if (a.kind === "rename_project") {
            summary = `Rename <strong>${escapeHtml(p.slug)}</strong> → <strong>${escapeHtml(p.new_slug)}</strong>`;
          }
          return `<div class="pending-item" data-id="${escapeHtml(a.id)}">
            <div>
              <div>${summary}</div>
              <div class="meta">${escapeHtml(a.source_tool || "agent")}${
            a.reason ? " · " + escapeHtml(a.reason) : ""
          }</div>
            </div>
            <div class="actions" style="margin:0">
              <button type="button" class="primary compact" data-approve="${escapeHtml(a.id)}">Approve</button>
              <button type="button" class="ghost compact" data-reject="${escapeHtml(a.id)}">Reject</button>
            </div>
          </div>`;
        })
        .join("")}`;
    banner.querySelectorAll("[data-approve]").forEach((btn) =>
      btn.addEventListener("click", () => approvePending(btn.dataset.approve))
    );
    banner.querySelectorAll("[data-reject]").forEach((btn) =>
      btn.addEventListener("click", () => rejectPending(btn.dataset.reject))
    );
  }
export async function approvePending(id) {
    try {
      await api(`/pending-actions/${encodeURIComponent(id)}/approve`, {
        method: "POST",
        body: "{}",
      });
      setMsg("Pending action approved.");
      await loadAll();
    } catch (e) {
      setMsg("Approve failed: " + e.message);
    }
  }
export async function rejectPending(id) {
    try {
      await api(`/pending-actions/${encodeURIComponent(id)}/reject`, {
        method: "POST",
        body: "{}",
      });
      setMsg("Pending action rejected.");
      await loadAll();
    } catch (e) {
      setMsg("Reject failed: " + e.message);
    }
  }
export async function archiveProject() {
    const slug = $("p_slug").value.trim();
    if (!slug) return;
    try {
      await api(`/projects/${encodeURIComponent(slug)}/archive`, { method: "POST", body: "{}" });
      $("project-dialog").close();
      setMsg("Project archived. Threads and notes are kept.");
      if (state.projectFilter === slug) state.projectFilter = null;
      await loadAll();
    } catch (e) {
      setMsg("Could not archive: " + e.message);
    }
  }
export async function restoreProject() {
    const slug = $("p_slug").value.trim();
    if (!slug) return;
    try {
      await api(`/projects/${encodeURIComponent(slug)}/restore`, { method: "POST", body: "{}" });
      $("project-dialog").close();
      setMsg("Project restored.");
      await loadAll();
      await selectProject(slug);
    } catch (e) {
      setMsg("Could not restore: " + e.message);
    }
  }
export async function syncProjectForge() {
    const slug = $("p_slug").value.trim();
    if (!slug) {
      setMsg("Save the project first, then Sync forge.");
      return;
    }
    const btn = $("btn-sync-project");
    if (btn) btn.disabled = true;
    setMsg(`Syncing forge for ${slug}…`);
    try {
      const out = await api(`/projects/${encodeURIComponent(slug)}/forge/sync`, {
        method: "POST",
        body: "{}",
      });
      if (out.skipped && out.reason === "no_forge_connection") {
        setMsg(
          out.hint || "Pick a Forge connection for this project, then Sync forge.",
          { variant: "warning" }
        );
        return;
      }
      const reconciled = Array.isArray(out.reconcile) ? out.reconcile.length : 0;
      const discovered = Array.isArray(out.discovery)
        ? out.discovery.reduce(
            (n, d) => n + ((d.imported && d.imported.length) || 0),
            0
          )
        : 0;
      setMsg(
        `Forge sync for ${slug}: ${reconciled} linked checked, ${discovered} imported.`
      );
      await loadAll();
    } catch (e) {
      setMsg("Project forge sync failed: " + e.message, { variant: "error" });
    } finally {
      if (btn) btn.disabled = false;
    }
  }
export async function saveProject() {
    const title = $("p_title").value.trim();
    if (!title) {
      setMsg("Title is required.");
      return;
    }
    const payload = {
      title,
      slug: $("p_slug").value.trim() || null,
      description: $("p_desc").value.trim() || null,
      workspace_paths: $("p_path").value.trim()
        ? [$("p_path").value.trim()]
        : [],
      repo_url: $("p_repo_url").value.trim() || null,
      forge_connection_profile_id: $("p_forge_connection_profile_id")?.value || null,
      forge_owner: $("p_forge_owner").value.trim() || null,
      forge_repo: $("p_forge_repo").value.trim() || null,
      forge_wiki_path: $("p_forge_wiki").value.trim() || null,
      forge_project_id: $("p_forge_project_id").value.trim() || null,
    };
    const saved = await api("/projects", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setMsg("Project saved.");
    state.projectFilter = saved.slug;
    $("project-dialog").close();
    await loadAll();
  }
export async function renameProject() {
    if (!state.projectFilter) return;
    const result = await confirmDialog({
      title: "Rename project slug",
      body: "Updates threads, local wiki folder, and forge path when sync is on.",
      extraHtml: `<label>New slug <input id="rename_slug" value="${escapeHtml(state.projectFilter)}" /></label>`,
    });
    if (!result.ok) return;
    const newSlug = (result.data.rename_slug || "").trim();
    if (!newSlug) return;
    try {
      const out = await api(
        `/projects/${encodeURIComponent(state.projectFilter)}/rename`,
        { method: "POST", body: JSON.stringify({ new_slug: newSlug }) }
      );
      state.projectFilter = out.project.slug;
      $("project-dialog").close();
      setMsg("Renamed to " + state.projectFilter);
      await loadAll();
    } catch (e) {
      setMsg("Rename failed: " + e.message);
    }
  }
export async function deleteProject() {
    if (!state.projectFilter) return;
    const result = await confirmDialog({
      title: "Delete project",
      body: "Removes the registry entry. Open threads keep their notes but lose the project link. Forge issues are never deleted.",
      extraHtml: `
        <label><input type="checkbox" id="del_progress" /> Also delete local PROGRESS.md</label>
        <label><input type="checkbox" id="del_remote" /> Also delete remote forge file</label>
      `,
    });
    if (!result.ok) return;
    const delete_progress = !!result.data.del_progress;
    const delete_remote = !!result.data.del_remote;
    const q = new URLSearchParams({
      delete_progress: String(delete_progress),
      delete_remote: String(delete_remote),
    });
    try {
      await api(
        `/projects/${encodeURIComponent(state.projectFilter)}?${q}`,
        { method: "DELETE" }
      );
      state.projectFilter = null;
      $("project-dialog").close();
      setMsg("Project deleted.");
      await loadAll();
    } catch (e) {
      setMsg("Delete failed: " + e.message);
    }
  }
