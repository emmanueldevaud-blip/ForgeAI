import { Sidebar } from './Sidebar.js';
import { Header } from './Header.js';
import { MainContent } from './MainContent.js';
import { MobileSidebar } from './MobileSidebar.js';
import { authStore } from '../stores/auth.js';
import { modulesApi } from '../services/api.js';

export class AppShell {
  constructor(router) {
    this.router = router;
    this.sidebar = null;
    this.header = null;
    this.mainContent = null;
    this.mobileSidebar = null;
    this.sidebarCollapsed = false;
    this.initialized = false;
    this._authUnsubscribe = null;
  }

  async initialize() {
    if (this.initialized) return;

    this._createStructure();
    this._mountComponents();
    this._setupEventListeners();
    await this._loadInitialData();
    this.initialized = true;
  }

  _createStructure() {
    const app = document.getElementById('app');
    if (!app) throw new Error('Element #app not found');

    app.innerHTML = `
      <div class="app-shell">
        <aside class="sidebar" id="sidebar" role="navigation" aria-label="Navigation principale"></aside>
        <header class="header" id="header" role="banner"></header>
        <main class="main-content" id="main-content" role="main"></main>
      </div>
    `;
  }

  _mountComponents() {
    const sidebarEl = document.getElementById('sidebar');
    const headerEl = document.getElementById('header');
    const mainContentEl = document.getElementById('main-content');

    this.sidebar = new Sidebar({
      onNavigate: (route) => this.router.navigate(route),
      onToggleCollapse: (collapsed) => { this.sidebarCollapsed = collapsed; },
    }).mount(sidebarEl);

    this.mobileSidebar = new MobileSidebar({
      onNavigate: (route) => this.router.navigate(route),
      onClose: () => {},
    });

    this.header = new Header({
      onMenuClick: () => {
        this.mobileSidebar?.open();
      },
      onSearch: (query) => this._handleSearch(query),
      onLogout: () => this._handleLogout(),
      onProfileClick: () => this._handleProfileClick(),
    }).mount(headerEl);

    this.mainContent = new MainContent().mount(mainContentEl);
  }

  _setupEventListeners() {
    this._authUnsubscribe = authStore.subscribe((state) => {
      this.header.setUser(state.currentUser);
      if (state.authenticated && !this.sidebar.navigation.length) {
        this.sidebar.loadNavigation().then(() => {
          this.mobileSidebar.setNavigation(this.sidebar.navigation);
        });
      } else if (!state.authenticated) {
        this.sidebar.clearNavigation();
        this.mobileSidebar.setNavigation([]);
      }
    });

    this.router.afterEach((route) => {
      this.sidebar.setCurrentRoute(route.path);
      this.mobileSidebar.setCurrentRoute(route.path);
      this._updatePageTitle(route);
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.mobileSidebar?.isOpen) {
        this.mobileSidebar.close();
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        this.header.element?.querySelector('.header-search-input')?.focus();
      }
    });

    window.addEventListener('resize', this._handleResize.bind(this));
    this._handleResize();
  }

  async _loadInitialData() {
    await authStore.loadCurrentUser();
    if (authStore.authenticated) {
      await this.sidebar.loadNavigation();
      this.mobileSidebar.setNavigation(this.sidebar.navigation);
    }
  }

  _updatePageTitle(route) {
    const moduleName = this._getModuleNameFromRoute(route.path);
    const breadcrumbs = this._buildBreadcrumbs(route.path);
    this.header.setPageTitle(moduleName, breadcrumbs);
  }

  _getModuleNameFromRoute(path) {
    const modules = {
      dashboard: 'Tableau de bord',
      buildings: 'Bâtiments',
      housing: 'Logements',
      maintenance: 'Maintenance',
      cleaning: 'Nettoyage',
      people: 'Personnes',
      studies: 'Études',
      surveys: 'Métrés',
      quoting: 'Chiffrage',
      inventory: 'Stocks',
      purchasing: 'Achats',
      suppliers: 'Fournisseurs',
      documents: 'Documents',
      reports: 'Rapports',
      administration: 'Administration',
      todos: 'Tâches',
    };
    const code = path.split('/').filter(Boolean)[0] || 'dashboard';
    return modules[code] || 'ForgeAI';
  }

  _buildBreadcrumbs(path) {
    const parts = path.split('/').filter(Boolean);
    if (parts.length <= 1) return [];

    const breadcrumbs = [{ label: 'Accueil', href: '/dashboard' }];
    let currentPath = '';
    parts.forEach((part, i) => {
      currentPath += '/' + part;
      if (i === parts.length - 1) return;
      const modules = {
        buildings: 'Bâtiments',
        housing: 'Logements',
        maintenance: 'Maintenance',
        cleaning: 'Nettoyage',
        people: 'Personnes',
        studies: 'Études',
        surveys: 'Métrés',
        quoting: 'Chiffrage',
        inventory: 'Stocks',
        purchasing: 'Achats',
        suppliers: 'Fournisseurs',
        documents: 'Documents',
        reports: 'Rapports',
        administration: 'Administration',
        todos: 'Tâches',
      };
      breadcrumbs.push({ label: modules[part] || part, href: currentPath });
    });
    return breadcrumbs;
  }

  _handleSearch(query) {
    console.log('Recherche:', query);
  }

  async _handleLogout() {
    await authStore.logout();
    this.router.navigate('/login', { replace: true });
  }

  _handleProfileClick() {
    console.log('Profil cliqué');
  }

  _handleResize() {
    const isMobile = window.innerWidth < 1024;
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
      sidebar.classList.toggle('sidebar--mobile-hidden', isMobile);
    }
  }

  showLoading() {
    this.mainContent.setLoading(true);
  }

  showError(error) {
    this.mainContent.setError(error);
  }

  showContent(content) {
    this.mainContent.setContent(content);
  }

  showEmptyState(message, action = null) {
    this.mainContent.setEmptyState(message, action);
  }

  getMainContentElement() {
    return this.mainContent.element;
  }

  destroy() {
    this._authUnsubscribe?.();
    this.sidebar?.destroy();
    this.header?.destroy();
    this.mainContent?.destroy();
    this.mobileSidebar?.close();
    window.removeEventListener('resize', this._handleResize.bind(this));
  }
}