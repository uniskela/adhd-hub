/**
 * Smoke checks for Now title coercion + undo-done toast wiring.
 * Run: node tests/js/now_title_undo_smoke.mjs
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const nowSrc = readFileSync(join(root, "src/adhd_hub/ui/js/now.js"), "utf8");
const stateSrc = readFileSync(join(root, "src/adhd_hub/ui/js/state.js"), "utf8");

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

// Mirror threadDisplayTitle (keep in sync with now.js).
function threadDisplayTitle(thread) {
  if (!thread || typeof thread !== "object") return "";
  const raw = thread.summary;
  if (typeof raw === "string") return raw.trim();
  if (raw && typeof raw === "object") return "";
  return "";
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

assert(nowSrc.includes("export function threadDisplayTitle"), "helper exported");
assert(nowSrc.includes("threadDisplayTitle(thread)"), "renderFocus uses helper");
assert(nowSrc.includes("/threads/undo-done"), "undo calls undo-done API");
assert(nowSrc.includes('label: "Undo"'), "Done toast offers Undo");
assert(stateSrc.includes("_toastSetAction"), "setMsg supports toast actions");
assert(stateSrc.includes("toast-action"), "toast action class wired");

console.log("now_title_undo_smoke: ok");
