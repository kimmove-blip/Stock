const CACHE_NAME = 'ai-stock-v4';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
];

// 설치 이벤트
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// 활성화 이벤트
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// 네트워크 요청 가로채기
self.addEventListener('fetch', (event) => {
  // API 요청은 네트워크 우선
  if (event.request.url.includes('/api/')) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          // 성공 시 캐시에 저장
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
          return response;
        })
        .catch(() => {
          // 오프라인 시 캐시에서 반환
          return caches.match(event.request);
        })
    );
    return;
  }

  // 정적 자산은 캐시 우선
  event.respondWith(
    caches.match(event.request).then((response) => {
      if (response) {
        return response;
      }
      return fetch(event.request).then((response) => {
        // 성공 시 캐시에 저장
        if (response.status === 200) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      });
    })
  );
});

// 푸시 알림
self.addEventListener('push', (event) => {
  console.log('Push event received:', event);

  let data = {
    title: 'KimsAI Stock',
    body: '새로운 알림이 있습니다.',
    icon: '/icons/icon-192x192.png',
    badge: '/icons/icon-72x72.png',
    url: '/'
  };

  if (event.data) {
    try {
      const payload = event.data.json();
      data = {
        title: payload.title || data.title,
        body: payload.body || data.body,
        icon: payload.icon || data.icon,
        badge: payload.badge || data.badge,
        url: payload.data?.url || payload.url || data.url
      };
    } catch (e) {
      console.error('Push data parse error:', e);
    }
  }

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: data.icon,
      badge: data.badge,
      data: { url: data.url },
      vibrate: [200, 100, 200],
      renotify: true,
      tag: Date.now().toString(),
      silent: false
    }).then(() => {
      // 앱 아이콘에 배지 표시
      if (navigator.setAppBadge) {
        navigator.setAppBadge(1);
      }
    })
  );
});

// 알림 클릭
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  // 배지 제거
  if (navigator.clearAppBadge) {
    navigator.clearAppBadge();
  }

  const urlToOpen = event.notification.data?.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // 이미 열린 창이 있으면 포커스
      for (const client of clientList) {
        if (client.url.includes('stock.kims-ai.com') && 'focus' in client) {
          client.navigate(urlToOpen);
          return client.focus();
        }
      }
      // 없으면 새 창 열기
      return clients.openWindow(urlToOpen);
    })
  );
});
