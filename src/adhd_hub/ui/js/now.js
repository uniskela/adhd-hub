import { state, preferences, completing, prefersReducedMotion, $, setMsg, escapeHtml } from './state.js';
import { api } from './api.js';
import { formatWhen } from './dom.js';
import { loadAll, loadOverview } from './load.js';
import { celebrate } from './progress.js';
import { openWork, showScreen } from './screens.js';
import { loadThreads } from './work.js';

export function rememberFocus() {
    if (state.chosenId) preferences.setItem("adhd_hub_chosen_thread", state.chosenId);
    else preferences.removeItem("adhd_hub_chosen_thread");
    preferences.setItem("adhd_hub_focus_state", state.focusState);
  }
export async function chooseThread(id) {
    const request = ++state.focusRequest;
    setMsg("Loading your choice…");
    try {
      const thread = await api("/threads/" + encodeURIComponent(id));
      if (request !== state.focusRequest) return;
      if (!["open", "blocked"].includes(thread.status)) {
        setMsg("That task is already finished. Choose another when you’re ready.");
        if (state.activeScreen === "work") await loadThreads();
        return;
      }
      state.chosenId = id;
      state.chosenThread = thread;
      state.focusState = thread.paused_at ? "paused" : "ready";
      state.nowMessage = "";
      rememberFocus();
      showScreen("now");
      renderFocus();
      setMsg("");
      $("focus-title").focus();
    } catch (error) { setMsg("Could not choose this task: " + error.message); }
  }
export async function loadChosenThread() {
    const request = ++state.focusRequest;
    if (!state.chosenId) { state.chosenThread = null; renderFocus(); return; }
    try {
      const thread = await api("/threads/" + encodeURIComponent(state.chosenId));
      if (request !== state.focusRequest) return;
      if (!["open", "blocked"].includes(thread.status)) {
        state.chosenId = null;
        state.chosenThread = null;
        state.nowMessage = "That task is finished. You can leave it here or choose another.";
        rememberFocus();
      } else { state.chosenThread = thread; }
      renderFocus();
    } catch (error) {
      if (request !== state.focusRequest) return;
      state.chosenThread = null;
      if (error.status === 404) {
        state.chosenId = null;
        rememberFocus();
        state.nowMessage = "That task is no longer available. Choose another when you’re ready.";
      } else { state.nowMessage = "Could not load your saved task. Retry when your connection returns."; }
      renderFocus();
    }
  }
export async function suggestThread() {
    const button = $("btn-suggest");
    button.disabled = true;
    try {
      const threads = await api("/threads?status=open&limit=100");
      if (state.activeScreen !== "now") return;
      const candidate = threads.find((thread) => thread.energy === "low") || threads[0];
      if (!candidate) { $("suggestion").textContent = "No open tasks yet. Save a thought to get started."; return; }
      $("suggestion").innerHTML = `<p class="hint">${candidate.energy === "low" ? "A low-energy option" : "One option to consider"}</p><h3>${escapeHtml(candidate.summary)}</h3><button type="button" class="primary" id="btn-accept-suggestion">Choose this</button>`;
      $("btn-accept-suggestion").addEventListener("click", () => chooseThread(candidate.id));
    } catch (error) { setMsg("Could not suggest a task: " + error.message); }
    finally { button.disabled = false; }
  }
export function openPause() {
    state.pauseTarget = state.chosenThread?.id;
    if (!state.pauseTarget) return;
    $("pause-step").value = state.chosenThread.resume_step || "";
    $("pause-task").textContent = state.chosenThread.summary;
    $("pause-error").textContent = "";
    $("pause-dialog").showModal();
  }
export async function pauseHere(event) {
    event.preventDefault();
    const step = $("pause-step").value.trim();
    if (!step || !state.pauseTarget) return;
    const button = $("pause-form").querySelector('[type="submit"]');
    button.disabled = true;
    try {
      await api("/threads/" + encodeURIComponent(state.pauseTarget) + "/pause", {
        method: "POST", body: JSON.stringify({ next_step: step }),
      });
      state.focusState = "paused";
      rememberFocus();
      $("pause-dialog").close();
      await loadChosenThread();
      setMsg("Next step saved. You can stop here.");
    } catch (error) { $("pause-error").textContent = error.message; }
    finally { button.disabled = false; }
  }
