import { state, preferences, tzKey, $, setMsg, escapeHtml } from './state.js';
import { api } from './api.js';
import { logout, showLogin } from './auth.js';
import { browserTz, confirmDialog, fillTimezoneSelect } from './dom.js';
import { loadAll, loadOverview } from './load.js';
import { saveRewardPreferences } from './progress.js';

export function selectSettingsTab(name, focus = false) {
    document.querySelectorAll("[data-settings-tab]").forEach((tab) => {
      const selected = tab.dataset.settingsTab === name;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      $(tab.getAttribute("aria-controls")).hidden = !selected;
      if (selected && focus) tab.focus();
    });
    $("settings-dialog").querySelector(".settings-content").scrollTop = 0;
  }
export async function loadPrefs() {
    try {
      const p = await api("/prefs");
      if (p.timezone) {
        state.currentTz = p.timezone;
        preferences.setItem(tzKey, state.currentTz);
      }
    } catch (_e) {
      /* keep local */
    }
    if (!preferences.getItem(tzKey + "_initialized")) {
      const local = browserTz();
      if (!state.currentTz || state.currentTz === "UTC") state.currentTz = local;
      preferences.setItem(tzKey, state.currentTz);
      preferences.setItem(tzKey + "_initialized", "1");
      try {
        await api("/prefs", {
          method: "PUT",
          body: JSON.stringify({ timezone: state.currentTz }),
        });
      } catch (_e2) {
        /* optional */
      }
    }
    fillTimezoneSelect(state.currentTz);
  }
export async function loadForge() {
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
      $("board_inbox_enabled").checked = !!c.board_inbox_enabled;
      $("board_inbox_authors").value = Array.isArray(c.board_inbox_authors)
        ? c.board_inbox_authors.join(", ")
        : c.board_inbox_authors || "";
      $("primary_memory_repo").checked = !!c.primary_memory_repo;
    } catch (_e) {
      /* forge optional */
    }
  }
export async function loadOpenClaw() {
    const config = await api("/openclaw/config");
    $("oc_enabled").checked = !!config.alerts_enabled;
    $("oc_webhook_url").value = config.webhook_url || "";
    $("oc_agent_url").value = config.agent_url || "";
    $("oc_token").value = "";
    $("oc_clear_token").checked = false;
    $("oc_cron").value = config.stale_nudge_cron || "0 9 * * *";
    $("oc_stale_days").value = config.stale_days || 3;
    $("oc_cooldown_days").value = config.remind_cooldown_days || 3;
    $("oc_digest_limit").value = config.digest_max_nudge || 2;
    $("oc_token_status").textContent = config.token_configured
      ? "A bearer token is saved. Enter a new one only to replace it."
      : "No saved bearer token.";
  }
export function openClawPayload() {
    return {
      alerts_enabled: $("oc_enabled").checked,
      webhook_url: $("oc_webhook_url").value.trim(),
      agent_url: $("oc_agent_url").value.trim(),
      token: $("oc_token").value.trim() || null,
      clear_token: $("oc_clear_token").checked,
      stale_nudge_cron: $("oc_cron").value.trim(),
      stale_days: Number($("oc_stale_days").value),
      remind_cooldown_days: Number($("oc_cooldown_days").value),
      digest_max_nudge: Number($("oc_digest_limit").value),
    };
  }
export async function saveOpenClaw() {
    $("openclaw-msg").textContent = "Saving…";
    const config = await api("/openclaw/config", {
      method: "PUT",
      body: JSON.stringify(openClawPayload()),
    });
    $("oc_token").value = "";
    $("oc_clear_token").checked = false;
    $("oc_token_status").textContent = config.token_configured
      ? "A bearer token is saved. Enter a new one only to replace it."
      : "No saved bearer token.";
    $("openclaw-msg").textContent = "OpenClaw settings saved.";
    return config;
  }
export async function testOpenClaw() {
    await saveOpenClaw();
    $("openclaw-msg").textContent = "Sending a private test alert…";
    const result = await api("/openclaw/test", { method: "POST", body: "{}" });
    $("openclaw-msg").textContent = result.message || "Test alert sent.";
  }
