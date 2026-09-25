import { state, preferences, tzKey, $, setMsg, escapeHtml } from './state.js';
import { api } from './api.js';
import { logout, showLogin } from './auth.js';
import { browserTz, confirmDialog, fillTimezoneSelect } from './dom.js';
import { loadAll, loadOverview } from './load.js';
import { saveRewardPreferences } from './progress.js';
import { syncAiRewriteUi } from './work.js';
import {
  IMPORT_POLICY_HINTS,
  IMPORT_POLICY_LABELS,
  tipHtml,
  attachTip,
  wireFieldTips,
  normalizeForgeOwnerRepo,
} from './help.js';
import { enqueueForgeJob, refreshForgeJobs } from './forge-jobs.js';
import { refreshSyncHealth, retryForgeSync } from './sync-health.js';

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
    let serverTz = null;
    try {
      const p = await api("/prefs");
      if (p.timezone) serverTz = p.timezone;
      applyConnectAgents(Array.isArray(p.connect_agents) ? p.connect_agents : []);
      applyConnectCompanions(
        Array.isArray(p.connect_companions) ? p.connect_companions : []
      );
    } catch (_e) {
      /* keep local */
    }
    const local = browserTz();
    const explicit = preferences.getItem(tzKey + "_explicit") === "1";
    // Default/env UTC must not stick forever: My Work would show UTC wall times
    // (often 00:00 for AU morning forge imports). Prefer browser until the
    // operator explicitly saves a timezone in Settings.
    if (explicit && serverTz) {
      state.currentTz = serverTz;
    } else if (serverTz && serverTz !== "UTC") {
      state.currentTz = serverTz;
    } else {
      state.currentTz = local || serverTz || "UTC";
      if (state.currentTz !== "UTC" && state.currentTz !== serverTz) {
        try {
          await api("/prefs", {
            method: "PUT",
            body: JSON.stringify({ timezone: state.currentTz }),
          });
        } catch (_e2) {
          /* optional — local display still uses browser TZ */
        }
      }
    }
    preferences.setItem(tzKey, state.currentTz);
    preferences.setItem(tzKey + "_initialized", "1");
    fillTimezoneSelect(state.currentTz);
    await loadAiConfig().catch(() => {});
  }