export function wireNotes(root) {
    root.querySelectorAll("details[data-notes]").forEach((details) => {
      if (details.dataset.notesWired) return;
      details.dataset.notesWired = "true";
      details.addEventListener("toggle", async () => {
        if (!details.open) return;
        // Fixed overlay: only one Notes panel at a time.
        document.querySelectorAll("details[data-notes][open]").forEach((other) => {
          if (other !== details) other.open = false;
        });
        if (details.dataset.loaded || details.dataset.loading) return;
        details.dataset.loading = "true";
        const content =
          details.querySelector(".notes-scroll") ||
          details.querySelector(".markdown-body");
        if (!content) {
          delete details.dataset.loading;
          return;
        }
        content.textContent = "Loading notes…";
        try {
          const thread = await api("/threads/" + encodeURIComponent(details.dataset.notes));
          content.innerHTML = thread.progress_html || "<p>No saved notes yet.</p>";
          details.dataset.loaded = "true";
          // Force layout after inject so flex scroll height resolves on first open.
          void content.offsetHeight;
        } catch (_) {
          content.textContent = "Could not load notes. Close and reopen to retry.";
        } finally {
          delete details.dataset.loading;
        }
      });
    });
  }
export async function captureStep(event) {
    event.preventDefault();
    const summary = $("capture-summary").value.trim();
    if (!summary) return;
    const asThread = $("capture-as-thread").checked;
    const button = $("quick-capture").querySelector('[type="submit"]');
    button.disabled = true;
    $("capture-error").textContent = "";
    try {
      if (asThread) {
        await api("/threads", { method: "POST", body: JSON.stringify({
          summary, project_slug: "unclassified", source_tool: "web",
        }) });
        setMsg("Saved as an open task in your inbox.");
      } else {
        await api("/progress", {
          method: "POST",
          body: JSON.stringify({
            project_slug: "unclassified",
            title: summary.slice(0, 80),
            content: `## Capture\n- ${summary}`,
            source_tool: "web",
            create_thread_if_missing: false,
          }),
        });
        setMsg("Thought saved to inbox notes (no open task).");
      }
      $("capture-summary").value = "";
      $("capture-dialog").close();
      await loadOverview();
      if (state.activeScreen === "work") await loadThreads();
    } catch (error) {
      if ($("capture-dialog").open) $("capture-error").textContent = "Could not save your thought: " + error.message;
      else setMsg("Thought saved; could not refresh your list.");
    } finally { button.disabled = false; }
  }
export function renderFocus() {
    const card = $("next-card");
    const thread = state.chosenThread;
    $("focus-title").setAttribute("tabindex", "-1");
    updateFocusModeUi();
    if (!thread) {
      $("focus-eyebrow").textContent = "YOUR CHOICE";
      $("focus-title").textContent = "What would you like to work on?";
      card.className = "next-card empty";
      card.innerHTML = `<p>${escapeHtml(state.nowMessage || "Choose one task. Everything else can wait.")}</p><div class="next-actions"><button type="button" class="primary" id="btn-choose-work">Choose a task</button><button type="button" class="ghost" id="btn-suggest">Help me choose</button>${state.chosenId ? '<button type="button" class="ghost" id="btn-retry-focus">Retry saved task</button>' : ""}</div><div id="suggestion" aria-live="polite"></div>`;
      $("btn-choose-work").addEventListener("click", () => openWork().catch((error) => setMsg(error.message)));
      $("btn-suggest").addEventListener("click", suggestThread);
      $("btn-retry-focus")?.addEventListener("click", loadChosenThread);
      return;
    }
    const returning = state.focusState === "paused" && !!thread.resume_step;
    $("focus-eyebrow").textContent = `${
      state.focusState === "working"
        ? "WORKING ON"
        : returning
          ? "WHERE YOU LEFT OFF"
          : state.focusState === "paused"
            ? "SAVED FOR YOUR RETURN"
            : "YOUR CHOICE"
    } · ${thread.project_slug === "unclassified" ? "Inbox" : thread.project_slug || ""}`;
    $("focus-title").textContent = thread.summary;
    card.className = "next-card has-item";
    const resumeBlock = thread.resume_step
      ? `<div class="resume-step${returning ? " resume-step-prominent" : ""}"><p class="eyebrow">${returning ? "PICK UP HERE" : "NEXT TINY STEP"}</p><div class="markdown-body">${thread.resume_step_html}</div>${returning ? '<p class="hint welcome-back">Welcome back. One small step is enough.</p>' : ""}</div>`
      : '<p class="start-cue">Start with the smallest part. You can leave a next step whenever you stop.</p>';
    card.innerHTML = `
      ${resumeBlock}
      ${state.focusState === "working" ? `<p class="work-state" role="status">${state.focusModeOn ? "Focus mode is on — stay with this project when you can." : "This is your focus. No timer, no rush."}</p>` : ""}
      <div class="next-actions">
        <button type="button" class="primary" id="btn-start">${state.focusState === "working" ? "Pause here" : returning || state.focusState === "paused" ? "Resume" : "Start"}</button>
        <button type="button" class="ghost" id="btn-choose-work">Choose another</button>
        <button type="button" class="ghost" data-done="${escapeHtml(thread.id)}">Done</button>
      </div>
      <details class="progress-details"><summary>Project notes</summary><p class="hint">Saved project notes</p><div class="markdown-body">${thread.progress_html || "<p>No project notes yet. Use Pause here to leave a next step.</p>"}</div></details>`;
    $("btn-start").addEventListener("click", () => {
      if (state.focusState === "working") { openPause(); return; }
      state.focusState = "working";
      rememberFocus();
      if (state.focusModeOn) startFocusSession();
      renderFocus();
      $("btn-start").focus();
    });
    $("btn-choose-work").addEventListener("click", () => openWork().catch((error) => setMsg(error.message)));
    card.querySelector("[data-done]").addEventListener("click", () => markDone(thread.id).catch((error) => setMsg(error.message)));
  }
