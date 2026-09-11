import { modulesApi } from '../services/api.js';
import { NavItem } from './NavItem.js';

export class Sidebar {
  constructor(options = {}) {
    this.onNavigate = options.onNavigate || (() => {});
    this.onToggleCollapse = options.onToggleCollapse || (() => {});
    this.collapsed = options.collapsed || false;
    this.mobileOpen = false;
    this.navigation = [];
    this.currentRoute = '/';
    this.loading = true;
    this.error = null;
    this.element = null;
    this.mobileOverlay = null;
    this._loadPromise = null;
  }

  async loadNavigation() {
    if (this._loadPromise) {
      return this._loadPromise;
    }

    this.loading = true;
    this.error = null;
    this._renderLoading();

    this._loadPromise = (async () => {
      try {
        const response = await modulesApi.get('/navigation');
        this.navigation = response.navigation || [];
        this.error = null;
      } catch (err) {
        console.error('Erreur chargement navigation:', err);
        this.error = err.message || 'Impossible de charger la navigation';
        this.navigation = [];
      } finally {
        this.loading = false;
        this._loadPromise = null;
        this._render();
      }
    })();

    return this._loadPromise;
  }

  clearNavigation() {
    this.navigation = [];
    this.error = null;
    this.loading = false;
    this._loadPromise = null;
    this._render();
  }

  setCurrentRoute(route) {
    this.currentRoute = route;
    this._updateActiveStates();
  }

  setCollapsed(collapsed) {
    this.collapsed = collapsed;
    if (this.element) {
      this.element.classList.toggle('sidebar--collapsed', collapsed);
      this._updateNavItemsCollapsed();
    }
  }

  toggleCollapsed() {
    this.setCollapsed(!this.collapsed);
    this.onToggleCollapse(!this.collapsed);
  }

  openMobile() {
    this.mobileOpen = true;
    this._renderMobile();
  }

  closeMobile() {
    this.mobileOpen = false;
    this._removeMobile();
  }

  toggleMobile() {
    if (this.mobileOpen) {
      this.closeMobile();
    } else {
      this.openMobile();
    }
  }

  _renderLoading() {
    if (!this.element) return;
    this.element.innerHTML = `
      <div class="sidebar-loading">
        <div class="spinner"></div>
        <span>Chargement...</span>
      </div>
    `;
  }

  _render() {
    if (!this.element) return;

    if (this.loading) {
      this._renderLoading();
      return;
    }

    if (this.error) {
      this.element.innerHTML = `
        <div class="sidebar-error">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
          <p>${this._escapeHtml(this.error)}</p>
          <button class="btn btn-sm btn-primary" data-action="retry">Réessayer</button>
        </div>
      `;
      this.element.querySelector('[data-action="retry"]')?.addEventListener('click', () => this.loadNavigation());
      return;
    }

    this.element.innerHTML = `
      <div class="sidebar-header">
        <div class="sidebar-brand">
          <svg class="sidebar-logo" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"></path><path d="M2 17l10 5 10-5"></path><path d="M2 12l10 5 10-5"></path></svg>
          <span class="sidebar-title">ForgeAI</span>
        </div>
        <button class="sidebar-toggle" aria-label="${this.collapsed ? 'Agrandir le menu' : 'Réduire le menu'}" data-action="toggle-collapse">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="${this.collapsed ? '15 18 9 12 15 6' : '9 18 15 12 9 6'}"></polyline></svg>
        </button>
      </div>
      <nav class="sidebar-nav" role="navigation" aria-label="Navigation principale">
        <ul class="nav-list" id="nav-list"></ul>
      </nav>
      <div class="sidebar-footer">
        <div class="sidebar-version">v1.0.0</div>
      </div>
    `;

    const navList = this.element.querySelector('#nav-list');
    this.navigation.forEach(item => {
      const navItem = new NavItem(item, {
        isActive: item.route === this.currentRoute,
        isCollapsed: this.collapsed,
        onClick: (action) => this._handleNavAction(action),
        level: 0,
      });
      navList.appendChild(navItem.render());
    });

    this.element.querySelector('[data-action="toggle-collapse"]')?.addEventListener('click', () => this.toggleCollapsed());
  }

  _renderMobile() {
    if (this.mobileOverlay) return;

    this.mobileOverlay = document.createElement('div');
    this.mobileOverlay.className = 'mobile-sidebar-overlay';
    this.mobileOverlay.innerHTML = `
      <div class="mobile-sidebar-drawer">
        <div class="mobile-sidebar-header">
          <div class="mobile-sidebar-brand">
            <svg class="sidebar-logo" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"></path><path d="M2 17l10 5 10-5"></path><path d="M2 12l10 5 10-5"></path></svg>
            <span class="sidebar-title">ForgeAI</span>
          </div>
          <button class="mobile-sidebar-close" aria-label="Fermer le menu">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        </div>
        <nav class="mobile-sidebar-nav" role="navigation" aria-label="Navigation principale">
          <ul class="mobile-nav-list" id="mobile-nav-list"></ul>
        </nav>
        <div class="mobile-sidebar-footer">
          <div class="mobile-sidebar-version">v1.0.0</div>
        </div>
      </div>
    `;

    const navList = this.mobileOverlay.querySelector('#mobile-nav-list');
    this.navigation.forEach(item => {
      const navItem = new NavItem(item, {
        isActive: item.route === this.currentRoute,
        isCollapsed: false,
        onClick: (action) => {
          this._handleNavAction(action);
          if (action.type === 'navigate') this.closeMobile();
        },
        level: 0,
      });
      navList.appendChild(navItem.render());
    });

    this.mobileOverlay.addEventListener('click', (e) => {
      if (e.target === this.mobileOverlay) this.closeMobile();
    });
    this.mobileOverlay.querySelector('.mobile-sidebar-close')?.addEventListener('click', () => this.closeMobile());

    document.body.appendChild(this.mobileOverlay);
    requestAnimationFrame(() => this.mobileOverlay.classList.add('open'));
  }

  _removeMobile() {
    if (!this.mobileOverlay) return;
    this.mobileOverlay.classList.remove('open');
    setTimeout(() => {
      this.mobileOverlay?.remove();
      this.mobileOverlay = null;
    }, 300);
  }

  _handleNavAction(action) {
    if (action.type === 'navigate' && action.route) {
      this.onNavigate(action.route);
    }
  }

  _updateActiveStates() {
    if (!this.element) return;
    this.element.querySelectorAll('.nav-item').forEach(itemEl => {
      const code = itemEl.dataset.navCode;
      const isActive = code === this._getCodeFromRoute(this.currentRoute);
      itemEl.classList.toggle('nav-item--active', isActive);
    });
  }

  _updateNavItemsCollapsed() {
    if (!this.element) return;
    this.element.querySelectorAll('.nav-link').forEach(link => {
      link.classList.toggle('nav-link--collapsed', this.collapsed);
    });
  }

  _getCodeFromRoute(route) {
    const parts = route.split('/').filter(Boolean);
    return parts[0] || 'dashboard';
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  mount(container) {
    this.element = container;
    this.element.className = 'sidebar';
    this._render();
    this.loadNavigation();
    return this;
  }

  destroy() {
    this.closeMobile();
    if (this.element) {
      this.element.innerHTML = '';
    }
  }
}