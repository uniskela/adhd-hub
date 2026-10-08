/** Plain-language duplicate-thread review. No network and no DOM. */

const EVIDENCE = {
  goal_exact_match: "The finishable goals match.",
  distinct_known_goal: "The finishable goals use different words.",
  no_recorded_goal: "A finishable goal is not recorded yet.",
  source_goal_required: "A finishable goal is needed before these can be treated as the same outcome.",
  same_project: "They are in the same project.",
  different_projects: "They are in different projects.",
};

const REASON_BITS = [
  ["token_overlap", "Some of the same words appear in both."],
  ["goal_in_query", "The goal wording shows up on the other step."],
  ["title_in_query", "The titles share wording."],
  ["slug_in_query", "They mention the same project."],
];

export const BLOCK_MESSAGES = {
  same_thread: "Choose two different steps.",
  already_merged: "One of these is already kept with another step. Open the active one.",
  unfinished_required: "Only open steps can be combined. Finished or set-aside work stays as it is.",
  different_projects: "These belong to different projects, so they stay separate.",
  goal_required: "Add a finishable goal to both steps before a merge can be offered.",
  distinct_outcomes: "The goals are different. A similar title is not enough to combine them.",
  forge_authoritative:
    "One of these follows a source issue. That issue stays in charge, so these cannot be combined here.",
};

export const ALTERNATIVES =
  "You can keep them separate, or mention the other step in a progress note. A note does not change who owns the work.";

export const KEPT_STATE =
  "The active step keeps its focus, all of its next steps, its blocker, its resume note and its pause. " +
  "The other step is set aside on this hub and kept in history, including its own next steps. " +
  "Those details are not copied onto the active step. Nothing outside this hub is changed.";

const SOURCE_NAMES = {
  web: "Quick capture",
  codex: "Codex",
  cursor: "Cursor",
  openclaw: "OpenClaw",
};

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function clean(value) {
  return String(value ?? "").trim();
}

function joinNext(thread) {
  return (Array.isArray(thread?.next_steps) ? thread.next_steps : [])
    .map((item) => clean(item))
    .filter(Boolean)
    .join(" · ");
}

export function sourceLabel(thread) {
  const source = thread?.source_tool || thread?.origin || "";
  return SOURCE_NAMES[String(source).toLowerCase()] || clean(source) || "Saved work";
}

export function goalLine(thread) {
  return clean(thread?.goal) || "No finishable goal recorded yet.";
}

export function suggestionReason(hit) {
  const lines = [];
  for (const code of hit?.evidence || []) {
    const sentence = EVIDENCE[code];
    if (sentence && !lines.includes(sentence)) lines.push(sentence);
  }
  const raw = String(hit?.reason || "");
  for (const [key, sentence] of REASON_BITS) {
    if (raw.includes(key) && !lines.includes(sentence)) lines.push(sentence);
  }
  if (!lines.length) lines.push("These steps look similar. That is only a suggestion.");
  return lines.join(" ");
}

export function blockMessage(code) {
  return (
    BLOCK_MESSAGES[code] ||
    "These steps cannot be combined automatically. You can keep reviewing them separately."
  );
}

export function pairKey(leftId, rightId) {
  return `${leftId}:${rightId}`;
}

export function visibleHits(payload, currentId, dismissed) {
  const hidden = new Set(dismissed || []);
  return (payload?.hits || []).filter((hit) => {
    const id = hit?.thread?.id;
    if (!id || id === currentId) return false;
    return !hidden.has(pairKey(currentId, id)) && !hidden.has(pairKey(id, currentId));
  });
}

export function usefulDifferences(current, other) {
  const rows = [
    ["Goal", current?.goal, other?.goal],
    ["Focus", current?.focus, other?.focus],
    ["Next", joinNext(current), joinNext(other)],
    ["Blocker", current?.blocked_reason, other?.blocked_reason],
    ["Resume", current?.resume_step, other?.resume_step],
    ["Paused", current?.paused_at, other?.paused_at],
    ["From", sourceLabel(current), sourceLabel(other)],
  ];
  return rows
    .map(([label, left, right]) => ({
      label,
      current: clean(left) || "Not recorded",
      other: clean(right) || "Not recorded",
      same: clean(left) === clean(right),
    }))
    .filter((row) => !row.same);
}

