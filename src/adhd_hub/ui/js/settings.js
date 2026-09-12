import { state, preferences, tzKey, $, setMsg, escapeHtml } from './state.js';
import { api } from './api.js';
import { logout, showLogin } from './auth.js';
import { browserTz, confirmDialog, fillTimezoneSelect } from './dom.js';
import { loadAll, loadOverview } from './load.js';
import { saveRewardPreferences } from './progress.js';

export function showSettingsIndex() {
  const view = $("settings-view");
  if (!view) return;
  view.classList.add("settings-index-open");
  const heading = view.querySelector("h1");
  if (heading) {
    if (!heading.hasAttribute("tabindex")) heading.setAttribute("tabindex", "-1");
    heading.focus({ preventScroll: true });
  }
}

export function selectSettingsTab(name, focus = false) {
  $("settings-view")?.classList.remove("settings-index-open");
  const tabs = [...document.querySelectorAll("[data-settings-tab]")];
  const known = new Set(tabs.map((tab) => tab.dataset.settingsTab));
  const next = known.has(name) ? name : "preferences";
  tabs.forEach((tab) => {
    const selected = tab.dataset.settingsTab === next;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    const panel = $(tab.getAttribute("aria-controls"));
    if (panel) panel.hidden = !selected;
    if (selected && focus) tab.focus();
  });
  const content = document.querySelector("#settings-view .settings-content");
  if (content) content.scrollTop = 0;
}
export async function loadPrefs() {
    try {
      const p = await api("/prefs");
      if (p.timezone) {
        state.currentTz = p.timezone;
        preferences.setItem(tzKey, state.currentTz);
      }
      applyConnectAgents(Array.isArray(p.connect_agents) ? p.connect_agents : []);
      applyConnectCompanions(
        Array.isArray(p.connect_companions) ? p.connect_companions : []
      );
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
export function selectedConnectAgents() {
    const all = $("ca_all")?.checked;
    if (all) return ["*"];
    return ["ca_cursor", "ca_codex", "ca_claude"]
      .map((id) => $(id))
      .filter((el) => el && el.checked)
      .map((el) => el.value);
  }
export function applyConnectAgents(agents) {
    const set = new Set((agents || []).map((a) => String(a).trim().toLowerCase()));
    if ($("ca_all")) $("ca_all").checked = set.has("*");
    if ($("ca_cursor")) $("ca_cursor").checked = set.has("cursor") || set.has("*");
    if ($("ca_codex")) $("ca_codex").checked = set.has("codex") || set.has("*");
    if ($("ca_claude")) $("ca_claude").checked = set.has("claude") || set.has("claude-code") || set.has("*");
    if (set.has("*")) {
      if ($("ca_cursor")) $("ca_cursor").checked = true;
      if ($("ca_codex")) $("ca_codex").checked = true;
      if ($("ca_claude")) $("ca_claude").checked = true;
    }
  }
export function selectedConnectCompanions() {
    return [
      "cc_i_have_adhd",
      "cc_graphify",
      "cc_rtk",
      "cc_superpowers",
      "cc_context7",
      "cc_agent_browser",
      "cc_serena",
    ]
      .map((id) => $(id))
      .filter((el) => el && el.checked)
      .map((el) => el.value);
  }
export function applyConnectCompanions(companions) {
    const set = new Set((companions || []).map((c) => String(c).trim().toLowerCase()));
    if ($("cc_i_have_adhd")) $("cc_i_have_adhd").checked = set.has("i-have-adhd");
    if ($("cc_graphify")) $("cc_graphify").checked = set.has("graphify");
    if ($("cc_rtk")) $("cc_rtk").checked = set.has("rtk");
    if ($("cc_superpowers")) $("cc_superpowers").checked = set.has("superpowers");
    if ($("cc_context7")) $("cc_context7").checked = set.has("context7");
    if ($("cc_agent_browser")) $("cc_agent_browser").checked = set.has("agent-browser");
    if ($("cc_serena")) $("cc_serena").checked = set.has("serena");
  }
export async function saveConnectAgents() {
    const agents = selectedConnectAgents();
    const companions = selectedConnectCompanions();
    const msg = $("connect-agents-msg");
    try {
      const saved = await api("/prefs", {
        method: "PUT",
        body: JSON.stringify({
          connect_agents: agents,
          connect_companions: companions,
        }),
      });
      applyConnectAgents(saved.connect_agents || agents);
      applyConnectCompanions(saved.connect_companions || companions);
      const parts = [];
      if (agents.length) parts.push(`agents: ${agents.join(", ")}`);
      else parts.push("no agents");
      if (companions.length) parts.push(`companions: ${companions.join(", ")}`);
      else parts.push("no companions");
      if (msg) {
        msg.textContent =
          `Saved (${parts.join("; ")}). Re-copy the install command — scripts pick this up.`;
      }
      setMsg(`Connect defaults saved (${parts.join("; ")}).`);
    } catch (e) {
      if (msg) msg.textContent = "Could not save: " + e.message;
      setMsg("Could not save connect defaults: " + e.message);
    }
  }
export async function loadForge() {
    try {
      const c = await api("/forge/config");
      state.forgeConfigCache = c;
      renderForgeProfiles(c);
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

function newProfileId() {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return crypto.randomUUID().replace(/-/g, "").slice(0, 12);
    }
    return `p${Date.now().toString(36)}`;
  }

function profileCardHtml(p, idx) {
    const id = escapeHtml(p.id || "");
    const policy = p.issue_import_policy || "manual";
    const labels = Array.isArray(p.issue_import_labels)
      ? p.issue_import_labels.join(", ")
      : "";
    return `<article class="forge-profile-card" data-profile-idx="${idx}" data-profile-id="${id}">
      <div class="form-grid">
        <label>Name <input data-f="name" value="${escapeHtml(p.name || "")}" /></label>
        <label>Provider
          <select data-f="provider">
            <option value="none"${p.provider === "none" ? " selected" : ""}>none</option>
            <option value="gitea"${p.provider === "gitea" ? " selected" : ""}>gitea</option>
            <option value="github"${p.provider === "github" ? " selected" : ""}>github</option>
          </select>
        </label>
        <label>API base URL <input data-f="base_url" value="${escapeHtml(p.base_url || "")}" /></label>
        <label>Web base URL <input data-f="web_base_url" value="${escapeHtml(p.web_base_url || "")}" /></label>
        <label>Owner <input data-f="owner" value="${escapeHtml(p.owner || "")}" /></label>
        <label>Repo <input data-f="repo" value="${escapeHtml(p.repo || "")}" /></label>
        <label class="span2">Token <input data-f="token" type="password" value="${escapeHtml(p.token || "")}" autocomplete="off" /></label>
        <label>Import policy
          <select data-f="issue_import_policy">
            <option value="manual"${policy === "manual" ? " selected" : ""}>manual</option>
            <option value="all_open"${policy === "all_open" ? " selected" : ""}>all_open</option>
            <option value="labels"${policy === "labels" ? " selected" : ""}>labels</option>
            <option value="assigned_to_me"${policy === "assigned_to_me" ? " selected" : ""}>assigned_to_me</option>
            <option value="adhd_inbox"${policy === "adhd_inbox" ? " selected" : ""}>adhd_inbox</option>
          </select>
        </label>
        <label>Import labels <input data-f="issue_import_labels" value="${escapeHtml(labels)}" placeholder="label-one, label-two" /></label>
        <label>Account login <input data-f="forge_account_login" value="${escapeHtml(p.forge_account_login || "")}" placeholder="for assigned_to_me" /></label>
        <label class="check-row span2"><input type="checkbox" data-f="publish_hub_status_block"${p.publish_hub_status_block ? " checked" : ""} /> Publish Hub status block on forge issues</label>
      </div>
      <div class="actions">
        <button type="button" class="ghost" data-test-profile>Test connection</button>
        <button type="button" class="danger" data-delete-profile>Delete</button>
      </div>
      <p class="hint forge-profile-test" data-test-msg hidden></p>
    </article>`;
  }

export function renderForgeProfiles(cfg) {
    const root = $("forge-profiles");
    const defSel = $("default_connection_profile_id");
    if (!root || !defSel) return;
    const profiles = Array.isArray(cfg?.connection_profiles) ? cfg.connection_profiles : [];
    root.innerHTML = profiles.length
      ? profiles.map((p, i) => profileCardHtml(p, i)).join("")
      : `<p class="hint">No profiles yet. Add one for GitHub, Gitea, or both.</p>`;
    defSel.innerHTML = profiles
      .map(
        (p) =>
          `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name || p.id)}</option>`
      )
      .join("");
    if (cfg?.default_connection_profile_id) {
      defSel.value = cfg.default_connection_profile_id;
    }
    root.querySelectorAll("[data-test-profile]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const card = btn.closest(".forge-profile-card");
        const pid = card?.dataset.profileId;
        if (pid) testForgeProfile(pid, card).catch((e) => setMsg(String(e)));
      });
    });
    root.querySelectorAll("[data-delete-profile]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const card = btn.closest(".forge-profile-card");
        const pid = card?.dataset.profileId;
        if (pid) deleteForgeProfile(pid).catch((e) => setMsg(String(e)));
      });
    });
  }

