import { preferences, $, setMsg } from "./state.js";
import { api } from "./api.js";
import { closeModal } from "./dom.js";
import {
  approveMergeRequest,
  historyRequest,
  inspectRequest,
  isStaleMergeError,
  mergeDirection,
  openSuggestionRequest,
  previewIsStale,
  queueMergeRequest,
  rejectMergeRequest,
  renderOverlap,
  visibleHits,
} from "./overlap-review.mjs";

const DISMISS_KEY = "adhd_hub_overlap_dismissed";
const cache = new Map();
let apiMissing = false;
let openNotes = async () => {};
let onChanged = async () => {};
let view = null;
let busy = false;
let confirmEpoch = 0;

export function setOverlapHooks({ openThreadNotes, onChanged: changed } = {}) {
  if (openThreadNotes) openNotes = openThreadNotes;
  if (changed) onChanged = changed;
}

function readDismissed() {
  try {
    const parsed = JSON.parse(preferences.getItem(DISMISS_KEY) || "[]");
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : [];
  } catch (_) {
    return [];
  }
}

function writeDismissed(list) {
  preferences.setItem(DISMISS_KEY, JSON.stringify(list.slice(-200)));
}

function dialog() {
  return $("overlap-dialog");
}

function paint(next) {
  view = next;
  const body = $("overlap-body");
  const sub = $("overlap-sub");
  if (!body) return;
  body.innerHTML = renderOverlap(view);
  body.setAttribute("aria-busy", view.phase === "loading" ? "true" : "false");
  if (sub) {
    sub.textContent =
      view.phase === "confirm"
        ? "Nothing is combined until you confirm."
        : "Looking does not change either step.";
  }
}

function showDialog() {
  const dlg = dialog();
  if (!dlg) return;
  if (!dlg.open) dlg.showModal();
  const title = $("overlap-title");
  if (title && !title.hasAttribute("tabindex")) title.setAttribute("tabindex", "-1");
  try {
    title?.focus({ preventScroll: true });
  } catch (_) {
    title?.focus();
  }
}

export function hideOverlapCue() {
  const cue = $("notes-overlap-cue");
  if (cue) cue.hidden = true;
}

function showCue(show) {
  const cue = $("notes-overlap-cue");
  if (cue) cue.hidden = !show;
}

async function loadSuggestions(threadId) {
  const request = openSuggestionRequest(threadId);
  return api(request.path);
}

export async function refreshOverlapCue(thread, isCurrent = () => true) {
  if (!thread?.id || thread.status === "done" || apiMissing) {
    if (isCurrent()) hideOverlapCue();
    return;
  }
  try {
    const payload = await loadSuggestions(thread.id);
    if (!isCurrent()) return;
    cache.set(thread.id, { thread, payload });
    showCue(visibleHits(payload, thread.id, readDismissed()).length > 0);
  } catch (error) {
    if (!isCurrent()) return;
    if (error.status === 404) apiMissing = true;
    hideOverlapCue();
  }
}

export async function openOverlapReview(thread, { force = false } = {}) {
  if (!thread?.id) return;
  paint({ phase: "loading", thread });
  showDialog();
  let payload = !force && cache.get(thread.id)?.payload;
  if (!payload) {
    try {
      payload = await loadSuggestions(thread.id);
      apiMissing = false;
      cache.set(thread.id, { thread, payload });
    } catch (error) {
      const missing = error.status === 404;
      if (missing) apiMissing = true;
      paint({
        phase: "error",
        thread,
        message: missing
          ? "Overlap suggestions are not available on this hub yet. Nothing was changed."
          : "Could not load suggestions. Nothing was changed.",
      });
      return;
    }
  }
  const hits = visibleHits(payload, thread.id, readDismissed());
  showCue(hits.length > 0 && thread.status !== "done");
  paint(hits.length ? { phase: "list", thread, hits } : { phase: "empty", thread });
}

function candidateFromView(id) {
  return (view?.hits || []).find((hit) => hit?.thread?.id === id)?.thread || null;
}

function shownPair() {
  const keep = document.querySelector("input[name='overlap-keep']:checked")?.value || view?.keep || "current";
  const direction = mergeDirection(view.thread.id, view.candidate.id, keep);
  const source = direction.sourceId === view.thread.id ? view.thread : view.candidate;
  const target = direction.targetId === view.thread.id ? view.thread : view.candidate;
  return { source, target, direction };
}

function stillConfirming(epoch) {
  return epoch === confirmEpoch;
}

