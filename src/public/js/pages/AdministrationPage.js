import { authStore } from '../stores/auth.js';
import { createUsersPage } from './UsersPage.js';
import { createGroupsPage } from './GroupsPage.js';
import { createRolesPage } from './RolesPage.js';
import { createPermissionsPage } from './PermissionsPage.js';

export class AdministrationPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.currentTab = 'users';
    this.tabs = [
      { id: 'users', label: 'Utilisateurs', permission: 'user_view', component: null },
      { id: 'groups', label: 'Groupes', permission: 'group_view', component: null },
      { id: 'roles', label: 'Rôles', permission: 'role_view', component: null },
      { id: 'permissions', label: 'Permissions', permission: 'permission_view', component: null },
      { id: 'audit', label: 'Audit', permission: 'audit_log_view', component: null },
      { id: 'active-directory', label: 'Active Directory', permission: 'ad_config', component: null },
    ];
    this.usersPage = null;
    this.groupsPage = null;
    this.rolesPage = null;
    this.permissionsPage = null;
    this.adPage = null;
    this._authUnsubscribe = null;
  }

  _getTabFromPath() {
    const path = this.router.getPath?.() || '/administration';
    if (path === '/administration' || path === '/administration/') return 'users';
    if (path.startsWith('/administration/')) {
      const tab = path.split('/administration/')[1].split('/')[0];
      const validTabs = this.tabs.map(t => t.id);
      if (validTabs.includes(tab)) return tab;
    }
    return 'users';
  }

  async initialize() {
    this.usersPage = createUsersPage(this.router);
    await this.usersPage.initialize();
    this.tabs[0].component = this.usersPage;

    this.groupsPage = createGroupsPage(this.router);
    await this.groupsPage.initialize();
    this.tabs[1].component = this.groupsPage;

    this.rolesPage = createRolesPage(this.router);
    await this.rolesPage.initialize();
    this.tabs[2].component = this.rolesPage;

    this.permissionsPage = createPermissionsPage(this.router);
    await this.permissionsPage.initialize();
    this.tabs[3].component = this.permissionsPage;

    const { createActiveDirectoryPage } = await import('./ActiveDirectoryPage.js');
    this.adPage = createActiveDirectoryPage(this.router);
    await this.adPage.initialize();
    this.tabs[5].component = this.adPage;

    this.currentTab = this._getTabFromPath();

    this._authUnsubscribe = authStore.subscribe(() => {
      if (this.element) this._updateTabVisibility();
    });

    this.router.afterEach?.((route) => {
      const newTab = this._getTabFromPath();
      if (newTab !== this.currentTab) {
        this.currentTab = newTab;
        if (this.element) {
          this._switchTab(newTab);
        }
      }
    });
  }

  _updateTabVisibility() {
    this.tabs.forEach(tab => {
      const tabEl = this.element?.querySelector(`[data-tab="${tab.id}"]`);
      if (tabEl) {
        const hasPermission = authStore.hasPermission(tab.permission);
        tabEl.style.display = hasPermission ? '' : 'none';
      }
    });

    const activeTab = this.tabs.find(t => t.id === this.currentTab);
    if (activeTab && !authStore.hasPermission(activeTab.permission)) {
      const firstAllowed = this.tabs.find(t => authStore.hasPermission(t.permission));
      if (firstAllowed) this._switchTab(firstAllowed.id);
    }
  }

  _switchTab(tabId) {
    this.currentTab = tabId;

    this.element?.querySelectorAll('[data-tab]').forEach(el => {
      el.classList.toggle('admin-tab--active', el.dataset.tab === tabId);
      el.setAttribute('aria-selected', el.dataset.tab === tabId);
    });

    this.element?.querySelectorAll('[data-tab-panel]').forEach(panel => {
      panel.classList.toggle('admin-tab-panel--active', panel.dataset.tabPanel === tabId);
      panel.hidden = panel.dataset.tabPanel !== tabId;
    });

    const tab = this.tabs.find(t => t.id === tabId);
    if (tab?.component?.onTabActivate) {
      tab.component.onTabActivate();
    }
  }

  _handleTabClick(tabId) {
    const tab = this.tabs.find(t => t.id === tabId);
    if (!tab) return;
    if (!authStore.hasPermission(tab.permission)) return;
    this.router.navigate(`/administration/${tabId}`);
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'administration-page';

    const allowedTabs = this.tabs.filter(t => authStore.hasPermission(t.permission));
    const hasMultipleTabs = allowedTabs.length > 1;

    this.element.innerHTML = `
      <div class="administration-header">
        <div class="administration-title-area">
          <h1 class="administration-title">Administration</h1>
          <p class="administration-description">Gestion du système et configuration</p>
        </div>
      </div>

      ${hasMultipleTabs ? `
        <div class="admin-tabs" role="tablist" aria-label="Sections d'administration">
          ${this.tabs.map(tab => `
            <button
              class="admin-tab ${!authStore.hasPermission(tab.permission) ? 'hidden' : ''}"
              role="tab"
              data-tab="${tab.id}"
              aria-selected="${tab.id === this.currentTab}"
              ${!authStore.hasPermission(tab.permission) ? 'disabled' : ''}
              ${tab.id === this.currentTab ? 'aria-current="true"' : ''}
            >
              ${tab.label}
            </button>
          `).join('')}
        </div>
      ` : ''}

      <div class="admin-tab-panels">
        ${this.tabs.map(tab => `
          <div
            class="admin-tab-panel ${tab.id === this.currentTab ? 'admin-tab-panel--active' : ''}"
            data-tab-panel="${tab.id}"
            role="tabpanel"
            aria-labelledby="tab-${tab.id}"
            ${tab.id !== this.currentTab ? 'hidden' : ''}
          >
            ${tab.component ? '' : '<div class="admin-placeholder">Bientôt disponible</div>'}
          </div>
        `).join('')}
      </div>
    `;

    if (hasMultipleTabs) {
      this.element.querySelectorAll('[data-tab]').forEach(btn => {
        btn.addEventListener('click', () => this._handleTabClick(btn.dataset.tab));
      });
    }

    const usersPanel = this.element.querySelector('[data-tab-panel="users"]');
    if (usersPanel && this.usersPage) {
      usersPanel.innerHTML = '';
      usersPanel.appendChild(this.usersPage.render());
    }

    const groupsPanel = this.element.querySelector('[data-tab-panel="groups"]');
    if (groupsPanel && this.groupsPage) {
      groupsPanel.innerHTML = '';
      groupsPanel.appendChild(this.groupsPage.render());
    }

    const rolesPanel = this.element.querySelector('[data-tab-panel="roles"]');
    if (rolesPanel && this.rolesPage) {
      rolesPanel.innerHTML = '';
      rolesPanel.appendChild(this.rolesPage.render());
    }

    const permissionsPanel = this.element.querySelector('[data-tab-panel="permissions"]');
    if (permissionsPanel && this.permissionsPage) {
      permissionsPanel.innerHTML = '';
      permissionsPanel.appendChild(this.permissionsPage.render());
    }

    const adPanel = this.element.querySelector('[data-tab-panel="active-directory"]');
    if (adPanel && this.adPage) {
      adPanel.innerHTML = '';
      adPanel.appendChild(this.adPage.render());
    }

    return this.element;
  }

  mount(container) {
    if (!this.element) this.render();
    container.innerHTML = '';
    container.appendChild(this.element);
    return this;
  }

  destroy() {
    this._authUnsubscribe?.();
    this.usersPage?.destroy?.();
    this.groupsPage?.destroy?.();
    this.rolesPage?.destroy?.();
    this.permissionsPage?.destroy?.();
    this.adPage?.destroy?.();
  }
}

export function createAdministrationPage(router) {
  return new AdministrationPage(router);
}