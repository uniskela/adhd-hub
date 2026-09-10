/* ADHD Progress Hub — shell cache only. Never caches /api or auth. */
const CACHE = "adhd-hub-shell-v4";
const PRECACHE = [
  "/ui/",
  "/ui/manifest.webmanifest",
  "/ui/brand/icon.svg",
  "/ui/brand/icon-192.png",
  "/ui/brand/icon-512.png",
  "/ui/js/boot.js",
  "/ui/js/state.js",
  "/ui/js/api.js",
  "/ui/js/auth.js",
  "/ui/js/dom.js",
  "/ui/js/screens.js",
  "/ui/js/theme.js",
  "/ui/js/load.js",
  "/ui/js/now.js",
  "/ui/js/work.js",
  "/ui/js/progress.js",
  "/ui/js/settings.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/mcp")) return;
  if (!url.pathname.startsWith("/ui")) return;

  // Network-first for HTML/JS/CSS so upgrades land; cache as offline fallback.
  const networkFirst =
    url.pathname === "/ui" ||
    url.pathname === "/ui/" ||
    url.pathname.endsWith(".html") ||
    url.pathname.endsWith(".js") ||
    url.pathname.endsWith(".css");

  if (networkFirst) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((cache) => cache.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req).then((hit) => hit || caches.match("/ui/")))
    );
    return;
  }

  event.respondWith(
    caches.match(req).then(
      (hit) =>
        hit ||
        fetch(req).then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((cache) => cache.put(req, copy));
          }
          return res;
        })
    )
  );
});
