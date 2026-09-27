/**
 * Smoke: Quiet check-in / Still-relevant triage keeps actions end-aligned.
 * Run: node tests/js/triage_layout_smoke.mjs
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const css = readFileSync(join(root, "src/adhd_hub/ui/app.css"), "utf8");
const nowSrc = readFileSync(join(root, "src/adhd_hub/ui/js/now.js"), "utf8");
const sw = readFileSync(join(root, "src/adhd_hub/ui/sw.js"), "utf8");

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

assert(css.includes(".triage-copy"), "triage-copy class present");
assert(css.includes(".triage-title"), "triage-title class present");
assert(
  /\.triage-copy\s*\{[^}]*min-width:\s*0/.test(css),
  "triage-copy uses min-width: 0 so title can shrink"
);
assert(
  /\.triage-title\s*\{[^}]*display:\s*block[^}]*text-overflow:\s*ellipsis/.test(css),
  "triage-title is block-level so ellipsis works on inline strong"
);
assert(
  /\.triage-actions\s*\{[^}]*flex:\s*0\s+0\s+auto/.test(css),
  "triage-actions do not shrink under long titles"
);
assert(
  /\.triage-item,\s*\n\.thread-triage\s*\{[^}]*flex-wrap:\s*wrap/.test(css) ||
    /\.triage-item,\s*\.thread-triage\s*\{[^}]*flex-wrap:\s*wrap/.test(css),
  "Quiet strip and in-card triage share flex wrap row"
);

assert(nowSrc.includes('class="triage-copy"'), "Quiet check-in uses triage-copy");
assert(
  /<div class="triage-copy"><strong class="triage-title">/.test(nowSrc),
  "Now-screen strip uses the triage title markup"
);
assert(
  /\.thread-triage\s*>\s*\.hint\s*\{[^}]*min-width:\s*0/.test(css),
  "in-card triage hint shrinks via CSS (no work.js markup change)"
);

assert(sw.includes("adhd-hub-shell-v42"), "PWA shell cache bumped for triage CSS");

console.log("triage_layout_smoke: ok");
