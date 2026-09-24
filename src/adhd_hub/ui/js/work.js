import { state, $, setMsg, escapeHtml } from './state.js';
import { api } from './api.js';
import { confirmDialog, copyReference, formatWhen, safeHttpUrl, safeLink } from './dom.js';
import { loadAll } from './load.js';
import { chooseThread, closeNotesReader, wireNotes } from './now.js';
import {
  IMPORT_POLICY_HINTS,
  IMPORT_POLICY_LABELS,
  attachTip,
  normalizeForgeOwnerRepo,
  parseOwnerRepoFromUrl,
} from './help.js';
import { enqueueForgeJob } from './forge-jobs.js';

export function renderProjects(projects) {
    const list = $("project-list");
    const active = (projects || []).filter((p) => !p.archived);
    populateTagFilter(active);
    const tagged = state.tagFilter
      ? active.filter((p) => (p.tags || []).includes(state.tagFilter))
      : active;
    const query = ($("project-search")?.value || "").trim().toLowerCase();
    const filtered = tagged.filter((p) => [p.title, p.slug, ...(p.tags || [])]
      .some((value) => String(value || "").toLowerCase().includes(query)));
    $("project-results").textContent = `${filtered.length} of ${active.length} projects`;
    list.innerHTML = filtered
      .map((p) => {
        const open = (p.counts && p.counts.open) || 0;
        const isActive = state.projectFilter === p.slug ? "active" : "";
        const tags = (p.tags || []).slice(0, 3).map((t) => escapeHtml(t)).join(", ");
        const tagLine = tags ? `<div class="proj-tags">${tags}</div>` : "";
        return `<button type="button" class="proj ${isActive}" data-slug="${escapeHtml(p.slug)}" aria-pressed="${state.projectFilter === p.slug}">
          <div>${escapeHtml(p.slug === "unclassified" ? "Inbox" : p.title || p.slug)}</div>
          <div class="meta">${open} open ${open === 1 ? "step" : "steps"}</div>
          ${tagLine}
        </button>`;
      })
      .join("");
    if (!filtered.length) list.innerHTML = '<p class="hint">No matching projects. Try another search or tag.</p>';
    $("proj-all").classList.toggle("active", !state.projectFilter);
    $("proj-all").setAttribute("aria-pressed", String(!state.projectFilter));
    list.querySelectorAll(".proj").forEach((el) => {
      el.addEventListener("click", () => selectProject(el.dataset.slug || null).catch((e) => setMsg(e.message)));
    });
    renderArchivedProjects();
  }

