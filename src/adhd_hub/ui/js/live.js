import { api } from './api.js';
import { loadAll } from './load.js';
import { $, setMsg } from './state.js';
import { refreshSyncHealth } from './sync-health.js';

const DEBOUNCE_MS = 400;
let source = null;
let debounceTimer = null;
let reconnectTimer = null;
let intentionalClose = false;

function setLiveState(state, detail) {
  const el = $("live-connection");
  if (!el) return;
  el.dataset.state = state;
  el.textContent =
    state === "live" ? "Live" : state === "reconnecting" ? "Reconnecting…" : "Offline";
  el.title = detail || "";
  el.hidden = false;
}

function scheduleRefresh() {
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    debounceTimer = null;
    loadAll()
      .then(() => refreshSyncHealth().catch(() => {}))
      .catch((err) => setMsg(err.message || "Could not refresh after live update."));
  }, DEBOUNCE_MS);
}

function clearReconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
}

export function stopLiveInvalidation() {
  intentionalClose = true;
  clearReconnect();
  if (debounceTimer) {
    clearTimeout(debounceTimer);
    debounceTimer = null;
  }
  if (source) {
    source.close();
    source = null;
  }
  setLiveState("offline", "Live updates paused.");
}

export function startLiveInvalidation() {
  intentionalClose = false;
  clearReconnect();
  if (source) {
    source.close();
    source = null;
  }
  // Same-origin EventSource sends the session cookie (path=/api).
  source = new EventSource("/api/events/stream");
  setLiveState("reconnecting", "Connecting to live updates…");

  source.addEventListener("open", () => {
    setLiveState("live", "Receiving live invalidation events.");
  });

  source.addEventListener("invalidate", () => {
    setLiveState("live", "Receiving live invalidation events.");
    scheduleRefresh();
  });

  source.onerror = () => {
    if (intentionalClose) return;
    setLiveState("reconnecting", "Live connection interrupted; retrying.");
    // EventSource auto-reconnects; also refresh when the tab becomes visible again.
    if (source && source.readyState === EventSource.CLOSED) {
      source = null;
      clearReconnect();
      reconnectTimer = setTimeout(() => {
        if (!intentionalClose) startLiveInvalidation();
      }, 3000);
    }
  };
}

export function bindLiveInvalidation() {
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    // Catch-up without depending on every SSE event.
    loadAll()
      .then(() => refreshSyncHealth().catch(() => {}))
      .catch(() => {});
    if (!source || source.readyState === EventSource.CLOSED) {
      startLiveInvalidation();
    }
  });
}

export async function probeLiveWithoutSse() {
  // Safe degradation path: ordinary API still works when EventSource is blocked.
  try {
    await api("/sync-health");
    return true;
  } catch (_) {
    return false;
  }
}