function lockReview(locked) {
  $("overlap-body")?.querySelectorAll("button, input").forEach((el) => {
    el.disabled = locked;
  });
}

async function rejectQuiet(actionId) {
  await api(rejectMergeRequest(actionId).path, {
    method: "POST",
    body: JSON.stringify(rejectMergeRequest(actionId).body),
  });
}

function successView(thread, keptId, projectionWarning) {
  return {
    phase: "success",
    thread,
    hits: view?.hits,
    keptId,
    targetId: keptId,
    projectionWarning: projectionWarning || "",
  };
}

async function runConfirm() {
  if (busy || !view || view.phase !== "confirm") return;
  const epoch = confirmEpoch;
  const review = view;
  const pair = review.pendingActionId ? null : shownPair();
  const keptId = pair ? pair.direction.targetId : review.target?.id;
  busy = true;
  lockReview(true);
  let actionId = review.pendingActionId || null;
  let createdAction = false;
  let saved = false;
  try {
    if (!actionId) {
      const queued = await api(queueMergeRequest(pair.direction.sourceId, pair.direction.targetId).path, {
        method: "POST",
        body: JSON.stringify(queueMergeRequest(pair.direction.sourceId, pair.direction.targetId).body),
      });
      if (!stillConfirming(epoch)) {
        if (queued?.pending && queued.action?.id) await rejectQuiet(queued.action.id).catch(() => {});
        if (dialog()?.open) paint({ phase: "list", thread: review.thread, hits: review.hits || [] });
        return;
      }
      if (!queued?.pending || !queued.merge_allowed) {
        paint({
          phase: "refused",
          thread: review.thread,
          hits: review.hits,
          message: queued?.message,
          reason: queued?.reason,
        });
        return;
      }
      actionId = queued.action?.id;
      createdAction = true;
      if (previewIsStale(pair.source, pair.target, queued.action?.payload)) {
        paint({ phase: "stale", thread: review.thread, hits: review.hits, actionId });
        return;
      }
    }
    if (!stillConfirming(epoch)) {
      if (createdAction && actionId) await rejectQuiet(actionId).catch(() => {});
      if (dialog()?.open) paint({ phase: "list", thread: review.thread, hits: review.hits || [] });
      return;
    }
    if (!actionId) {
      paint({
        phase: "error",
        thread: review.thread,
        hits: review.hits,
        message: "The merge preview did not start. Nothing was combined.",
      });
      return;
    }
    const approved = await api(approveMergeRequest(actionId).path, {
      method: "POST",
      body: JSON.stringify(approveMergeRequest(actionId).body),
    });
    const savedId = approved?.result?.target_thread_id || keptId;
    if (approved?.already_resolved && !approved?.approved && !approved?.result) {
      if (!stillConfirming(epoch)) return;
      paint({
        phase: "error",
        thread: review.thread,
        hits: review.hits,
        actionId,
        message: "This merge was already settled. Nothing else was changed.",
      });
      return;
    }
    saved = true;
    busy = false;
    cache.delete(review.thread?.id);
    const warning = approved?.projection_warning
      ? "The merge was saved. The local project page did not refresh. Use Refresh when you can."
      : "";
    if (stillConfirming(epoch)) paint(successView(review.thread, savedId, warning));
    try {
      await onChanged();
    } catch (_) {
      if (stillConfirming(epoch)) {
        paint(successView(
          review.thread,
          savedId,
          "The merge was saved. The list did not refresh. Use Refresh when you can.",
        ));
      }
    }
  } catch (error) {
    if (!stillConfirming(epoch)) return;
    if (saved) {
      paint(successView(
        review.thread,
        keptId,
        "The merge was saved. The list did not refresh. Use Refresh when you can.",
      ));
      return;
    }
    if (isStaleMergeError(error.message)) {
      paint({ phase: "stale", thread: review.thread, hits: review.hits, actionId });
      return;
    }
    if (!error.status && actionId) {
      paint({ phase: "unknown", thread: review.thread, hits: review.hits, actionId, keptId });
      return;
    }
    paint({
      phase: "error",
      thread: review.thread,
      hits: review.hits,
      actionId: createdAction ? actionId : review.pendingActionId,
      message: "Could not finish the merge. Nothing was combined.",
    });
  } finally {
    busy = false;
    lockReview(false);
  }
}

