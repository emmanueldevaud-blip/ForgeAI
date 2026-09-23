const TYPE_LABELS = {
  success: 'Succès',
  info: 'Information',
  warning: 'Attention',
  error: 'Erreur',
};

const TYPE_ICONS = {
  success: '✓',
  info: 'i',
  warning: '!',
  error: '×',
};

export class NotificationCenter {
  constructor() {
    this.element = null;
  }

  show(message, type = 'info', duration = 4500) {
    this._ensureElement();
    const normalizedType = TYPE_LABELS[type] ? type : 'info';
    const notification = document.createElement('div');
    notification.className = `forgeai-notification forgeai-notification--${normalizedType}`;
    notification.setAttribute('role', normalizedType === 'error' ? 'alert' : 'status');
    notification.innerHTML = `
      <span class="forgeai-notification-icon" aria-hidden="true">${TYPE_ICONS[normalizedType]}</span>
      <div class="forgeai-notification-content"><strong>${TYPE_LABELS[normalizedType]}</strong><span data-message></span></div>
      <button type="button" class="forgeai-notification-close" aria-label="Fermer la notification">×</button>
    `;
    notification.querySelector('[data-message]').textContent = message;
    notification.querySelector('button').addEventListener('click', () => this._dismiss(notification));
    this.element.appendChild(notification);
    requestAnimationFrame(() => notification.classList.add('is-visible'));
    if (duration > 0) window.setTimeout(() => this._dismiss(notification), duration);
    return notification;
  }

  success(message, duration) { return this.show(message, 'success', duration); }
  info(message, duration) { return this.show(message, 'info', duration); }
  warning(message, duration) { return this.show(message, 'warning', duration); }
  error(message, duration) { return this.show(message, 'error', duration); }

  _ensureElement() {
    if (this.element?.isConnected) return;
    this.element = document.createElement('div');
    this.element.className = 'forgeai-notifications';
    this.element.setAttribute('aria-live', 'polite');
    document.body.appendChild(this.element);
  }

  _dismiss(notification) {
    if (!notification.isConnected) return;
    notification.classList.remove('is-visible');
    window.setTimeout(() => notification.remove(), 180);
  }
}

export const notifications = new NotificationCenter();
