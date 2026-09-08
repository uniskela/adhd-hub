(() => {
  const tokenKey = "adhd_hub_token";
  const tzKey = "adhd_hub_timezone";
  let currentView = "open";
  let projectFilter = null;
  let overviewCache = null;
  let detailCache = null;
  let currentTz =
    localStorage.getItem(tzKey) ||
    Intl.DateTimeFormat().resolvedOptions().timeZone ||
    "UTC";

  const $ = (id) => document.getElementById(id);
  const setMsg = (t) => {
    $("msg").textContent = t || "";
  };
  const escapeHtml = (s) =>
    String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");

  function token() {
    return localStorage.getItem(tokenKey) || $("token").value || "";
  }

  function browserTz() {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  }

  function fillTimezoneSelect(selected) {
    const sel = $("timezone");
    const local = browserTz();
    const extras = [
      "UTC",
      "Australia/Sydney",
      "Australia/Melbourne",
      "Australia/Brisbane",
      "Pacific/Auckland",
      "Asia/Tokyo",
      "Europe/London",
      "America/New_York",
      "America/Los_Angeles",
    ];
    const zones = Array.from(new Set([local, selected, ...extras].filter(Boolean)));
    sel.innerHTML = zones
      .map((z) => {
        const label = z === local ? `${z} (local)` : z;
        return `<option value="${escapeHtml(z)}">${escapeHtml(label)}</option>`;
      })
      .join("");
    sel.value = selected || local;
    currentTz = sel.value;
  }

  function formatWhen(iso) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return String(iso).slice(0, 16);
      return new Intl.DateTimeFormat(undefined, {
        timeZone: currentTz || "UTC",
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(d);
    } catch (_e) {
      return String(iso).slice(0, 16);
    }
  }

  async function api(path, opts = {}) {
    const headers = Object.assign(
      { "Content-Type": "application/json" },
      opts.headers || {}
    );
    const t = token();
    if (t) headers.Authorization = "Bearer " + t;
    const res = await fetch("/api" + path, Object.assign({}, opts, { headers }));
    if (res.status === 401) {
      const err = new Error("Unauthorized");
      err.status = 401;
      throw err;
    }
    if (!res.ok) throw new Error(await res.text());
    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res;
  }

  function showLogin(message) {
    $("app-shell").hidden = true;
    $("login-gate").hidden = false;
    $("login-error").textContent = message || "";
    $("login-token").value = "";
    $("login-token").focus();
  }

  function showApp() {
    $("login-gate").hidden = true;
    $("app-shell").hidden = false;
    $("token").value = localStorage.getItem(tokenKey) || "";
  }

  async function tryAuth() {
    try {
      await api("/overview");
      showApp();
      return true;
    } catch (e) {
      if (e.status === 401) {
        localStorage.removeItem(tokenKey);
        showLogin(
          token()
            ? "Invalid token. Check ADHD_HUB_AUTH_TOKEN in .env."
            : "Enter the hub bearer token from ADHD_HUB_AUTH_TOKEN."
        );
        return false;
      }
      // Network / other — still show app so user can see error
      showApp();
      setMsg(String(e.message || e));
      return true;
    }
  }

  async function handleLogin(ev) {
    ev.preventDefault();
    const value = $("login-token").value.trim();
    if (!value) return;
    localStorage.setItem(tokenKey, value);
    $("token").value = value;
    $("login-error").textContent = "Checking…";
    const ok = await tryAuth();
    if (ok) {
      await loadAll();
    }
  }

  function logout() {
    localStorage.removeItem(tokenKey);
    showLogin("");
  }

  async function loadPrefs() {
    try {
      const p = await api("/prefs");
      if (p.timezone) {
        currentTz = p.timezone;
        localStorage.setItem(tzKey, currentTz);
      }
    } catch (_e) {
      /* keep local */
    }
    if (!localStorage.getItem(tzKey + "_initialized")) {
      const local = browserTz();
      if (!currentTz || currentTz === "UTC") currentTz = local;
      localStorage.setItem(tzKey, currentTz);
      localStorage.setItem(tzKey + "_initialized", "1");
      try {
        await api("/prefs", {
          method: "PUT",
          body: JSON.stringify({ timezone: currentTz }),
        });
      } catch (_e2) {
        /* optional */
      }
    }
    fillTimezoneSelect(currentTz);
  }

  function renderStats(o) {
    $("stats").innerHTML = [
      ["Open", o.open],
      ["Stale", o.stale],
      ["Done today", o.done_today],
      ["Streak", o.day_streak],
    ]
      .map(
        ([k, v]) =>
          `<span class="stat"><strong>${escapeHtml(v)}</strong> ${escapeHtml(k)}</span>`
      )
      .join("");
    const series = o.added_vs_finished || [];
    const wrap = $("chart-wrap");
    const chart = $("chart");
    if (!series.length) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    const max = Math.max(1, ...series.map((d) => Math.max(d.added || 0, d.finished || 0)));
    chart.innerHTML = series
      .map((d) => {
        const a = Math.round(((d.added || 0) / max) * 100);
        const f = Math.round(((d.finished || 0) / max) * 100);
        return `<div class="col" title="${escapeHtml(d.date)}: +${d.added || 0} / ✓${d.finished || 0}">
          <div class="bar add" style="height:${a}%"></div>
          <div class="bar done" style="height:${f}%"></div>
        </div>`;
      })
      .join("");
  }

  function renderProjects(projects) {
    const list = $("project-list");
    list.innerHTML = (projects || [])
      .map((p) => {
        const open = (p.counts && p.counts.open) || 0;
        const active = projectFilter === p.slug ? "active" : "";
        return `<button type="button" class="proj ${active}" data-slug="${escapeHtml(p.slug)}">
          <div>${escapeHtml(p.title || p.slug)}</div>
          <div class="meta">${open} open · ${escapeHtml(p.slug)}</div>
        </button>`;
      })
      .join("");
    $("proj-all").classList.toggle("active", !projectFilter);
    list.querySelectorAll(".proj").forEach((el) => {
      el.addEventListener("click", () => selectProject(el.dataset.slug || null));
    });
  }

  function fillProjectForm(p) {
    $("project-edit").hidden = !p;
    if (!p) return;
    $("edit-heading").textContent = p.unregistered
      ? `Register ${p.slug}`
      : `Edit ${p.title || p.slug}`;
    $("p_title").value = p.title || "";
    $("p_slug").value = p.slug || "";
    $("p_slug").readOnly = !p.unregistered;
    $("p_path").value = (p.workspace_paths && p.workspace_paths[0]) || "";
    $("p_desc").value = p.description || "";
    $("p_forge_owner").value = p.forge_owner || "";
    $("p_forge_repo").value = p.forge_repo || "";
    $("p_forge_wiki").value = p.forge_wiki_path || "";
    $("p_forge_project_id").value = p.forge_project_id || "";
  }

  function renderFocus(detail) {
    const title = detail
      ? detail.title || detail.slug
      : "All open work";
    $("focus-title").textContent = title;
    $("focus-eyebrow").textContent = detail ? "Project focus" : "Overview";
    const links = $("focus-links");
    links.innerHTML = "";
    if (detail && detail.forge && detail.forge.folder_url) {
      links.innerHTML = `<a class="btn ghost" href="${escapeHtml(detail.forge.folder_url)}" target="_blank" rel="noopener">Folder on forge</a>`;
    }
    const card = $("next-card");
    const next = detail && detail.next_up;
    if (!next) {
      card.className = "next-card empty";
      card.innerHTML = projectFilter
        ? "Nothing open in this project. Nice."
        : "No open threads. Capture the next unfinished thing from an agent, or pick a project.";
      return;
    }
    card.className = "next-card has-item";
    const snippet = (detail.progress || "").slice(0, 500);
    card.innerHTML = `
      <p class="eyebrow">Next up</p>
      <h3>${escapeHtml(next.summary)}</h3>
      <div class="meta">updated ${escapeHtml(formatWhen(next.updated_at))}</div>
      ${snippet ? `<pre class="snippet">${escapeHtml(snippet)}</pre>` : ""}
      <div class="next-actions">
        <button type="button" class="primary" data-done="${escapeHtml(next.id)}">Mark done</button>
        ${
          next.forge_issue_url
            ? `<a class="btn ghost" href="${escapeHtml(next.forge_issue_url)}" target="_blank" rel="noopener">Open issue #${escapeHtml(next.forge_issue_number)}</a>`
            : ""
        }
        <button type="button" class="ghost" data-copy="${escapeHtml(next.id)}">Copy id</button>
      </div>`;
    card.querySelector("[data-done]")?.addEventListener("click", () =>
      markDone(next.id)
    );
    card.querySelector("[data-copy]")?.addEventListener("click", async () => {
      await navigator.clipboard.writeText(next.id);
      setMsg("Thread id copied.");
    });
  }

  function renderThreads(threads) {
    const root = $("threads");
    if (!threads.length) {
      root.innerHTML = `<p class="hint">Nothing here.</p>`;
      return;
    }
    root.innerHTML = threads
      .map((t) => {
        const snip = (t.progress_snippet || "").slice(0, 280);
        return `<article class="thread">
          <h3>${escapeHtml(t.summary)}</h3>
          <div class="meta">${escapeHtml(t.project_slug || "")} · ${escapeHtml(
          t.source_tool || t.origin || ""
        )} · updated ${escapeHtml(formatWhen(t.updated_at))}</div>
          ${snip ? `<pre class="snippet">${escapeHtml(snip)}</pre>` : ""}
          <div class="actions">
            ${
              t.status !== "done"
                ? `<button type="button" class="primary compact" data-done="${escapeHtml(t.id)}">Mark done</button>`
                : ""
            }
            ${
              t.forge_issue_url
                ? `<a class="btn ghost compact" href="${escapeHtml(t.forge_issue_url)}" target="_blank" rel="noopener">Issue #${escapeHtml(t.forge_issue_number)}</a>`
                : ""
            }
            <button type="button" class="ghost compact" data-copy="${escapeHtml(t.id)}">Copy id</button>
          </div>
        </article>`;
      })
      .join("");
    root.querySelectorAll("[data-done]").forEach((btn) =>
      btn.addEventListener("click", () => markDone(btn.dataset.done))
    );
    root.querySelectorAll("[data-copy]").forEach((btn) =>
      btn.addEventListener("click", async () => {
        await navigator.clipboard.writeText(btn.dataset.copy);
        setMsg("Thread id copied.");
      })
    );
  }

  async function markDone(id) {
    await api("/threads/mark-done", {
      method: "POST",
      body: JSON.stringify({ id, note: "Marked done from /ui" }),
    });
    setMsg("Marked done.");
    await loadAll();
  }

  async function loadThreads() {
    const params = new URLSearchParams();
    if (currentView === "stale") params.set("stale", "true");
    else params.set("status", currentView === "done" ? "done" : "open");
    if (projectFilter) params.set("project_slug", projectFilter);
    params.set("limit", "100");
    const threads = await api("/threads?" + params.toString());
    renderThreads(threads);
  }

  async function selectProject(slug) {
    projectFilter = slug || null;
    renderProjects(overviewCache?.projects || []);
    if (!projectFilter) {
      detailCache = null;
      fillProjectForm(null);
      renderFocus(null);
      await loadThreads();
      return;
    }
    try {
      detailCache = await api("/projects/" + encodeURIComponent(projectFilter));
      fillProjectForm(detailCache);
      renderFocus(detailCache);
    } catch (e) {
      setMsg("Could not load project: " + e.message);
    }
    await loadThreads();
  }

  function renderPending(actions) {
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

  async function approvePending(id) {
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

  async function rejectPending(id) {
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

  function renderImportBanner(preview) {
    const el = $("import-banner");
    if (!preview || preview.skipped || !preview.importable_count) {
      el.hidden = true;
      el.innerHTML = "";
      return;
    }
    const names = (preview.candidates || [])
      .filter((c) => c.status === "new" || c.status === "local_wiki_only")
      .filter((c) => c.has_remote_progress)
      .map((c) => c.slug)
      .slice(0, 8);
    const extra =
      preview.importable_count > names.length
        ? ` (+${preview.importable_count - names.length} more)`
        : "";
    el.hidden = false;
    el.innerHTML = `
      <div>
        <strong>Forge has ${preview.importable_count} project(s) not in this hub</strong>
        <p class="hint">${escapeHtml(names.join(", "))}${escapeHtml(extra)}. Import registers them and pulls PROGRESS.md.</p>
      </div>
      <div class="actions">
        <button type="button" class="primary compact" id="btn-import-forge">Import</button>
        <button type="button" class="ghost compact" id="btn-dismiss-import">Dismiss</button>
      </div>
    `;
    $("btn-import-forge").onclick = () =>
      runForgeImport().catch((e) => setMsg(String(e)));
    $("btn-dismiss-import").onclick = () => {
      el.hidden = true;
      el.innerHTML = "";
    };
  }

  async function scanForgeImport() {
    const preview = await api("/forge/import/preview");
    renderImportBanner(preview);
    if (preview.skipped) {
      setMsg("Forge wiki sync is off or not configured.");
    } else if (!preview.importable_count) {
      setMsg("No new forge projects to import.");
    } else {
      setMsg(`Found ${preview.importable_count} project(s) to import.`);
    }
    return preview;
  }

  async function runForgeImport() {
    const result = await confirmDialog({
      title: "Import from forge",
      body: "Register missing projects and pull PROGRESS.md into this hub.",
      extraHtml: `<label><input type="checkbox" id="overwrite_local" /> Overwrite local PROGRESS.md when it already exists</label>`,
    });
    if (!result.ok) return;
    setMsg("Importing from forge…");
    const out = await api("/forge/import", {
      method: "POST",
      body: JSON.stringify({
        overwrite_local: !!result.data.overwrite_local,
      }),
    });
    const n = (out.imported || []).length;
    setMsg(`Imported ${n} project(s) from forge.`);
    $("import-banner").hidden = true;
    await loadAll();
  }

  async function exportBackup() {
    const t = token();
    const res = await fetch("/api/admin/export", {
      headers: t ? { Authorization: "Bearer " + t } : {},
    });
    if (res.status === 401) {
      logout();
      return;
    }
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "adhd-hub-backup.zip";
    a.click();
    URL.revokeObjectURL(url);
    setMsg("Backup downloaded.");
  }

  async function importBackup(file) {
    const result = await confirmDialog({
      title: "Restore backup",
      body: "This replaces SQLite, wiki, and forge/prefs on this instance. Prefer stopping the container for large restores. Continue?",
    });
    if (!result.ok) return;
    const t = token();
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/admin/import?replace=true", {
      method: "POST",
      headers: t ? { Authorization: "Bearer " + t } : {},
      body: fd,
    });
    if (res.status === 401) {
      logout();
      return;
    }
    if (!res.ok) throw new Error(await res.text());
    const out = await res.json();
    setMsg("Restored: " + (out.restored || []).join(", "));
    await loadAll();
  }

  async function loadOverview() {
    overviewCache = await api("/overview");
    renderStats(overviewCache);
    renderProjects(overviewCache.projects || []);
    renderPending(overviewCache.pending_actions || []);
  }

  async function loadForge() {
    try {
      const c = await api("/forge/config");
      $("provider").value = c.provider || "none";
      $("base_url").value = c.base_url || "";
      $("owner").value = c.owner || "";
      $("repo").value = c.repo || "";
      $("forge_token").value = c.token || "";
      $("wiki_path").value = c.wiki_path ?? "";
      $("wiki_branch").value = c.wiki_branch || "main";
      $("hub_public_url").value = c.hub_public_url || "";
      $("project_id").value = c.project_id || "";
      $("wiki_enabled").checked = !!c.wiki_enabled;
      $("board_enabled").checked = !!c.board_enabled;
      $("primary_memory_repo").checked = !!c.primary_memory_repo;
    } catch (_e) {
      /* forge optional */
    }
  }

  async function saveProject() {
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
    projectFilter = saved.slug;
    await loadAll();
  }

  function confirmDialog({ title, body, extraHtml }) {
    return new Promise((resolve) => {
      $("confirm-title").textContent = title;
      $("confirm-body").textContent = body;
      $("confirm-extra").innerHTML = extraHtml || "";
      const dlg = $("confirm-dialog");
      const yes = $("confirm-yes");
      const capture = () => {
        const data = {};
        $("confirm-extra")
          .querySelectorAll("input, select, textarea")
          .forEach((el) => {
            if (el.type === "checkbox") data[el.id] = el.checked;
            else data[el.id] = el.value;
          });
        dlg._captured = data;
      };
      yes.addEventListener("click", capture, { once: true });
      const onClose = () => {
        dlg.removeEventListener("close", onClose);
        resolve({
          ok: dlg.returnValue === "yes",
          data: dlg._captured || {},
        });
      };
      dlg.addEventListener("close", onClose);
      dlg.showModal();
    });
  }

  async function renameProject() {
    if (!projectFilter) return;
    const result = await confirmDialog({
      title: "Rename project slug",
      body: "Updates threads, local wiki folder, and forge path when sync is on.",
      extraHtml: `<label>New slug <input id="rename_slug" value="${escapeHtml(projectFilter)}" /></label>`,
    });
    if (!result.ok) return;
    const newSlug = (result.data.rename_slug || "").trim();
    if (!newSlug) return;
    try {
      const out = await api(
        `/projects/${encodeURIComponent(projectFilter)}/rename`,
        { method: "POST", body: JSON.stringify({ new_slug: newSlug }) }
      );
      projectFilter = out.project.slug;
      setMsg("Renamed to " + projectFilter);
      await loadAll();
    } catch (e) {
      setMsg("Rename failed: " + e.message);
    }
  }

  async function deleteProject() {
    if (!projectFilter) return;
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
        `/projects/${encodeURIComponent(projectFilter)}?${q}`,
        { method: "DELETE" }
      );
      projectFilter = null;
      setMsg("Project deleted.");
      await loadAll();
    } catch (e) {
      setMsg("Delete failed: " + e.message);
    }
  }

  async function saveSettings() {
    localStorage.setItem(tokenKey, $("token").value.trim());
    const tz = $("timezone").value || browserTz();
    currentTz = tz;
    localStorage.setItem(tzKey, tz);
    try {
      await api("/prefs", { method: "PUT", body: JSON.stringify({ timezone: tz }) });
      setMsg("Settings saved.");
    } catch (e) {
      if (e.status === 401) {
        showLogin("Token rejected. Update ADHD_HUB_AUTH_TOKEN or try again.");
        return;
      }
      setMsg("Token saved locally; prefs: " + e.message);
    }
  }

  async function saveForge() {
    const payload = {
      provider: $("provider").value,
      base_url: $("base_url").value.trim(),
      owner: $("owner").value.trim(),
      repo: $("repo").value.trim(),
      token: $("forge_token").value.trim(),
      wiki_path: $("wiki_path").value.trim(),
      wiki_branch: $("wiki_branch").value.trim() || "main",
      hub_public_url: $("hub_public_url").value.trim(),
      project_id: $("project_id").value.trim() || null,
      wiki_enabled: $("wiki_enabled").checked,
      board_enabled: $("board_enabled").checked,
      primary_memory_repo: $("primary_memory_repo").checked,
    };
    await api("/forge/config", { method: "PUT", body: JSON.stringify(payload) });
    setMsg("Forge settings saved.");
    await scanForgeImport().catch(() => {});
  }

  async function syncForge() {
    setMsg("Syncing forge…");
    const out = await api("/forge/sync", { method: "POST", body: "{}" });
    const uploaded = out.wiki?.uploaded?.length || 0;
    setMsg(`Forge sync done (${uploaded} wiki files).`);
    if (out.import_preview) renderImportBanner(out.import_preview);
    else await scanForgeImport().catch(() => {});
  }

  async function loadAll() {
    await loadPrefs();
    await loadOverview();
    await loadForge();
    if (projectFilter) await selectProject(projectFilter);
    else {
      renderFocus(null);
      fillProjectForm(null);
      await loadThreads();
    }
    try {
      const preview = await api("/forge/import/preview");
      renderImportBanner(preview);
    } catch (_e) {
      /* forge optional */
    }
  }

  $("proj-all").addEventListener("click", () => selectProject(null));
  $("btn-refresh").addEventListener("click", () => loadAll().catch((e) => setMsg(String(e))));
  $("btn-settings").addEventListener("click", () => $("settings-dialog").showModal());
  $("btn-logout").addEventListener("click", () => logout());
  $("login-form").addEventListener("submit", (e) =>
    handleLogin(e).catch((err) => {
      $("login-error").textContent = String(err.message || err);
    })
  );
  $("btn-save-settings").addEventListener("click", (e) => {
    e.preventDefault();
    saveSettings();
  });
  $("btn-save-forge").addEventListener("click", () =>
    saveForge().catch((e) => setMsg(String(e)))
  );
  $("btn-sync-forge").addEventListener("click", () =>
    syncForge().catch((e) => setMsg(String(e)))
  );
  $("btn-scan-forge").addEventListener("click", () =>
    scanForgeImport().catch((e) => setMsg(String(e)))
  );
  $("btn-export").addEventListener("click", () =>
    exportBackup().catch((e) => setMsg(String(e)))
  );
  $("import-file").addEventListener("change", (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = "";
    if (file) importBackup(file).catch((err) => setMsg(String(err)));
  });
  $("btn-save-project").addEventListener("click", () =>
    saveProject().catch((e) => setMsg(String(e)))
  );
  $("btn-rename-project").addEventListener("click", () => renameProject());
  $("btn-delete-project").addEventListener("click", () => deleteProject());
  $("btn-new-project").addEventListener("click", () => {
    projectFilter = null;
    fillProjectForm({
      title: "",
      slug: "",
      workspace_paths: [],
      unregistered: true,
    });
    $("project-edit").hidden = false;
    $("p_slug").readOnly = false;
    $("focus-title").textContent = "New project";
    $("next-card").className = "next-card empty";
    $("next-card").textContent = "Fill the form below, then Save.";
    setMsg("Creating a new project.");
  });

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      currentView = tab.dataset.view;
      loadThreads().catch((e) => setMsg(String(e)));
    });
  });

  $("token").value = localStorage.getItem(tokenKey) || "";
  fillTimezoneSelect(currentTz);
  tryAuth()
    .then((ok) => (ok ? loadAll() : null))
    .catch((e) => setMsg(String(e)));
})();