function formatAiStatus(config) {
    if (!config) return "AI: status unavailable";
    if (config.active) {
      const model = config.model || "model";
      const host = (config.base_url || "").replace(/^https?:\/\//, "") || "provider";
      return `AI: on · ${model} via ${host}`;
    }
    if (config.enabled && !config.base_url) return "AI: enable needs a base URL";
    return "AI: off — heuristic scan-lines only";
  }

/** Well-known OpenAI-compatible API roots for the Base URL preset select + datalist. */
export const AI_BASE_URL_PRESETS = [
    "http://127.0.0.1:11434/v1",
    "http://127.0.0.1:1234/v1",
    "https://api.openai.com/v1",
    "https://generativelanguage.googleapis.com/v1beta/openai/",
    "https://openrouter.ai/api/v1",
    "https://api.groq.com/openai/v1",
  ];

/** Strip trailing slashes so saved URLs match preset option values. */
export function normalizeAiBaseUrl(url) {
    return String(url || "").trim().replace(/\/+$/, "");
}

/**
 * Return the preset option value that matches ``url``, or "" for Custom….
 * Compares without trailing slashes (AiConfig persists URLs without them).
 */
export function matchAiBaseUrlPreset(url) {
    const normalized = normalizeAiBaseUrl(url);
    if (!normalized) return "";
    const match = AI_BASE_URL_PRESETS.find(
      (p) => normalizeAiBaseUrl(p) === normalized
    );
    return match || "";
}

export function syncAiLoadModelsButton() {
    const btn = $("btn-load-ai-models");
    if (!btn) return;
    btn.disabled = !($("ai_base_url")?.value || "").trim();
  }

/** Match the Base URL input to a preset option, or Custom… when unknown. */
export function syncAiBaseUrlPreset() {
    const sel = $("ai_base_url_preset");
    const input = $("ai_base_url");
    if (!sel || !input) return;
    sel.value = matchAiBaseUrlPreset(input.value);
  }

/**
 * Apply the selected preset into the Base URL field.
 * Custom… leaves a typed URL alone (only clears when the field is empty).
 */
export function applyAiBaseUrlPreset() {
    const sel = $("ai_base_url_preset");
    const input = $("ai_base_url");
    if (!sel || !input) return;
    const value = (sel.value || "").trim();
    if (!value) {
      // Custom… — do not wipe a typed custom URL.
      syncAiLoadModelsButton();
      return;
    }
    input.value = value;
    syncAiLoadModelsButton();
  }

/**
 * Replace model `<select>` options with the given list (no merge from prior providers).
 * Keeps the current/saved model when missing from the list, labeled "(saved)".
 */
export function fillAiModelList(models, preferred) {
    const sel = $("ai_model");
    if (!sel) return;
    const fromModels = Array.isArray(models)
      ? models.map((m) => String(m).trim()).filter(Boolean)
      : [];
    const current = (preferred ?? sel.value ?? "").trim();
    const ordered = [];
    const seen = new Set();
    for (const id of fromModels) {
      if (!id || seen.has(id)) continue;
      seen.add(id);
      ordered.push({ id, label: id });
    }
    if (current && !seen.has(current)) {
      seen.add(current);
      const label = fromModels.length ? `${current} (saved)` : current;
      ordered.unshift({ id: current, label });
    }
    if (!ordered.length) {
      const fallback = current || "llama3.2";
      ordered.push({ id: fallback, label: fallback });
      seen.add(fallback);
    }
    sel.replaceChildren();
    for (const { id, label } of ordered) {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = label;
      sel.appendChild(opt);
    }
    sel.value = current && seen.has(current) ? current : ordered[0].id;
  }

export async function loadAiConfig() {
    const status = $("ai-status");
    const keyStatus = $("ai_key_status");
    if (!$("ai_enabled")) return null;
    try {
      const config = await api("/ai/config");
      $("ai_enabled").checked = !!config.enabled;
      if ($("ai_auto_review_scan")) {
        $("ai_auto_review_scan").checked = !!config.auto_review_scan_lines;
      }
      if ($("ai_auto_summarise_notes")) {
        $("ai_auto_summarise_notes").checked = !!config.auto_summarise_notes;
      }
      // URL field is source of truth; preset select is derived from it.
      $("ai_base_url").value = config.base_url || "";
      syncAiBaseUrlPreset();
      fillAiModelList([], config.model || "llama3.2");
      $("ai_timeout").value = config.timeout_seconds ?? 15;
      $("ai_api_key").value = "";
      $("ai_clear_key").checked = false;
      if (keyStatus) {
        keyStatus.textContent = config.api_key_configured
          ? "An API key is saved. Enter a new one only to replace it."
          : "No saved API key.";
      }
      if (status) status.textContent = formatAiStatus(config);
      state.aiConfigCache = config;
      syncAiLoadModelsButton();
      syncAiRewriteUi();
      return config;
    } catch (_e) {
      if (status) status.textContent = "AI: could not load settings";
      syncAiLoadModelsButton();
      syncAiRewriteUi();
      return null;
    }
  }

export function aiConfigPayload() {
    // Always send the URL field value — never a stale preset selection.
    return {
      enabled: !!$("ai_enabled")?.checked,
      auto_review_scan_lines: !!$("ai_auto_review_scan")?.checked,
      auto_summarise_notes: !!$("ai_auto_summarise_notes")?.checked,
      base_url: $("ai_base_url")?.value.trim() || "",
      model: ($("ai_model")?.value || "").trim() || "llama3.2",
      timeout_seconds: Number($("ai_timeout")?.value) || 15,
      api_key: $("ai_api_key")?.value.trim() || null,
      clear_api_key: !!$("ai_clear_key")?.checked,
    };
  }

export async function saveAiConfig() {
    const msg = $("ai-msg");
    if (msg) msg.textContent = "Saving…";
    const config = await api("/ai/config", {
      method: "PUT",
      body: JSON.stringify(aiConfigPayload()),
    });
    $("ai_api_key").value = "";
    $("ai_clear_key").checked = false;
    $("ai_key_status").textContent = config.api_key_configured
      ? "An API key is saved. Enter a new one only to replace it."
      : "No saved API key.";
    $("ai-status").textContent = formatAiStatus(config);
    state.aiConfigCache = config;
    syncAiLoadModelsButton();
    syncAiRewriteUi();
    if (msg) msg.textContent = "AI settings saved.";
    return config;
  }

export async function testAndLoadAiModels() {
    const msg = $("ai-msg");
    const status = $("ai-status");
    syncAiLoadModelsButton();
    const baseUrl = ($("ai_base_url")?.value || "").trim();
    if (!baseUrl) {
      if (msg) msg.textContent = "Add a base URL before loading models.";
      return null;
    }
    if (msg) msg.textContent = "Testing connection…";
    const payload = {
      base_url: baseUrl,
      timeout_seconds: Number($("ai_timeout")?.value) || 15,
    };
    const key = ($("ai_api_key")?.value || "").trim();
    if (key) payload.api_key = key;
    else if ($("ai_clear_key")?.checked) payload.api_key = "";
    const result = await api("/ai/models", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    fillAiModelList(result.models || [], ($("ai_model")?.value || "").trim());
    const host = baseUrl.replace(/^https?:\/\//, "") || "provider";
    const count = Array.isArray(result.models) ? result.models.length : 0;
    if (status) status.textContent = `AI: connection OK · ${count} models via ${host}`;
    if (msg) msg.textContent = result.message || "Models loaded.";
    return result;
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
      attachHubForgeTips();
      await refreshForgeJobs().catch(() => {});
      await refreshSyncHealth().catch(() => {});
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
    const unsaved = p._unsaved ? ' data-unsaved="1"' : "";
    const badge = p._unsaved
      ? '<span class="unsaved-badge" title="Not saved yet">Unsaved</span>'
      : "";
    const policyOptions = ["manual", "all_open", "labels", "assigned_to_me", "adhd_inbox"]
      .map((v) => {
        const label = IMPORT_POLICY_LABELS[v] || v;
        return `<option value="${v}"${policy === v ? " selected" : ""}>${escapeHtml(label)}</option>`;
      })
      .join("");
    return `<article class="forge-profile-card" data-profile-idx="${idx}" data-profile-id="${id}"${unsaved}>
      <div class="forge-profile-head"><strong>${escapeHtml(p.name || "Connection")}</strong>${badge}</div>
      <div class="form-grid">
        <label>Name ${tipHtml("Friendly label for this connection (shown in project pickers).")}
          <input data-f="name" value="${escapeHtml(p.name || "")}" placeholder="Github personal" /></label>
        <label>Provider ${tipHtml("GitHub or Gitea/Forgejo API dialect for this token.")}
          <select data-f="provider">
            <option value="none"${p.provider === "none" ? " selected" : ""}>none</option>
            <option value="gitea"${p.provider === "gitea" ? " selected" : ""}>gitea</option>
            <option value="github"${p.provider === "github" ? " selected" : ""}>github</option>
          </select>
        </label>
        <label>API base URL ${tipHtml("REST API root. GitHub.com: https://api.github.com — Gitea often ends with /api/v1.")}
          <input data-f="base_url" value="${escapeHtml(p.base_url || "")}" placeholder="https://api.github.com" /></label>
        <label>Web base URL ${tipHtml("Browser base for issue links (https://github.com or your Gitea host).")}
          <input data-f="web_base_url" value="${escapeHtml(p.web_base_url || "")}" placeholder="https://github.com" /></label>
        <label>Owner ${tipHtml("Account or org name only — not a URL. Example: user123")}
          <input data-f="owner" value="${escapeHtml(p.owner || "")}" placeholder="user123" /></label>
        <label>Repo ${tipHtml("Repository name only (my-repo), never a full https:// URL. Full URLs belong in a project Repository URL.")}
          <input data-f="repo" value="${escapeHtml(p.repo || "")}" placeholder="my-repo" /></label>
        <label class="span2">Token ${tipHtml("Personal access token for this provider. Leave blank to keep the saved token. Never paste tokens into project fields.")}
          <input data-f="token" type="password" value="" autocomplete="off" placeholder="${p.token ? "Saved — paste only to replace" : "ghp_… or gitea_…"}" />
          <span class="hint" data-token-status>${p.token ? "A token is saved for this profile. Leave blank on Save to keep it." : "No token saved yet."}</span>
        </label>
        <label class="span2">Import policy ${tipHtml("Controls whether Sync imports new issues. Default manual only reconciles already-linked threads (0 imported).")}
          <select data-f="issue_import_policy">${policyOptions}</select>
        </label>
        <p class="hint import-policy-hint span2" data-policy-hint>${escapeHtml(IMPORT_POLICY_HINTS[policy] || IMPORT_POLICY_HINTS.manual)}</p>
        <label>Import labels ${tipHtml("Comma-separated labels used when Import policy is Matching labels.")}
          <input data-f="issue_import_labels" value="${escapeHtml(labels)}" placeholder="label-one, label-two" /></label>
        <label>Account login ${tipHtml("Forge username for Assigned to me. Leave blank to use the token’s /user login.")}
          <input data-f="forge_account_login" value="${escapeHtml(p.forge_account_login || "")}" placeholder="user123" /></label>
        <label class="check-row span2"><input type="checkbox" data-f="publish_hub_status_block"${p.publish_hub_status_block ? " checked" : ""} /> Publish Hub status block on forge issues ${tipHtml("When on, Hub writes a status block into mirrored forge issue bodies.")}</label>
      </div>
      <div class="actions">
        <button type="button" class="ghost" data-test-profile>Test connection</button>
        <button type="button" class="danger" data-delete-profile>Delete</button>
      </div>
      <p class="hint forge-profile-test" data-test-msg hidden></p>
      <p class="hint">Test uses this card’s current fields (including unsaved drafts). Save forge to keep the profile.</p>
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
    root.querySelectorAll('[data-f="issue_import_policy"]').forEach((sel) => {
      const hint = sel.closest(".forge-profile-card")?.querySelector("[data-policy-hint]");
      const sync = () => {
        if (hint) hint.textContent = IMPORT_POLICY_HINTS[sel.value] || IMPORT_POLICY_HINTS.manual;
      };
      sel.addEventListener("change", sync);
      sync();
    });
    root.querySelectorAll('[data-f="provider"]').forEach((sel) => {
      sel.addEventListener("change", () => {
        const card = sel.closest(".forge-profile-card");
        if (!card) return;
        const base = card.querySelector('[data-f="base_url"]');
        const web = card.querySelector('[data-f="web_base_url"]');
        const v = sel.value;
        const baseVal = (base?.value || "").trim();
        const webVal = (web?.value || "").trim();
        const hostnameOf = (raw) => {
          const s = String(raw || "").trim();
          if (!s) return "";
          try {
            return new URL(s.includes("://") ? s : `https://${s}`).hostname.toLowerCase();
          } catch (_e) {
            return "";
          }
        };
        const baseHost = hostnameOf(baseVal);
        const webHost = hostnameOf(webVal);
        const isGithubApiHost = (h) => h === "api.github.com";
        const isGithubWebHost = (h) => h === "github.com" || h === "www.github.com";
        const looksGiteaBase =
          /\/api\/v1\/?$/i.test(baseVal) ||
          /(^|\.)gitea\./i.test(baseHost) ||
          baseHost.endsWith(".gitea.io");
        if (v === "github") {
          // Provider "github" means github.com — reset non-GitHub hosts (incl. prior Gitea web URLs).
          if (!baseVal || looksGiteaBase || (baseHost && !isGithubApiHost(baseHost))) {
            if (base) base.value = "https://api.github.com";
          }
          if (!webVal || looksGiteaBase || (webHost && !isGithubWebHost(webHost))) {
            if (web) web.value = "https://github.com";
          }
        } else if (v === "gitea") {
          if (isGithubApiHost(baseHost)) {
            if (base) base.value = "";
            base?.setAttribute("placeholder", "https://git.example/api/v1");
          }
          if (isGithubWebHost(webHost)) {
            if (web) web.value = "";
            web?.setAttribute("placeholder", "https://git.example");
          }
        }
      });
    });
    wireFieldTips(root);
  }

