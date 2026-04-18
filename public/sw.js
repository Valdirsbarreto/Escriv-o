// Escrivão AI — Service Worker mínimo (habilita instalação PWA)
const CACHE = "escrivao-v1";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(clients.claim()));

self.addEventListener("fetch", (e) => {
  // Passa tudo para a rede (sem cache offline por ora)
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
