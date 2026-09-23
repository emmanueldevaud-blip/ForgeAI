import { Table } from '../components/Table.js';
import { authStore } from '../stores/auth.js';
import { listProviders, getProvider, createProvider, updateProvider } from '../services/maintenanceApi.js';

export class MaintenanceProvidersPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.items = [];
    this.total = 0;
    this.page = 1;
    this.pageSize = 20;
    this.totalPages = 1;
    this.sortBy = 'name';
    this.sortOrder = 'asc';
    this.search = '';
    this.filters = { is_active: '' };
    this.table = null;
    this._authUnsubscribe = null;
  }

  async initialize() {
    this.table = new Table({
      columns: [
        { key: 'name', label: 'Nom', sortable: true },
        { key: 'code', label: 'Code', sortable: true },
        { key: 'company_name', label: 'Société', sortable: false },
        { key: 'email', label: 'Email', sortable: false },
        { key: 'phone', label: 'Téléphone', sortable: false },
        { key: 'specialties', label: 'Spécialités', sortable: false, render: (item) => item.specialties || '-' },
        { key: 'is_active', label: 'Statut', sortable: true, render: (item) => `<span class="status-badge status-${item.is_active ? 'active' : 'inactive'}">${item.is_active ? 'Actif' : 'Inactif'}</span>` },
      ],
      actions: [
        { key: 'edit', label: 'Modifier', icon: 'edit', disabled: (item) => !authStore.hasPermission('maintenance.update') },
      ],
      onAction: (action, item) => this._handleAction(action, item),
      emptyMessage: 'Aucun prestataire trouvé',
    });
    this._authUnsubscribe = authStore.subscribe(() => { if (this.element) this.renderTableState(); });
  }

  async loadData() {
    try {
      const params = { page: this.page, page_size: this.pageSize, sort_by: this.sortBy, sort_order: this.sortOrder };
      if (this.search) params.search = this.search;
      if (this.filters.is_active !== '') params.is_active = this.filters.is_active;
      const r = await listProviders(params);
      this.items = r.items || [];
      this.total = r.total || 0;
      this.totalPages = r.total_pages || 1;
      this.renderTableState();
    } catch (e) { console.error('Erreur chargement prestataires:', e); }
  }

  renderTableState() {
    if (!this.element) return;
    const countEl = this.element.querySelector('[data-count]');
    if (countEl) countEl.textContent = `${this.total} prestataire${this.total > 1 ? 's' : ''}`;
    const tableContainer = this.element.querySelector('[data-table]');
    if (tableContainer) {
      this.table.setData({ items: this.items, total: this.total, page: this.page, pageSize: this.pageSize, totalPages: this.totalPages, sortBy: this.sortBy, sortOrder: this.sortOrder });
      tableContainer.innerHTML = '';
      tableContainer.appendChild(this.table.render());
    }
    const pageInfo = this.element.querySelector('[data-page-info]');
    if (pageInfo) pageInfo.textContent = `Page ${this.page} / ${this.totalPages}`;
    this.element.querySelector('[data-page="prev"]')?.setAttribute('disabled', this.page <= 1);
    this.element.querySelector('[data-page="next"]')?.setAttribute('disabled', this.page >= this.totalPages);
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content maintenance-page';
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>Prestataires</h1>
          <p class="page-subtitle">Gestion des prestataires de maintenance</p>
        </div>
        <div class="page-header-right">
          ${authStore.hasPermission('maintenance.create') ? '<button class="btn btn-primary" data-action="create">+ Nouveau prestataire</button>' : ''}
        </div>
      </div>
      <div class="page-filters">
        <input type="text" class="form-input" placeholder="Rechercher..." data-filter="search" value="${this.search}">
        <select class="form-select" data-filter="is_active">
          <option value="">Tous</option>
          <option value="true" ${this.filters.is_active === 'true' ? 'selected' : ''}>Actif</option>
          <option value="false" ${this.filters.is_active === 'false' ? 'selected' : ''}>Inactif</option>
        </select>
      </div>
      <div class="page-info"><span data-count>${this.total} prestataire${this.total > 1 ? 's' : ''}</span></div>
      <div data-table></div>
      <div class="pagination">
        <button class="btn btn-secondary" data-page="prev" ${this.page <= 1 ? 'disabled' : ''}>Précédent</button>
        <span data-page-info>Page ${this.page} / ${this.totalPages}</span>
        <button class="btn btn-secondary" data-page="next" ${this.page >= this.totalPages ? 'disabled' : ''}>Suivant</button>
      </div>
    `;
    this._setupEventListeners();
    this.renderTableState();
    return this.element;
  }

  _setupEventListeners() {
    const searchInput = this.element.querySelector('[data-filter="search"]');
    let t;
    if (searchInput) searchInput.addEventListener('input', (e) => { clearTimeout(t); t = setTimeout(() => { this.search = e.target.value; this.page = 1; this.loadData(); }, 300); });
    this.element.querySelector('[data-filter="is_active"]')?.addEventListener('change', (e) => { this.filters.is_active = e.target.value; this.page = 1; this.loadData(); });
    this.element.querySelector('[data-action="create"]')?.addEventListener('click', () => this._showFormModal(null));
    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => { if (this.page > 1) { this.page--; this.loadData(); } });
    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => { if (this.page < this.totalPages) { this.page++; this.loadData(); } });
  }

  async _handleAction(action, item) {
    if (action === 'edit') {
      try { const full = await getProvider(item.id); await this._showFormModal(full); } catch (e) { alert(e.message || 'Erreur'); }
    }
  }

  async _showFormModal(provider) {
    const isEdit = !!provider;
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal">
        <div class="modal-content">
          <div class="modal-header">
            <h2>${isEdit ? 'Modifier le prestataire' : 'Nouveau prestataire'}</h2>
            <button class="modal-close" data-action="close" aria-label="Fermer">&times;</button>
          </div>
          <div class="modal-body">
            <form data-form>
              <div class="form-row">
                <label><span>Nom *</span><input name="name" value="${isEdit ? provider.name : ''}" required maxlength="200"></label>
                <label><span>Code</span><input name="code" value="${isEdit ? (provider.code || '') : ''}" maxlength="50"></label>
              </div>
              <div class="form-row">
                <label><span>Société</span><input name="company_name" value="${isEdit ? (provider.company_name || '') : ''}" maxlength="200"></label>
              </div>
              <div class="form-row">
                <label><span>Email</span><input type="email" name="email" value="${isEdit ? (provider.email || '') : ''}" maxlength="200"></label>
                <label><span>Téléphone</span><input name="phone" value="${isEdit ? (provider.phone || '') : ''}" maxlength="50"></label>
              </div>
              <div class="form-row">
                <label><span>Adresse</span><input name="address" value="${isEdit ? (provider.address || '') : ''}" maxlength="500"></label>
              </div>
              <div class="form-row">
                <label><span>Spécialités</span><input name="specialties" value="${isEdit ? (provider.specialties || '') : ''}" maxlength="500" placeholder="Ex: Électricité, Plomberie, Mécanique"></label>
              </div>
              <div class="form-row">
                <label><span>Actif</span><input type="checkbox" name="is_active" ${isEdit ? (provider.is_active ? 'checked' : '') : 'checked'}></label>
              </div>
            </form>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" data-action="close">Annuler</button>
            <button class="btn btn-primary" data-action="save">${isEdit ? 'Enregistrer' : 'Créer'}</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    modal.querySelector('[data-action="close"]')?.addEventListener('click', () => modal.remove());
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    modal.querySelector('[data-action="save"]')?.addEventListener('click', async () => {
      const fd = new FormData(modal.querySelector('[data-form]'));
      const data = {};
      for (const [k, v] of fd.entries()) {
        if (k === 'is_active') { data[k] = true; continue; }
        if (v !== '') data[k] = v;
      }
      if (!data.name) { alert('Le nom est obligatoire'); return; }
      try {
        if (isEdit) await updateProvider(provider.id, data);
        else await createProvider(data);
        modal.remove();
        this.loadData();
      } catch (e) { alert(e.message || 'Erreur lors de la sauvegarde'); }
    });
  }

  destroy() {
    this._authUnsubscribe?.();
    if (this.element) this.element.remove();
    this.element = null;
  }
}

export function createMaintenanceProvidersPage(router) { return new MaintenanceProvidersPage(router); }
