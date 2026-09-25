import { state, preferences, completing, prefersReducedMotion, $, setMsg, escapeHtml } from './state.js';
import { api } from './api.js';
import { copyText, formatNotesTimes, formatWhen } from './dom.js';
import { loadAll, loadOverview } from './load.js';
import { celebrate } from './progress.js';
import { openWork, showScreen } from './screens.js';
import { loadThreads } from './work.js';

/** Thread id currently shown in the Notes reader (for Summarise). */
let notesThreadId = null;
/** Resolve display title for a project slug from the overview cache. */
export function projectTitleForSlug(slug) {
    if (!slug || slug === "unclassified") return "Inbox";
    const project = (state.overviewCache?.projects || []).find((item) => item.slug === slug);
    const title = project?.title;
    if (typeof title === "string" && title.trim()) return title.trim();
    return slug;
  }

/**
 * Safe display title for Now / pause / focus chrome.
 * GET /threads/{id} once merged a notes-summary *object* onto `summary`
 * (or null), which rendered as "[object Object]" or blank — prefer strings only.
 * @param {object | null | undefined} thread
 * @returns {string}
 */
export function threadDisplayTitle(thread) {
    if (!thread || typeof thread !== "object") return "";
    const raw = thread.summary;
    if (typeof raw === "string") return raw.trim();
    // Legacy clobber: notes card parked under summary — never stringify it.
    if (raw && typeof raw === "object") return "";
    return "";
  }

/**
 * ADHD-scannable prompt for a coding agent, from thread public fields already on Now.
 * Omits empty sections; caps Next at 3 and progress snippet length.
 * Omits Progress when it is only a milestone/boilerplate wall (Resume/Next/Goal/Focus stay).
 * @param {object} thread
 * @param {{ projectTitle?: string }} [opts]
 */
export function isBoilerplateProgressSnippet(snippet) {
    const text = String(snippet || "").trim();
    if (!text) return true;
    if (/^(thread\s+upserted\s+from|checkpoint(?:ed)?\s+from|progress\s+(?:update|note)\s+from|upsert(?:ed)?\s+from)\b/i.test(text)) {
      return true;
    }
    const bits = text.split(/\s+—\s+/).map((b) => b.trim()).filter(Boolean);
    if (!bits.length) return true;
    const fieldish = bits.filter((b) =>
      /^(Title|Goal|Focus|Next|Blocked|Resume|Status)\s*→/i.test(b)
      || /^Unblocked$/i.test(b)
      || /^Started:\s/i.test(b)
      || /^(thread\s+upserted\s+from|checkpoint(?:ed)?\s+from)\b/i.test(b)
    );
    // Milestone / system checkpoint lines dominate Progress noise.
    return fieldish.length >= 1 && fieldish.length >= Math.ceil(bits.length / 2);
  }

export function buildCodingAgentPrompt(thread, opts = {}) {
    if (!thread) return "";
    const lines = [
      "Continue this ADHD Hub thread as a coding agent.",
      "",
      "Open the repo and any linked forge issue, then continue from Resume / Next. Checkpoint with Hub upsert_progress when you pause.",
      "",
      "## Project",
    ];
    const slug = thread.project_slug || "";
    const title = opts.projectTitle || (slug === "unclassified" ? "Inbox" : slug);
    if (slug) lines.push(`- slug: \`${slug}\``);
    if (title) lines.push(`- title: ${title}`);
    if (thread.summary && typeof thread.summary === "string") {
      lines.push(`- thread: ${thread.summary.trim()}`);
    } else {
      const title = threadDisplayTitle(thread);
      if (title) lines.push(`- thread: ${title}`);
    }
    if (thread.id) lines.push(`- thread_id: \`${thread.id}\``);
    lines.push("");

    const issueNum = thread.forge_issue_number;
    const issueUrl = thread.forge_issue_url;
    if (issueNum != null || issueUrl) {
      lines.push("## Linked forge issue");
      if (issueNum != null) lines.push(`- number: #${issueNum}`);
      if (issueUrl) lines.push(`- url: ${issueUrl}`);
      lines.push("");
    }

    lines.push("## Continuity");
    const goal = String(thread.goal || "").trim();
    const focus = String(thread.focus || "").trim();
    const blocked = String(thread.blocked_reason || "").trim();
    const resume = String(thread.resume_step || "").trim();
    const nextSteps = (Array.isArray(thread.next_steps) ? thread.next_steps : [])
      .map((step) => String(step || "").trim())
      .filter(Boolean)
      .slice(0, 3);
    const snippet = String(thread.progress_snippet || "").trim().slice(0, 800);
    const includeProgress = snippet && !isBoilerplateProgressSnippet(snippet);

    if (goal) {
      lines.push("**Goal**", "", goal, "");
    }
    if (focus) {
      lines.push("**Focus**", "", focus, "");
    }
    if (nextSteps.length) {
      lines.push("**Next**", "");
      nextSteps.forEach((step, i) => lines.push(`${i + 1}. ${step}`));
      lines.push("");
    }
    if (blocked) {
      lines.push("**Blocked**", "", blocked, "");
    }
    if (resume) {
      lines.push("**Resume**", "", resume, "");
    }
    if (includeProgress) {
      lines.push("**Progress**", "", snippet, "");
    }
    if (!goal && !focus && !nextSteps.length && !blocked && !resume && !includeProgress) {
      lines.push("_No continuity fields yet — use the thread summary and forge issue._", "");
    }
    return lines.join("\n").replace(/\n{3,}/g, "\n\n").trim() + "\n";
  }

