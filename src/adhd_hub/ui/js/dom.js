import { state, $, setMsg, escapeHtml } from './state.js';

export async function copyReference(id) {
    try {
      await navigator.clipboard.writeText(id);
      setMsg("Reference copied. You can paste it into your assistant.");
    } catch (_) { setMsg("Clipboard unavailable. Thread reference: " + id); }
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
export function formatWhen(iso) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return String(iso).slice(0, 16);
      return new Intl.DateTimeFormat(undefined, {
        timeZone: state.currentTz || "UTC",
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(d);
    } catch (_e) {
      return String(iso).slice(0, 16);
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
      dlg.showModal();
    });
  }
