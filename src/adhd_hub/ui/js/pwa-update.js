/**
 * Calm PWA update nudge — adapted from ts6-manager’s waiting-SW + SKIP_WAITING flow.
 * Does not auto-activate updates; Refresh posts SKIP_WAITING then reloads on controllerchange.
 */
import { setMsg } from "./state.js";

const UPDATE_TOAST_KEY = "pwa-update";
const CHECK_MIN_MS = 60_000;
const RELOAD_FALLBACK_MS = 12_000;

/**
 * Register the Hub shell service worker and offer a sticky Refresh toast when a
 * new worker is waiting (an active worker already controls the page).
 */
export function registerPwaUpdates() {
  if (!("serviceWorker" in navigator) || !window.isSecureContext) return;

  /** @type {ServiceWorkerRegistration | undefined} */
  let registration;
  let hadController = Boolean(navigator.serviceWorker.controller);
  let refreshing = false;
  let activating = false;
  let lastCheck = 0;

  const offerRefresh = (reg) => {
    if (!reg?.active || !reg.waiting) return;
    setMsg("A newer Hub is ready.", {
      key: UPDATE_TOAST_KEY,
      sticky: true,
      variant: "info",
      action: {
        label: "Refresh",
        onClick: () => {
          if (activating) return;
          activating = true;
          const waiting = reg.waiting;
          if (!waiting) {
            window.location.reload();
            return;
          }
          waiting.postMessage({ type: "SKIP_WAITING" });
          window.setTimeout(() => {
            if (!refreshing) window.location.reload();
          }, RELOAD_FALLBACK_MS);
        },
      },
    });
  };

  const detectWaiting = () => {
    if (registration) offerRefresh(registration);
  };

  const onUpdateFound = () => {
    const worker = registration?.installing;
    worker?.addEventListener("statechange", () => {
      if (worker.state === "installed") detectWaiting();
    });
  };

  const checkUpdate = () => {
    if (!registration || !navigator.onLine || document.visibilityState === "hidden") {
      return;
    }
    if (Date.now() - lastCheck < CHECK_MIN_MS) return;
    lastCheck = Date.now();
    void registration.update().catch(() => {
      /* Retry on the next check / resume. */
    });
  };

  const resume = () => {
    checkUpdate();
    detectWaiting();
  };

  navigator.serviceWorker.addEventListener("controllerchange", () => {
    // First install claims without interrupting. Reload only this tab after Refresh
    // (other controlled tabs get controllerchange via clients.claim but keep working).
    if (hadController && activating && !refreshing) {
      refreshing = true;
      window.location.reload();
    }
    hadController = Boolean(navigator.serviceWorker.controller);
  });

  void navigator.serviceWorker
    .register("/ui/sw.js", { scope: "/ui/", updateViaCache: "none" })
    .then((reg) => {
      registration = reg;
      reg.addEventListener("updatefound", onUpdateFound);
      onUpdateFound();
      detectWaiting();
      checkUpdate();
    })
    .catch(() => {
      /* Progressive enhancement — browser use still works without a SW. */
    });

  window.setInterval(resume, CHECK_MIN_MS);
  window.addEventListener("online", resume);
  document.addEventListener("visibilitychange", resume);
}