export async function markDone(id) {
    if (completing.has(id)) return;
    completing.add(id);
    try {
      await api("/threads/mark-done", {
        method: "POST", body: JSON.stringify({ id, note: "Marked done from /ui" }),
      });
      if (state.chosenId === id) {
        state.chosenId = null;
        state.chosenThread = null;
        state.focusState = "ready";
        state.nowMessage = "That’s done. You can stop here, or choose another when you’re ready.";
        rememberFocus();
        renderFocus();
      }
      setMsg("Done. That’s one less thing to hold in your head.");
      celebrate();
      await loadAll();
    } finally { completing.delete(id); }
  }
export function renderReminders(due, all) {
    const banner = $("reminder-banner");
    const strip = $("now-reminders");
    const dueList = due || [];
    // Only surface due reminders — snoozed/future items stay quiet until due.
    if (!dueList.length) {
      banner.hidden = true;
      banner.innerHTML = "";
      strip.hidden = true;
      strip.innerHTML = "";
      return;
    }
    const items = dueList
      .map((r) => {
        const dueLabel = r.due_at ? formatWhen(r.due_at) : r.kind;
        return `<div class="pending-item" data-reminder="${escapeHtml(r.id)}">
          <div>
            <div>${escapeHtml(r.message)}</div>
            <div class="meta">${escapeHtml(String(r.kind))} · ${escapeHtml(dueLabel)}</div>
          </div>
          <div class="actions" style="margin:0">
            <button type="button" class="ghost compact" data-snooze="${escapeHtml(r.id)}">Snooze 1h</button>
            <button type="button" class="ghost compact" data-dismiss-reminder="${escapeHtml(r.id)}">Dismiss</button>
          </div>
        </div>`;
      })
      .join("");
    banner.hidden = false;
    banner.innerHTML = `<h2>Reminders</h2><p class="hint">Due now — gentle nudges, not alarms.</p>${items}`;
    banner.querySelectorAll("[data-snooze]").forEach((btn) =>
      btn.addEventListener("click", () => snoozeReminder(btn.dataset.snooze))
    );
    banner.querySelectorAll("[data-dismiss-reminder]").forEach((btn) =>
      btn.addEventListener("click", () => dismissReminder(btn.dataset.dismissReminder))
    );
    if (state.activeScreen === "now") {
      strip.hidden = false;
      strip.innerHTML = `<p class="eyebrow">REMINDERS</p>${dueList
        .slice(0, 3)
        .map((r) => `<p>${escapeHtml(r.message)}</p>`)
        .join("")}`;
    } else {
      strip.hidden = true;
      strip.innerHTML = "";
    }
  }
export function renderDriftBanner() {
    const el = $("drift-banner");
    if (!state.focusModeOn || state.activeScreen !== "work" || !state.chosenThread) {
      el.hidden = true;
      el.innerHTML = "";
      return;
    }
    el.hidden = false;
    el.innerHTML = `
      <div>
        <strong>Still focusing on ${escapeHtml(state.chosenThread.summary)}</strong>
        <p class="hint">My work is available — return to Now when you’re ready.</p>
      </div>
      <button type="button" class="primary compact" id="btn-return-focus">Back to Now</button>`;
    $("btn-return-focus").addEventListener("click", () => {
      showScreen("now");
      renderFocus();
    });
  }
export async function snoozeReminder(id) {
    try {
      await api(`/reminders/${encodeURIComponent(id)}/snooze`, {
        method: "POST",
        body: JSON.stringify({ minutes: 60 }),
      });
      setMsg("Reminder snoozed for an hour.");
      await loadOverview();
    } catch (e) {
      setMsg("Could not snooze reminder: " + e.message);
    }
  }
export async function dismissReminder(id) {
    try {
      await api(`/reminders/${encodeURIComponent(id)}/dismiss`, {
        method: "POST",
        body: "{}",
      });
      setMsg("Reminder dismissed.");
      await loadOverview();
    } catch (e) {
      setMsg("Could not dismiss reminder: " + e.message);
    }
  }