function collectForgeProfilesFromDom() {
    return [...document.querySelectorAll(".forge-profile-card")].map((card) => {
      const get = (name) => card.querySelector(`[data-f="${name}"]`);
      const labelsRaw = get("issue_import_labels")?.value || "";
      return {
        id: card.dataset.profileId,
        name: get("name")?.value?.trim() || "",
        provider: get("provider")?.value || "none",
        base_url: get("base_url")?.value?.trim() || "",
        web_base_url: get("web_base_url")?.value?.trim() || "",
        owner: get("owner")?.value?.trim() || "",
        repo: get("repo")?.value?.trim() || "",
        token: get("token")?.value?.trim() || "",
        issue_import_policy: get("issue_import_policy")?.value || "manual",
        issue_import_labels: labelsRaw
          .split(/[,;]/)
          .map((s) => s.trim())
          .filter(Boolean),
        forge_account_login: get("forge_account_login")?.value?.trim() || "",
        publish_hub_status_block: !!get("publish_hub_status_block")?.checked,
      };
    });
  }

export function addForgeProfile() {
    const cfg = state.forgeConfigCache || { connection_profiles: [] };
    const profiles = collectForgeProfilesFromDom();
    profiles.push({
      id: newProfileId(),
      name: "New connection",
      provider: "github",
      base_url: "https://api.github.com",
      web_base_url: "https://github.com",
      owner: "",
      repo: "",
      token: "",
      issue_import_policy: "manual",
      issue_import_labels: [],
      forge_account_login: "",
      publish_hub_status_block: false,
    });
    const next = { ...cfg, connection_profiles: profiles };
    state.forgeConfigCache = next;
    renderForgeProfiles(next);
  }

