import { state, $, setMsg, escapeHtml } from './state.js';

export async function copyText(text, successMsg) {
    try {
      await navigator.clipboard.writeText(text);
      setMsg(successMsg || "Copied.");
      return true;
    } catch (_) {
      setMsg("Clipboard unavailable.");
      return false;
    }
  }
export async function copyReference(id) {
    const ok = await copyText(id, "Reference copied. You can paste it into your assistant.");
    if (!ok) setMsg("Clipboard unavailable. Thread reference: " + id);
  }
export function safeHttpUrl(value) {
    try {
      const url = new URL(value);
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch (_) { return ""; }
  }
export function safeLink(value) {
    return escapeHtml(safeHttpUrl(value) || "#");
  }
export function browserTz() {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  }
export function fillTimezoneSelect(selected) {
    const sel = $("timezone");
    const local = browserTz();
    const extras = [
      "UTC",
      "Australia/Sydney",
      "Australia/Melbourne",
      "Australia/Brisbane",
      "Pacific/Auckland",
      "Asia/Tokyo",
      "Europe/London",
      "America/New_York",
      "America/Los_Angeles",
    ];
    const zones = Array.from(new Set([local, selected, ...extras].filter(Boolean)));
    sel.innerHTML = zones
      .map((z) => {
        const label = z === local ? `${z} (local)` : z;
        return `<option value="${escapeHtml(z)}">${escapeHtml(label)}</option>`;
      })
      .join("");
    sel.value = selected || local;
    state.currentTz = sel.value;
  }
/** Parse Hub timestamps; naive / date-only values are UTC (storage contract). */
export function parseHubInstant(iso) {
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
      // No offset → Hub UTC, not browser-local (avoids false 00:00 wall times).
      s = `${s}Z`;
    }
    const d = new Date(s);
    return Number.isNaN(d.getTime()) ? null : d;
  }
export function formatWhen(iso, timeZone) {
    if (!iso) return "";
    try {
      const d = parseHubInstant(iso);
      if (!d) return String(iso).slice(0, 19);
      return new Intl.DateTimeFormat(undefined, {
        timeZone: timeZone || state.currentTz || "UTC",
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(d);
    } catch (_e) {
      return String(iso).slice(0, 19);
    }
  }
/** Calm relative label ("yesterday", "3 days ago"); falls back to formatWhen past a year. */
export function formatRelative(iso, now = Date.now()) {
    const d = parseHubInstant(iso);
    if (!d) return "";
    const seconds = Math.round((d.getTime() - now) / 1000);
    const abs = Math.abs(seconds);
    if (abs < 60) return "just now";
    const units = [
      ["minute", 60, 3600],
      ["hour", 3600, 86400],
      ["day", 86400, 86400 * 7],
      ["week", 86400 * 7, 86400 * 30],
      ["month", 86400 * 30, 86400 * 365],
    ];
    const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
    for (const [unit, size, limit] of units) {
      if (abs < limit) return rtf.format(Math.round(seconds / size), unit);
    }
    return formatWhen(iso);
  }
/** Reformat injected Notes HTML <time datetime> labels using prefs / browser TZ. */
export function formatNotesTimes(root) {
    if (!root) return;
    root.querySelectorAll("time[datetime]").forEach((el) => {
      const iso = el.getAttribute("datetime");
      if (!iso) return;
      const label = formatWhen(iso);
      if (label) el.textContent = label;
    });
  }
/** Viewport floor for overflow menus (above mobile bottom nav when visible). */
function overflowMenuFloor() {
    const nav = document.querySelector(".mobile-nav");
    if (nav) {
      const cs = getComputedStyle(nav);
      if (cs.display !== "none" && cs.visibility !== "hidden") {
        return Math.min(window.innerHeight, nav.getBoundingClientRect().top);
      }
    }
    return window.innerHeight;
  }

/**
 * Flip / clamp an absolute overflow panel so it stays reachable without
 * scrolling the page (prefer open-down; flip up when space below is short).
 */
export function positionOverflowMenu(details) {
    const panel = details?.querySelector(
      ":scope > .thread-utility-panel"
    );
    if (!panel) return;
    panel.classList.remove("opens-up");
    panel.style.removeProperty("--overflow-menu-max-h");
    if (!details.open) return;

    const summary = details.querySelector(":scope > summary");
    if (!summary) return;

    // Measure with default (open-down) placement from CSS.
    const summaryRect = summary.getBoundingClientRect();
    const panelRect = panel.getBoundingClientRect();
    const panelH = Math.ceil(panelRect.height);
    const gap = 8;
    const floor = overflowMenuFloor();
    const spaceBelow = floor - summaryRect.bottom - gap;
    const spaceAbove = summaryRect.top - gap;
    const preferUp = spaceBelow < panelH && spaceAbove > spaceBelow;
    if (preferUp) panel.classList.add("opens-up");

    const available = Math.max(0, preferUp ? spaceAbove : spaceBelow);
    if (panelH > available && available >= 96) {
      panel.style.setProperty("--overflow-menu-max-h", `${Math.floor(available)}px`);
    }
  }

/** Wire toggle reposition for a details-based overflow menu (idempotent). */
export function wireOverflowMenu(details) {
    if (!details || details.dataset.overflowWired === "true") return;
    details.dataset.overflowWired = "true";
    details.addEventListener("toggle", () => {
      if (details.open) {
        requestAnimationFrame(() => positionOverflowMenu(details));
      } else {
        positionOverflowMenu(details);
      }
    });
  }

/**
 * Details-based menu: flips to fit, closes on Escape (focus back to its
 * button) and after an item inside is chosen. Idempotent.
 */
export function wireMenu(details) {
    if (!details || details.dataset.menuWired === "true") return;
    details.dataset.menuWired = "true";
    wireOverflowMenu(details);
    const summary = details.querySelector(":scope > summary");
    details.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || !details.open) return;
      event.preventDefault();
      event.stopPropagation();
      details.open = false;
      summary?.focus();
    });
    details.addEventListener("click", (event) => {
      const item = event.target.closest(".thread-utility-actions button, .thread-utility-actions a");
      if (item && details.contains(item)) details.open = false;
    });
  }

