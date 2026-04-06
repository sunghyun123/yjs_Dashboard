/* YJS Dashboard — 최소 PWA(설치용). 오프라인 캐시는 사용하지 않습니다. */
self.addEventListener('install', (event) => {
    event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
    event.waitUntil(self.clients.claim());
});
