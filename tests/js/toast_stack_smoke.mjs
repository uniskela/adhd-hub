/**
 * Smoke checks: celebration + Done/Undo share toast-host (no fixed-banner overlap).
 * Run: node tests/js/toast_stack_smoke.mjs
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const progressSrc = readFileSync(join(root, "src/adhd_hub/ui/js/progress.js"), "utf8");
const stateSrc = readFileSync(join(root, "src/adhd_hub/ui/js/state.js"), "utf8");
const css = readFileSync(join(root, "src/adhd_hub/ui/app.css"), "utf8");
const sw = readFileSync(join(root, "src/adhd_hub/ui/sw.js"), "utf8");
const pwaSrc = readFileSync(join(root, "src/adhd_hub/ui/js/pwa-update.js"), "utf8");
const workSrc = readFileSync(join(root, "src/adhd_hub/ui/js/work.js"), "utf8");
const nowSrc = readFileSync(join(root, "src/adhd_hub/ui/js/now.js"), "utf8");

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

assert(
  progressSrc.includes('CELEBRATION_TOAST_KEY = "celebration"'),
  "celebration uses a sticky toast key"
);
assert(
  /export function celebrate\(\) \{[\s\S]*setMsg\("One step finished\. Take a breath\."/.test(
    progressSrc
  ),
  "celebrate routes through setMsg / toast-host"
);
assert(
  /export function dismissCelebration\(\) \{[\s\S]*dismiss: true/.test(progressSrc),
  "dismissCelebration clears keyed celebration toast"
);
assert(
  !/export function celebrate\(\) \{[\s\S]*\$\("celebration"\)\.hidden = false/.test(
    progressSrc
  ),
  "celebrate must not show the fixed #celebration banner"
);

assert(css.includes(".toast-host"), "toast-host present");
assert(/\.toast-host\s*\{[^}]*gap:\s*\.55rem/.test(css), "toast-host stacks with gap");
assert(
  /flex-direction:\s*column-reverse/.test(css),
  "toast-host uses column-reverse stack"
);
assert(
  css.includes('.toast[data-key="celebration"]'),
  "celebration toast has distinct calm styling"
);

// Sticky / keyed notification paths that must share toast-host (not a second overlay).
assert(pwaSrc.includes('UPDATE_TOAST_KEY = "pwa-update"'), "PWA update toast keyed");
assert(pwaSrc.includes("sticky: true"), "PWA update toast sticky");
assert(workSrc.includes("rewriteAllToastKey"), "rewrite-all toast keyed");
assert(workSrc.includes("sticky: true"), "rewrite-all toast sticky");
assert(nowSrc.includes('toastKey = "notes-summarise"'), "notes summarise toast keyed");
assert(nowSrc.includes('key: `done-${id}`'), "Done/Undo toast keyed for replace");

assert(stateSrc.includes("opts.key"), "setMsg supports sticky keys");
assert(
  /if \(key && opts\.dismiss\)/.test(stateSrc),
  "setMsg dismisses by key when text empty"
);

assert(sw.includes("adhd-hub-shell-v45"), "PWA shell cache bumped past v40");

console.log("toast_stack_smoke: ok");
