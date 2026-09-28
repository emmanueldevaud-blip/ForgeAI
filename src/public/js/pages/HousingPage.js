import { authStore } from '../stores/auth.js';
import { createHousingPlanningPage } from './HousingPlanningPage.js?v=22';
import { createHousingCleaningPage } from './HousingCleaningPage.js?v=10';
import { createHousingOccupantsPage } from './HousingOccupantsPage.js?v=1';
import { createHousingEmailTemplatesPage } from './HousingEmailTemplatesPage.js?v=11';
import { createHousingListPage } from './HousingListPage.js';

export class HousingPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.currentTab = 'planning';
    this.tabs = [
      { id: 'planning', label: 'Planning', permission: 'housing.view', component: null, mounted: false },
      { id: 'cleaning', label: 'Ménage', permission: 'housing.view', component: null, mounted: false },
      { id: 'occupants', label: 'Occupants', permission: 'housing.view', component: null, mounted: false },
      { id: 'email-templates', label: 'Modèles d’e-mails', permission: 'housing.manage_email_templates', component: null, mounted: false },
      { id: 'housings', label: 'Paramètres', permission: 'housing.manage', component: null, mounted: false },
    ];
    this._authUnsubscribe = null;
  }

  _getTabFromPath() {
    const path = this.router.getPath?.() || '/housing';
    // Check hash first (client-side tabs)
    const hash = window.location.hash.slice(1);
    if (hash && this.tabs.some(t => t.id === hash)) return hash;
    // Fallback to path for backward compatibility
    if (path === '/housing' || path === '/housing/') return 'planning';
    if (path.startsWith('/housing/')) {
      const tab = path.split('/housing/')[1].split('/')[0];
      if (this.tabs.some(t => t.id === tab)) return tab;
    }
    return 'planning';
  }

  async initialize() {
    const planning = createHousingPlanningPage(this.router);
    await planning.initialize();
    this.tabs[0].component = planning;

    const cleaning = createHousingCleaningPage(this.router);
    await cleaning.initialize();
    this.tabs[1].component = cleaning;

    const occupants = createHousingOccupantsPage(this.router);
    await occupants.initialize();
    this.tabs[2].component = occupants;

    if (authStore.hasPermission('housing.manage_email_templates')) {
      const emailTemplates = createHousingEmailTemplatesPage();
      await emailTemplates.initialize();
      this.tabs[3].component = emailTemplates;
    }

    if (authStore.hasPermission('housing.manage')) {
      const list = createHousingListPage(this.router);
      await list.initialize();
      this.tabs[4].component = list;
    }

    this.currentTab = this._getTabFromPath();

    this._authUnsubscribe = authStore.subscribe(() => {
      if (this.element) this._updateTabVisibility();
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
    if (!tab?.component || !authStore.hasPermission(tab.permission)) return;

    const panel = this.element?.querySelector(`[data-tab-panel="${tabId}"]`);
    if (!panel) return;
    if (!tab.mounted) {
      panel.innerHTML = '';
      panel.appendChild(tab.component.render());
      tab.mounted = true;
    }
    tab.component.loadData?.();
  }

  _handleTabClick(tabId) {
    const tab = this.tabs.find(t => t.id === tabId);
    if (!tab) return;
    if (!authStore.hasPermission(tab.permission)) return;
    this._switchTab(tabId);
    // Update URL hash for bookmarking without triggering route change
    window.history.replaceState(null, '', `/housing#${tabId}`);
  }

  render() {
    this.currentTab = this._getTabFromPath();
    const activeTab = this.tabs.find(t => t.id === this.currentTab);
    if (!activeTab || !authStore.hasPermission(activeTab.permission)) {
      const firstAllowed = this.tabs.find(t => authStore.hasPermission(t.permission));
      if (firstAllowed) this.currentTab = firstAllowed.id;
    }
    this.tabs.forEach(tab => { tab.mounted = false; });

    this.element = document.createElement('div');
    this.element.className = 'page-content housing-page';

    const allowedTabs = this.tabs.filter(t => authStore.hasPermission(t.permission));

    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>Hébergements</h1>
          <p class="page-subtitle">Planning d’occupation, ménage, occupants et configuration</p>
        </div>
      </div>

      ${allowedTabs.length > 1 ? `
        <div class="admin-tabs" role="tablist" aria-label="Sections d’hébergement">
          ${this.tabs.map(tab => `
            <button
              class="admin-tab ${!authStore.hasPermission(tab.permission) ? 'hidden' : ''}"
              role="tab"
              id="tab-${tab.id}"
              data-tab="${tab.id}"
              aria-selected="${tab.id === this.currentTab}"
              ${!authStore.hasPermission(tab.permission) ? 'disabled' : ''}
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
          ></div>
        `).join('')}
      </div>
    `;

    this.element.querySelectorAll('[data-tab]').forEach(btn => {
      btn.addEventListener('click', () => this._handleTabClick(btn.dataset.tab));
    });

    this._switchTab(this.currentTab);

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
    this.tabs.forEach(tab => tab.component?.destroy?.());
    this.element = null;
  }
}

export function createHousingPage(router) {
  return new HousingPage(router);
}
