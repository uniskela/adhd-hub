/** Tiny field-tip + example-ghost helpers for forge forms. */

export const IMPORT_POLICY_HINTS = {
  manual:
    "Manual — Sync only checks already-linked threads. It will not import new issues (0 imported).",
  all_open:
    "All open issues — Import every open issue in the target owner/repo (no extra filter).",
  labels:
    "Matching labels — Import open issues that have at least one of the Import labels listed below.",
  assigned_to_me:
    "Assigned to me — Import open issues assigned to Account login (or the token’s /user login).",
  adhd_inbox:
    "ADHD inbox — Import issues from allowlisted authors with an [ADHD] title and/or hub label. Fail closed if inbox authors are empty.",
};

export const IMPORT_POLICY_LABELS = {
  manual: "Manual — no auto-import",
  all_open: "All open issues",
  labels: "Matching labels",
  assigned_to_me: "Assigned to me",
  adhd_inbox: "ADHD inbox ([ADHD] / hub label)",
};

/** Build a focusable ? tip control (string HTML for template cards). */
export function tipHtml(text, { id } = {}) {
  const tipId = id || `tip-${Math.random().toString(36).slice(2, 9)}`;
  const safe = String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
  return `<button type="button" class="field-tip" aria-describedby="${tipId}" aria-label="More info">?<span id="${tipId}" class="field-tip-panel" role="tooltip">${safe}</span></button>`;
}

/** Wrap an existing <label> element: insert tip before the first control. */
export function attachTip(labelEl, text) {
  if (!labelEl || labelEl.querySelector(".field-tip")) return;
  const tip = document.createElement("button");
  tip.type = "button";
  tip.className = "field-tip";
  tip.setAttribute("aria-label", "More info");
  const panel = document.createElement("span");
  panel.className = "field-tip-panel";
  panel.setAttribute("role", "tooltip");
  panel.id = `tip-${Math.random().toString(36).slice(2, 9)}`;
  panel.textContent = text;
  tip.setAttribute("aria-describedby", panel.id);
  tip.appendChild(panel);
  tip.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    tip.classList.toggle("open");
  });
  const control = labelEl.querySelector("input, select, textarea");
  if (control) labelEl.insertBefore(tip, control);
  else labelEl.appendChild(tip);
}

/** Parse https://host/owner/repo[.git] → { owner, repo } or null.
 * Uses the first two path segments so /owner/repo/tree/main still works. */
export function parseOwnerRepoFromUrl(url) {
  const raw = String(url || "").trim();
  if (!raw) return null;
  try {
    let path = raw;
    if (/^[a-z][a-z0-9+.-]*:\/\//i.test(raw)) {
      const u = new URL(raw);
      path = u.pathname || "";
    } else if (raw.includes(":") && !raw.includes("://") && raw.includes("/")) {
      const after = raw.split(":").slice(1).join(":");
      path = after.startsWith("/") ? after : `/${after}`;
    } else if (raw.includes("/") && !raw.includes(" ")) {
      path = raw.startsWith("/") ? raw : `/${raw}`;
    } else {
      return null;
    }
    let parts = path
      .split("/")
      .map((p) => p.trim())
      .filter(Boolean);
    if (parts.length < 2) return null;
    if (
      ["api", "gitea", "src", "repos"].includes(parts[0].toLowerCase()) &&
      parts.length >= 4
    ) {
      for (let i = 0; i < parts.length - 1; i++) {
        if (
          ["repos", "repositories"].includes(parts[i].toLowerCase()) &&
          i + 2 < parts.length
        ) {
          parts = parts.slice(i + 1);
          break;
        }
      }
    }
    const owner = parts[0];
    const repo = parts[1].replace(/\.git$/i, "");
    if (!owner || !repo || owner.includes(":") || repo.includes(":")) return null;
    if (/^https?$/i.test(owner)) return null;
    return { owner, repo };
  } catch {
    return null;
  }
}

/** Normalize forge owner/repo inputs: strip URL → name fragments. */
export function normalizeForgeOwnerRepo(owner, repo) {
  let o = String(owner || "").trim();
  let r = String(repo || "").trim();
  if (r.includes("://") || r.includes("git@") || (r.includes("/") && !o)) {
    const parsed = parseOwnerRepoFromUrl(
      r.startsWith("http") || r.includes("git@") ? r : `https://placeholder.invalid/${r}`
    );
    if (parsed) {
      if (!o) o = parsed.owner;
      r = parsed.repo;
    }
  }
  if (o.includes("://") || o.includes("/")) {
    const parsed = parseOwnerRepoFromUrl(o);
    if (parsed) {
      o = parsed.owner;
      if (!r) r = parsed.repo;
    }
  }
  if (o.includes("://")) o = "";
  if (r.includes("://")) r = "";
  o = o.replace(/^\/+|\/+$/g, "");
  r = r.replace(/^\/+|\/+$/g, "").replace(/\.git$/i, "");
  return { owner: o, repo: r };
}