export async function copyCodingAgentPrompt(thread) {
    const text = buildCodingAgentPrompt(thread, {
      projectTitle: projectTitleForSlug(thread?.project_slug),
    });
    if (!text.trim()) {
      setMsg("Nothing to copy yet.");
      return;
    }
    await copyText(text, "Copied coding-agent prompt");
  }

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
      $("suggestion").innerHTML = `<p class="hint">${candidate.energy === "low" ? "A low-energy option" : "One option to consider"}</p><h3>${escapeHtml(threadDisplayTitle(candidate) || "Open step")}</h3><button type="button" class="primary" id="btn-accept-suggestion">Choose this</button>`;
      $("btn-accept-suggestion").addEventListener("click", () => chooseThread(candidate.id));
    } catch (error) { setMsg("Could not suggest a task: " + error.message); }
    finally { button.disabled = false; }
  }
export function openPause() {
    state.pauseTarget = state.chosenThread?.id;
    if (!state.pauseTarget) return;
    $("pause-step").value = state.chosenThread.resume_step || "";
    $("pause-task").textContent = threadDisplayTitle(state.chosenThread) || "This task";
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
let notesTrigger = null;
let notesRequest = 0;

function syncNotesReaderHeight() {
    const reader = $("notes-reader");
    if (!reader || reader.hidden || matchMedia("(max-width: 1099px)").matches) {
      reader?.style.removeProperty("--notes-reader-height");
      return;
    }
    const viewportHeight = window.visualViewport?.height || window.innerHeight;
    const top = Math.max(16, reader.getBoundingClientRect().top);
    reader.style.setProperty("--notes-reader-height", `${Math.max(160, viewportHeight - top - 16)}px`);
  }

function setNotesMode(mode) {
    const layout = $("notes-reader")?.closest(".layout");
    if (!layout) return;
    const expanded = mode === "expanded";
    layout.classList.toggle("notes-expanded", expanded);
    layout.classList.toggle("notes-docked", !expanded);
    $("btn-notes-dock")?.setAttribute("aria-pressed", String(!expanded));
    $("btn-notes-expand")?.setAttribute("aria-pressed", String(expanded));
    requestAnimationFrame(syncNotesReaderHeight);
  }

export function closeNotesReader({ restoreFocus = true } = {}) {
    const reader = $("notes-reader");
    if (!reader || reader.hidden) return;
    ++notesRequest;
    notesThreadId = null;
    const summariseBtn = $("btn-notes-summarise");
    if (summariseBtn) {
      summariseBtn.hidden = true;
      summariseBtn.disabled = false;
      summariseBtn.textContent = "Summarise";
    }
    const focusBtn = $("btn-notes-focus");
    if (focusBtn) focusBtn.hidden = true;
    reader.hidden = true;
    reader.closest(".layout")?.classList.remove("notes-docked", "notes-expanded");
    document.body.classList.remove("notes-reader-open");
    document.querySelectorAll("[data-notes][aria-expanded='true']").forEach((button) =>
      button.setAttribute("aria-expanded", "false")
    );
    const restoreTarget = notesTrigger;
    notesTrigger = null;
    if (restoreFocus && restoreTarget?.isConnected) restoreTarget.focus();
  }

function wireNotesActions(root) {
    if (!root) return;
    formatNotesTimes(root);
    root.querySelectorAll("button[data-choose]").forEach((button) => {
      if (button.dataset.chooseWired) return;
      button.dataset.chooseWired = "true";
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const id = button.dataset.choose;
        if (!id) return;
        closeNotesReader({ restoreFocus: false });
        chooseThread(id).catch((error) => setMsg(error.message));
      });
    });
  }

