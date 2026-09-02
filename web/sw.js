// Offline cache for pdftts.
//
// The point of the connector: a narration you have saved plays on the phone
// with the laptop asleep and no network. The app shell is cached on install;
// individual narrations are cached on demand when you tap "Save offline".
const SHELL = "pdftts-shell-v1";
const MEDIA = "pdftts-media-v1";
const SHELL_FILES = ["/", "/manifest.webmanifest", "/icon.svg"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== SHELL && k !== MEDIA).map(k => caches.delete(k))))
      .then(() => self.clients.claim()));
});

// Saving a narration: cache its audio and its detail JSON together, so the
// reader and the timeline survive offline too, not just the sound.
self.addEventListener("message", async event => {
  const { action, id } = event.data || {};
  const reply = r => event.source && event.source.postMessage(r);

  if (action === "save") {
    try {
      const cache = await caches.open(MEDIA);
      await cache.addAll([`/api/library/${id}`, `/api/library/${id}/audio`]);
      reply({ action: "saved", id, ok: true });
    } catch (err) {
      reply({ action: "saved", id, ok: false, error: String(err) });
    }
  }

  if (action === "forget") {
    const cache = await caches.open(MEDIA);
    await cache.delete(`/api/library/${id}`);
    await cache.delete(`/api/library/${id}/audio`);
    reply({ action: "forgotten", id });
  }

  if (action === "list") {
    const cache = await caches.open(MEDIA);
    const keys = await cache.keys();
    const ids = keys
      .map(r => (r.url.match(/\/api\/library\/([^/]+)\/audio$/) || [])[1])
      .filter(Boolean);
    reply({ action: "list", ids });
  }
});

self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== location.origin) return;

  // Saved narrations: cache first, so playback never waits on the server.
  if (/^\/api\/library\/[^/]+(\/audio)?$/.test(url.pathname)) {
    event.respondWith(
      caches.match(event.request).then(hit => hit || fetch(event.request)));
    return;
  }

  // Everything else: network first, falling back to the cached shell offline.
  event.respondWith(
    fetch(event.request)
      .then(res => {
        if (SHELL_FILES.includes(url.pathname)) {
          const copy = res.clone();
          caches.open(SHELL).then(c => c.put(event.request, copy));
        }
        return res;
      })
      .catch(() => caches.match(event.request).then(hit => hit || caches.match("/"))));
});
