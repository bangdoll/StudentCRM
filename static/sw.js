// StudentCRM Service Worker - Local-First & Offline Resilience
const CACHE_NAME = 'student-crm-v1.1';
const PRECACHE_ASSETS = [
  '/static/css/style.css',
  '/static/manifest.json',
  '/static/favicon.ico',
  '/static/apple-touch-icon.png'
];

// Install: pre-cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_ASSETS).catch((err) => {
        console.warn('Pre-cache partial failure:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

// Activate: clean up obsolete caches
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

// Fetch: Stale-While-Revalidate for HTML pages, Cache-First for static assets
self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Only handle GET requests
  if (request.method !== 'GET') return;

  // Ignore chrome-extension or external analytics
  if (url.origin !== self.location.origin) return;

  // Cache-first for static assets
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then((cachedResponse) => {
        if (cachedResponse) {
          return cachedResponse;
        }
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

  // Stale-While-Revalidate for navigation/HTML requests (home, apple-ceo, student pages)
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
            // If network fails, return cached page; do not fallback to / for student hubs
            if (cachedResponse) return cachedResponse;
            if (!url.pathname.startsWith('/my/') && !url.pathname.startsWith('/hub/')) {
              return caches.match('/');
            }
            return new Response('<h3>您目前處於離線狀態</h3><p>請重新整理或恢復連線後再試。</p>', {
              headers: { 'Content-Type': 'text/html; charset=utf-8' }
            });
          });

        return cachedResponse || fetchPromise;
      })
    );
  }
});