function aiAutoSummariseNotesEnabled() {
    const cfg = state.aiConfigCache;
    if (!cfg) return false;
    const active = cfg.active != null
      ? Boolean(cfg.active)
      : Boolean(cfg.enabled && String(cfg.base_url || "").trim());
    return Boolean(active && cfg.auto_summarise_notes);
  }

export async function summariseNotes({ mode = "force", quiet = false } = {}) {
    const threadId = notesThreadId;
    const request = notesRequest;
    const isCurrent = () => request === notesRequest && notesThreadId === threadId;
    if (!threadId) {
      if (!quiet) setMsg("Open a thread’s notes first.");
      return;
    }
    const btn = $("btn-notes-summarise");
    const body = $("notes-reader-body");
    const toastKey = "notes-summarise";
    if (btn) {
      btn.disabled = true;
      btn.textContent = mode === "ensure" ? "Checking…" : "Summarising…";
    }
    // Sticky keyed toast: AI calls can outlast the default info dismiss window.
    if (!quiet) {
      setMsg(mode === "ensure" ? "Updating notes summary…" : "Summarising notes…", {
        key: toastKey,
        sticky: true,
        variant: "info",
      });
    }
    try {
      const out = await api(`/threads/${encodeURIComponent(threadId)}/notes-summary`, {
        method: "POST",
        body: JSON.stringify({ mode }),
      });
      if (out.progress_html && body && isCurrent()) {
        body.innerHTML = out.progress_html;
        wireNotesActions(body);
      }
      if (isCurrent() && !(quiet && out.skipped)) {
        setMsg(out.message || "Summary updated.", {
          key: toastKey,
          variant: out.settings_hint ? "warning" : "info",
        });
      }
      if (out.settings_hint && !quiet && isCurrent()) {
        showScreen("settings");
        // Soft cue into Preferences → AI (avoid importing settings.js — circular via load.js).
        const prefsTab = document.querySelector('[data-settings-tab="preferences"]');
        prefsTab?.click();
        const aiBlock = $("ai_enabled");
        if (aiBlock) {
          try {
            aiBlock.focus({ preventScroll: true });
          } catch (_) {
            aiBlock.focus();
          }
        }
      }
    } catch (error) {
      if (!quiet && isCurrent()) {
        setMsg(error.message || "Could not summarise notes.", {
          key: toastKey,
          variant: "error",
        });
      }
    } finally {
      if (btn && isCurrent()) {
        btn.disabled = false;
        btn.textContent = "Summarise";
      }
    }
  }

async function openNotesReader(trigger) {
    const reader = $("notes-reader");
    const body = $("notes-reader-body");
    if (!reader || !body) return;
    const request = ++notesRequest;
    document.querySelectorAll("[data-notes][aria-expanded='true']").forEach((button) =>
      button.setAttribute("aria-expanded", "false")
    );
    notesTrigger = trigger;
    trigger.setAttribute("aria-expanded", "true");
    const thread = trigger.closest(".thread");
    notesThreadId = trigger.dataset.notes || null;
    const summariseBtn = $("btn-notes-summarise");
    if (summariseBtn) {
      summariseBtn.hidden = !notesThreadId;
      summariseBtn.disabled = false;
      summariseBtn.textContent = "Summarise";
    }
    const focusBtn = $("btn-notes-focus");
    if (focusBtn) {
      // Reuse the thread-card Focus control: same chooseThread path and labels.
      const cardChoose = thread?.querySelector("button[data-choose]");
      if (cardChoose && notesThreadId) {
        focusBtn.hidden = false;
        focusBtn.textContent = cardChoose.textContent || "Focus on this";
      } else {
        focusBtn.hidden = true;
      }
    }
    $("notes-reader-title").textContent = thread?.querySelector("h3")?.textContent || "Saved context";
    $("notes-reader-meta").textContent = [...(thread?.querySelectorAll(".thread-meta span") || [])]
      .map((item) => item.textContent.trim())
      .filter(Boolean)
      .join(" · ");
    reader.hidden = false;
    document.body.classList.add("notes-reader-open");
    setNotesMode(matchMedia("(max-width: 1099px)").matches ? "expanded" : "docked");
    body.textContent = "Loading notes…";
    try {
      const data = await api("/threads/" + encodeURIComponent(trigger.dataset.notes));
      if (request !== notesRequest) return;
      body.innerHTML = data.progress_html || "<p class=\"notes-empty-hint\">No saved notes yet.</p>";
      wireNotesActions(body);
      body.focus({ preventScroll: true });
      if (
        notesThreadId
        && aiAutoSummariseNotesEnabled()
        && data.notes_summary_needs_ai
      ) {
        summariseNotes({ mode: "ensure", quiet: true }).catch(() => {});
      }
    } catch (_) {
      if (request === notesRequest) body.textContent = "Could not load notes. Close and reopen to retry.";
    }
  }

