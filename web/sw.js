/*
 * YJS Dashboard — 최소 PWA(설치용) 서비스 워커.
 * 의도적으로 fetch 이벤트를 가로채지 않아 오프라인 캐싱을 하지 않습니다.
 *  - 신규 배포의 JS/CSS가 즉시 반영됨 (정적 파일 stale 이슈 없음).
 *  - 모바일에서 "홈 화면에 추가" 가능하도록 manifest와 함께 PWA 자격만 충족.
 * 만약 오프라인 모드가 필요해지면 fetch 이벤트에서 stale-while-revalidate 캐싱을 추가하세요.
 */
self.addEventListener('install', (event) => {
    event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
    event.waitUntil(self.clients.claim());
});
