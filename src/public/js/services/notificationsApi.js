import { ApiClient } from './api.js?v=2';

const notificationsApi = new ApiClient('/notifications');

export async function listNotifications({ unreadOnly = false, category = null, limit = 50 } = {}) {
  const query = new URLSearchParams();
  if (unreadOnly) query.append('unread_only', 'true');
  if (category) query.append('category', category);
  query.append('limit', limit);
  return notificationsApi.get(`?${query}`);
}

export async function getUnreadCount() {
  return notificationsApi.get('/unread-count');
}

export async function markNotificationRead(notificationId) {
  return notificationsApi.post(`/${encodeURIComponent(notificationId)}/read`);
}

export async function markAllNotificationsRead() {
  return notificationsApi.post('/read-all');
}

export async function getVapidPublicKey() {
  const data = await notificationsApi.get('/push/vapid-public-key');
  return data?.publicKey || '';
}

export async function subscribePushSubscription(subscription) {
  const json = subscription.toJSON();
  return notificationsApi.post('/push/subscribe', {
    endpoint: json.endpoint,
    p256dh: json.keys?.p256dh || '',
    auth: json.keys?.auth || '',
  });
}

export async function unsubscribePushSubscription(endpoint) {
  return notificationsApi.post('/push/unsubscribe', { endpoint });
}

export async function sendTestNotification() {
  return notificationsApi.post('/push/test', {});
}

function _urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = window.atob(base64);
  return Uint8Array.from([...raw].map(char => char.charCodeAt(0)));
}

export async function isPushSupported() {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
}

// Enregistre le service worker puis s'abonne aux notifications (telephone).
// Retourne { enabled, reason } — ne lance jamais d'exception non gérée.
export async function enablePhoneNotifications() {
  if (!(await isPushSupported())) {
    return { enabled: false, reason: 'Ce navigateur ne prend pas en charge les notifications.' };
  }
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') {
    return { enabled: false, reason: 'Permission de notifications refusée.' };
  }
  const publicKey = await getVapidPublicKey();
  if (!publicKey) {
    return { enabled: false, reason: 'Notifications non configurées sur le serveur (clé VAPID absente).' };
  }
  try {
    const registration = await navigator.serviceWorker.register('/sw.js');
    const ready = await navigator.serviceWorker.ready;
    let subscription = await ready.pushManager.getSubscription();
    if (!subscription) {
      subscription = await ready.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: _urlBase64ToUint8Array(publicKey),
      });
    }
    await subscribePushSubscription(subscription);
    return { enabled: true, reason: null };
  } catch (error) {
    console.error('Abonnement push impossible:', error);
    return { enabled: false, reason: "Abonnement aux notifications impossible." };
  }
}
