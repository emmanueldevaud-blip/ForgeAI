import { authStore } from '../stores/auth.js';
import { modulesApi } from '../services/api.js';

const STATUS_META = {
  active: { label: 'Actif', className: 'status-badge active' },
  inactive: { label: 'Inactif', className: 'status-badge inactive' },
  installing: { label: 'Installation', className: 'status-badge badge-warning' },
  error: { label: 'Erreur', className: 'status-badge badge-danger' },
};

export class ModulesPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.loading = false;
    this.error = null;
    this.modules = [];
    this._authUnsubscribe = null;
  }

  async initialize() {
    this._authUnsubscribe = authStore.subscribe(() => {
      this.renderModules();
    });

    await this.loadModules();
  }

  async loadModules() {
    this.loading = true;
    this.error = null;
    this.renderModules();

    try {
      const response = await modulesApi.get('');
      this.modules = response.modules || [];
    } catch (error) {
      console.error('Erreur chargement modules:', error);
      this.error = error.message || 'Erreur lors du chargement des modules';
      this.modules = [];
    } finally {
      this.loading = false;
      this.renderModules();
    }
  }

  _canToggle(module) {
    if (module.status === 'installing' || module.status === 'error') return false;
    const permission = module.status === 'active' ? 'module_disable' : 'module_enable';
    return authStore.hasPermission(permission);
  }

  async handleToggle(module, checked) {
    const action = checked ? 'enable' : 'disable';
    const permission = checked ? 'module_enable' : 'module_disable';

    if (!authStore.hasPermission(permission)) {
      this.showToast('Permissions insuffisantes', 'error');
      this.renderModules();
      return;
    }

    const input = this.element?.querySelector(`[data-module-toggle="${module.code}"]`);
    if (input) input.disabled = true;

    try {
      const response = await modulesApi.post(`/${module.code}/${action}`);
      module.status = response.module?.status || (checked ? 'active' : 'inactive');
      this.showToast(response.message || `Module ${checked ? 'activé' : 'désactivé'}`, 'success');
      // Intendance pilote ses sous-modules (cascade) : recharger pour refléter leurs statuts.
      if (module.code === 'gestion_bureaux') {
        await this.loadModules();
      }
      window.dispatchEvent(new CustomEvent('modules:changed', { detail: { code: module.code, status: module.status } }));
    } catch (error) {
      console.error('Erreur bascule module:', error);
      this.showToast(error.message || 'Erreur lors de la modification du module', 'error');
    } finally {
      this.renderModules();
    }
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text ?? '';
    return div.innerHTML;
  }

  showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;
    toast.textContent = message;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'polite');

    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }

    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('toast--visible'));
    setTimeout(() => {
      toast.classList.remove('toast--visible');
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  renderModules() {
    const container = this.element?.querySelector('[data-modules-list]');
    if (!container) return;

    if (this.loading) {
      container.innerHTML = `
        <div class="table-loading">
          <div class="spinner"></div>
          <p>Chargement...</p>
        </div>
      `;
      return;
    }

    if (this.error) {
      container.innerHTML = `
        <div class="table-error">
          <h3>Erreur</h3>
          <p>${this._escapeHtml(this.error)}</p>
          <button class="btn btn-primary" data-action="retry">Réessayer</button>
        </div>
      `;
      container.querySelector('[data-action="retry"]')?.addEventListener('click', () => this.loadModules());
      return;
    }

    if (!this.modules.length) {
      container.innerHTML = `
        <div class="table-error">
          <p>Aucun module disponible.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = this.modules.map((module) => {
      const status = STATUS_META[module.status] || { label: module.status, className: 'status-badge' };
      const canToggle = this._canToggle(module);
      const isActive = module.status === 'active';

      return `
        <div class="module-item" data-module-code="${this._escapeHtml(module.code)}">
          <div class="module-item__info">
            <div class="module-item__title">
              <span class="module-item__name">${this._escapeHtml(module.name)}</span>
              <span class="${status.className}">${status.label}</span>
              ${module.is_core ? '<span class="status-badge badge-muted">Cœur</span>' : ''}
              <span class="module-item__version">v${this._escapeHtml(module.version)}</span>
            </div>
            ${module.description ? `<p class="module-item__description">${this._escapeHtml(module.description)}</p>` : ''}
          </div>
          <label class="toggle-switch module-item__toggle" title="${isActive ? 'Désactiver' : 'Activer'} le module">
            <input
              type="checkbox"
              data-module-toggle="${this._escapeHtml(module.code)}"
              ${isActive ? 'checked' : ''}
              ${canToggle ? '' : 'disabled'}
              aria-label="${isActive ? 'Désactiver' : 'Activer'} le module ${this._escapeHtml(module.name)}"
            >
            <span class="toggle-slider"></span>
          </label>
        </div>
      `;
    }).join('');

    container.querySelectorAll('[data-module-toggle]').forEach((input) => {
      input.addEventListener('change', (event) => {
        const code = event.target.dataset.moduleToggle;
        const module = this.modules.find((m) => m.code === code);
        if (module) this.handleToggle(module, event.target.checked);
      });
    });
  }

  onTabActivate() {
    this.loadModules();
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'admin-settings-page modules-page';
    this.element.innerHTML = `
      <div class="card">
        <div class="card-header">
          <div>
            <h2>Modules</h2>
            <p class="text-muted">Activez ou désactivez les modules de l'application.</p>
          </div>
        </div>
        <div class="card-body" data-modules-list></div>
      </div>
    `;

    this.renderModules();
    return this.element;
  }

  destroy() {
    this._authUnsubscribe?.();
  }
}

export function createModulesPage(router) {
  return new ModulesPage(router);
}