function wireNotesReaderControls() {
    const reader = $("notes-reader");
    if (!reader || reader.dataset.wired) return;
    reader.dataset.wired = "true";
    $("btn-notes-summarise")?.addEventListener("click", () => {
      summariseNotes().catch((error) => setMsg(error.message));
    });
    $("btn-notes-focus")?.addEventListener("click", () => {
      const id = notesThreadId;
      if (!id) return;
      closeNotesReader({ restoreFocus: false });
      chooseThread(id).catch((error) => setMsg(error.message));
    });
    $("btn-notes-dock")?.addEventListener("click", () => setNotesMode("docked"));
    $("btn-notes-expand")?.addEventListener("click", () => setNotesMode("expanded"));
    $("btn-notes-close")?.addEventListener("click", () => closeNotesReader());
    window.addEventListener("resize", syncNotesReaderHeight);
    window.visualViewport?.addEventListener("resize", syncNotesReaderHeight);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !reader.hidden) {
        event.preventDefault();
        closeNotesReader();
      }
    });
  }

export function wireNotes(root) {
    wireNotesReaderControls();
    root.querySelectorAll("button[data-notes]").forEach((button) => {
      if (button.dataset.notesWired) return;
      button.dataset.notesWired = "true";
      button.addEventListener("click", () => openNotesReader(button));
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
    } · ${projectTitleForSlug(thread.project_slug)}`;
    $("focus-title").textContent = threadDisplayTitle(thread) || "Untitled step";
    card.className = "next-card has-item";
    const resumeBlock = thread.resume_step
      ? `<div class="resume-step${returning ? " resume-step-prominent" : ""}"><p class="eyebrow">${returning ? "PICK UP HERE" : "NEXT TINY STEP"}</p><div class="markdown-body">${thread.resume_step_html}</div>${returning ? '<p class="hint welcome-back">Welcome back. One small step is enough.</p>' : ""}</div>`
      : '<p class="start-cue">Start with the smallest part. You can leave a next step whenever you stop.</p>';
    card.innerHTML = `
      ${resumeBlock}
      ${state.focusState === "working" ? `<p class="work-state" role="status">${state.focusModeOn ? "Focus mode is on — stay with this project when you can." : "This is your focus. No timer, no rush."}</p>` : ""}
      <div class="next-actions">
        <button type="button" class="primary" id="btn-start">${state.focusState === "working" ? "Pause here" : returning || state.focusState === "paused" ? "Resume" : "Start"}</button>
        <button type="button" class="ghost" data-done="${escapeHtml(thread.id)}">Done</button>
      </div>
      <details class="focus-options"><summary>More actions</summary><div class="actions">
        <button type="button" class="ghost" id="btn-choose-work">Choose another</button>
        <button type="button" class="ghost" id="btn-copy-agent-prompt" title="Copy as prompt for Coding Agent to begin work">Copy agent prompt</button>
      </div></details>
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
    $("btn-copy-agent-prompt")?.addEventListener("click", () => {
      copyCodingAgentPrompt(thread).catch((error) => setMsg(error.message));
    });
    wireNotesActions(card);
  }
export async function markDone(id) {
    if (completing.has(id)) return;
    completing.add(id);
    const previousChosen = state.chosenId === id;
    const previousFocus = state.focusState;
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
      setMsg("Done. That’s one less thing to hold in your head.", {
        key: `done-${id}`,
        duration: 8000,
        action: {
          label: "Undo",
          onClick: () => {
            undoMarkDone(id, {
              restoreChoice: previousChosen,
              previousFocus,
            }).catch((error) => setMsg(error.message));
          },
        },
      });
      celebrate();
      await loadAll();
    } finally { completing.delete(id); }
  }

/** Reopen a thread after mark-done (toast Undo). */
export async function undoMarkDone(id, opts = {}) {
    if (completing.has(id)) return;
    completing.add(id);
    try {
      await api("/threads/undo-done", {
        method: "POST",
        body: JSON.stringify({ id, note: "Undone from /ui" }),
      });
      if (opts.restoreChoice) {
        state.chosenId = id;
        state.focusState = opts.previousFocus || "ready";
        state.nowMessage = "";
        rememberFocus();
        // Re-fetch public thread (summary, resume HTML, notes meta) like choose.
        await loadChosenThread();
        showScreen("now");
      }
      setMsg("Restored. It’s open again.", { key: `done-${id}`, variant: "success" });
      await loadAll();
      if (opts.restoreChoice && state.chosenId === id) {
        await loadChosenThread();
      }
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
        <strong>Still focusing on ${escapeHtml(threadDisplayTitle(state.chosenThread) || "this task")}</strong>
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
