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
  /\.triage-item\s*\{[^}]*flex-wrap:\s*wrap/.test(css),
  "Still relevant rows wrap instead of squeezing the actions"
);
assert(!nowSrc.includes("triage-banner"), "Still relevant lives on Now only (no My work banner)");

assert(nowSrc.includes('class="triage-copy"'), "Quiet check-in uses triage-copy");
assert(
  /<div class="triage-copy"><strong class="triage-title">/.test(nowSrc),
  "Now-screen gentle check uses the triage title markup"
);
assert(nowSrc.includes("Is this still on your list?"), "Now-screen gentle check asks plainly");
assert(
  /\.check-actions\s*\{[^}]*flex:\s*0\s+0\s+auto/.test(css),
  "gentle check actions do not shrink under long step names"
);

assert(sw.includes("adhd-hub-shell-v44"), "PWA shell cache bumped for triage CSS");

console.log("triage_layout_smoke: ok");
