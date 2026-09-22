/**
 * Smoke-test parseHubInstant / formatWhen without loading the full UI module graph.
 * Mirrors the logic in src/adhd_hub/ui/js/dom.js — keep in sync when changing parse rules.
 */
function parseHubInstant(iso) {
  if (iso == null || iso === "") return null;
  if (iso instanceof Date) {
    return Number.isNaN(iso.getTime()) ? null : iso;
  }
  let s = String(iso).trim();
  if (!s) return null;
  if (/^\d{4}-\d{2}-\d{2} /.test(s)) s = s.replace(" ", "T");
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    s = `${s}T00:00:00.000Z`;
  } else if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s)) {
    s = `${s}Z`;
  }
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatWhen(iso, timeZone) {
  if (!iso) return "";
  const d = parseHubInstant(iso);
  if (!d) return String(iso).slice(0, 19);
  return new Intl.DateTimeFormat("en-AU", {
    timeZone: timeZone || "UTC",
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
}

const cases = [
  ["2026-09-23T14:30:21", "2026-09-23T14:30:21.000Z"],
  ["2026-09-23T14:30:21Z", "2026-09-23T14:30:21.000Z"],
  ["2026-09-23", "2026-09-23T00:00:00.000Z"],
  ["2026-09-23T00:00:00", "2026-09-23T00:00:00.000Z"],
];
for (const [input, expect] of cases) {
  const d = parseHubInstant(input);
  if (!d || d.toISOString() !== expect) {
    console.error("parse mismatch", input, d && d.toISOString(), expect);
    process.exit(1);
  }
}

const afternoon = formatWhen("2026-09-23T04:15:00Z", "Australia/Sydney");
if (afternoon.includes("00:00")) {
  console.error("afternoon collapsed to midnight", afternoon);
  process.exit(1);
}
if (!afternoon.includes("23 Sept 2026")) {
  console.error("unexpected afternoon label", afternoon);
  process.exit(1);
}

// Naive midnight must be UTC → 10:00 AEST in Sydney (not browser-local 00:00)
const naiveMid = formatWhen("2026-09-23T00:00:00", "Australia/Sydney");
if (naiveMid.includes("00:00")) {
  console.error("naive midnight displayed as local 00:00", naiveMid);
  process.exit(1);
}
if (!/10:00|11:00/.test(naiveMid)) {
  console.error("expected Sydney morning for UTC midnight", naiveMid);
  process.exit(1);
}

// Source / Updated style stamp with real clock time
const imported = formatWhen("2026-09-23T10:15:30Z", "Australia/Sydney");
if (imported.includes("00:00")) {
  console.error("imported stamp became midnight", imported);
  process.exit(1);
}

console.log("ok", { afternoon, naiveMid, imported });
