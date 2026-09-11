export class GroupUsersModal {
  constructor(options = {}) {
    this.onClose = options.onClose || (() => {});

    this.element = null;
    this.overlay = null;
    this.currentGroup = null;
    this.users = [];
    this.loading = false;
  }

  open(options = {}) {
    this.currentGroup = options.group || null;
    this.users = options.users || [];
    this.loading = options.loading || false;

    this._createModal();
    this._renderContent();

    document.body.appendChild(this.overlay);

    requestAnimationFrame(() => {
      this.overlay.classList.add('open');
      this.element.classList.add('open');
    });

    this._handleKeydown = this._handleKeydown.bind(this);
    this._handleOverlayClick = this._handleOverlayClick.bind(this);

    document.addEventListener('keydown', this._handleKeydown);
    this.overlay.addEventListener('click', this._handleOverlayClick);
  }

  _createModal() {
    this.overlay = document.createElement('div');
    this.overlay.className = 'modal-overlay';

    this.element = document.createElement('div');
    this.element.className = 'modal';
    this.element.setAttribute('role', 'dialog');
    this.element.setAttribute('aria-modal', 'true');

    this.modalContent = document.createElement('div');
    this.modalContent.className = 'modal-content';

    this.element.appendChild(this.modalContent);
    this.overlay.appendChild(this.element);
  }

  _renderContent() {
    const groupName = this.currentGroup ? this._escapeHtml(this.currentGroup.name) : '';

    this.modalContent.innerHTML = `
      <div class="modal-header">
        <h2 id="modal-title">Utilisateurs du groupe : ${groupName}</h2>

        <button
          type="button"
          class="modal-close"
          aria-label="Fermer"
          data-action="close"
        >
          <svg width="24" height="24" viewBox="0 0 24 24"
               fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>

      <div class="modal-body" data-modal-body></div>

      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" data-action="close">
          Fermer
        </button>
      </div>
    `;

    this.modalContent
      .querySelector('[data-action="close"]')
      .addEventListener('click', () => this.close());

    const body = this.modalContent.querySelector('[data-modal-body]');

    if (this.loading) {
      body.innerHTML = `
        <div class="table-loading">
          <div class="spinner"></div>
          <p>Chargement des utilisateurs...</p>
        </div>
      `;
      return;
    }

    if (!this.users || this.users.length === 0) {
      body.innerHTML = `
        <div class="table-empty" style="padding: 2rem; text-align: center;">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom: 1rem; opacity: 0.5;">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
            <circle cx="9" cy="7" r="4"></circle>
            <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
            <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
          </svg>
          <p style="color: var(--text-secondary, #666);">Aucun utilisateur dans ce groupe.</p>
        </div>
      `;
      return;
    }

    const countText = `${this.users.length} utilisateur${this.users.length > 1 ? 's' : ''}`;

    let usersHtml = `
      <p style="margin-bottom: 1rem; color: var(--text-secondary, #666);">${countText}</p>
      <div class="group-users-list" style="max-height: 400px; overflow-y: auto;">
    `;

    for (const user of this.users) {
      const displayName = [user.first_name, user.last_name].filter(Boolean).join(' ');
      const statusClass = user.is_active ? 'active' : 'inactive';
      const statusText = user.is_active ? 'Actif' : 'Inactif';

      usersHtml += `
        <div class="group-user-item" style="display: flex; align-items: center; justify-content: space-between; padding: 0.75rem 1rem; border-bottom: 1px solid var(--border-color, #e5e7eb);">
          <div style="display: flex; align-items: center; gap: 0.75rem;">
            <div style="width: 36px; height: 36px; border-radius: 50%; background: var(--primary-color, #3b82f6); color: white; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 0.875rem;">
              ${this._getInitials(user.username)}
            </div>
            <div>
              <div style="font-weight: 500;">${this._escapeHtml(user.username)}</div>
              ${displayName ? `<div style="font-size: 0.875rem; color: var(--text-secondary, #666);">${this._escapeHtml(displayName)}</div>` : ''}
            </div>
          </div>
          <span class="status-badge ${statusClass}">${statusText}</span>
        </div>
      `;
    }

    usersHtml += '</div>';
    body.innerHTML = usersHtml;
  }

  _getInitials(username) {
    return username
      .split(/[^a-zA-Z0-9]/)
      .filter(Boolean)
      .map(word => word[0])
      .join('')
      .toUpperCase()
      .slice(0, 2);
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  close() {
    if (!this.overlay) return;

    document.removeEventListener('keydown', this._handleKeydown);
    this.overlay.removeEventListener('click', this._handleOverlayClick);

    this.overlay.classList.remove('open');
    this.element.classList.remove('open');

    setTimeout(() => {
      this.overlay?.remove();

      this.overlay = null;
      this.element = null;
      this.currentGroup = null;
      this.users = [];

      this.onClose();
    }, 200);
  }

  _handleKeydown(e) {
    if (e.key === 'Escape') {
      this.close();
    }
  }

  _handleOverlayClick(e) {
    if (e.target === this.overlay) {
      this.close();
    }
  }

  destroy() {
    this.close();
  }
}
