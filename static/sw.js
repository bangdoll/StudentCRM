// StudentCRM Service Worker v1.3 - Local-First & Offline Resilience
const CACHE_NAME = 'student-crm-v1.3';
const PRECACHE_ASSETS = [
  '/static/style.css',
  '/static/site.webmanifest',
  '/static/favicon.svg',
  '/static/apple-touch-icon.png',
  '/static/logo.svg',
  '/static/icon-192.png'
];

// Install: pre-cache critical static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_ASSETS).catch((err) => {
        console.warn('Pre-cache partial failure:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

// Activate: clean up obsolete cache versions
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch dispatcher
self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Only handle GET requests
  if (request.method !== 'GET') return;

  // 1. External fonts (Google Fonts & Webfonts) -> Cache-First
  if (url.origin === 'https://fonts.googleapis.com' || url.origin === 'https://fonts.gstatic.com') {
    event.respondWith(
      caches.match(request).then((cachedResponse) => {
        if (cachedResponse) return cachedResponse;
        return fetch(request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, responseClone));
          }
          return networkResponse;
        }).catch(() => cachedResponse);
      })
    );
    return;
  }

  // Ignore external origins
  if (url.origin !== self.location.origin) return;

  // 2. Cache-First for static assets
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then((cachedResponse) => {
        if (cachedResponse) return cachedResponse;
        return fetch(request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, responseClone));
          }
          return networkResponse;
        });
      })
    );
    return;
  }

  // 3. Stale-While-Revalidate for read-only learning APIs & dynamic student manifests
  if (
    url.pathname.startsWith('/api/cases') ||
    url.pathname.startsWith('/api/practice/random') ||
    url.pathname.endsWith('/manifest.webmanifest')
  ) {
    event.respondWith(
      caches.match(request).then((cachedResponse) => {
        const fetchPromise = fetch(request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, responseClone));
          }
          return networkResponse;
        }).catch(() => cachedResponse);

        if (cachedResponse) {
          event.waitUntil(fetchPromise);
          return cachedResponse;
        }
        return fetchPromise;
      })
    );
    return;
  }

  // 4. Stale-While-Revalidate for navigation/HTML requests (dashboard, apple-ceo, notes, student hubs)
  if (request.mode === 'navigate' || request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(
      caches.match(request).then((cachedResponse) => {
        const fetchPromise = fetch(request)
          .then((networkResponse) => {
            if (networkResponse && networkResponse.status === 200) {
              const responseClone = networkResponse.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(request, responseClone));
            }
            return networkResponse;
          })
          .catch(() => {
            // If network fails, return cached page
            if (cachedResponse) return cachedResponse;
            if (!url.pathname.startsWith('/my/') && !url.pathname.startsWith('/hub/') && !url.pathname.startsWith('/note')) {
              return caches.match('/');
            }
            return new Response(
              '<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>離線閱讀模式</title><link rel="stylesheet" href="/static/style.css"></head><body style="padding: 40px; text-align: center; color: #c9d1d9; background: #0d1117;"><div style="max-width: 500px; margin: 0 auto;"><h3>📱 您目前處於離線狀態</h3><p style="color: #8b949e; margin: 12px 0 20px;">若此頁面或筆記先前已開啟過，將自動從本機快取為您載入；否則請重新整理或恢復連線後再試。</p><a href="javascript:location.reload()" style="display: inline-block; padding: 8px 18px; background: #238636; color: #fff; text-decoration: none; border-radius: 6px; font-weight: 600;">重新整理</a></div></body></html>',
              { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
            );
          });

        if (cachedResponse) {
          event.waitUntil(fetchPromise);
          return cachedResponse;
        }
        return fetchPromise;
      })
    );
  }
});