export function continuityStamp(thread) {
  return JSON.stringify({
    goal: clean(thread?.goal),
    focus: clean(thread?.focus),
    next: joinNext(thread),
    blocked: clean(thread?.blocked_reason),
    resume: clean(thread?.resume_step),
    paused: clean(thread?.paused_at),
    status: clean(thread?.status),
    project: clean(thread?.project_slug),
    merged: clean(thread?.merged_into),
  });
}

export function previewIsStale(shownSource, shownTarget, payload) {
  const source = payload?.source;
  const target = payload?.target;
  if (!source || !target) return true;
  return (
    continuityStamp(shownSource) !== continuityStamp(source) ||
    continuityStamp(shownTarget) !== continuityStamp(target)
  );
}

export function mergeDirection(currentId, otherId, keep) {
  if (keep === "other") return { sourceId: currentId, targetId: otherId };
  return { sourceId: otherId, targetId: currentId };
}

export function isStaleMergeError(message) {
  return String(message || "").includes("merge_preview_stale");
}

export function openSuggestionRequest(threadId) {
  return { method: "GET", path: `/threads/${encodeURIComponent(threadId)}/duplicates?limit=5`, body: null };
}

export function inspectRequest(threadId) {
  return { method: "GET", path: `/threads/${encodeURIComponent(threadId)}`, body: null };
}

export function queueMergeRequest(sourceId, targetId) {
  return {
    method: "POST",
    path: `/threads/${encodeURIComponent(sourceId)}/merge`,
    body: { target_thread_id: targetId },
  };
}

export function approveMergeRequest(actionId) {
  return {
    method: "POST",
    path: `/pending-actions/${encodeURIComponent(actionId)}/approve`,
    body: { confirm_merge: true },
  };
}

export function rejectMergeRequest(actionId) {
  return {
    method: "POST",
    path: `/pending-actions/${encodeURIComponent(actionId)}/reject`,
    body: {},
  };
}

export function historyRequest(threadId) {
  return {
    method: "GET",
    path: `/threads/${encodeURIComponent(threadId)}/merge-history?limit=50`,
    body: null,
  };
}

/** Dismissing a suggestion is local only. */
export function dismissRequest() {
  return null;
}

function titleOf(thread) {
  return clean(thread?.summary) || "Untitled step";
}

function detailList(thread) {
  const rows = [
    ["Goal", goalLine(thread)],
    ["Focus", clean(thread?.focus) || "Not recorded"],
    ["Next", joinNext(thread) || "Not recorded"],
    ["Blocker", clean(thread?.blocked_reason) || "None recorded"],
    ["Resume", clean(thread?.resume_step) || "Not recorded"],
    ["Paused", clean(thread?.paused_at) || "Not paused"],
    ["From", sourceLabel(thread)],
  ];
  return `<dl class="overlap-details">${rows
    .map(
      ([label, value]) =>
        `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`
    )
    .join("")}</dl>`;
}

function actions(buttons) {
  return `<div class="actions">${buttons.join("")}</div>`;
}

function button(action, label, className, extra = "") {
  return `<button type="button" class="${className}" data-overlap-action="${action}" ${extra}>${escapeHtml(label)}</button>`;
}

function hitCard(current, hit) {
  const other = hit.thread || {};
  const diffs = usefulDifferences(current, other);
  const diffHtml = diffs.length
    ? `<ul class="overlap-diffs">${diffs
        .map(
          (row) =>
            `<li><span>${escapeHtml(row.label)}</span> This step: ${escapeHtml(row.current)}. Other step: ${escapeHtml(row.other)}.</li>`
        )
        .join("")}</ul>`
    : `<p class="overlap-note">${
        hit.merge_allowed
          ? "No useful differences in the recorded details. They stay separate until you confirm a merge."
          : "No useful differences in the recorded details. They stay separate."
      }</p>`;
  const blocked = hit.merge_allowed
    ? ""
    : `<p class="overlap-note">${escapeHtml(blockMessage(hit.merge_blocked_reason))} ${escapeHtml(ALTERNATIVES)}</p>`;
  const mergeButton = hit.merge_allowed
    ? button("review", "Review a safe merge", "primary", `data-thread-id="${escapeHtml(other.id)}"`)
    : "";
  return `<article class="overlap-hit">
    <h3>${escapeHtml(titleOf(other))}</h3>
    <p><span class="overlap-label">Finishable goal</span> ${escapeHtml(goalLine(other))}</p>
    <p class="overlap-reason">${escapeHtml(suggestionReason(hit))}</p>
    ${diffHtml}
    ${blocked}
    ${actions([
      button("inspect", "Look at this step", "ghost", `data-thread-id="${escapeHtml(other.id)}"`),
      button("dismiss", "Hide this suggestion", "ghost", `data-thread-id="${escapeHtml(other.id)}"`),
      mergeButton,
    ])}
  </article>`;
}

