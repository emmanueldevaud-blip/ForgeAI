export class MobileSidebar {
  constructor(options = {}) {
    this.onNavigate = options.onNavigate || (() => {});
    this.onClose = options.onClose || (() => {});
    this.navigation = [];
    this.currentRoute = '/';
    this.isOpen = false;
    this.overlay = null;
  }

  setNavigation(navigation) {
    this.navigation = navigation || [];
    if (this.overlay && this.isOpen) {
      this._renderNav();
    }
  }

  setCurrentRoute(route) {
    this.currentRoute = route;
    if (this.overlay && this.isOpen) {
      this._updateActiveStates();
    }
  }

  open() {
    if (this.isOpen) return;
    this.isOpen = true;
    this._createOverlay();
  }

  close() {
    if (!this.isOpen) return;
    this.isOpen = false;
    this._removeOverlay();
    this.onClose();
  }

  toggle() {
    if (this.isOpen) this.close(); else this.open();
  }

  _createOverlay() {
    if (this.overlay) return;

    this.overlay = document.createElement('div');
    this.overlay.className = 'mobile-sidebar-overlay';
    this.overlay.innerHTML = `
      <div class="mobile-sidebar-drawer">
        <div class="mobile-sidebar-header">
          <div class="mobile-sidebar-brand">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"></path><path d="M2 17l10 5 10-5"></path><path d="M2 12l10 5 10-5"></path></svg>
            <span>ForgeAI</span>
          </div>
          <button class="mobile-sidebar-close" aria-label="Fermer le menu">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        </div>
        <nav class="mobile-sidebar-nav" role="navigation" aria-label="Navigation mobile">
          <ul class="mobile-nav-list" id="mobile-nav-list"></ul>
        </nav>
        <div class="mobile-sidebar-footer">
          <div class="mobile-sidebar-version">v1.0.0</div>
        </div>
      </div>
    `;

    this._renderNav();

    this.overlay.addEventListener('click', (e) => {
      if (e.target === this.overlay) this.close();
    });
    this.overlay.querySelector('.mobile-sidebar-close')?.addEventListener('click', () => this.close());

    document.body.appendChild(this.overlay);
    requestAnimationFrame(() => this.overlay.classList.add('open'));
    document.body.style.overflow = 'hidden';
  }

  _removeOverlay() {
    if (!this.overlay) return;
    this.overlay.classList.remove('open');
    document.body.style.overflow = '';
    setTimeout(() => {
      this.overlay?.remove();
      this.overlay = null;
    }, 300);
  }

  _renderNav() {
    if (!this.overlay) return;
    const navList = this.overlay.querySelector('#mobile-nav-list');
    if (!navList) return;

    navList.innerHTML = '';
    this.navigation.forEach(item => {
      const li = this._createNavItem(item, 0);
      navList.appendChild(li);
    });
  }

  _createNavItem(item, level) {
    const { code, name, icon, route, children } = item;
    const hasChildren = children && children.length > 0;
    const isExpanded = item._mobileExpanded === true;
    const isActive = route === this.currentRoute || (hasChildren && this._isChildActive(children));

    const li = document.createElement('li');
    li.className = 'mobile-nav-item';
    li.dataset.navCode = code;
    if (isActive) li.classList.add('mobile-nav-item--active');
    if (hasChildren) li.classList.add('mobile-nav-item--has-children');
    if (level > 0) li.classList.add('mobile-nav-item--nested');

    const link = document.createElement('a');
    link.className = 'mobile-nav-link';
    link.href = route || '#';
    link.dataset.link = 'true';

    const iconEl = document.createElement('span');
    iconEl.className = 'mobile-nav-icon';
    iconEl.innerHTML = this._getIconSVG(icon);
    iconEl.setAttribute('aria-hidden', 'true');

    const labelEl = document.createElement('span');
    labelEl.className = 'mobile-nav-label';
    labelEl.textContent = name;

    link.appendChild(iconEl);
    link.appendChild(labelEl);

    if (hasChildren) {
      const chevron = document.createElement('span');
      chevron.className = `mobile-nav-chevron ${isExpanded ? 'expanded' : ''}`;
      chevron.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"></polyline></svg>';
      chevron.setAttribute('aria-hidden', 'true');
      link.appendChild(chevron);
    }

    link.addEventListener('click', (e) => {
      if (hasChildren) {
        e.preventDefault();
        item._mobileExpanded = !isExpanded;
        this._renderNav();
      } else if (route) {
        e.preventDefault();
        this.onNavigate(route);
        this.close();
      }
    });

    li.appendChild(link);

    if (hasChildren && isExpanded) {
      const sublist = document.createElement('ul');
      sublist.className = 'mobile-nav-sublist';
      children.forEach(child => {
        sublist.appendChild(this._createNavItem(child, level + 1));
      });
      li.appendChild(sublist);
    }

    return li;
  }

  _isChildActive(children) {
    return children.some(child => {
      if (child.route === this.currentRoute) return true;
      if (child.children) return this._isChildActive(child.children);
      return false;
    });
  }

  _updateActiveStates() {
    if (!this.overlay) return;
    this.overlay.querySelectorAll('.mobile-nav-item').forEach(itemEl => {
      const code = itemEl.dataset.navCode;
      const isActive = code === this._getCodeFromRoute(this.currentRoute);
      itemEl.classList.toggle('mobile-nav-item--active', isActive);
    });
  }

  _getCodeFromRoute(route) {
    const parts = route.split('/').filter(Boolean);
    return parts[0] || 'dashboard';
  }

  _getIconSVG(iconName) {
    const icons = {
      dashboard: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"></rect><rect x="14" y="3" width="7" height="7" rx="1"></rect><rect x="3" y="14" width="7" height="7" rx="1"></rect><rect x="14" y="14" width="7" height="7" rx="1"></rect></svg>',
      building: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"></rect><path d="M3 9h18"></path><path d="M3 15h18"></path><path d="M9 3v18"></path><path d="M15 3v18"></path></svg>',
      home: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>',
      wrench: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path></svg>',
      sparkles: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 6 15 11"></polyline><path d="M12 1v3"></path><path d="M12 20v3"></path><path d="M4.22 4.22l1.42 1.42"></path><path d="M18.36 18.36l1.42 1.42"></path><path d="M1 12h3"></path><path d="M20 12h3"></path><path d="M4.22 19.78l1.42-1.42"></path><path d="M18.36 5.64l1.42-1.42"></path></svg>',
      users: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>',
      'file-text': '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>',
      ruler: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="5" x2="19" y2="19"></line><line x1="5" y1="19" x2="19" y2="5"></line><line x1="12" y1="2" x2="12" y2="22"></line><line x1="2" y1="12" x2="22" y2="12"></line></svg>',
      calculator: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="20" rx="2"></rect><line x1="6" y1="8" x2="18" y2="8"></line><line x1="6" y1="12" x2="18" y2="12"></line><line x1="6" y1="16" x2="18" y2="16"></line><line x1="8" y1="6" x2="8" y2="18"></line><line x1="12" y1="6" x2="12" y2="18"></line><line x1="16" y1="6" x2="16" y2="18"></line></svg>',
      package: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="16.5" y1="9.4" x2="7.5" y2="4.21"></line><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>',
      'shopping-cart': '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="21" r="1"></circle><circle cx="20" cy="21" r="1"></circle><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path></svg>',
      truck: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="1" y="3" width="15" height="13"></rect><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"></polygon><circle cx="5.5" cy="18.5" r="2.5"></circle><circle cx="18.5" cy="18.5" r="2.5"></circle></svg>',
      folder: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>',
      'bar-chart': '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>',
      settings: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>',
      'check-square': '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"></polyline><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path></svg>',
    };
    return icons[iconName] || icons.dashboard;
  }
}