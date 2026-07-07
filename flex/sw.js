// THE FLEX Service Worker
const CACHE_NAME = 'flex-v9'; // バージョン上げてキャッシュリフレッシュ
const CORE_ASSETS = [
  './manifest.json',
  './kaching.wav',
  './reward.wav',
  './coin.wav',
  './bell.wav',
];

self.addEventListener('install', (e) => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE_NAME).then((c) => c.addAll(CORE_ASSETS).catch(()=>{}))
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;

  let url;
  try { url = new URL(req.url); } catch(_) { return; }

  // index.html / ルート / HTML は network-first（常に最新を取得）
  const isHTML = url.pathname === '/' ||
                 url.pathname.endsWith('/') ||
                 url.pathname.endsWith('.html') ||
                 req.destination === 'document';

  if (isHTML) {
    e.respondWith(
      fetch(req).then((res) => {
        if (res && res.ok) {
          try {
            const clone = res.clone();
            caches.open(CACHE_NAME).then((c) => c.put(req, clone)).catch(()=>{});
          } catch(_){}
        }
        return res;
      }).catch(() => caches.match(req))
    );
    return;
  }

  // それ以外: stale-while-revalidate
  e.respondWith(
    caches.match(req).then((cached) => {
      const network = fetch(req).then((res) => {
        try {
          if (res && res.status === 200 && url.origin === location.origin) {
            const clone = res.clone();
            caches.open(CACHE_NAME).then((c) => c.put(req, clone)).catch(()=>{});
          }
        } catch(_){}
        return res;
      }).catch(() => cached);
      return cached || network;
    })
  );
});
