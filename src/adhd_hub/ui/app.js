(() => {
  // Some browsers deny storage access. Keep the app usable for this visit.
  const preferenceCache = new Map();
  const preferences = {
    getItem(key) {
      if (preferenceCache.has(key)) return preferenceCache.get(key);
      try { return localStorage.getItem(key); } catch (_) { return null; }
    },
    setItem(key, value) {
      preferenceCache.set(key, String(value));
      try { localStorage.setItem(key, value); } catch (_) { /* In-memory fallback. */ }
    },
    removeItem(key) {
      preferenceCache.set(key, null);
      try { localStorage.removeItem(key); } catch (_) { /* Storage is unavailable. */ }
    },
  };
  // Remove credentials persisted by older dashboard versions.
  preferences.removeItem("adhd_hub_token");
  let authStatus = { password_configured: false, development_mode: false };
  let loginMode = "token";
  let celebrationTimeout;
  const completing = new Set();
  let threadsCache = [];
  let threadsRequest = 0;
  let projectRequest = 0;
  const tzKey = "adhd_hub_timezone";
  let currentView = "open";
  let projectFilter = null;
  let overviewCache = null;
  let detailCache = null;
  let activeScreen = "now";
  let chosenId = preferences.getItem("adhd_hub_chosen_thread");
  let chosenThread = null;
  let focusState = preferences.getItem("adhd_hub_focus_state") || "ready";
  let focusRequest = 0;
  let pauseTarget = null;
  let nowMessage = "";
  let shareFile = null;
  let shareVersion = 0;
  let currentTz =
    preferences.getItem(tzKey) ||
    Intl.DateTimeFormat().resolvedOptions().timeZone ||
    "UTC";

  const $ = (id) => document.getElementById(id);
  const repoUrl = $("repo-link").href;
  const repoDisplayUrl = repoUrl.replace(/^https:\/\//, "");
  const setMsg = (t) => {
    $("msg").textContent = t || "";
    $("settings-msg").textContent = t || "";
  };
  const escapeHtml = (s) =>
    String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");

  async function copyReference(id) {
    try {
      await navigator.clipboard.writeText(id);
      setMsg("Reference copied. You can paste it into your assistant.");
    } catch (_) { setMsg("Clipboard unavailable. Thread reference: " + id); }
  }

  function safeHttpUrl(value) {
    try {
      const url = new URL(value);
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch (_) { return ""; }
  }

  function safeLink(value) {
    return escapeHtml(safeHttpUrl(value) || "#");
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
      { "Content-Type": "application/json", "X-Hub-Request": "1" },
      opts.headers || {}
    );
    const res = await fetch("/api" + path, Object.assign({}, opts, { headers }));
    if (!res.ok) {
      let message = "Something went wrong. Please try again.";
      try {
        const body = await res.json();
        message = typeof body.detail === "string" ? body.detail : "Please check the fields and try again.";
      } catch (_) { /* The server may return a non-JSON gateway error. */ }
      if (res.status === 401 && !path.startsWith("/auth/")) {
        showLogin("Your session ended. Sign in to continue.");
      }
      const err = new Error(message);
      err.status = res.status;
      throw err;
    }
    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res;
  }

  function showLogin(message) {
    ++projectRequest;
    ++threadsRequest;
    ++focusRequest;
    clearTimeout(celebrationTimeout);
    $("celebration").hidden = true;
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    $("app-shell").hidden = true;
    $("login-gate").hidden = false;
    $("login-error").textContent = message || "";
    $("login-token").value = "";
    setLoginMode(authStatus.password_configured ? "password" : "token");
    $("login-token").focus();
  }

  function showApp() {
    $("login-gate").hidden = true;
    $("app-shell").hidden = false;
    $("password-banner").hidden = authStatus.password_configured || authStatus.development_mode;
    showScreen("now");
  }

  async function tryAuth() {
    try {
      await api("/overview");
      showApp();
      return true;
    } catch (e) {
      if (e.status === 401) {
        showLogin("");
        return false;
      }
      showLogin("Could not reach your hub. Check your connection and try again.");
      return false;
    }
  }

  async function handleLogin(ev) {
    ev.preventDefault();
    const value = loginMode === "token" ? $("login-token").value.trim() : $("login-token").value;
    if (!value) return;
    const button = $("login-form").querySelector('button[type="submit"]');
    button.disabled = true;
    button.textContent = "Signing in…";
    $("login-error").textContent = "";
    try {
      await api("/auth/login", { method: "POST", body: JSON.stringify({ [loginMode]: value }) });
      $("login-token").value = "";
      showApp();
      await loadAll();
    } catch (error) {
      if (error.status === 401) { $("login-error").textContent = error.message; $("login-token").focus(); }
      else if (!$("app-shell").hidden) setMsg("Could not load dashboard: " + error.message);
      else $("login-error").textContent = error.status ? error.message : "Could not sign in. Check your connection and try again.";
    } finally {
      button.disabled = false;
      button.textContent = "Sign in";
    }
  }

  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
      overviewCache = null;
      detailCache = null;
      threadsCache = [];
      showLogin("Signed out.");
    } catch (error) {
      setMsg("Could not sign out. Please try again: " + error.message);
    }
  }

  function setLoginMode(mode) {
    loginMode = mode;
    const password = mode === "password";
    $("login-label").textContent = password ? "Password" : "Access token";
    $("login-description").textContent = password ? "Your next step is right where you left it." :
      "Use your hub token to get started. You can create a password once you’re in.";
    $("btn-login-method").textContent = password ? "Use recovery access token" : "Use dashboard password";
    $("btn-login-method").hidden = !authStatus.password_configured;
    $("login-token").type = "password";
    $("btn-show-password").textContent = "Show";
    $("btn-show-password").setAttribute("aria-pressed", "false");
    $("btn-show-password").setAttribute("aria-label", password ? "Show password" : "Show access token");
  }

  async function loadAuthStatus() {
    authStatus = await api("/auth/status");
    setLoginMode(authStatus.password_configured ? "password" : "token");
    $("password-banner").hidden = authStatus.password_configured || authStatus.development_mode;
    $("password-status").textContent = authStatus.development_mode
      ? "Local development mode. Set a private ADHD_HUB_AUTH_TOKEN on your server to enable password setup."
      : authStatus.password_configured ? "Dashboard password is set. Your assistant access token is separate."
      : "Create a password so you can keep the access token in your assistant configuration.";
  }

  function openPasswordDialog() {
    $("settings-dialog").close();
    $("password-title").textContent = authStatus.password_configured ? "Change your password" : "Set a dashboard password";
    $("password-method").value = authStatus.password_configured ? "password" : "token";
    $("password-dialog").showModal();
  }

  async function savePassword(event) {
    event.preventDefault();
    if ($("password-new").value !== $("password-confirm").value) {
      $("password-error").textContent = "The new passwords don’t match yet.";
      $("password-confirm").focus();
      return;
    }
    const button = $("password-form").querySelector('[type="submit"]');
    button.disabled = true;
    $("password-error").textContent = "";
    try {
      await api("/auth/password", { method: "PUT", body: JSON.stringify({
        current_secret: $("password-current").value,
        current_method: $("password-method").value,
        password: $("password-new").value,
      }) });
      $("password-dialog").close();
      await loadAuthStatus();
      setMsg("Password saved. Other browser sessions have been signed out.");
    } catch (error) { $("password-error").textContent = error.message; }
    finally { button.disabled = false; }
  }

  function applyTheme() {
    const selection = $("theme-select").value;
    document.documentElement.dataset.theme = selection === "system"
      ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : selection;
  }

  function renderRewards() {
    const enabled = $("rewards-enabled").checked;
    $("rewards-panel").hidden = !enabled;
    $("rewards-off").hidden = enabled;
    $("daily-goal").disabled = !enabled;
    if (!enabled || !overviewCache) return;
    const total = overviewCache.done || 0;
    const today = overviewCache.done_today || 0;
    const goal = Number($("daily-goal").value);
    $("goal-count").textContent = `${today} / ${goal}`;
    $("daily-progress").max = goal;
    $("daily-progress").value = Math.min(today, goal);
    $("rewards-title").textContent = today >= goal ? "A little win, well earned." : "Small steps add up.";
    $("rewards-caption").textContent = today >= goal ? "You’ve met your goal. It’s okay to leave it here." : "Your progress stays with you. Breaks don’t reset it.";
    const rewards = overviewCache.rewards;
    if (!rewards) return;
    $("reward-level").textContent = `Level ${rewards.level} · ${rewards.xp} XP · ${total} finished`;
    $("rank-name").textContent = rewards.rank.name;
    $("rank-next").textContent = rewards.next_rank
      ? `${rewards.next_rank.remaining} more finished steps to ${rewards.next_rank.name}. Whenever you’re ready.`
      : "You’ve reached Trailblazer. Every little step still counts.";
    $("rank-progress").max = rewards.next_rank ? rewards.next_rank.threshold - rewards.rank.threshold : 1;
    $("rank-progress").value = rewards.next_rank ? total - rewards.rank.threshold : 1;
    $("rank-progress").setAttribute("aria-valuetext", rewards.next_rank ? `${rewards.next_rank.remaining} steps to ${rewards.next_rank.name}` : "Highest rank reached");
    const earned = rewards.badges.filter((badge) => badge.earned);
    $("badge-count").textContent = `${earned.length} of ${rewards.badges.length} earned`;
    $("badges").innerHTML = rewards.badges.map((badge, index) => `
      <li class="badge ${badge.earned ? "earned" : ""}">
        ${badgeIcon(index)}<strong>${escapeHtml(badge.name)}</strong>
        <span class="hint">${badge.threshold} finished ${badge.threshold === 1 ? "step" : "steps"}</span>
        <span class="badge-state">${badge.earned ? "Earned ✓" : `${badge.threshold - total} to go · no deadline`}</span>
      </li>`).join("");
  }

  function badgeIcon(index) {
    const paths = [
      '<path d="m9 16 5 5 10-11"/>',
      '<path d="M9 23v-6m7 6V9m7 14V5"/>',
      '<path d="M16 26V14M16 18C7 18 6 10 7 7c8 0 9 6 9 11Zm0-3c8 0 10-6 9-10-6 0-9 4-9 10Z"/>',
      '<path d="M16 27V11m0 9L7 12m9 3 9-8"/><circle cx="7" cy="9" r="3"/><circle cx="25" cy="5" r="3"/>',
      '<path d="m16 4 4 8 9 1-7 6 2 9-8-4-8 4 2-9-7-6 9-1Z"/>',
      '<path d="m6 11 5 5 5-10 5 10 5-5-3 15H9Z"/>',
    ];
    return `<svg class="badge-symbol" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[index % paths.length]}</svg>`;
  }

  function selectSettingsTab(name, focus = false) {
    document.querySelectorAll("[data-settings-tab]").forEach((tab) => {
      const selected = tab.dataset.settingsTab === name;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      $(tab.getAttribute("aria-controls")).hidden = !selected;
      if (selected && focus) tab.focus();
    });
    $("settings-dialog").querySelector(".settings-content").scrollTop = 0;
  }

  function openSharePreview() {
    const rewards = overviewCache?.rewards;
    if (!rewards || !$("rewards-enabled").checked) return;
    const version = ++shareVersion;
    shareFile = null;
    $("btn-native-share").hidden = true;
    $("share-msg").textContent = "";
    const earned = rewards.badges.filter((badge) => badge.earned);
    const text = `My Progress Hub: ${rewards.rank.name} · Level ${rewards.level} · ${rewards.xp} XP · ${rewards.completed} finished steps.\n${earned.length ? "Milestones: " + earned.map((badge) => badge.name).join(", ") + "." : "A fresh start. One step at a time."}\nSmall steps. Your pace.\n${repoUrl}`;
    $("share-text").value = text;
    const canvas = $("share-card");
    canvas.setAttribute("aria-label", text);
    const ctx = canvas.getContext("2d");
    if (!ctx) { setMsg("Your browser cannot create a progress card."); return; }
    ctx.fillStyle = "#F7F5EF"; ctx.fillRect(0, 0, 1200, 720);
    ctx.fillStyle = "#E4F0E9"; ctx.fillRect(0, 0, 1200, 18);
    ctx.fillStyle = "#176B60"; ctx.beginPath(); ctx.roundRect(64, 58, 64, 64, 18); ctx.fill();
    ctx.strokeStyle = "#F7F5EF"; ctx.lineWidth = 7; ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(82, 102); ctx.lineTo(91, 102); ctx.quadraticCurveTo(104, 102, 104, 89); ctx.lineTo(104, 79); ctx.stroke();
    ctx.fillStyle = "#EFC978"; ctx.beginPath(); ctx.arc(83, 81, 5, 0, 2 * Math.PI); ctx.fill();
    ctx.fillStyle = "#203832"; ctx.font = "bold 30px system-ui, sans-serif"; ctx.fillText("Progress Hub", 148, 101);
    ctx.fillStyle = "#5B6F66"; ctx.font = "20px system-ui, sans-serif"; ctx.fillText("MY HUB’S LITTLE WINS", 64, 188);
    ctx.fillStyle = "#203832"; ctx.font = "bold 76px system-ui, sans-serif"; ctx.fillText(rewards.rank.name, 60, 279);
    ctx.fillStyle = "#176B60"; ctx.font = "32px system-ui, sans-serif";
    ctx.fillText(`Level ${rewards.level}   ·   ${rewards.xp} XP   ·   ${rewards.completed} finished steps`, 64, 343, 1070);
    ctx.fillStyle = "#D4DDD5"; ctx.fillRect(64, 385, 1072, 2);
    ctx.fillStyle = "#5B6F66"; ctx.font = "20px system-ui, sans-serif"; ctx.fillText("EARNED MILESTONES", 64, 437);
    if (!earned.length) { ctx.fillText("A fresh start. One step at a time.", 64, 490); }
    earned.forEach((badge, i) => {
      const x = 64 + (i % 3) * 358, y = 462 + Math.floor(i / 3) * 66;
      ctx.fillStyle = "#FAF0D6"; ctx.beginPath(); ctx.roundRect(x, y, 338, 52, 12); ctx.fill();
      ctx.fillStyle = "#715017"; ctx.font = "bold 21px system-ui, sans-serif"; ctx.fillText("✓ " + badge.name, x + 18, y + 33);
    });
    ctx.fillStyle = "#5B6F66"; ctx.font = "22px system-ui, sans-serif"; ctx.fillText("Small steps. Your pace.", 64, 658);
    ctx.textAlign = "right"; ctx.font = "21px system-ui, sans-serif";
    ctx.fillText(repoDisplayUrl, 1136, 658); ctx.textAlign = "left";
    $("share-dialog").showModal();
    canvas.toBlob((blob) => {
      if (!blob || version !== shareVersion || !$("share-dialog").open) return;
      shareFile = new File([blob], "progress-hub.png", { type: "image/png" });
      try { $("btn-native-share").hidden = !(navigator.share && navigator.canShare?.({ files: [shareFile] })); }
      catch (_) { $("btn-native-share").hidden = true; }
    }, "image/png");
  }

  function celebrate() {
    if (!$("rewards-enabled").checked) return;
    clearTimeout(celebrationTimeout);
    $("celebration").textContent = "One step finished. Take a breath.";
    $("celebration").hidden = false;
    celebrationTimeout = setTimeout(() => { $("celebration").hidden = true; }, 4500);
  }

  function saveRewardPreferences() {
    preferences.setItem("adhd_hub_rewards", String($("rewards-enabled").checked));
    preferences.setItem("adhd_hub_daily_goal", $("daily-goal").value);
    if (!$("rewards-enabled").checked) {
      $("celebration").hidden = true;
      $("share-dialog").close();
    }
    renderRewards();
  }

  async function captureStep(event) {
    event.preventDefault();
    const summary = $("capture-summary").value.trim();
    if (!summary) return;
    const button = $("quick-capture").querySelector('[type="submit"]');
    button.disabled = true;
    $("capture-error").textContent = "";
    try {
      await api("/threads", { method: "POST", body: JSON.stringify({
        summary, project_slug: "unclassified", source_tool: "web",
      }) });
      $("capture-summary").value = "";
      $("capture-dialog").close();
      setMsg("Saved to your inbox.");
      await loadOverview();
      if (activeScreen === "work") await loadThreads();
    } catch (error) {
      if ($("capture-dialog").open) $("capture-error").textContent = "Could not save your thought: " + error.message;
      else setMsg("Thought saved; could not refresh your list.");
    } finally { button.disabled = false; }
  }

  function showScreen(screen) {
    activeScreen = screen;
    ["now", "work", "progress"].forEach((name) => { $(name + "-view").hidden = name !== screen; });
    document.querySelectorAll("[data-screen]").forEach((button) => {
      if (button.dataset.screen === screen) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    if (screen !== "work") { ++projectRequest; ++threadsRequest; }
  }

  async function openWork() {
    showScreen("work");
    await selectProject(projectFilter);
  }

  function rememberFocus() {
    if (chosenId) preferences.setItem("adhd_hub_chosen_thread", chosenId);
    else preferences.removeItem("adhd_hub_chosen_thread");
    preferences.setItem("adhd_hub_focus_state", focusState);
  }

  async function chooseThread(id) {
    const request = ++focusRequest;
    setMsg("Loading your choice…");
    try {
      const thread = await api("/threads/" + encodeURIComponent(id));
      if (request !== focusRequest) return;
      if (!["open", "blocked"].includes(thread.status)) {
        setMsg("That task is already finished. Choose another when you’re ready.");
        if (activeScreen === "work") await loadThreads();
        return;
      }
      chosenId = id;
      chosenThread = thread;
      focusState = thread.paused_at ? "paused" : "ready";
      nowMessage = "";
      rememberFocus();
      showScreen("now");
      renderFocus();
      setMsg("");
      $("focus-title").focus();
    } catch (error) { setMsg("Could not choose this task: " + error.message); }
  }

  async function loadChosenThread() {
    const request = ++focusRequest;
    if (!chosenId) { chosenThread = null; renderFocus(); return; }
    try {
      const thread = await api("/threads/" + encodeURIComponent(chosenId));
      if (request !== focusRequest) return;
      if (!["open", "blocked"].includes(thread.status)) {
        chosenId = null;
        chosenThread = null;
        nowMessage = "That task is finished. You can leave it here or choose another.";
        rememberFocus();
      } else { chosenThread = thread; }
      renderFocus();
    } catch (error) {
      if (request !== focusRequest) return;
      chosenThread = null;
      if (error.status === 404) {
        chosenId = null;
        rememberFocus();
        nowMessage = "That task is no longer available. Choose another when you’re ready.";
      } else { nowMessage = "Could not load your saved task. Retry when your connection returns."; }
      renderFocus();
    }
  }

  async function suggestThread() {
    const button = $("btn-suggest");
    button.disabled = true;
    try {
      const threads = await api("/threads?status=open&limit=100");
      if (activeScreen !== "now") return;
      const candidate = threads.find((thread) => thread.energy === "low") || threads[0];
      if (!candidate) { $("suggestion").textContent = "No open tasks yet. Save a thought to get started."; return; }
      $("suggestion").innerHTML = `<p class="hint">${candidate.energy === "low" ? "A low-energy option" : "One option to consider"}</p><h3>${escapeHtml(candidate.summary)}</h3><button type="button" class="primary" id="btn-accept-suggestion">Choose this</button>`;
      $("btn-accept-suggestion").addEventListener("click", () => chooseThread(candidate.id));
    } catch (error) { setMsg("Could not suggest a task: " + error.message); }
    finally { button.disabled = false; }
  }

  function openPause() {
    pauseTarget = chosenThread?.id;
    if (!pauseTarget) return;
    $("pause-step").value = chosenThread.resume_step || "";
    $("pause-task").textContent = chosenThread.summary;
    $("pause-error").textContent = "";
    $("pause-dialog").showModal();
  }

  async function pauseHere(event) {
    event.preventDefault();
    const step = $("pause-step").value.trim();
    if (!step || !pauseTarget) return;
    const button = $("pause-form").querySelector('[type="submit"]');
    button.disabled = true;
    try {
      await api("/threads/" + encodeURIComponent(pauseTarget) + "/pause", {
        method: "POST", body: JSON.stringify({ next_step: step }),
      });
      focusState = "paused";
      rememberFocus();
      $("pause-dialog").close();
      await loadChosenThread();
      setMsg("Next step saved. You can stop here.");
    } catch (error) { $("pause-error").textContent = error.message; }
    finally { button.disabled = false; }
  }

  function wireNotes(root) {
    root.querySelectorAll("details[data-notes]").forEach((details) => {
      details.addEventListener("toggle", async () => {
        if (!details.open || details.dataset.loaded || details.dataset.loading) return;
        details.dataset.loading = "true";
        const content = details.querySelector(".markdown-body");
        content.textContent = "Loading notes…";
        try {
          const thread = await api("/threads/" + encodeURIComponent(details.dataset.notes));
          content.innerHTML = thread.progress_html || "<p>No saved notes yet.</p>";
          details.dataset.loaded = "true";
        } catch (_) { content.textContent = "Could not load notes. Close and reopen to retry."; }
        finally { delete details.dataset.loading; }
      });
    });
  }

  async function loadPrefs() {
    try {
      const p = await api("/prefs");
      if (p.timezone) {
        currentTz = p.timezone;
        preferences.setItem(tzKey, currentTz);
      }
    } catch (_e) {
      /* keep local */
    }
    if (!preferences.getItem(tzKey + "_initialized")) {
      const local = browserTz();
      if (!currentTz || currentTz === "UTC") currentTz = local;
      preferences.setItem(tzKey, currentTz);
      preferences.setItem(tzKey + "_initialized", "1");
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
      ["Finished this week", o.done_week],
    ]
      .map(
        ([k, v]) =>
          `<span class="stat"><strong>${escapeHtml(v)}</strong> ${escapeHtml(k)}</span>`
      )
      .join("");
    renderRewards();
    const series = o.added_vs_finished || [];
    const wrap = $("chart-wrap");
    const chart = $("chart");
    if (!series.length) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    chart.setAttribute("aria-label", "Last 14 days: " + series.map((day) => `${day.date}: ${day.added} added, ${day.finished} finished`).join("; "));
    const max = Math.max(1, ...series.map((d) => (d.added || 0) + (d.finished || 0)));
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
        return `<button type="button" class="proj ${active}" data-slug="${escapeHtml(p.slug)}" aria-pressed="${projectFilter === p.slug}">
          <div>${escapeHtml(p.slug === "unclassified" ? "Inbox" : p.title || p.slug)}</div>
          <div class="meta">${open} open ${open === 1 ? "step" : "steps"}</div>
        </button>`;
      })
      .join("");
    $("proj-all").classList.toggle("active", !projectFilter);
    $("proj-all").setAttribute("aria-pressed", String(!projectFilter));
    list.querySelectorAll(".proj").forEach((el) => {
      el.addEventListener("click", () => selectProject(el.dataset.slug || null).catch((e) => setMsg(e.message)));
    });
  }

  function fillProjectForm(p) {
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
    $("btn-rename-project").hidden = !!p.unregistered;
    $("btn-delete-project").hidden = !!p.unregistered;
  }

  function renderProjectHeader(p) {
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

  function openProjectDialog(project) {
    if (!project) return;
    fillProjectForm(project);
    $("project-dialog").showModal();
    $("p_title").focus();
  }

  function renderFocus() {
    const card = $("next-card");
    const thread = chosenThread;
    $("focus-title").setAttribute("tabindex", "-1");
    if (!thread) {
      $("focus-eyebrow").textContent = "YOUR CHOICE";
      $("focus-title").textContent = "What would you like to work on?";
      card.className = "next-card empty";
      card.innerHTML = `<p>${escapeHtml(nowMessage || "Choose one task. Everything else can wait.")}</p><div class="next-actions"><button type="button" class="primary" id="btn-choose-work">Choose a task</button><button type="button" class="ghost" id="btn-suggest">Help me choose</button>${chosenId ? '<button type="button" class="ghost" id="btn-retry-focus">Retry saved task</button>' : ""}</div><div id="suggestion" aria-live="polite"></div>`;
      $("btn-choose-work").addEventListener("click", () => openWork().catch((error) => setMsg(error.message)));
      $("btn-suggest").addEventListener("click", suggestThread);
      $("btn-retry-focus")?.addEventListener("click", loadChosenThread);
      return;
    }
    $("focus-eyebrow").textContent = `${focusState === "working" ? "WORKING ON" : focusState === "paused" ? "SAVED FOR YOUR RETURN" : "YOUR CHOICE"} · ${thread.project_slug === "unclassified" ? "Inbox" : thread.project_slug || ""}`;
    $("focus-title").textContent = thread.summary;
    card.className = "next-card has-item";
    card.innerHTML = `
      ${thread.resume_step ? `<div class="resume-step"><p class="eyebrow">NEXT TINY STEP</p><div class="markdown-body">${thread.resume_step_html}</div></div>` : '<p class="start-cue">Start with the smallest part. You can leave a next step whenever you stop.</p>'}
      ${focusState === "working" ? '<p class="work-state" role="status">This is your focus. No timer, no rush.</p>' : ""}
      <div class="next-actions">
        <button type="button" class="primary" id="btn-start">${focusState === "working" ? "Pause here" : focusState === "paused" ? "Resume" : "Start"}</button>
        <button type="button" class="ghost" id="btn-choose-work">Choose another</button>
        <button type="button" class="ghost" data-done="${escapeHtml(thread.id)}">Done</button>
      </div>
      <details class="progress-details"><summary>Where you left off</summary><p class="hint">Saved project notes</p><div class="markdown-body">${thread.progress_html || "<p>No project notes yet. Use Pause here to leave a next step.</p>"}</div></details>`;
    $("btn-start").addEventListener("click", () => {
      if (focusState === "working") { openPause(); return; }
      focusState = "working";
      rememberFocus();
      renderFocus();
      $("btn-start").focus();
    });
    $("btn-choose-work").addEventListener("click", () => openWork().catch((error) => setMsg(error.message)));
    card.querySelector("[data-done]").addEventListener("click", () => markDone(thread.id).catch((error) => setMsg(error.message)));
  }

  function renderThreads(threads) {
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
        currentView === "done" ? "Finished work will appear here when you mark a thread done." :
        currentView === "stale" ? "Nothing waiting here. Return whenever you’re ready." :
        "No open threads here. Save progress from your connected assistant to pick it up later.";
      root.innerHTML = `<p class="hint">${message}</p>`;
      return;
    }
    const projectName = (slug) => {
      if (!slug || slug === "unclassified") return "Inbox";
      const project = (overviewCache?.projects || []).find((item) => item.slug === slug);
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
        const isChosen = t.id === chosenId;
        const statusLabel = t.status === "done" ? "Finished" : currentView === "stale" ? "Waiting" : "Ready";
        return `<article class="thread${isChosen ? " chosen" : ""}" aria-labelledby="thread-title-${index}">
          <div class="thread-topline">
            <span class="thread-number">${index + 1}</span>
            <span class="thread-project">${escapeHtml(projectName(t.project_slug))}</span>
            <span class="thread-status">${escapeHtml(statusLabel)}</span>
          </div>
          <h3 id="thread-title-${index}">${escapeHtml(t.summary)}</h3>
          <div class="thread-meta"><span>${escapeHtml(sourceName(t.source_tool || t.origin))}</span><span>Updated ${escapeHtml(formatWhen(t.updated_at))}</span></div>
          <details class="progress-details" data-notes="${escapeHtml(t.id)}"><summary>Notes &amp; context</summary><div class="markdown-body"></div></details>
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

  async function markDone(id) {
    if (completing.has(id)) return;
    completing.add(id);
    try {
      await api("/threads/mark-done", {
        method: "POST", body: JSON.stringify({ id, note: "Marked done from /ui" }),
      });
      if (chosenId === id) {
        chosenId = null;
        chosenThread = null;
        focusState = "ready";
        nowMessage = "That’s done. You can stop here, or choose another when you’re ready.";
        rememberFocus();
        renderFocus();
      }
      setMsg("Done. That’s one less thing to hold in your head.");
      celebrate();
      await loadAll();
    } finally { completing.delete(id); }
  }

  async function loadThreads() {
    const request = ++threadsRequest;
    const params = new URLSearchParams();
    if (currentView === "stale") params.set("stale", "true");
    else params.set("status", currentView === "done" ? "done" : "open");
    if (projectFilter) params.set("project_slug", projectFilter);
    params.set("limit", "100");
    const threads = await api("/threads?" + params.toString());
    if (request !== threadsRequest) return;
    threadsCache = threads;
    renderThreads(threadsCache);
  }

  async function selectProject(slug) {
    const request = ++projectRequest;
    ++threadsRequest;
    projectFilter = slug || null;
    detailCache = null;
    threadsCache = [];

    renderProjects(overviewCache?.projects || []);
    renderProjectHeader(null);
    $("threads").textContent = "Loading your steps…";
    $("thread-count").textContent = "";
    $("focus-links").replaceChildren();
    if (!projectFilter) {
      $("work-title").textContent = "All projects";
      await loadThreads();
      return;
    }
    $("work-title").textContent = "Loading project…";
    try {
      const detail = await api("/projects/" + encodeURIComponent(projectFilter));
      if (request !== projectRequest) return;
      detailCache = detail;
      fillProjectForm(detailCache);
      $("work-title").textContent = detailCache.slug === "unclassified" ? "Inbox" : detailCache.title || detailCache.slug;
      renderProjectHeader(detailCache);
    } catch (e) {
      if (request !== projectRequest) return;
      $("work-title").textContent = "Project unavailable";
      setMsg("Could not load project: " + e.message);
    }
    if (request === projectRequest) await loadThreads();
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
    const res = await fetch("/api/admin/export", {
      headers: { "X-Hub-Request": "1" },
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
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/admin/import?replace=true", {
      method: "POST",
      headers: { "X-Hub-Request": "1" },
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

  async function loadOpenClaw() {
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

  function openClawPayload() {
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

  async function saveOpenClaw() {
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

  async function testOpenClaw() {
    await saveOpenClaw();
    $("openclaw-msg").textContent = "Sending a private test alert…";
    const result = await api("/openclaw/test", { method: "POST", body: "{}" });
    $("openclaw-msg").textContent = result.message || "Test alert sent.";
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
      repo_url: $("p_repo_url").value.trim() || null,
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
    $("project-dialog").close();
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
      $("project-dialog").close();
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
      $("project-dialog").close();
      setMsg("Project deleted.");
      await loadAll();
    } catch (e) {
      setMsg("Delete failed: " + e.message);
    }
  }

  async function saveSettings() {
    saveRewardPreferences();
    const tz = $("timezone").value || browserTz();
    currentTz = tz;
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
    await loadChosenThread();
    if (activeScreen === "work") await selectProject(projectFilter);
  }

  $("proj-all").addEventListener("click", () => selectProject(null).catch((e) => setMsg(e.message)));
  $("btn-refresh").addEventListener("click", async () => {
    const button = $("btn-refresh");
    button.disabled = true;
    button.textContent = "Refreshing…";
    try { await loadAll(); setMsg("Up to date."); }
    catch (error) { setMsg("Could not refresh: " + error.message); }
    finally { button.disabled = false; button.textContent = "Refresh"; }
  });
  $("btn-settings").addEventListener("click", () => {
    loadForge().catch((error) => setMsg(error.message));
    loadOpenClaw().catch((error) => setMsg(error.message));
    selectSettingsTab("preferences");
    $("settings-theme").value = $("theme-select").value;
    $("mcp-url").value = location.origin + "/mcp";
    $("install-cmd").value =
      'curl -fsSL "' + location.origin + '/install.sh" | sh -s -- .';
    $("settings-msg").textContent = "";
    $("settings-dialog").showModal();
    api("/health").then((health) => {
      $("app-version").textContent = health.version ? `v${health.version}` : "Version unavailable";
    }).catch(() => { $("app-version").textContent = "Version unavailable"; });
  });
  $("btn-close-settings").addEventListener("click", () => $("settings-dialog").close());
  document.querySelectorAll("[data-settings-tab]").forEach((tab) => {
    tab.addEventListener("click", () => selectSettingsTab(tab.dataset.settingsTab));
    tab.addEventListener("keydown", (event) => {
      const tabs = [...document.querySelectorAll("[data-settings-tab]")];
      let index = tabs.indexOf(tab);
      if (event.key === "ArrowRight") index = (index + 1) % tabs.length;
      else if (event.key === "ArrowLeft") index = (index + tabs.length - 1) % tabs.length;
      else if (event.key === "Home") index = 0;
      else if (event.key === "End") index = tabs.length - 1;
      else return;
      event.preventDefault(); selectSettingsTab(tabs[index].dataset.settingsTab, true);
    });
  });
  $("settings-theme").addEventListener("change", () => {
    $("theme-select").value = $("settings-theme").value;
    $("theme-select").dispatchEvent(new Event("change"));
  });
  $("btn-share-progress").addEventListener("click", openSharePreview);
  $("btn-close-share").addEventListener("click", () => $("share-dialog").close());
  $("share-dialog").addEventListener("close", () => { ++shareVersion; shareFile = null; });
  $("btn-download-card").addEventListener("click", () => {
    try {
      const link = document.createElement("a");
      link.download = "progress-hub.png"; link.href = $("share-card").toDataURL("image/png");
      document.body.append(link); link.click(); link.remove();
      $("share-msg").textContent = "Download ready. Share it wherever you like.";
    } catch (_) { $("share-msg").textContent = "Could not download the card. You can copy the text below."; }
  });
  $("btn-copy-progress").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("share-text").value); $("share-msg").textContent = "Progress text copied."; }
    catch (_) { $("share-text").focus(); $("share-text").select(); $("share-msg").textContent = "Select and copy the text above."; }
  });
  $("btn-native-share").addEventListener("click", async () => {
    if (!shareFile) return;
    try { await navigator.share({ files: [shareFile], title: "My Progress Hub", text: $("share-text").value }); }
    catch (error) { if (error.name !== "AbortError") $("share-msg").textContent = "Sharing unavailable. Download the PNG or copy the text instead."; }
  });
  $("btn-copy-mcp").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("mcp-url").value); setMsg("MCP URL copied."); }
    catch (_) { $("mcp-url").focus(); $("mcp-url").select(); setMsg("Select and copy the MCP URL above."); }
  });
  $("btn-copy-install").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("install-cmd").value); setMsg("Install command copied."); }
    catch (_) { $("install-cmd").focus(); $("install-cmd").select(); setMsg("Select and copy the install command above."); }
  });
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
  $("btn-save-openclaw").addEventListener("click", () =>
    saveOpenClaw().catch((e) => { $("openclaw-msg").textContent = e.message; })
  );
  $("btn-test-openclaw").addEventListener("click", () =>
    testOpenClaw().catch((e) => { $("openclaw-msg").textContent = e.message; })
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
  $("project-form").addEventListener("submit", (event) => {
    event.preventDefault();
    saveProject().catch((e) => setMsg(String(e)));
  });
  $("btn-close-project").addEventListener("click", () => $("project-dialog").close());
  $("btn-edit-project").addEventListener("click", () => openProjectDialog(detailCache));
  $("btn-rename-project").addEventListener("click", () => renameProject());
  $("btn-delete-project").addEventListener("click", () => deleteProject());
  $("btn-new-project").addEventListener("click", () => {
    const newProject = {
      title: "",
      slug: "",
      repo_url: "",
      workspace_paths: [],
      unregistered: true,
    };
    fillProjectForm(newProject);
    $("p_slug").readOnly = false;
    setMsg("Creating a new project.");
    $("project-dialog").showModal();
    $("p_title").focus();
  });

  $("thread-search").addEventListener("input", () => renderThreads(threadsCache));
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => {
        t.classList.remove("active");
        t.setAttribute("aria-pressed", "false");
      });
      tab.classList.add("active");
      tab.setAttribute("aria-pressed", "true");
      currentView = tab.dataset.view;
      loadThreads().catch((e) => setMsg(String(e)));
    });
  });

  $("theme-select").value = preferences.getItem("adhd_hub_theme") || "system";
  if (!$("theme-select").value) $("theme-select").value = "system";
  applyTheme();
  $("theme-select").addEventListener("change", () => {
    preferences.setItem("adhd_hub_theme", $("theme-select").value);
    $("settings-theme").value = $("theme-select").value;
    applyTheme();
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);
  $("rewards-enabled").checked = preferences.getItem("adhd_hub_rewards") === "true";
  const savedGoal = preferences.getItem("adhd_hub_daily_goal") || "1";
  $("daily-goal").value = ["1", "3", "5"].includes(savedGoal) ? savedGoal : "1";
  $("rewards-enabled").addEventListener("change", saveRewardPreferences);
  $("daily-goal").addEventListener("change", saveRewardPreferences);
  document.querySelectorAll("[data-screen]").forEach((button) => {
    button.addEventListener("click", async () => {
      setMsg("");
      showScreen(button.dataset.screen);
      try {
        if (activeScreen === "work") await selectProject(projectFilter);
        else if (activeScreen === "now") await loadChosenThread();
        else await loadOverview();
      } catch (error) { setMsg(error.message); }
    });
  });
  $("btn-capture").addEventListener("click", () => {
    $("capture-error").textContent = "";
    $("capture-dialog").showModal();
    $("capture-summary").focus();
  });
  $("btn-cancel-capture").addEventListener("click", () => $("capture-dialog").close());
  $("pause-form").addEventListener("submit", pauseHere);
  $("btn-cancel-pause").addEventListener("click", () => $("pause-dialog").close());
  $("btn-login-method").addEventListener("click", () => {
    setLoginMode(loginMode === "password" ? "token" : "password");
    $("login-token").value = "";
    $("login-error").textContent = "";
    $("login-token").focus();
  });
  $("btn-show-password").addEventListener("click", () => {
    const show = $("login-token").type === "password";
    $("login-token").type = show ? "text" : "password";
    $("btn-show-password").textContent = show ? "Hide" : "Show";
    $("btn-show-password").setAttribute("aria-pressed", String(show));
    $("btn-show-password").setAttribute("aria-label", `${show ? "Hide" : "Show"} ${loginMode === "password" ? "password" : "access token"}`);
  });
  $("btn-setup-password").addEventListener("click", openPasswordDialog);
  $("btn-manage-password").addEventListener("click", openPasswordDialog);
  $("password-form").addEventListener("submit", savePassword);
  $("btn-cancel-password").addEventListener("click", () => $("password-dialog").close());
  $("password-dialog").addEventListener("close", () => {
    $("password-form").reset();
    $("password-error").textContent = "";
  });
  $("quick-capture").addEventListener("submit", captureStep);
  fillTimezoneSelect(currentTz);
  loadAuthStatus().then(() => tryAuth())
    .then((ok) => (ok ? loadAll() : null))
    .catch(() => showLogin("Could not reach your hub. Check your connection and try again."));
})();
