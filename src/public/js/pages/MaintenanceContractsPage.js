import { Table } from '../components/Table.js';
import { authStore } from '../stores/auth.js';
import { listContracts, getContract, createContract, updateContract, listProviders } from '../services/maintenanceApi.js';

const CONTRACT_TYPES = [
  { value: 'full_service', label: 'Full Service' },
  { value: 'maintenance_only', label: 'Maintenance' },
  { value: 'call_on_demand', label: 'Intervention ponctuelle' },
  { value: 'warranty', label: 'Garantie' },
  { value: 'other', label: 'Autre' },
];

function getTypeLabel(t) { return (CONTRACT_TYPES.find(x => x.value === t) || {}).label || t; }
function formatDate(d) { return d ? new Date(d).toLocaleDateString('fr-FR') : '-'; }

export class MaintenanceContractsPage {
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
    this.filters = { provider_id: '', is_active: '' };
    this.table = null;
    this.providers = [];
    this._authUnsubscribe = null;
  }

  async initialize() {
    this.table = new Table({
      columns: [
        { key: 'reference', label: 'Référence', sortable: true },
        { key: 'name', label: 'Nom', sortable: true },
        { key: 'contract_type', label: 'Type', sortable: true, render: (item) => getTypeLabel(item.contract_type) },
        { key: 'provider', label: 'Prestataire', sortable: false, render: (item) => item.provider ? item.provider.name : '-' },
        { key: 'start_date', label: 'Début', sortable: true, render: (item) => formatDate(item.start_date) },
        { key: 'end_date', label: 'Fin', sortable: true, render: (item) => formatDate(item.end_date) },
        { key: 'annual_cost', label: 'Coût annuel', sortable: false, render: (item) => item.annual_cost ? item.annual_cost.toFixed(2) + ' €' : '-' },
        { key: 'is_active', label: 'Statut', sortable: true, render: (item) => `<span class="status-badge status-${item.is_active ? 'active' : 'inactive'}">${item.is_active ? 'Actif' : 'Inactif'}</span>` },
      ],
      actions: [
        { key: 'view', label: 'Voir', icon: 'eye' },
        { key: 'edit', label: 'Modifier', icon: 'edit', disabled: (item) => !authStore.hasPermission('maintenance.update') },
      ],
      onAction: (action, item) => this._handleAction(action, item),
      emptyMessage: 'Aucun contrat trouvé',
    });
    this._authUnsubscribe = authStore.subscribe(() => { if (this.element) this.renderTableState(); });
    await this._loadProviders();
  }

  async _loadProviders() { try { const r = await listProviders({ page_size: 1000, is_active: true }); this.providers = r.items || []; } catch (e) { this.providers = []; } }

  async loadData() {
    try {
      const params = { page: this.page, page_size: this.pageSize, sort_by: this.sortBy, sort_order: this.sortOrder };
      if (this.search) params.search = this.search;
      if (this.filters.provider_id) params.provider_id = this.filters.provider_id;
      if (this.filters.is_active !== '') params.is_active = this.filters.is_active;
      const r = await listContracts(params);
      this.items = r.items || [];
      this.total = r.total || 0;
      this.totalPages = r.total_pages || 1;
      this.renderTableState();
    } catch (e) { console.error('Erreur chargement contrats:', e); }
  }

  renderTableState() {
    if (!this.element) return;
    const countEl = this.element.querySelector('[data-count]');
    if (countEl) countEl.textContent = `${this.total} contrat${this.total > 1 ? 's' : ''}`;
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
    this.element.className = 'page-content';
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>Contrats</h1>
          <p class="page-subtitle">Gestion des contrats de maintenance</p>
        </div>
        <div class="page-header-right">
          ${authStore.hasPermission('maintenance.create') ? '<button class="btn btn-primary" data-action="create">+ Nouveau contrat</button>' : ''}
        </div>
      </div>
      <div class="page-filters">
        <input type="text" class="form-input" placeholder="Rechercher..." data-filter="search" value="${this.search}">
        <select class="form-select" data-filter="provider_id">
          <option value="">Tous les prestataires</option>
          ${this.providers.map(p => `<option value="${p.id}" ${this.filters.provider_id == p.id ? 'selected' : ''}>${p.name}</option>`).join('')}
        </select>
        <select class="form-select" data-filter="is_active">
          <option value="">Tous</option>
          <option value="true" ${this.filters.is_active === 'true' ? 'selected' : ''}>Actif</option>
          <option value="false" ${this.filters.is_active === 'false' ? 'selected' : ''}>Inactif</option>
        </select>
      </div>
      <div class="page-info"><span data-count>${this.total} contrat${this.total > 1 ? 's' : ''}</span></div>
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
    this.element.querySelector('[data-filter="provider_id"]')?.addEventListener('change', (e) => { this.filters.provider_id = e.target.value; this.page = 1; this.loadData(); });
    this.element.querySelector('[data-filter="is_active"]')?.addEventListener('change', (e) => { this.filters.is_active = e.target.value; this.page = 1; this.loadData(); });
    this.element.querySelector('[data-action="create"]')?.addEventListener('click', () => this._showFormModal(null));
    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => { if (this.page > 1) { this.page--; this.loadData(); } });
    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => { if (this.page < this.totalPages) { this.page++; this.loadData(); } });
  }

  async _handleAction(action, item) {
    if (action === 'view' || action === 'edit') {
      try { const full = await getContract(item.id); await this._showFormModal(full); } catch (e) { alert(e.message || 'Erreur'); }
    }
  }

  async _showFormModal(contract) {
    const isEdit = !!contract;
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal">
        <div class="modal-content">
          <div class="modal-header">
            <h2>${isEdit ? 'Modifier le contrat' : 'Nouveau contrat'}</h2>
            <button class="modal-close" data-action="close">&times;</button>
          </div>
          <div class="modal-body">
            <form data-form>
              <div class="form-row">
                <label><span>Nom *</span><input name="name" value="${isEdit ? contract.name : ''}" required maxlength="200"></label>
                <label><span>Référence</span><input name="reference" value="${isEdit ? (contract.reference || '') : ''}" maxlength="100"></label>
              </div>
              <div class="form-row">
                <label><span>Type *</span><select name="contract_type" required>
                  ${CONTRACT_TYPES.map(t => `<option value="${t.value}" ${isEdit && contract.contract_type === t.value ? 'selected' : ''}>${t.label}</option>`).join('')}
                </select></label>
                <label><span>Prestataire *</span><select name="provider_id" required>
                  <option value="">-- Sélectionner --</option>
                  ${this.providers.map(p => `<option value="${p.id}" ${isEdit && contract.provider_id == p.id ? 'selected' : ''}>${p.name}</option>`).join('')}
                </select></label>
              </div>
              <div class="form-row">
                <label><span>Date début *</span><input type="date" name="start_date" value="${isEdit && contract.start_date ? contract.start_date : ''}" required></label>
                <label><span>Date fin</span><input type="date" name="end_date" value="${isEdit && contract.end_date ? contract.end_date : ''}"></label>
              </div>
              <div class="form-row">
                <label><span>Coût annuel</span><input type="number" name="annual_cost" step="0.01" min="0" value="${isEdit && contract.annual_cost ? contract.annual_cost : ''}"></label>
                <label><span>Renouvellement auto</span><input type="checkbox" name="auto_renew" ${isEdit && contract.auto_renew ? 'checked' : ''}></label>
              </div>
              <div class="form-row">
                <label><span>Description</span><textarea name="description" rows="3">${isEdit ? (contract.description || '') : ''}</textarea></label>
              </div>
              <div class="form-row">
                <label><span>Actif</span><input type="checkbox" name="is_active" ${isEdit ? (contract.is_active ? 'checked' : '') : 'checked'}></label>
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
        if (k === 'is_active' || k === 'auto_renew') { data[k] = true; continue; }
        if (v === '') continue;
        if (k === 'provider_id') data[k] = parseInt(v, 10);
        else if (k === 'annual_cost') data[k] = parseFloat(v);
        else data[k] = v;
      }
      if (!data.name || !data.contract_type || !data.provider_id) { alert('Les champs Nom, Type et Prestataire sont obligatoires'); return; }
      try {
        if (isEdit) await updateContract(contract.id, data);
        else await createContract(data);
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

export function createMaintenanceContractsPage(router) { return new MaintenanceContractsPage(router); }
