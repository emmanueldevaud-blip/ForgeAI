import {
  listNotifications,
  getUnreadCount,
  markNotificationRead,
  markAllNotificationsRead,
} from '../services/notificationsApi.js?v=2';

const POLL_INTERVAL_MS = 60000;

function formatDateTime(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str ?? '';
  return div.innerHTML;
}

/* Cloche de notifications du header : pastille d'unread + panneau listant les
   dernières notifications (analyses, conseils du coach, système). */
export class NotificationBell {
  constructor(options = {}) {
    this.onNavigate = options.onNavigate || (() => {});
    this.element = null;
    this.isOpen = false;
    this.unread = 0;
    this.items = [];
    this._pollTimer = null;
    this._boundOutsideClick = this._handleOutsideClick.bind(this);
  }

  mount(container) {
    this.element = container;
    this.element.className = 'header-notifications';
    this.element.innerHTML = `
      <button type="button" class="header-bell-btn" aria-label="Notifications" aria-expanded="false" data-action="toggle-notifications">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
          <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
        </svg>
        <span class="header-bell-badge" hidden></span>
      </button>
      <div class="notification-panel hidden" role="dialog" aria-label="Notifications">
        <div class="notification-panel-header">
          <h4 class="notification-panel-title">Notifications</h4>
          <button type="button" class="notification-panel-clear" data-action="mark-all">Tout marquer lu</button>
        </div>
        <div class="notification-panel-list" data-list>
          <p class="empty-message">Chargement…</p>
        </div>
      </div>
    `;

    this.element
      .querySelector('[data-action="toggle-notifications"]')
      ?.addEventListener('click', (event) => {
        event.stopPropagation();
        this.toggle();
      });
    this.element
      .querySelector('[data-action="mark-all"]')
      ?.addEventListener('click', () => this.markAllRead());

    this.refresh();
    this._startPolling();
    return this;
  }

  async refresh() {
    try {
      const data = await getUnreadCount();
      this.unread = data?.count || 0;
    } catch (error) {
      return;
    }
    const badge = this.element?.querySelector('.header-bell-badge');
    if (badge) {
      badge.hidden = this.unread <= 0;
      badge.textContent = this.unread > 99 ? '99+' : String(this.unread);
    }
    if ('setAppBadge' in navigator) {
      try {
        if (this.unread > 0) await navigator.setAppBadge(this.unread);
        else await navigator.clearAppBadge();
      } catch (error) {
        /* best-effort */
      }
    }
    if (this.isOpen) this._renderList();
  }

  async load() {
    try {
      const data = await listNotifications({ limit: 30 });
      this.items = data?.items || [];
    } catch (error) {
      this.items = [];
    }
    this._renderList();
  }

  async toggle() {
    this.isOpen = !this.isOpen;
    const panel = this.element?.querySelector('.notification-panel');
    const btn = this.element?.querySelector('[data-action="toggle-notifications"]');
    panel?.classList.toggle('hidden', !this.isOpen);
    btn?.setAttribute('aria-expanded', String(this.isOpen));
    if (this.isOpen) {
      document.addEventListener('click', this._boundOutsideClick);
      await this.load();
    } else {
      document.removeEventListener('click', this._boundOutsideClick);
    }
  }

  close() {
    if (!this.isOpen) return;
    this.isOpen = false;
    this.element?.querySelector('.notification-panel')?.classList.add('hidden');
    this.element
      ?.querySelector('[data-action="toggle-notifications"]')
      ?.setAttribute('aria-expanded', 'false');
    document.removeEventListener('click', this._boundOutsideClick);
  }

  async markAllRead() {
    try {
      await markAllNotificationsRead();
    } catch (error) {
      return;
    }
    this.items = this.items.map((item) => ({ ...item, is_read: true }));
    this._renderList();
    await this.refresh();
  }

  async _openItem(item) {
    if (!item.is_read) {
      try {
        await markNotificationRead(item.id);
      } catch (error) {
        /* on navigue quand même */
      }
    }
    this.close();
    await this.refresh();
    const url = item.data?.url;
    if (typeof url === 'string' && url.startsWith('/')) this.onNavigate(url);
  }

  _renderList() {
    const list = this.element?.querySelector('[data-list]');
    if (!list || !this.isOpen) return;

    if (!this.items.length) {
      list.innerHTML = '<p class="empty-message">Aucune notification</p>';
      return;
    }

    list.innerHTML = this.items.map((item) => `
      <button type="button" class="notification-item${item.is_read ? '' : ' notification-item--unread'}" data-notification-id="${item.id}">
        <span class="notification-item-title">${escapeHtml(item.title)}</span>
        <span class="notification-item-message">${escapeHtml(item.message)}</span>
        <span class="notification-item-time">${escapeHtml(formatDateTime(item.created_at))}</span>
      </button>
    `).join('');

    list.querySelectorAll('.notification-item').forEach((el) => {
      el.addEventListener('click', () => {
        const item = this.items.find((entry) => entry.id === parseInt(el.dataset.notificationId, 10));
        if (item) this._openItem(item);
      });
    });
  }

  _handleOutsideClick(event) {
    if (!event.target.closest('.header-notifications')) this.close();
  }

  _startPolling() {
    this._stopPolling();
    this._pollTimer = window.setInterval(() => this.refresh(), POLL_INTERVAL_MS);
  }

  _stopPolling() {
    if (this._pollTimer) {
      window.clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
  }

  destroy() {
    this._stopPolling();
    document.removeEventListener('click', this._boundOutsideClick);
    this.element = null;
    this.isOpen = false;
  }
}
