/**
 * Smoke: Possible overlap review copy, states, and the merge request contract.
 * Run: node tests/js/overlap_review_smoke.mjs
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  ALTERNATIVES,
  KEPT_STATE,
  approveMergeRequest,
  blockMessage,
  dismissRequest,
  mergeDirection,
  openSuggestionRequest,
  previewIsStale,
  queueMergeRequest,
  renderOverlap,
  suggestionReason,
  usefulDifferences,
  visibleHits,
} from "../../src/adhd_hub/ui/js/overlap-review.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const css = readFileSync(join(root, "src/adhd_hub/ui/app.css"), "utf8");
const html = readFileSync(join(root, "src/adhd_hub/ui/index.html"), "utf8");
const overlapJs = readFileSync(join(root, "src/adhd_hub/ui/js/overlap.js"), "utf8");
const workJs = readFileSync(join(root, "src/adhd_hub/ui/js/work.js"), "utf8");
const sw = readFileSync(join(root, "src/adhd_hub/ui/sw.js"), "utf8");

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const current = {
  id: "source",
  summary: "Ship DNS cutover",
  goal: "Ship DNS cutover",
  focus: "Review source checklist",
  next_steps: ["source step 1", "source step 2", "source step 3"],
  resume_step: "Open source cutover log",
  blocked_reason: null,
  paused_at: null,
  source_tool: "cursor",
  status: "open",
  project_slug: "dns",
};
const other = {
  ...current,
  id: "target",
  focus: "Review target checklist",
  next_steps: ["target step 1", "target step 2", "target step 3"],
  resume_step: "Open target cutover log",
  source_tool: "codex",
};
const allowed = {
  thread: other,
  reason: "token_overlap=0.30; goal_in_query; title_in_query; slug_in_query",
  outcome: "same_outcome",
  evidence: ["goal_exact_match", "same_project"],
  merge_allowed: true,
  merge_blocked_reason: null,
};
const blocked = {
  thread: { ...other, id: "docs", summary: "Document DNS cutover", goal: "Document DNS cutover" },
  reason: "token_overlap=0.40",
  outcome: "related",
  evidence: ["distinct_known_goal", "same_project"],
  merge_allowed: false,
  merge_blocked_reason: "distinct_outcomes",
};

const alarm = /\b(overdue|behind|guilty|urgent|alarm|warning|duplicate|you failed|you should have)\b/i;

function calm(htmlText, label) {
  assert(!alarm.test(htmlText), `${label} uses alarming copy: ${htmlText.match(alarm)?.[0]}`);
  assert(!htmlText.includes("confirm_merge"), `${label} must not embed the confirm flag`);
}

const loading = renderOverlap({ phase: "loading" });
calm(loading, "loading");
assert(loading.includes("Looking for similar steps"), "loading copy");

const empty = renderOverlap({ phase: "empty" });
calm(empty, "empty");
assert(empty.includes("No other open steps look like this one."), "empty copy");

const error = renderOverlap({ phase: "error" });
calm(error, "error");
assert(error.includes("Nothing was changed."), "error does not imply a merge");

const list = renderOverlap({ phase: "list", thread: current, hits: [allowed, blocked] });
calm(list, "list");
assert(list.includes("Ship DNS cutover") && list.includes("Document DNS cutover"), "both candidates");
assert(list.includes("Finishable goal"), "goals are labeled");
assert(list.includes(suggestionReason(allowed)), "plain reason");
assert(list.includes("Review a safe merge"), "safe merge is explicit");
assert(list.includes(blockMessage("distinct_outcomes")), "blocked pair is explained");
assert(list.includes(ALTERNATIVES), "alternatives stay available");
assert(list.includes("Hide this suggestion") && list.includes("Look at this step"), "dismiss and inspect");
assert((list.match(/Review a safe merge/g) || []).length === 1, "only the safe pair offers merge");
assert(list.includes("Opening this does not change either step."), "viewing is not a merge");

const diffs = usefulDifferences(current, other);
assert(diffs.some((row) => row.label === "Next" && row.current.includes("source step 1")), "next-step difference");
assert(diffs.some((row) => row.label === "From"), "source identity difference");

const confirm = renderOverlap({
  phase: "confirm",
  thread: current,
  candidate: other,
  source: other,
  target: current,
  keep: "current",
  directionLocked: false,
});
calm(confirm, "confirm");
assert(confirm.includes("Confirm merge"), "explicit confirm");
assert(confirm.includes(KEPT_STATE), "kept state is explained");
assert(confirm.includes("Stays active") && confirm.includes("kept in history"), "direction is visible");
assert(confirm.includes("target step 1") && confirm.includes("source step 1"), "both next lists stay intact");
assert(confirm.includes("Which step stays active?"), "direction is a choice");

const stale = renderOverlap({ phase: "stale", actionId: "act" });
calm(stale, "stale");
assert(stale.includes("Nothing was merged."), "stale merge did not happen");
assert(stale.includes("Set this preview aside"), "stale preview can be rejected");

const success = renderOverlap({ phase: "success" });
calm(success, "success");
assert(success.includes("Nothing outside this hub was changed."), "no remote write claim");

assert(dismissRequest() === null, "dismiss does not call the API");
const open = openSuggestionRequest("source");
assert(open.method === "GET" && open.body === null, "opening suggestions is a read");
const queued = queueMergeRequest("target", "source");
assert(queued.method === "POST" && queued.body.target_thread_id === "source", "queue names the kept step");
const approved = approveMergeRequest("act");
assert(approved.body.confirm_merge === true && typeof approved.body.confirm_merge === "boolean", "confirm flag is boolean true");
assert(mergeDirection("source", "target", "current").targetId === "source", "default keeps the open step");
assert(mergeDirection("source", "target", "other").targetId === "target", "other direction keeps the candidate");
assert(visibleHits({ hits: [allowed, blocked] }, "source", ["source:target"]).length === 1, "dismiss hides one pair");
assert(
  previewIsStale(other, current, { source: { ...other, goal: "Document DNS cutover" }, target: current }),
  "changed goal makes the preview stale"
);
assert(!previewIsStale(other, current, { source: other, target: current }), "matching snapshots are current");

const unknown = renderOverlap({ phase: "unknown", actionId: "act" });
calm(unknown, "unknown");
assert(unknown.includes("might already be saved"), "an unanswered merge stays uncertain");
assert(unknown.includes("Set this preview aside"), "an uncertain preview can be set aside");
assert(overlapJs.includes("keptId"), "retained notes use the step the merge kept");
assert(overlapJs.includes("confirmEpoch"), "leaving during confirm does not approve afterwards");
assert(overlapJs.includes("approveMergeRequest"), "controller uses the confirm request");
assert(!overlapJs.includes("confirm_merge"), "controller does not hand-build the confirm flag");
assert(workJs.includes('a.kind === "merge_threads"'), "pending merges are recognized");
assert(workJs.includes("data-review-merge"), "pending merges open review");
assert(workJs.includes("Nothing has been combined yet."), "pending banner does not imply a finished merge");
assert(html.includes('id="overlap-dialog"'), "review dialog exists");
assert(html.includes("Possible overlap"), "quiet cue copy");
assert(html.includes("Check for similar steps"), "explicit check");
assert(css.includes(".overlap-pair"), "pair layout");
assert(/@media \(min-width: 640px\) \{\s*\.overlap-pair \{\s*grid-template-columns: 1fr 1fr;/.test(css), "wide layout is two columns");
assert(css.includes(".overlap-pair { display: grid; grid-template-columns: 1fr;"), "narrow layout stacks");
assert(
  /@media \(prefers-reduced-motion: reduce\) \{\s*\.overlap-review, \.overlap-review \* \{ animation: none !important; transition: none !important;/.test(css),
  "reduced motion disables overlap motion"
);
assert(!css.includes(".overlap-review { animation"), "overlap surface has no entrance animation");
assert(sw.includes("adhd-hub-shell-v51"), "shell cache includes the review module");
assert(sw.includes("/ui/js/overlap.js"), "service worker precaches the controller");

console.log("overlap_review_smoke: ok");