async function testForgeProfile(profile_id, card) {
    const msg = card?.querySelector("[data-test-msg]");
    if (msg) {
      msg.hidden = false;
      msg.textContent = "Testing…";
    }
    const out = await api(`/forge/profiles/${encodeURIComponent(profile_id)}/test`, {
      method: "POST",
      body: "{}",
    });
    const text = out.ok
      ? `Connected${out.login ? ` as ${out.login}` : ""} (${out.provider || ""} @ ${out.host || ""})`
      : `Failed: ${out.error || "unknown"}`;
    if (msg) msg.textContent = text;
    setMsg(text, { variant: out.ok ? "success" : "error" });
  }

async function deleteForgeProfile(profile_id) {
    const result = await confirmDialog({
      title: "Delete connection profile?",
      body: "Projects using this profile must be reassigned first.",
    });
    if (!result.ok) return;
    try {
      await api(`/forge/profiles/${encodeURIComponent(profile_id)}`, { method: "DELETE" });
      setMsg("Profile deleted.");
      await loadForge();
    } catch (e) {
      setMsg(e.message || "Could not delete profile", { variant: "error" });
    }
  }
export function openClawSetupPrompt(hubOrigin = location.origin, userCode = "") {
    const hub = String(hubOrigin || "").replace(/\/$/, "") || "http://127.0.0.1:8787";
    const code = String(userCode || "").trim();
    const codeLine = code
      ? `Pairing code from the Hub UI: ${code}`
      : "Pairing code: (missing — operator must click Start OpenClaw pairing in Hub Settings → OpenClaw, then copy this prompt again)";
    const codeJson = code || "<PAIRING_CODE_FROM_HUB>";
    return [
      "Set up ADHD Progress Hub ↔ OpenClaw on my private LAN or Tailscale.",
      "",
      codeLine,
      "",
      "Do this end-to-end:",
      "1. Install Hub skills for OpenClaw (non-interactive):",
      "   npx skills add uniskela/adhd-hub -g -y -a openclaw",
      "2. Ensure the OpenClaw gateway exposes /hooks/wake and optional /hooks/agent",
      "   on a LAN/Tailscale URL (not the public internet).",
      "3. Create or reveal a bearer token those hooks accept.",
      "4. Submit the pair to the Hub (no Hub auth token — pairing code only):",
      `   POST ${hub}/api/openclaw/pair/submit`,
      "   JSON body:",
      "   {",
      `     "user_code": "${codeJson}",`,
      '     "webhook_url": "http(s)://<openclaw-host>:18789/hooks/wake",',
      '     "agent_url": "http(s)://<openclaw-host>:18789/hooks/agent",',
      '     "token": "<openclaw-hook-bearer-token>",',
      '     "alerts_enabled": true',
      "   }",
      "5. Recommended Hub alert defaults unless I say otherwise:",
      '   cron "0 9 * * *", stale after 3 days, cooldown 3 days, digest limit 2.',
      "6. Tell me when submit succeeds so I can Approve in Hub Settings → OpenClaw,",
      "   then help interpret Save & send test if needed.",
      "",
      `Hub UI: ${hub}/ui`,
      "Never put ADHD_HUB_AUTH_TOKEN into OpenClaw config, skills, or chat logs.",
      "Summaries only — no raw transcripts.",
    ].join("\n");
  }