export function openReminderDialog() {
    $("reminder-error").textContent = "";
    $("reminder-message").value = "";
    $("reminder-kind").value = "once";
    const local = new Date(Date.now() + 60 * 60 * 1000);
    const pad = (n) => String(n).padStart(2, "0");
    $("reminder-due").value = `${local.getFullYear()}-${pad(local.getMonth() + 1)}-${pad(local.getDate())}T${pad(local.getHours())}:${pad(local.getMinutes())}`;
    toggleReminderDue();
    $("reminder-dialog").showModal();
    $("reminder-message").focus();
  }
export function toggleReminderDue() {
    const once = $("reminder-kind").value === "once";
    $("reminder-due").hidden = !once;
    $("reminder-due-label").hidden = !once;
    $("reminder-due").required = once;
  }
export async function saveReminder(event) {
    event.preventDefault();
    const message = $("reminder-message").value.trim();
    if (!message) return;
    const kind = $("reminder-kind").value;
    const payload = { message, kind };
    if (kind === "once") {
      const raw = $("reminder-due").value;
      if (!raw) {
        $("reminder-error").textContent = "Choose a due time.";
        return;
      }
      payload.due_at = new Date(raw).toISOString();
    }
    const button = $("reminder-form").querySelector('[type="submit"]');
    button.disabled = true;
    try {
      await api("/reminders", { method: "POST", body: JSON.stringify(payload) });
      $("reminder-dialog").close();
      setMsg("Reminder saved.");
      await loadOverview();
    } catch (e) {
      $("reminder-error").textContent = e.message;
    } finally {
      button.disabled = false;
    }
  }
export function startFocusSession() {
    const minutes = Number($("focus-minutes").value || 25);
    state.focusEndsAt = Date.now() + minutes * 60 * 1000;
    preferences.setItem("adhd_hub_focus_ends_at", String(state.focusEndsAt));
    if (state.focusTimerId) {
      clearInterval(state.focusTimerId);
      state.focusTimerId = null;
    }
    tickFocusSession();
  }
export function clearFocusSession() {
    state.focusEndsAt = 0;
    preferences.removeItem("adhd_hub_focus_ends_at");
    if (state.focusTimerId) {
      clearInterval(state.focusTimerId);
      state.focusTimerId = null;
    }
    const el = $("focus-session");
    el.hidden = true;
    el.textContent = "";
  }
export function tickFocusSession() {
    const el = $("focus-session");
    if (!state.focusModeOn || !state.focusEndsAt) {
      if (!state.focusModeOn) clearFocusSession();
      return;
    }
    const remaining = state.focusEndsAt - Date.now();
    if (remaining <= 0) {
      el.hidden = false;
      el.textContent = "Session complete. Pause here or keep going gently.";
      if (state.focusTimerId) {
        clearInterval(state.focusTimerId);
        state.focusTimerId = null;
      }
      // Clear end marker so the next Start can begin a fresh session.
      state.focusEndsAt = 0;
      preferences.removeItem("adhd_hub_focus_ends_at");
      return;
    }
    const mins = Math.floor(remaining / 60000);
    const secs = Math.floor((remaining % 60000) / 1000);
    el.hidden = false;
    el.textContent = prefersReducedMotion()
      ? `About ${mins + (secs > 0 ? 1 : 0)} min left in this focus session.`
      : `Focus session · ${mins}:${String(secs).padStart(2, "0")} left`;
    if (!state.focusTimerId && !prefersReducedMotion()) {
      state.focusTimerId = setInterval(tickFocusSession, 1000);
    } else if (!state.focusTimerId && prefersReducedMotion()) {
      state.focusTimerId = setInterval(tickFocusSession, 15000);
    }
  }
export function updateFocusModeUi() {
    document.body.classList.toggle("focus-mode", state.focusModeOn);
    const btn = $("btn-focus-mode");
    btn.setAttribute("aria-pressed", String(state.focusModeOn));
    btn.textContent = state.focusModeOn ? "Exit focus" : "Focus mode";
    $("focus-timer-wrap").hidden = !state.focusModeOn;
    if (state.focusModeOn) tickFocusSession();
    else clearFocusSession();
    renderDriftBanner();
  }
export function toggleFocusMode() {
    state.focusModeOn = !state.focusModeOn;
    preferences.setItem("adhd_hub_focus_mode", String(state.focusModeOn));
    if (state.focusModeOn) {
      if (state.focusState === "working") startFocusSession();
      else clearFocusSession();
      showScreen("now");
    } else {
      clearFocusSession();
    }
    updateFocusModeUi();
    renderFocus();
  }