function collectForgeProfilesFromDom() {
    return [...document.querySelectorAll(".forge-profile-card")].map((card) => {
      const get = (name) => card.querySelector(`[data-f="${name}"]`);
      const labelsRaw = get("issue_import_labels")?.value || "";
      const rawOwner = get("owner")?.value?.trim() || "";
      const rawRepo = get("repo")?.value?.trim() || "";
      const { owner, repo } = normalizeForgeOwnerRepo(rawOwner, rawRepo);
      if (get("owner") && owner !== rawOwner) get("owner").value = owner;
      if (get("repo") && repo !== rawRepo) get("repo").value = repo;
      return {
        id: card.dataset.profileId,
        name: get("name")?.value?.trim() || "",
        provider: get("provider")?.value || "none",
        base_url: get("base_url")?.value?.trim() || "",
        web_base_url: get("web_base_url")?.value?.trim() || "",
        owner,
        repo,
        token: get("token")?.value?.trim() || "",
        issue_import_policy: get("issue_import_policy")?.value || "manual",
        issue_import_labels: labelsRaw
          .split(/[,;]/)
          .map((s) => s.trim())
          .filter(Boolean),
        forge_account_login: get("forge_account_login")?.value?.trim() || "",
        publish_hub_status_block: !!get("publish_hub_status_block")?.checked,
        _unsaved: card.dataset.unsaved === "1",
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
      _unsaved: true,
    });
    const next = { ...cfg, connection_profiles: profiles };
    state.forgeConfigCache = next;
    renderForgeProfiles(next);
  }

function draftFromForgeCard(card) {
    if (!card) return null;
    const id = card.dataset.profileId;
    const row = collectForgeProfilesFromDom().find((p) => p.id === id);
    if (!row) return null;
    const { _unsaved, ...draft } = row;
    return draft;
  }

async function testForgeProfile(profile_id, card) {
    const msg = card?.querySelector("[data-test-msg]");
    if (msg) {
      msg.hidden = false;
      msg.textContent = "Testing…";
    }
    const draft = draftFromForgeCard(card);
    const out = await api(`/forge/profiles/${encodeURIComponent(profile_id)}/test`, {
      method: "POST",
      body: JSON.stringify(draft || {}),
    });
    const textOut = out.ok
      ? `Connected${out.login ? ` as ${out.login}` : ""} (${out.provider || ""} @ ${out.host || ""})`
      : `Failed: ${out.error || "unknown"}${out.hint ? ` — ${out.hint}` : ""}`;
    if (msg) msg.textContent = textOut;
    setMsg(textOut, { variant: out.ok ? "success" : "error" });
  }

async function deleteForgeProfile(profile_id) {
    const card = document.querySelector(
      `.forge-profile-card[data-profile-id="${CSS.escape(profile_id)}"]`
    );
    if (card?.dataset.unsaved === "1") {
      card.remove();
      const cfg = state.forgeConfigCache || { connection_profiles: [] };
      state.forgeConfigCache = {
        ...cfg,
        connection_profiles: collectForgeProfilesFromDom().map(({ _unsaved, ...p }) => p),
      };
      setMsg("Unsaved profile discarded.");
      return;
    }
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
    const { result: out } = await enqueueForgeJob(
      "/forge/import",
      { overwrite_local: !!result.data.overwrite_local },
      { pendingLabel: "Import from forge" }
    );
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
    preferences.setItem(tzKey + "_explicit", "1");
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
function attachHubForgeTips() {
    const tips = [
      [
        "default_connection_profile_id",
        "Default profile is the Hub memory connection for all wiki / PROGRESS.md / INDEX.md pushes. A project’s own forge repo only affects issues/board — never the progress wiki target.",
      ],
      [
        "wiki_path",
        "Path inside the Hub memory repo for wiki files. Blank = repository root (primary memory layout).",
      ],
      ["wiki_branch", "Branch used for wiki Contents API writes (usually main)."],
      [
        "hub_public_url",
        "Public Hub URL written into forge status links (https://hub.example.com).",
      ],
      ["project_id", "Optional Gitea/Forgejo project board id for board attach."],
      [
        "wiki_enabled",
        "Push PROGRESS.md / INDEX.md to the Default profile memory repo.",
      ],
      [
        "board_enabled",
        "Create/update forge issues for Hub threads on the project’s forge target.",
      ],
      [
        "board_inbox_enabled",
        "Poll allowlisted authors for cloud-agent ADHD inbox issues.",
      ],
      [
        "primary_memory_repo",
        "Treat Default profile owner/repo as the Hub primary memory tree (projects/<slug>/PROGRESS.md at repo root).",
      ],
      [
        "board_inbox_authors",
        "Comma-separated forge logins allowed to open inbox issues. Empty allowlist imports nothing (fail closed).",
      ],
    ];
    for (const [id, tip] of tips) {
      const el = $(id);
      const label = el?.closest("label");
      if (label) attachTip(label, tip);
    }
  }

export async function saveForge() {
    const profiles = collectForgeProfilesFromDom().map(({ _unsaved, ...p }) => p);
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
    try {
      await scanForgeImport();
    } catch (e) {
      setMsg(`Forge settings saved. Import scan: ${e.message || e}`, { variant: "error" });
    }
  }
export async function syncForge() {
    const { result: out } = await enqueueForgeJob("/forge/sync", {}, { pendingLabel: "Sync forge" });
    const uploaded = out.wiki?.uploaded?.length || 0;
    const warnings = Array.isArray(out.warnings) ? out.warnings : [];
    let msg = `Forge sync done (${uploaded} wiki files).`;
    if (warnings.length) {
      msg += ` ${warnings[0]}`;
      setMsg(msg, { variant: "warning" });
    } else {
      setMsg(msg);
    }
    if (out.import_preview) renderImportBanner(out.import_preview);
    else await scanForgeImport().catch(() => {});
    await refreshSyncHealth().catch(() => {});
  }
export async function importForgeInbox() {
    const { result: out } = await enqueueForgeJob(
      "/forge/inbox/import",
      {},
      { pendingLabel: "Import issue inbox" }
    );
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
    const imported = out.count || 0;
    const refreshed = out.refreshed_count || 0;
    const unchanged = out.unchanged_count || 0;
    const conflicts = out.conflict_count || 0;
    setMsg(
      `Imported ${imported} · Refreshed ${refreshed} · Unchanged ${unchanged} · Needs review ${conflicts}`,
      conflicts ? { variant: "warning" } : undefined
    );
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
