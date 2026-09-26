/**
 * Smoke checks for Now title coercion + undo-done toast wiring.
 * Run: node tests/js/now_title_undo_smoke.mjs
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { threadDisplayTitle } from "../../src/adhd_hub/ui/js/thread-title.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const nowSrc = readFileSync(join(root, "src/adhd_hub/ui/js/now.js"), "utf8");
const stateSrc = readFileSync(join(root, "src/adhd_hub/ui/js/state.js"), "utf8");
const titleSrc = readFileSync(
  join(root, "src/adhd_hub/ui/js/thread-title.mjs"),
  "utf8"
);

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

assert(
  threadDisplayTitle({ summary: "Ship DNS" }) === "Ship DNS",
  "string summary should render"
);
assert(
  threadDisplayTitle({ summary: "  padded  " }) === "padded",
  "string summary should trim"
);
assert(
  threadDisplayTitle({ summary: "   " }) === "",
  "whitespace-only summary should be blank"
);
assert(
  threadDisplayTitle({
    summary: { done: "card", plan_focus: "x", next: [] },
  }) === "",
  "object-shaped summary must not become [object Object]"
);
assert(
  threadDisplayTitle({ summary: null }) === "",
  "null summary should be blank (not coerce)"
);
assert(threadDisplayTitle(null) === "", "null thread");
assert(
  String({ done: "x" }) === "[object Object]",
  "sanity: Object stringifies badly (the bug we avoid)"
);

assert(titleSrc.includes("export function threadDisplayTitle"), "helper in module");
assert(
  nowSrc.includes("from './thread-title.mjs'") ||
    nowSrc.includes('from "./thread-title.mjs"'),
  "now.js imports standalone title helper"
);
assert(nowSrc.includes("export { threadDisplayTitle }"), "now.js re-exports helper");
assert(nowSrc.includes("threadDisplayTitle(thread)"), "renderFocus uses helper");
assert(
  /const threadTitle = threadDisplayTitle\(thread\)/.test(nowSrc),
  "coding-agent prompt uses threadDisplayTitle"
);
assert(
  !/if \(thread\.summary && typeof thread\.summary === "string"\)/.test(nowSrc),
  "coding-agent prompt must not use raw whitespace-truthy summary"
);
assert(nowSrc.includes("/threads/undo-done"), "undo calls undo-done API");
assert(nowSrc.includes('label: "Undo"'), "Done toast offers Undo");
assert(
  nowSrc.includes("async function reloadAfterUndo"),
  "post-undo reloads are a separate helper"
);
assert(
  nowSrc.includes('error?.code === "UNDO_RELOAD_FAILED"'),
  "reload failures are tagged UNDO_RELOAD_FAILED"
);
assert(
  /const retryReload = \(\) => \{[\s\S]*reloadAfterUndo\(id, undoOpts\)\.catch/.test(
    nowSrc
  ),
  "reload-only Retry calls reloadAfterUndo (no undo-done)"
);
assert(
  /onClick: reloadOnly \? retryReload : retryUndo/.test(nowSrc),
  "catch routes undo vs reload Retry separately"
);
assert(
  /const retryUndo = \(\) => \{[\s\S]*undoMarkDone\(id, undoOpts\)\.catch\(\(error\) => \{[\s\S]*label: "Retry"/.test(
    nowSrc
  ),
  "failed undo recreates keyed toast with Retry"
);
assert(
  /finally \{[\s\S]*completing\.delete\(id\);[\s\S]*if \(marked\) \{[\s\S]*label: "Undo"/.test(
    nowSrc
  ),
  "Undo toast published after completing lock clears"
);
assert(stateSrc.includes("_toastSetAction"), "setMsg supports toast actions");
assert(stateSrc.includes("toast-action"), "toast action class wired");
// Keep toast removal-before-onClick; Retry lives in now.js, not state.js.
assert(
  /el\.remove\(\);\s*try \{\s*action\.onClick\(\);/.test(stateSrc),
  "toast action still removes toast before onClick"
);

console.log("now_title_undo_smoke: ok");
