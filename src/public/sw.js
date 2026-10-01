/* Service worker ForgeAI : notifications Web Push (telephone) + cache statique. */

/* Cache strictement limite aux ressources statiques (CSS/JS/icônes).
   Jamais l'API ni les pages HTML : aucune donnee utilisateur en cache. */
const STATIC_CACHE = 'forgeai-static-v5';
const STATIC_PREFIXES = ['/css/', '/js/', '/icons/'];

self.addEventListener('install', event => {
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(key => key !== STATIC_CACHE).map(key => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (!STATIC_PREFIXES.some(prefix => url.pathname.startsWith(prefix))) return;

  event.respondWith(
    caches.open(STATIC_CACHE).then(async cache => {
      const cached = await cache.match(request);
      /* Stale-while-revalidate : reponse cachee immediatee, reactualisation
         en arriere-plan (prise en compte du prochain deploiement). */
      fetch(request).then(response => {
        if (response && response.ok) cache.put(request, response.clone());
      }).catch(() => {});
      if (cached) return cached;
      return fetch(request);
    })
  );
});

self.addEventListener('push', event => {
  let payload = { title: 'ForgeAI', body: '' };
  try {
    if (event.data) {
      const parsed = event.data.json();
      if (parsed && typeof parsed === 'object') payload = { ...payload, ...parsed };
      else payload.body = String(parsed);
    }
  } catch (error) {
    payload.body = event.data ? event.data.text() : '';
  }
  const options = {
    body: payload.body || '',
    tag: payload.tag || 'forgeai',
    data: { url: payload.url || '/' },
  };
  event.waitUntil((async () => {
    await self.registration.showNotification(payload.title || 'ForgeAI', options);
    await _updateAppBadge(payload.unread);
  })());
});

/* Pastille sur l'icone d'accueil (Badging API : iOS 16.4+ / Chrome).
   Pose le nombre de notifications non lues. Si l'app est deja ouverte
   et visible, la pastille n'est pas posee : l'utilisateur est dedans. */
async function _updateAppBadge(unread) {
  if (!('setAppBadge' in self.navigator)) return;
  const count = Number(unread);
  if (!Number.isFinite(count) || count <= 0) return;
  try {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    if (windows.some(client => client.visibilityState === 'visible')) return;
    await self.navigator.setAppBadge(count);
  } catch (error) {
    /* best-effort : la notification reste affichee meme sans pastille. */
  }
}

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clients => {
      for (const client of clients) {
        if ('focus' in client) {
          client.navigate(url);
          return client.focus();
        }
      }
      return self.clients.openWindow(url);
    })
  );
});
