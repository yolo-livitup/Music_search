const CACHE = "music-search-v1";
const PRECACHE = ["/", "/index.html", "/style.css", "/app.js", "/manifest.json"];

self.addEventListener("install", (e) => {
    e.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)));
    self.skipWaiting();
});

self.addEventListener("activate", (e) => {
    e.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener("fetch", (e) => {
    if (e.request.method !== "GET") return;
    e.respondWith(
        caches.open(CACHE).then((cache) =>
            cache.match(e.request).then(
                (cached) =>
                    cached ||
                    fetch(e.request).then((res) => {
                        if (res.ok && res.type === "basic") {
                            cache.put(e.request, res.clone());
                        }
                        return res;
                    })
            )
        )
    );
});
