const CACHE = "jarvis-v2";
const STATIC = [
  "/",
  "/static/manifest.json",
  "/health",
];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(STATIC))
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);

  // Cache static assets first
  if (url.pathname === "/" || url.pathname.startsWith("/static/")) {
    e.respondWith(
      caches.match(e.request).then((cached) => {
        const fetched = fetch(e.request).then((res) => {
          const clone = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, clone));
          return res;
        });
        return cached || fetched;
      })
    );
    return;
  }

  // API calls: network first, fallback to cache
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        const clone = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, clone));
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});

// Background sync for offline message queue
self.addEventListener("sync", (e) => {
  if (e.tag === "sync-messages") {
    e.waitUntil(syncMessages());
  }
});

async function syncMessages() {
  try {
    const cache = await caches.open("outbox");
    const keys = await cache.keys();
    for (const req of keys) {
      try {
        const res = await fetch(req);
        if (res.ok) {
          await cache.delete(req);
        }
      } catch (err) {
        console.log("Sync deferred:", err);
      }
    }
  } catch (err) {
    console.log("Sync error:", err);
  }
}

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  e.waitUntil(
    clients.matchAll({ type: "window" }).then((clientsList) => {
      if (clientsList.length > 0) {
        clientsList[0].focus();
      } else {
        clients.openWindow("/");
      }
    })
  );
});