export function renderImportBanner(preview) {
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
export async function scanForgeImport() {
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
export async function runForgeImport() {
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
export async function exportBackup() {
    const passphrase = ($("backup-passphrase")?.value || "").trim();
    const headers = { "X-Hub-Request": "1" };
    if (passphrase) headers["X-Backup-Passphrase"] = passphrase;
    const res = await fetch("/api/admin/export", { headers });
    if (res.status === 401) {
      logout();
      return;
    }
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = passphrase ? "adhd-hub-backup.zip.enc" : "adhd-hub-backup.zip";
    a.click();
    URL.revokeObjectURL(url);
    setMsg(passphrase ? "Encrypted backup downloaded." : "Backup downloaded.");
  }
export async function importBackup(file) {
    const result = await confirmDialog({
      title: "Restore backup",
      body: "This replaces SQLite, wiki, and forge/prefs on this instance. Prefer stopping the container for large restores. Continue?",
    });
    if (!result.ok) return;
    const passphrase = ($("import-passphrase")?.value || "").trim();
    const headers = { "X-Hub-Request": "1" };
    if (passphrase) headers["X-Backup-Passphrase"] = passphrase;
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/admin/import?replace=true", {
      method: "POST",
      headers,
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
export async function saveSettings() {
    saveRewardPreferences();
    const tz = $("timezone").value || browserTz();
    state.currentTz = tz;
    preferences.setItem(tzKey, tz);
    try {
      await api("/prefs", { method: "PUT", body: JSON.stringify({ timezone: tz }) });
      await loadOverview();
      setMsg("Settings saved.");
    } catch (e) {
      if (e.status === 401) {
        showLogin("Token rejected. Update ADHD_HUB_AUTH_TOKEN or try again.");
        return;
      }
      setMsg("Could not save settings: " + e.message);
    }
  }
export async function saveForge() {
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
      board_inbox_enabled: $("board_inbox_enabled").checked,
      board_inbox_authors: $("board_inbox_authors")
        .value.split(/[,;]/)
        .map((s) => s.trim())
        .filter(Boolean),
      primary_memory_repo: $("primary_memory_repo").checked,
    };
    await api("/forge/config", { method: "PUT", body: JSON.stringify(payload) });
    setMsg("Forge settings saved.");
    await scanForgeImport().catch(() => {});
  }
export async function syncForge() {
    setMsg("Syncing forge…");
    const out = await api("/forge/sync", { method: "POST", body: "{}" });
    const uploaded = out.wiki?.uploaded?.length || 0;
    setMsg(`Forge sync done (${uploaded} wiki files).`);
    if (out.import_preview) renderImportBanner(out.import_preview);
    else await scanForgeImport().catch(() => {});
  }
export async function importForgeInbox() {
    setMsg("Importing forge issue inbox…");
    const out = await api("/forge/inbox/import", { method: "POST", body: "{}" });
    if (out.skipped) {
      if (out.reason === "board_inbox_authors_required") {
        setMsg(
          "Issue inbox needs an allowlist — add your forge username under Inbox authors, then save."
        );
        return;
      }
      setMsg("Issue inbox import skipped — enable Board sync + Import cloud-agent issues.");
      return;
    }
    if (out.error) {
      setMsg("Issue inbox import failed: " + out.error);
      return;
    }
    const n = out.count || 0;
    setMsg(`Imported ${n} forge issue${n === 1 ? "" : "s"} into Hub threads.`);
    await loadAll();
  }
export function pendingConnectCode() {
    try {
      const params = new URLSearchParams(location.search);
      const fromQuery = params.get("connect");
      if (fromQuery) {
        sessionStorage.setItem("adhd_hub_connect_code", fromQuery);
        params.delete("connect");
        const qs = params.toString();
        history.replaceState({}, "", location.pathname + (qs ? `?${qs}` : "") + location.hash);
      }
      return sessionStorage.getItem("adhd_hub_connect_code") || "";
    } catch (_e) {
      return new URLSearchParams(location.search).get("connect") || "";
    }
  }
export function offerPendingConnect() {
    const code = pendingConnectCode();
    if (!code) return;
    $("cli-connect-code-input").value = code;
    $("cli-connect-code-label").textContent = code;
    $("cli-connect-dialog-msg").textContent = "";
    if (!$("app-shell").hidden) $("cli-connect-dialog").showModal();
  }
export async function loadCliSessions() {
    try {
      const data = await api("/connect/sessions");
      const sessions = data.sessions || [];
      $("cli-sessions-wrap").hidden = sessions.length === 0;
      $("cli-sessions-list").innerHTML = sessions
        .map(
          (s) =>
            `<li>CLI session <code>${escapeHtml(String(s.id).slice(0, 8))}</code> <button type="button" class="text-button" data-revoke="${escapeHtml(s.id)}">Revoke</button></li>`
        )
        .join("");
      $("cli-sessions-list")
        .querySelectorAll("[data-revoke]")
        .forEach((btn) => {
          btn.addEventListener("click", () =>
            revokeCliSession(btn.getAttribute("data-revoke")).catch((e) => setMsg(String(e)))
          );
        });
    } catch (_e) {
      /* optional */
    }
  }
export async function revokeCliSession(sessionId) {
    await api("/connect/sessions/" + encodeURIComponent(sessionId), { method: "DELETE" });
    setMsg("CLI session revoked.");
    await loadCliSessions();
  }
export async function approveCliConnect(userCode, messageId) {
    const msg = $(messageId);
    const code = (userCode || "").trim();
    if (!code) {
      msg.textContent = "Enter the code from the CLI first.";
      return null;
    }
    msg.textContent = "Allowing…";
    const result = await api("/connect/approve", {
      method: "POST",
      body: JSON.stringify({ user_code: code }),
    });
    msg.textContent = "Allowed. The CLI can finish on its own.";
    try {
      sessionStorage.removeItem("adhd_hub_connect_code");
    } catch (_e) {
      /* ignore */
    }
    if (result.redirect) {
      const popup = window.open(result.redirect, "adhd-hub-cli");
      if (!popup) {
        fetch(result.redirect, { mode: "no-cors" }).catch(() => {});
      }
    }
    await loadCliSessions();
    return result;
  }
