export class Header {
  constructor(options = {}) {
    this.onMenuClick = options.onMenuClick || (() => {});
    this.onSearch = options.onSearch || (() => {});
    this.onLogout = options.onLogout || (() => {});
    this.onProfileClick = options.onProfileClick || (() => {});
    this.user = null;
    this.pageTitle = '';
    this.breadcrumbs = [];
    this.searchQuery = '';
    this.showSearch = false;
    this.element = null;
    this.userMenuOpen = false;
    this._boundHandleOutsideClick = this._handleOutsideClick.bind(this);
  }

  setUser(user) {
    this.user = user;
    this._renderUserMenu();
  }

  setPageTitle(title, breadcrumbs = []) {
    this.pageTitle = title;
    this.breadcrumbs = breadcrumbs;
    this._renderTitle();
  }

  setSearchQuery(query) {
    this.searchQuery = query;
    if (this.element) {
      const input = this.element.querySelector('.header-search-input');
      if (input) input.value = query;
    }
  }

  _renderUserMenu() {
    if (!this.element) return;

    const userMenu = this.element.querySelector('.header-user-menu');
    if (!userMenu) return;

    if (!this.user) {
      userMenu.innerHTML = '';
      return;
    }

    const displayName = this.user.full_name || this.user.username;
    const roleLabel = this._getRoleLabel(this.user);
    const roleClass = this.user.role === 'admin' ? 'admin' : 'user';

    userMenu.innerHTML = `
      <button class="header-user-btn" aria-expanded="${this.userMenuOpen}" aria-haspopup="true" data-action="toggle-user-menu">
        <div class="header-user-avatar">${this._getInitials(displayName)}</div>
        <div class="header-user-info">
          <span class="header-user-name">${this._escapeHtml(displayName)}</span>
          <span class="header-user-role ${roleClass}">${roleLabel}</span>
        </div>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline></svg>
      </button>
      <div class="header-user-dropdown${this.userMenuOpen ? '' : ' hidden'}" role="menu">
        <div class="header-user-dropdown-header">
          <div class="header-user-avatar-lg">${this._getInitials(displayName)}</div>
          <div>
            <div class="header-user-dropdown-name">${this._escapeHtml(displayName)}</div>
            <div class="header-user-dropdown-email">${this._escapeHtml(this.user.email)}</div>
          </div>
        </div>
        <hr class="dropdown-divider">
        <button class="dropdown-item" data-action="profile" role="menuitem">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
          <span>Mon profil</span>
        </button>
        <button class="dropdown-item" data-action="settings" role="menuitem">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
          <span>Paramètres</span>
        </button>
        <hr class="dropdown-divider">
        <button class="dropdown-item dropdown-item--danger" data-action="logout" role="menuitem">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
          <span>Déconnexion</span>
        </button>
      </div>
    `;

    userMenu.querySelector('[data-action="toggle-user-menu"]')?.addEventListener('click', (e) => {
      e.stopPropagation();
      this._toggleUserMenu();
    });

    userMenu.querySelector('[data-action="logout"]')?.addEventListener('click', () => {
      this.onLogout();
      this._closeUserMenu();
    });

    userMenu.querySelector('[data-action="profile"]')?.addEventListener('click', () => {
      this.onProfileClick();
      this._closeUserMenu();
    });

    userMenu.querySelector('[data-action="settings"]')?.addEventListener('click', () => {
      this._closeUserMenu();
    });

    document.addEventListener('click', this._boundHandleOutsideClick);
  }

  _toggleUserMenu() {
    this.userMenuOpen = !this.userMenuOpen;
    this._renderUserMenu();
  }

  _closeUserMenu() {
    this.userMenuOpen = false;
    this._renderUserMenu();
  }

  _handleOutsideClick(e) {
    if (this.userMenuOpen && !e.target.closest('.header-user-menu')) {
      this._closeUserMenu();
    }
  }

  _renderTitle() {
    if (!this.element) return;

    const titleEl = this.element.querySelector('.header-page-title');
    const breadcrumbEl = this.element.querySelector('.header-breadcrumbs');

    if (titleEl) {
      titleEl.textContent = this.pageTitle;
    }

    if (breadcrumbEl && this.breadcrumbs.length > 0) {
      breadcrumbEl.innerHTML = this.breadcrumbs.map((crumb, i) => `
        ${i > 0 ? '<span class="breadcrumb-separator" aria-hidden="true">/</span>' : ''}
        ${i === this.breadcrumbs.length - 1
          ? `<span class="breadcrumb-current" aria-current="page">${this._escapeHtml(crumb.label)}</span>`
          : `<a href="${this._escapeHtml(crumb.href)}" class="breadcrumb-link" data-link>${this._escapeHtml(crumb.label)}</a>`
        }
      `).join('');
    }
  }

  _getRoleLabel(user) {
    if (user.role === 'admin') return 'Administrateur';
    return 'Utilisateur';
  }

  _getInitials(name) {
    return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  mount(container) {
    this.element = container;
    this.element.className = 'header';
    this.element.innerHTML = `
      <div class="header-left">
        <button class="header-menu-btn" aria-label="Ouvrir le menu" data-action="menu">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
        </button>
        <div class="header-title-area">
          <h1 class="header-page-title"></h1>
          <nav class="header-breadcrumbs" aria-label="Fil d'Ariane"></nav>
        </div>
      </div>
      <div class="header-center">
        <div class="header-search" role="search">
          <svg class="header-search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          <input type="search" class="header-search-input" placeholder="Recherche globale..." aria-label="Recherche globale" autocomplete="off">
          <button class="header-search-clear hidden" aria-label="Effacer la recherche">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        </div>
      </div>
      <div class="header-right">
        <div class="header-user-menu"></div>
      </div>
    `;

    this.element.querySelector('[data-action="menu"]')?.addEventListener('click', () => this.onMenuClick());

    const searchInput = this.element.querySelector('.header-search-input');
    const searchClear = this.element.querySelector('.header-search-clear');

    searchInput?.addEventListener('input', (e) => {
      this.searchQuery = e.target.value;
      searchClear?.classList.toggle('hidden', !this.searchQuery);
      this.onSearch(this.searchQuery);
    });

    searchClear?.addEventListener('click', () => {
      searchInput.value = '';
      this.searchQuery = '';
      searchClear.classList.add('hidden');
      searchInput.focus();
      this.onSearch('');
    });

    this._renderUserMenu();
    return this;
  }

  destroy() {
    document.removeEventListener('click', this._boundHandleOutsideClick);
    if (this.element) {
      this.element.innerHTML = '';
    }
  }
}