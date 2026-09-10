import { state, preferences, $, setMsg, initRepoLinks } from './state.js';
import { api } from './api.js';
import { handleLogin, loadAuthStatus, logout, openPasswordDialog, savePassword, setLoginMode, showLogin, tryAuth } from './auth.js';
import { fillTimezoneSelect } from './dom.js';
import { loadAll, loadOverview } from './load.js';
import { captureStep, loadChosenThread, openReminderDialog, pauseHere, renderDriftBanner, saveReminder, startFocusSession, toggleFocusMode, toggleReminderDue, updateFocusModeUi } from './now.js';
import { openSharePreview, saveRewardPreferences } from './progress.js';
import { showScreen } from './screens.js';
import { approveCliConnect, exportBackup, importBackup, importForgeInbox, loadCliSessions, loadForge, loadOpenClaw, offerPendingConnect, saveForge, saveOpenClaw, saveSettings, scanForgeImport, selectSettingsTab, syncForge, testOpenClaw } from './settings.js';
import { applyTheme } from './theme.js';
import { archiveProject, deleteProject, fillProjectForm, loadThreads, openProjectDialog, renameProject, renderThreads, restoreProject, saveProject, selectProject } from './work.js';

initRepoLinks();

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
  loadCliSessions().catch(() => {});
  selectSettingsTab("preferences");
  $("settings-theme").value = $("theme-select").value;
  $("mcp-url").value = location.origin + "/mcp";
  $("install-cmd").value =
    'curl -fsSL "' + location.origin + '/install.sh" | sh -s -- .';
  $("install-cmd-win").value =
    'irm "' + location.origin + '/install.ps1" | iex';
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
$("share-dialog").addEventListener("close", () => { ++state.shareVersion; state.shareFile = null; });
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
  if (!state.shareFile) return;
  try { await navigator.share({ files: [state.shareFile], title: "My Progress Hub", text: $("share-text").value }); }
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
$("btn-copy-install-win").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText($("install-cmd-win").value); setMsg("Windows install command copied."); }
  catch (_) { $("install-cmd-win").focus(); $("install-cmd-win").select(); setMsg("Select and copy the Windows install command above."); }
});
$("btn-allow-cli").addEventListener("click", () =>
  approveCliConnect($("cli-connect-code-input").value, "cli-connect-msg").catch((e) => {
    $("cli-connect-msg").textContent = e.message;
  })
);
$("cli-connect-dialog").querySelector("form").addEventListener("submit", (event) => {
  if (event.submitter && event.submitter.value === "cancel") return;
  event.preventDefault();
  approveCliConnect($("cli-connect-code-label").textContent, "cli-connect-dialog-msg")
    .then((result) => {
      if (result) $("cli-connect-dialog").close();
    })
    .catch((e) => {
      $("cli-connect-dialog-msg").textContent = e.message;
    });
});
$("btn-logout").addEventListener("click", () => logout());
$("login-form").addEventListener("submit", (e) =>
  handleLogin(e).catch((err) => {
    $("login-error").textContent = String(err.message || err);
  }).then(() => {
    if (!$("app-shell").hidden) offerPendingConnect();
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
$("btn-import-inbox").addEventListener("click", () =>
  importForgeInbox().catch((e) => setMsg(String(e)))
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
$("btn-edit-project").addEventListener("click", () => openProjectDialog(state.detailCache));
$("btn-rename-project").addEventListener("click", () => renameProject());
$("btn-delete-project").addEventListener("click", () => deleteProject());
$("btn-archive-project").addEventListener("click", () => archiveProject().catch((e) => setMsg(String(e))));
$("btn-restore-project").addEventListener("click", () => restoreProject().catch((e) => setMsg(String(e))));
$("btn-focus-mode").addEventListener("click", toggleFocusMode);
$("focus-minutes").addEventListener("change", () => {
  if (state.focusModeOn && state.focusState === "working") startFocusSession();
});
$("btn-new-reminder").addEventListener("click", openReminderDialog);
$("btn-cancel-reminder").addEventListener("click", () => $("reminder-dialog").close());
$("reminder-kind").addEventListener("change", toggleReminderDue);
$("reminder-form").addEventListener("submit", (e) => saveReminder(e).catch((err) => setMsg(String(err))));
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

$("thread-search").addEventListener("input", () => renderThreads(state.threadsCache));
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => {
      t.classList.remove("active");
      t.setAttribute("aria-pressed", "false");
    });
    tab.classList.add("active");
    tab.setAttribute("aria-pressed", "true");
    state.currentView = tab.dataset.view;
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
    renderDriftBanner();
    try {
      if (state.activeScreen === "work") await selectProject(state.projectFilter);
      else if (state.activeScreen === "now") await loadChosenThread();
      else await loadOverview();
    } catch (error) { setMsg(error.message); }
  });
});
updateFocusModeUi();
$("btn-capture").addEventListener("click", () => {
  $("capture-error").textContent = "";
  $("capture-dialog").showModal();
  $("capture-summary").focus();
});
$("btn-cancel-capture").addEventListener("click", () => $("capture-dialog").close());
$("pause-form").addEventListener("submit", pauseHere);
$("btn-cancel-pause").addEventListener("click", () => $("pause-dialog").close());
$("btn-login-method").addEventListener("click", () => {
  setLoginMode(state.loginMode === "password" ? "token" : "password");
  $("login-token").value = "";
  $("login-error").textContent = "";
  $("login-token").focus();
});
$("btn-show-password").addEventListener("click", () => {
  const show = $("login-token").type === "password";
  $("login-token").type = show ? "text" : "password";
  $("btn-show-password").textContent = show ? "Hide" : "Show";
  $("btn-show-password").setAttribute("aria-pressed", String(show));
  $("btn-show-password").setAttribute("aria-label", `${show ? "Hide" : "Show"} ${state.loginMode === "password" ? "password" : "access token"}`);
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
fillTimezoneSelect(state.currentTz);
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/ui/sw.js", { scope: "/ui/" }).catch(() => {});
}
loadAuthStatus().then(() => tryAuth())
  .then((ok) => (ok ? loadAll() : null))
  .then(() => offerPendingConnect())
  .catch(() => showLogin("Could not reach your hub. Check your connection and try again."));