export function renderOpenClawPair(pair) {
    const status = $("oc-pair-status");
    const approve = $("btn-oc-pair-approve");
    const cancel = $("btn-oc-pair-cancel");
    const promptEl = $("oc-setup-prompt");
    if (!status) return;
    const state = pair || { status: "none" };
    if (approve) approve.hidden = state.status !== "submitted";
    if (cancel) cancel.hidden = state.status !== "waiting" && state.status !== "submitted";
    if (state.status === "waiting") {
      status.textContent = `Pairing code ${state.user_code} (expires in ~${state.expires_in || 0}s). Copy the prompt into OpenClaw.`;
      if (promptEl) promptEl.value = pair.prompt || openClawSetupPrompt(location.origin, state.user_code);
    } else if (state.status === "submitted") {
      status.textContent = `OpenClaw submitted ${state.webhook_url || "endpoints"}. Review and Approve.`;
      if (promptEl && !promptEl.value.trim()) {
        promptEl.value = openClawSetupPrompt(location.origin, state.user_code);
      }
    } else {
      status.textContent = "No active pairing. Start pairing, or configure manually below.";
      if (promptEl) promptEl.value = openClawSetupPrompt(location.origin);
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
    try {
      const pair = await api("/openclaw/pair");
      renderOpenClawPair(pair);
    } catch (_e) {
      renderOpenClawPair({ status: "none" });
    }
  }
export async function startOpenClawPair() {
    try {
      const pair = await api("/openclaw/pair/start", { method: "POST", body: "{}" });
      renderOpenClawPair(pair);
      $("openclaw-msg").textContent = `Pairing started: ${pair.user_code}`;
      setMsg(`OpenClaw pairing code ${pair.user_code}`);
      return pair;
    } catch (e) {
      const msg = String(e.message || e);
      if (msg.includes("pair_submitted_pending_approval") || e.status === 409) {
        $("openclaw-msg").textContent =
          "A submitted pair is waiting — Approve or Cancel it before starting again.";
        const pair = await api("/openclaw/pair").catch(() => null);
        if (pair) renderOpenClawPair(pair);
        return pair;
      }
      throw e;
    }
  }
export async function approveOpenClawPair() {
    const { ok } = await confirmDialog({
      title: "Approve OpenClaw pair?",
      body: "Save the webhook/agent URLs and hook token OpenClaw submitted?",
    });
    if (!ok) return;
    const config = await api("/openclaw/pair/approve", { method: "POST", body: "{}" });
    $("openclaw-msg").textContent = "OpenClaw pair approved and saved.";
    setMsg("OpenClaw pair approved.");
    await loadOpenClaw();
    if (config.webhook_url) $("oc_webhook_url").value = config.webhook_url;
    if (config.agent_url) $("oc_agent_url").value = config.agent_url || "";
  }
export async function cancelOpenClawPair() {
    await api("/openclaw/pair/cancel", { method: "POST", body: "{}" });
    $("openclaw-msg").textContent = "OpenClaw pairing cancelled.";
    renderOpenClawPair({ status: "none" });
  }
export async function copyOpenClawPrompt() {
    const promptEl = $("oc-setup-prompt");
    // If no pairing code yet, start one so the copied prompt is complete.
    const current = (promptEl && promptEl.value) || "";
    if (!/Pairing code from the Hub UI: [A-Z0-9]{4}-[A-Z0-9]{4}/.test(current)) {
      try {
        await startOpenClawPair();
      } catch (_e) {
        /* fall through with whatever prompt we have */
      }
    }
    const text = (promptEl && promptEl.value) || openClawSetupPrompt(location.origin);
    try {
      await navigator.clipboard.writeText(text);
      $("openclaw-msg").textContent = "OpenClaw setup prompt copied.";
      setMsg("OpenClaw setup prompt copied.");
    } catch (_) {
      if (promptEl) {
        promptEl.focus();
        promptEl.select();
      }
      $("openclaw-msg").textContent = "Select and copy the OpenClaw prompt above.";
    }
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
    const profiles = collectForgeProfilesFromDom();
    const payload = {
      connection_profiles: profiles,
      default_connection_profile_id: $("default_connection_profile_id").value || null,
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
    await loadForge();
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
    const shortId = String(sessionId || "").slice(0, 8);
    const { ok } = await confirmDialog({
      title: "Revoke CLI session?",
      body: `Revoke session ${shortId}? That computer will need to connect again.`,
    });
    if (!ok) return;
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