function populateTagFilter(projects) {
    const sel = $("tag-filter");
    if (!sel) return;
    const tags = new Set();
    for (const p of projects || []) {
      for (const t of p.tags || []) {
        if (t) tags.add(String(t));
      }
    }
    const sorted = [...tags].sort((a, b) => a.localeCompare(b));
    const previous = state.tagFilter || "";
    sel.innerHTML =
      `<option value="">All tags</option>` +
      sorted
        .map((t) => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`)
        .join("");
    if (previous && sorted.includes(previous)) {
      sel.value = previous;
      state.tagFilter = previous;
    } else {
      sel.value = "";
      state.tagFilter = null;
    }
  }

export function onProjectSearchChange() {
    renderProjects(state.overviewCache?.projects || []);
  }

export function onTagFilterChange() {
    const sel = $("tag-filter");
    state.tagFilter = (sel && sel.value) || null;
    const projects = state.overviewCache?.projects || [];
    renderProjects(projects);
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
    $("p_tags").value = (p.tags || []).join(", ");
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
    attachProjectForgeTips();
    maybePrefillForgeOwnerRepoFromUrl();
    updateEffectiveImportPolicy();
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
    updateEffectiveImportPolicy();
  }

function updateEffectiveImportPolicy() {
    const el = $("p_effective_import_policy");
    const sel = $("p_forge_connection_profile_id");
    if (!el || !sel) return;
    const id = sel.value || "";
    if (!id) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    const profiles = state.forgeConfigCache?.connection_profiles || [];
    const profile = profiles.find((p) => p.id === id);
    if (!profile) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    const policy = profile.issue_import_policy || "manual";
    const label = IMPORT_POLICY_LABELS[policy] || policy;
    const detail = IMPORT_POLICY_HINTS[policy] || "";
    el.hidden = false;
    el.textContent = `Import policy: ${label}. ${detail}`;
  }

function maybePrefillForgeOwnerRepoFromUrl() {
    const ownerEl = $("p_forge_owner");
    const repoEl = $("p_forge_repo");
    const urlEl = $("p_repo_url");
    if (!ownerEl || !repoEl || !urlEl) return;
    if ((ownerEl.value || "").trim() || (repoEl.value || "").trim()) return;
    const parsed = parseOwnerRepoFromUrl(urlEl.value.trim());
    if (!parsed) return;
    ownerEl.value = parsed.owner;
    repoEl.value = parsed.repo;
  }

function attachProjectForgeTips() {
    const tips = [
      [
        "p_forge_connection_profile_id",
        "Which forge profile’s credentials and import policy this project uses for issues/board sync.",
      ],
      [
        "p_forge_owner",
        "Forge owner/org name only (user123). Overrides the profile default for issues/board — not the Hub wiki memory repo.",
      ],
      [
        "p_forge_repo",
        "Repository name only (my-repo), never a full URL. Full URLs belong in Repository URL above.",
      ],
      [
        "p_forge_wiki",
        "Optional wiki path override for this project’s forge target. Blank = repo root. Hub PROGRESS.md still uses the Default profile.",
      ],
      ["p_forge_project_id", "Optional Gitea/Forgejo project board id for this project."],
      [
        "p_repo_url",
        "Full repository URL for display/open-repo. When Advanced forge owner/repo are blank, owner/repo are derived from this URL on blur.",
      ],
    ];
    for (const [id, tip] of tips) {
      const el = $(id);
      const label = el?.closest("label");
      if (label) attachTip(label, tip);
    }
    const sel = $("p_forge_connection_profile_id");
    if (sel && !sel.dataset.policyBound) {
      sel.dataset.policyBound = "1";
      sel.addEventListener("change", () => updateEffectiveImportPolicy());
    }
    const url = $("p_repo_url");
    if (url && !url.dataset.prefillBound) {
      url.dataset.prefillBound = "1";
      url.addEventListener("blur", () => maybePrefillForgeOwnerRepoFromUrl());
      url.addEventListener("change", () => maybePrefillForgeOwnerRepoFromUrl());
    }
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

function sourceValue(value) {
    if (Array.isArray(value)) return value.join("\n");
    return value == null ? "—" : String(value);
  }

export async function openSourceRefresh(threadId) {
    const dialog = $("source-refresh-dialog");
    const body = $("source-refresh-body");
    const apply = $("btn-apply-source-refresh");
    body.textContent = "Checking the linked issue…";
    apply.disabled = true;
    dialog.showModal();
    let preview;
    try {
      preview = await api(`/threads/${encodeURIComponent(threadId)}/source-refresh`);
    } catch (error) {
      body.textContent = `Source issue could not be loaded: ${error.message}`;
      return;
    }
    if (preview.error || preview.source_state === "unavailable") {
      body.textContent = "The source issue is unavailable, deleted, or this connection cannot access it. No Hub data was changed.";
      return;
    }
    const changes = Object.entries(preview.changes || {});
    const conflicts = Object.entries(preview.conflicts || {});
    const rows = [];
    const lastImported = preview.last_imported_at
      ? formatWhen(preview.last_imported_at)
      : "Never (legacy import)";
    rows.push(`<p class="hint">Last imported ${escapeHtml(lastImported)} · Source is ${escapeHtml(preview.source_state || "available")} · <a href="${safeLink(preview.source_issue_url)}" target="_blank" rel="noopener">Open source issue</a></p>`);
    changes.forEach(([field, value]) => {
      rows.push(`<div class="source-change"><strong>${escapeHtml(field.replaceAll("_", " "))}</strong><pre>${escapeHtml(sourceValue(value))}</pre></div>`);
    });
    conflicts.forEach(([field, values]) => {
      rows.push(`<div class="source-conflict">
        <strong>${escapeHtml(field.replaceAll("_", " "))} — changed in both places</strong>
        <p><small>Previously imported</small><br>${escapeHtml(sourceValue(values.previous))}</p>
        <p><small>Current Hub</small><br>${escapeHtml(sourceValue(values.hub))}</p>
        <p><small>Current forge</small><br>${escapeHtml(sourceValue(values.forge))}</p>
        <label>Resolution
          <select data-source-resolution="${escapeHtml(field)}">
            <option value="forge">Use forge version</option>
            <option value="hub">Keep Hub version</option>
            <option value="manual">Merge/edit manually</option>
          </select>
        </label>
        <textarea data-source-manual="${escapeHtml(field)}" rows="3" aria-label="Manual merged value">${escapeHtml(sourceValue(values.hub) === "—" ? "" : sourceValue(values.hub))}</textarea>
      </div>`);
    });
    if (!changes.length && !conflicts.length) {
      rows.push("<p>No source-controlled fields changed.</p>");
    }
    body.innerHTML = rows.join("");
    apply.disabled = !changes.length && !conflicts.length;
    apply.onclick = async () => {
      const resolutions = {};
      const manual_values = {};
      body.querySelectorAll("[data-source-resolution]").forEach((select) => {
        const field = select.dataset.sourceResolution;
        resolutions[field] = select.value;
        if (select.value === "manual") {
          const raw = body.querySelector(`[data-source-manual="${CSS.escape(field)}"]`).value;
          manual_values[field] = field === "next_steps"
            ? raw.split("\n").map((item) => item.trim()).filter(Boolean).slice(0, 3)
            : raw.trim() || null;
        }
      });
      apply.disabled = true;
      try {
        const result = await api(`/threads/${encodeURIComponent(threadId)}/source-refresh`, {
          method: "POST",
          body: JSON.stringify({ resolutions, manual_values }),
        });
        if (result.needs_review) {
          setMsg("Refresh still has unresolved conflicts.", { variant: "warning" });
          return;
        }
        dialog.close();
        setMsg(`Refreshed from source (${(result.updated_fields || []).length} fields updated).`);
        await loadAll();
      } catch (error) {
        setMsg(`Source refresh failed: ${error.message}`, { variant: "error" });
      } finally {
        apply.disabled = false;
      }
    };
  }
export function renderThreads(threads) {
    closeNotesReader({ restoreFocus: false });
    const query = $("thread-search").value.trim().toLowerCase();
    const total = threads.length;
    threads = threads.filter((thread) =>
      [thread.summary, thread.scan_line, thread.project_slug, thread.progress_snippet].some((value) =>
        String(value || "").toLowerCase().includes(query)
      )
    );
    $("thread-count").textContent = query
      ? `${threads.length} ${threads.length === 1 ? "match" : "matches"} out of ${total} ${total === 1 ? "step" : "steps"}${total === 100 ? " · searching the latest 100" : ""}`
      : `${total} ${total === 1 ? "step" : "steps"}${total === 100 ? " · latest 100" : ""}`;
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
        const statusLabel = isChosen ? "In focus" : t.status === "done" ? "Finished" : state.currentView === "stale" ? "Pick up later" : "";
        const sourceState = ({
          current: "Source current",
          refresh_available: "Refresh available",
          conflicted: "Source conflict",
          unavailable: "Source unavailable",
          untracked: "Source linked",
        })[t.source_sync_state] || "";
        const sourceNeedsAttention = ["refresh_available", "conflicted", "unavailable"].includes(t.source_sync_state);
        const sourceSync = sourceState
          ? `<span class="source-sync source-sync-${escapeHtml(t.source_sync_state)}">${escapeHtml(sourceState)}${(t.display_source_at || t.source_imported_at) ? ` · ${escapeHtml(formatWhen(t.display_source_at || t.source_imported_at))}` : ""}</span>`
          : "";
        return `<article class="thread${isChosen ? " chosen" : ""}" aria-labelledby="thread-title-${index}">
          <div class="thread-topline">
            <span class="thread-number">${index + 1}</span>
            <span class="thread-project">${escapeHtml(projectName(t.project_slug))}</span>
            ${statusLabel ? `<span class="thread-status">${escapeHtml(statusLabel)}</span>` : ""}
          </div>
          <div class="thread-main">
            <h3 id="thread-title-${index}">${escapeHtml(t.summary)}</h3>
            ${t.scan_line ? `<p class="thread-scan">${escapeHtml(t.scan_line)}</p>` : ""}
          </div>
          <div class="thread-meta"><span>Updated ${escapeHtml(formatWhen(t.display_updated_at || t.updated_at))}</span></div>
          ${sourceNeedsAttention ? sourceSync : ""}
          <div class="actions thread-actions">
            ${
              t.status !== "done"
                ? `<button type="button" class="thread-primary compact" data-choose="${escapeHtml(t.id)}">${isChosen ? "Return to focus" : "Focus on this"}</button>`
                : ""
            }
            <button type="button" class="notes-trigger" data-notes="${escapeHtml(t.id)}" aria-controls="notes-reader" aria-expanded="false"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5"/></svg><span>Read notes</span></button>
          </div>
          <details class="thread-utility">
            <summary aria-label="Actions for ${escapeHtml(t.summary)}">⋯ Actions</summary>
            <div class="thread-utility-panel">
            <p class="hint">${escapeHtml(sourceName(t.source_tool || t.origin))}</p>
            <div class="actions thread-utility-actions">
            ${!sourceNeedsAttention ? sourceSync : ""}
            ${
              t.forge_issue_url
                ? `<a class="btn ghost compact" href="${safeLink(t.forge_issue_url)}" target="_blank" rel="noopener">Open issue #${escapeHtml(t.forge_issue_number)}</a>`
                : ""
            }
            ${t.source_issue_url ? `<button type="button" class="ghost compact" data-refresh-source="${escapeHtml(t.id)}">Refresh from source issue</button>` : ""}
            <button type="button" class="ghost compact" data-rewrite-scan="${escapeHtml(t.id)}">Rewrite scan line</button>
            <button type="button" class="ghost compact thread-secondary" data-copy="${escapeHtml(t.id)}">Copy link</button>
            </div>
            </div>
          </details>
        </article>`;
      })
      .join("");
    root.querySelectorAll(".thread-utility").forEach((panel) => {
      panel.addEventListener("toggle", () => {
        if (panel.open) root.querySelectorAll(".thread-utility[open]").forEach((other) => {
          if (other !== panel) other.open = false;
        });
      });
      panel.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          panel.open = false;
          panel.querySelector("summary").focus();
          event.stopPropagation();
        }
      });
      panel.addEventListener("focusout", () => {
        requestAnimationFrame(() => { if (!panel.contains(document.activeElement)) panel.open = false; });
      });
    });
    wireNotes(root);
    root.querySelectorAll("[data-choose]").forEach((btn) =>
      btn.addEventListener("click", () => chooseThread(btn.dataset.choose))
    );
    root.querySelectorAll("[data-copy]").forEach((btn) =>
      btn.addEventListener("click", () => copyReference(btn.dataset.copy))
    );
    root.querySelectorAll("[data-refresh-source]").forEach((btn) =>
      btn.addEventListener("click", () => openSourceRefresh(btn.dataset.refreshSource))
    );
    root.querySelectorAll("[data-rewrite-scan]").forEach((btn) =>
      btn.addEventListener("click", () => rewriteScanLine(btn.dataset.rewriteScan))
    );
  }

export async function rewriteScanLine(threadId) {
    if (!threadId) return;
    const btn = document.querySelector(`[data-rewrite-scan="${CSS.escape(threadId)}"]`);
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Rewriting…";
    }
    try {
      const out = await api(`/threads/${encodeURIComponent(threadId)}/scan-line`, {
        method: "POST",
        body: "{}",
      });
      const updated = out.thread;
      if (updated && Array.isArray(state.threadsCache)) {
        state.threadsCache = state.threadsCache.map((t) =>
          t.id === threadId ? { ...t, ...updated } : t
        );
        renderThreads(state.threadsCache);
      }
      setMsg(out.message || "Scan line updated.");
    } catch (e) {
      setMsg(e.message || "Could not rewrite scan line.");
    } finally {
      const again = document.querySelector(`[data-rewrite-scan="${CSS.escape(threadId)}"]`);
      if (again) {
        again.disabled = false;
        again.textContent = "Rewrite scan line";
      }
    }
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
    try {
      const { result: out } = await enqueueForgeJob(
        `/projects/${encodeURIComponent(slug)}/forge/sync`,
        {},
        { pendingLabel: `Sync forge (${slug})` }
      );
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
      const warnings = Array.isArray(out.warnings) ? out.warnings : [];
      const sel = $("p_forge_connection_profile_id");
      const profiles = state.forgeConfigCache?.connection_profiles || [];
      const profile = profiles.find((p) => p.id === (sel?.value || ""));
      const policy = profile?.issue_import_policy || "manual";
      let extra = "";
      if (discovered === 0 && policy === "manual") {
        extra =
          " (import policy: manual — Sync will not import new issues; change the policy on the forge profile to import)";
      } else if (discovered === 0 && profile) {
        extra = ` (import policy: ${IMPORT_POLICY_LABELS[policy] || policy})`;
      }
      if (warnings.length) {
        extra += ` — ${warnings[0]}`;
      }
      setMsg(
        `Forge sync for ${slug}: ${reconciled} linked checked, ${discovered} imported.${extra}`,
        { variant: warnings.length ? "warning" : undefined }
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
    maybePrefillForgeOwnerRepoFromUrl();
    const rawOwner = $("p_forge_owner").value.trim();
    const rawRepo = $("p_forge_repo").value.trim();
    const { owner, repo } = normalizeForgeOwnerRepo(rawOwner, rawRepo);
    if ($("p_forge_owner")) $("p_forge_owner").value = owner;
    if ($("p_forge_repo")) $("p_forge_repo").value = repo;
    const payload = {
      title,
      slug: $("p_slug").value.trim() || null,
      description: $("p_desc").value.trim() || null,
      workspace_paths: $("p_path").value.trim()
        ? [$("p_path").value.trim()]
        : [],
      tags: ($("p_tags").value || "")
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      repo_url: $("p_repo_url").value.trim() || null,
      forge_connection_profile_id: $("p_forge_connection_profile_id")?.value || null,
      forge_owner: owner || null,
      forge_repo: repo || null,
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

export async function openOrganiseDialog() {
    const dialog = $("organise-dialog");
    const list = $("organise-list");
    const empty = $("organise-empty");
    list.innerHTML = `<p class="hint">Loading suggestions…</p>`;
    empty.hidden = true;
    empty.textContent = "No new tag suggestions right now. You can still edit tags in project settings.";
    dialog.showModal();
    try {
      const data = await api("/projects/organise/suggestions");
      const suggestions = data.suggestions || [];
      if (!suggestions.length) {
        list.innerHTML = "";
        empty.hidden = false;
        return;
      }
      empty.hidden = true;
      list.innerHTML = suggestions
        .map((item, index) => {
          const suggested = (item.suggested_tags || []).join(", ");
          const current = (item.current_tags || []).join(", ") || "No tags yet";
          const reason = (item.reasons || []).join("; ");
          return `<div class="organise-row">
            <input type="checkbox" data-organise-index="${index}" id="organise-select-${index}" aria-label="Add suggested tags to ${escapeHtml(item.title || item.slug)}" checked />
            <span class="organise-copy">
              <label for="organise-select-${index}" class="organise-project-name">${escapeHtml(item.title || item.slug)}</label>
              <span class="meta">Current tags: ${escapeHtml(current)}</span>
              ${reason ? `<span class="meta organise-reason">Why these tags: ${escapeHtml(reason)}</span>` : ""}
              <label for="organise-tags-${index}" class="organise-tags-label">Suggested tags to add</label>
              <input type="text" id="organise-tags-${index}" data-organise-tags="${index}" value="${escapeHtml(suggested)}" />
              <input type="hidden" data-organise-slug="${index}" value="${escapeHtml(item.slug)}" />
            </span>
          </div>`;
        })
        .join("");
    } catch (e) {
      list.innerHTML = "";
      empty.hidden = false;
      empty.textContent = "Could not load suggestions: " + e.message;
    }
  }

export async function applyOrganiseSelection() {
    const list = $("organise-list");
    const items = [];
    list.querySelectorAll("[data-organise-index]").forEach((box) => {
      if (!box.checked) return;
      const index = box.dataset.organiseIndex;
      const slug = list.querySelector(`[data-organise-slug="${index}"]`)?.value;
      const raw = list.querySelector(`[data-organise-tags="${index}"]`)?.value || "";
      const tags = raw
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      if (slug && tags.length) items.push({ slug, tags });
    });
    if (!items.length) {
      setMsg("Select at least one suggestion with tags to apply.");
      return;
    }
    try {
      const out = await api("/projects/organise/apply", {
        method: "POST",
        body: JSON.stringify({ items }),
      });
      $("organise-dialog").close();
      const n = (out.applied || []).length;
      const skipped = (out.skipped || []).length;
      setMsg((n ? `Applied tags to ${n} project${n === 1 ? "" : "s"}.` : "Nothing applied.") +
        (skipped ? ` ${skipped} skipped; reopen Organise to review current projects and tag limits.` : ""));
      await loadAll();
    } catch (e) {
      setMsg("Could not apply organisation: " + e.message);
    }
  }