/** "Needs you" on My work: one summary line over approvals, imports and due reminders. */
let needsExpanded = false;
export function syncNeedsYou() {
    const wrap = $("needs-you");
    const body = $("needs-you-body");
    if (!wrap || !body) return;
    const count = body.querySelectorAll(".need").length;
    wrap.hidden = count === 0;
    if (!count) needsExpanded = false;
    $("needs-you-summary").textContent =
      count === 1 ? "1 thing needs a quick look" : `${count} things need a quick look`;
    body.hidden = !needsExpanded;
    const toggle = $("btn-toggle-needs");
    toggle.textContent = needsExpanded ? "Hide" : "Review";
    toggle.setAttribute("aria-expanded", String(needsExpanded));
  }
export function toggleNeedsYou() {
    needsExpanded = !needsExpanded;
    syncNeedsYou();
  }

/**
 * Close a modal <dialog> without letting the closing pointer event fall through
 * to controls underneath (e.g. Now overview links that switch to Progress).
 */
export function closeModal(dialog, returnValue) {
  if (!dialog) return;
  const root = document.documentElement;
  const prev = root.style.pointerEvents;
  root.style.pointerEvents = "none";
  try {
    if (returnValue !== undefined) dialog.close(returnValue);
    else dialog.close();
  } finally {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        root.style.pointerEvents = prev;
      });
    });
  }
}

export function confirmDialog({ title, body, extraHtml }) {
    return new Promise((resolve) => {
      $("confirm-title").textContent = title;
      $("confirm-body").textContent = body;
      $("confirm-extra").innerHTML = extraHtml || "";
      const dlg = $("confirm-dialog");
      const yes = $("confirm-yes");
      const capture = () => {
        const data = {};
        $("confirm-extra")
          .querySelectorAll("input, select, textarea")
          .forEach((el) => {
            if (el.type === "checkbox") data[el.id] = el.checked;
            else data[el.id] = el.value;
          });
        dlg._captured = data;
      };
      yes.addEventListener("click", capture, { once: true });
      const onClose = () => {
        dlg.removeEventListener("close", onClose);
        resolve({
          ok: dlg.returnValue === "yes",
          data: dlg._captured || {},
        });
      };
      dlg.addEventListener("close", onClose);
      // Escape keeps the old returnValue, so clear it or a past "yes" would count again.
      dlg.returnValue = "";
      dlg.showModal();
    });
  }
