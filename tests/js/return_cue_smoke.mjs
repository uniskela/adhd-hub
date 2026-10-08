/**
 * Smoke: return-cue coaching view model against the shared fixtures.
 * Run: node tests/js/return_cue_smoke.mjs
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  applyCueFill,
  coachingView,
  suggestionAction,
  undoCueFill,
  usefulResumeText,
} from "../../src/adhd_hub/ui/js/return-cue.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const cases = JSON.parse(readFileSync(join(root, "tests/fixtures/return_cue/cases.json"), "utf8"));
const nowSrc = readFileSync(join(root, "src/adhd_hub/ui/js/now.js"), "utf8");
const workSrc = readFileSync(join(root, "src/adhd_hub/ui/js/work.js"), "utf8");
const overlapSrc = readFileSync(join(root, "src/adhd_hub/ui/js/overlap-review.mjs"), "utf8");
const css = readFileSync(join(root, "src/adhd_hub/ui/app.css"), "utf8");
const sw = readFileSync(join(root, "src/adhd_hub/ui/sw.js"), "utf8");

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const focusSuggestion = { source: "focus", text: "Open service.py and run pytest" };
const nextSuggestion = { source: "next_steps", text: "Review #54" };

for (const row of cases) {
  const concrete = row.quality === "concrete";
  const cue = {
    quality: row.quality,
    signals: row.signals,
    hint: concrete ? null : "A quiet hint for this fixture.",
    suggestion: concrete ? null : focusSuggestion,
    advisory: true,
    version: 1,
  };
  const view = coachingView(cue, row.resume_step, row.resume_step, null);
  assert(view.blockSave === false, `${row.name} must not block save`);
  if (concrete) {
    assert(!view.showHint && !view.action, `${row.name} is concrete`);
    assert(usefulResumeText({ resume_step: row.resume_step, return_cue: cue }) === String(row.resume_step).trim(), row.name);
  } else {
    assert(view.showHint && view.hint === cue.hint, `${row.name} shows the backend hint`);
    assert(view.action?.label === "Use Focus", `${row.name} offers Use Focus`);
    assert(usefulResumeText({ resume_step: row.resume_step, return_cue: cue }) === "", `${row.name} is not a pickup line`);
  }
}

const vague = cases.find((row) => row.name === "continue_later");
const edited = coachingView(
  { quality: "vague", hint: "hint", suggestion: nextSuggestion },
  "Review the auth callback test",
  vague.resume_step,
  null,
);
assert(!edited.showHint && !edited.action, "manual edit hides coaching");
assert(suggestionAction(nextSuggestion).label === "Use next step");

const applied = applyCueFill(vague.resume_step, suggestionAction(focusSuggestion));
assert(applied.value === focusSuggestion.text, "suggestion fills the field");
const pending = coachingView(
  { quality: "vague", hint: "hint", suggestion: focusSuggestion },
  applied.value,
  vague.resume_step,
  applied.fill,
);
assert(!pending.showHint && pending.showUndo && pending.pendingLabel, "accepted suggestion is unsaved");
assert(undoCueFill(applied.fill) === vague.resume_step, "undo restores the earlier note");
const restored = coachingView(
  { quality: "vague", hint: "hint", suggestion: focusSuggestion },
  undoCueFill(applied.fill),
  vague.resume_step,
  null,
);
assert(restored.showHint && restored.action, "undo brings the hint back");

const stray = coachingView(
  { quality: "concrete", hint: "should not show", suggestion: focusSuggestion },
  "Run pytest",
  "Run pytest",
  null,
);
assert(!stray.showHint && !stray.action, "concrete ignores hint and suggestion");

assert(usefulResumeText({ resume_step: "Call the dentist", return_cue: null }) === "Call the dentist");
assert(usefulResumeText({ resume_step: "   ", return_cue: { quality: "missing" } }) === "");

assert(nowSrc.includes('from \'./return-cue.mjs\''), "Now uses the coaching module");
assert(nowSrc.includes('id="btn-use-cue"'), "pause field has the suggestion action");
assert(nowSrc.includes('id="btn-undo-cue"'), "suggestion can be undone");
assert(nowSrc.includes(">Save and pause</button>"), "save stays in the pause form");
assert(!nowSrc.includes('id="btn-use-cue" disabled'), "suggestion action is not disabled");
assert(nowSrc.includes("data-done="), "done stays on the working card");
assert(!nowSrc.includes("assess_return_cue"), "UI does not score cues");
assert(workSrc.includes("usefulResumeText"), "thread list uses the pickup helper");
assert(!overlapSrc.includes("return-cue"), "overlap review is unchanged");
assert(css.includes(".pause-form .return-cue"), "coaching has quiet styles");
assert(!css.slice(css.indexOf(".pause-form .return-cue"), css.indexOf("#suggestion .suggestion-cue")).includes("--danger"), "coaching is not a red alert");
assert(sw.includes("/ui/js/return-cue.mjs"), "service worker precaches the module");

console.log("return_cue_smoke: ok");