async function onAction(action, threadId) {
  if (!view) return;
  if (busy) {
    if (action === "back") confirmEpoch += 1;
    return;
  }
  if (action === "dismiss" && threadId && view.thread?.id) {
    const key = `${view.thread.id}:${threadId}`;
    const next = readDismissed();
    if (!next.includes(key)) next.push(key);
    writeDismissed(next);
    const hits = (view.hits || []).filter((hit) => hit?.thread?.id !== threadId);
    showCue(hits.length > 0);
    paint(hits.length ? { phase: "list", thread: view.thread, hits } : { phase: "empty", thread: view.thread });
    return;
  }
  if (action === "inspect" && threadId) {
    const request = inspectRequest(threadId);
    if (request.method !== "GET") return;
    closeModal(dialog());
    try {
      await openNotes(threadId);
    } catch (error) {
      setMsg(error.message || "Could not open that step.");
    }
    return;
  }
  if (action === "review" && threadId) {
    const candidate = candidateFromView(threadId);
    if (!candidate) return;
    paint({
      phase: "confirm",
      thread: view.thread,
      hits: view.hits,
      candidate,
      keep: "current",
      source: candidate,
      target: view.thread,
      directionLocked: false,
    });
    return;
  }
  if (action === "confirm") return runConfirm();
  if (action === "back") {
    if (view.pendingActionId) {
      await rejectPending(view.pendingActionId);
      return;
    }
    const hits = view.hits || [];
    paint(hits.length ? { phase: "list", thread: view.thread, hits } : { phase: "empty", thread: view.thread });
    return;
  }
  if (action === "retry" && view.thread?.id) {
    cache.delete(view.thread.id);
    await openOverlapReview(view.thread, { force: true });
    return;
  }
  if (action === "reject" && view.actionId) {
    await rejectPending(view.actionId);
    return;
  }
  if (action === "history") {
    const threadId = view.targetId || view.thread?.id;
    if (!threadId) return;
    try {
      const history = await api(historyRequest(threadId).path);
      paint({ phase: "history", thread: view.thread, historyItems: history?.items || [] });
    } catch (_) {
      paint({
        phase: "error",
        thread: view.thread,
        message: "Retained notes could not be loaded. The merge itself was saved.",
      });
    }
    return;
  }
  if (action === "close") closeModal(dialog());
}

async function rejectPending(actionId) {
  try {
    await api(rejectMergeRequest(actionId).path, {
      method: "POST",
      body: JSON.stringify(rejectMergeRequest(actionId).body),
    });
    paint({
      phase: "error",
      thread: view?.thread,
      message: "The preview was set aside. Both steps are unchanged.",
    });
    await onChanged();
  } catch (error) {
    paint({
      phase: "error",
      thread: view?.thread,
      message: error.message || "Could not set the preview aside. Nothing was merged.",
    });
  }
}

export async function reviewPendingMerge(actionId) {
  paint({ phase: "loading" });
  showDialog();
  try {
    const actions = await api("/pending-actions");
    const action = (actions || []).find((item) => item.id === actionId && item.kind === "merge_threads");
    const source = action?.payload?.source;
    const target = action?.payload?.target;
    if (!action || !source || !target) {
      paint({
        phase: "error",
        message: "That merge preview is no longer waiting. Nothing was changed.",
      });
      return;
    }
    paint({
      phase: "confirm",
      thread: target,
      candidate: source,
      source,
      target,
      keep: "current",
      directionLocked: true,
      pendingActionId: action.id,
    });
  } catch (_) {
    paint({
      phase: "error",
      message: "Could not open the merge preview. Nothing was changed.",
    });
  }
}

export function bindOverlapReview() {
  const root = $("overlap-body");
  if (!root || root.dataset.wired) return;
  root.dataset.wired = "true";
  root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-overlap-action]");
    if (!button) return;
    onAction(button.dataset.overlapAction, button.dataset.threadId).catch((error) => {
      paint({
        phase: "error",
        thread: view?.thread,
        message: error.message || "Something went wrong. Nothing was changed.",
      });
    });
  });
  dialog()?.addEventListener("close", () => {
    if (busy) confirmEpoch += 1;
  });
  root.addEventListener("change", (event) => {
    if (busy || event.target?.name !== "overlap-keep" || view?.phase !== "confirm" || view.directionLocked) return;
    const keep = event.target.value === "other" ? "other" : "current";
    const source = keep === "other" ? view.thread : view.candidate;
    const target = keep === "other" ? view.candidate : view.thread;
    paint({ ...view, keep, source, target });
  });
}
