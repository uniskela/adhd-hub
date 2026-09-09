/* ADHD Progress Hub — shell cache only. Never caches /api or auth. */
const CACHE = "adhd-hub-shell-v1";
const PRECACHE = [
  "/ui/",
  "/ui/app.css",
  "/ui/app.js",
  "/ui/manifest.webmanifest",
  "/ui/brand/icon.svg",
  "/ui/brand/icon-192.png",
  "/ui/brand/icon-512.png",
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

  // Network-first for HTML shell so deploys show up; cache fallback offline.
  if (url.pathname === "/ui" || url.pathname === "/ui/" || url.pathname.endsWith(".html")) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put("/ui/", copy));
          return res;
        })
        .catch(() => caches.match("/ui/"))
    );
    return;
  }

  if (!url.pathname.startsWith("/ui/")) return;

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