function confirmView(model) {
  const source = model.source;
  const target = model.target;
  const radios = model.directionLocked
    ? ""
    : `<fieldset class="overlap-keep">
        <legend>Which step stays active?</legend>
        <label><input type="radio" name="overlap-keep" value="current" ${model.keep === "other" ? "" : "checked"} /> Keep “${escapeHtml(titleOf(model.thread))}”</label>
        <label><input type="radio" name="overlap-keep" value="other" ${model.keep === "other" ? "checked" : ""} /> Keep “${escapeHtml(titleOf(model.candidate))}”</label>
      </fieldset>`;
  return `<p>Keep <strong>${escapeHtml(titleOf(target))}</strong> active. Set <strong>${escapeHtml(source ? titleOf(source) : "")}</strong> aside in history.</p>
    ${radios}
    <div class="overlap-pair">
      <section class="overlap-side"><h3>Stays active</h3>${detailList(target)}</section>
      <section class="overlap-side"><h3>Set aside, kept in history</h3>${detailList(source)}</section>
    </div>
    <p class="overlap-note">${escapeHtml(KEPT_STATE)}</p>
    ${actions([
      button("confirm", "Confirm merge", "primary"),
      button("back", "Leave both as they are", "ghost"),
    ])}`;
}

export function renderOverlap(model) {
  const phase = model?.phase || "loading";
  if (phase === "loading") {
    return `<p class="overlap-status" role="status">Looking for similar steps…</p>`;
  }
  if (phase === "empty") {
    return `<p class="overlap-status" role="status">No other open steps look like this one.</p>${actions([
      button("retry", "Look again", "ghost"),
    ])}`;
  }
  if (phase === "error") {
    return `<p class="overlap-status" role="status">${escapeHtml(model.message || "Could not load suggestions. Nothing was changed.")}</p>${actions([
      button("retry", "Try again", "ghost"),
    ])}`;
  }
  if (phase === "list") {
    const hits = model.hits || [];
    if (!hits.length) return renderOverlap({ phase: "empty" });
    return `<p class="overlap-note">These might be the same piece of work. Opening this does not change either step.</p>${hits
      .map((hit) => hitCard(model.thread, hit))
      .join("")}`;
  }
  if (phase === "confirm") return confirmView(model);
  if (phase === "refused") {
    return `<p class="overlap-status" role="status">${escapeHtml(model.message || blockMessage(model.reason))}</p>
      <p class="overlap-note">${escapeHtml(ALTERNATIVES)}</p>
      ${actions([button("back", "Back to suggestions", "ghost")])}`;
  }
  if (phase === "stale") {
    const aside = model.actionId
      ? button("reject", "Set this preview aside", "ghost")
      : "";
    return `<p class="overlap-status" role="status">This preview is out of date. Nothing was merged. Set it aside and look again when you are ready.</p>${actions([
      aside,
      button("retry", "Look again", "ghost"),
    ])}`;
  }
  if (phase === "success") {
    const warning = model.projectionWarning
      ? `<p class="overlap-note">${escapeHtml(model.projectionWarning)}</p>`
      : "";
    return `<p class="overlap-status" role="status">The active step stays as it was. The other step is set aside here, and its notes stay under their original ids. Nothing outside this hub was changed.</p>
      ${warning}
      ${actions([
        button("history", "Show retained notes", "ghost"),
        button("close", "Close", "primary"),
      ])}`;
  }
  if (phase === "history") {
    const items = model.historyItems || [];
    const body = items.length
      ? items
          .map((item) => {
            const thread = item.thread || {};
            const notes = (item.notes || [])
              .map((note) => `<li>${escapeHtml(clean(note.content) || "Empty note")}</li>`)
              .join("");
            return `<article class="overlap-hit"><h3>${escapeHtml(titleOf(thread))}</h3>${detailList(thread)}${
              notes ? `<ul class="overlap-diffs">${notes}</ul>` : `<p class="overlap-note">No retained notes on this step.</p>`
            }</article>`;
          })
          .join("")
      : `<p class="overlap-status" role="status">No retained history was returned. Nothing else was changed.</p>`;
    return `${body}${actions([button("close", "Close", "primary")])}`;
  }
  return renderOverlap({ phase: "error", message: "Something unexpected happened. Nothing was changed." });
}
