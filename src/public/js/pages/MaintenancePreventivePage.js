import { Table } from '../components/Table.js';
import { authStore } from '../stores/auth.js';
import { listPlans, getPlan, createPlan, updatePlan } from '../services/maintenanceApi.js';
import { listEquipments } from '../services/equipmentApi.js';

const FREQUENCIES = [
  { value: 'daily', label: 'Quotidien' },
  { value: 'weekly', label: 'Hebdomadaire' },
  { value: 'monthly', label: 'Mensuel' },
  { value: 'quarterly', label: 'Trimestriel' },
  { value: 'biannual', label: 'Semestriel' },
  { value: 'annual', label: 'Annuel' },
  { value: 'hours', label: 'Par heures' },
];

function getFrequencyLabel(f) { return (FREQUENCIES.find(x => x.value === f) || {}).label || f; }
function formatDate(d) { return d ? new Date(d).toLocaleDateString('fr-FR') : '-'; }

export class MaintenancePreventivePage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.items = [];
    this.total = 0;
    this.page = 1;
    this.pageSize = 20;
    this.totalPages = 1;
    this.sortBy = 'created_at';
    this.sortOrder = 'desc';
    this.search = '';
    this.filters = { frequency: '', is_active: '' };
    this.table = null;
    this.equipments = [];
    this._authUnsubscribe = null;
  }

  async initialize() {
    this.table = new Table({
      columns: [
        { key: 'name', label: 'Nom', sortable: true },
        { key: 'equipment', label: 'Équipement', sortable: false, render: (item) => item.equipment ? item.equipment.name : '-' },
        { key: 'frequency', label: 'Fréquence', sortable: true, render: (item) => getFrequencyLabel(item.frequency) },
        { key: 'interval_value', label: 'Intervalle', sortable: false, render: (item) => item.interval_value ? `${item.interval_value} ${item.frequency === 'hours' ? 'h' : ''}` : '-' },
        { key: 'next_due_date', label: 'Prochaine échéance', sortable: true, render: (item) => formatDate(item.next_due_date) },
        { key: 'is_active', label: 'Statut', sortable: true, render: (item) => `<span class="status-badge status-${item.is_active ? 'active' : 'inactive'}">${item.is_active ? 'Actif' : 'Inactif'}</span>` },
      ],
      actions: [
        { key: 'view', label: 'Voir', icon: 'eye' },
        { key: 'edit', label: 'Modifier', icon: 'edit', disabled: (item) => !authStore.hasPermission('maintenance.update') },
      ],
      onAction: (action, item) => this._handleAction(action, item),
      emptyMessage: 'Aucun plan de maintenance trouvé',
    });
    this._authUnsubscribe = authStore.subscribe(() => { if (this.element) this.renderTableState(); });
    await this._loadEquipments();
  }

  async _loadEquipments() { try { const r = await listEquipments({ page_size: 1000, is_active: true }); this.equipments = r.items || []; } catch (e) { this.equipments = []; } }

  async loadData() {
    try {
      const params = { page: this.page, page_size: this.pageSize, sort_by: this.sortBy, sort_order: this.sortOrder };
      if (this.search) params.search = this.search;
      if (this.filters.frequency) params.frequency = this.filters.frequency;
      if (this.filters.is_active !== '') params.is_active = this.filters.is_active;
      const r = await listPlans(params);
      this.items = r.items || [];
      this.total = r.total || 0;
      this.totalPages = r.total_pages || 1;
      this.renderTableState();
    } catch (e) { console.error('Erreur chargement plans:', e); }
  }

  renderTableState() {
    if (!this.element) return;
    const countEl = this.element.querySelector('[data-count]');
    if (countEl) countEl.textContent = `${this.total} plan${this.total > 1 ? 's' : ''}`;
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
          <h1>Maintenance préventive</h1>
          <p class="page-subtitle">Plans de maintenance préventive</p>
        </div>
        <div class="page-header-right">
          ${authStore.hasPermission('maintenance.create') ? '<button class="btn btn-primary" data-action="create">+ Nouveau plan</button>' : ''}
        </div>
      </div>
      <div class="page-filters">
        <input type="text" class="form-input" placeholder="Rechercher..." data-filter="search" value="${this.search}">
        <select class="form-select" data-filter="frequency">
          <option value="">Toutes les fréquences</option>
          ${FREQUENCIES.map(f => `<option value="${f.value}" ${this.filters.frequency === f.value ? 'selected' : ''}>${f.label}</option>`).join('')}
        </select>
        <select class="form-select" data-filter="is_active">
          <option value="">Tous</option>
          <option value="true" ${this.filters.is_active === 'true' ? 'selected' : ''}>Actif</option>
          <option value="false" ${this.filters.is_active === 'false' ? 'selected' : ''}>Inactif</option>
        </select>
      </div>
      <div class="page-info"><span data-count>${this.total} plan${this.total > 1 ? 's' : ''}</span></div>
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
    this.element.querySelectorAll('.form-select[data-filter]').forEach(s => s.addEventListener('change', (e) => { this.filters[s.dataset.filter] = e.target.value; this.page = 1; this.loadData(); }));
    this.element.querySelector('[data-action="create"]')?.addEventListener('click', () => this._showFormModal(null));
    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => { if (this.page > 1) { this.page--; this.loadData(); } });
    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => { if (this.page < this.totalPages) { this.page++; this.loadData(); } });
  }

  async _handleAction(action, item) {
    if (action === 'view' || action === 'edit') {
      try { const full = await getPlan(item.id); await this._showFormModal(full); } catch (e) { alert(e.message || 'Erreur'); }
    }
  }

  async _showFormModal(plan) {
    const isEdit = !!plan;
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal">
        <div class="modal-content">
          <div class="modal-header">
            <h2>${isEdit ? 'Modifier le plan' : 'Nouveau plan'}</h2>
            <button class="modal-close" data-action="close" aria-label="Fermer">&times;</button>
          </div>
          <div class="modal-body">
            <form data-form>
              <div class="form-row">
                <label><span>Nom *</span><input name="name" value="${isEdit ? plan.name : ''}" required maxlength="200"></label>
              </div>
              <div class="form-row">
                <label><span>Équipement *</span><select name="equipment_id" required>
                  <option value="">-- Sélectionner --</option>
                  ${this.equipments.map(e => `<option value="${e.id}" ${isEdit && plan.equipment_id == e.id ? 'selected' : ''}>${e.reference} - ${e.name}</option>`).join('')}
                </select></label>
              </div>
              <div class="form-row">
                <label><span>Fréquence *</span><select name="frequency" required>
                  ${FREQUENCIES.map(f => `<option value="${f.value}" ${isEdit && plan.frequency === f.value ? 'selected' : ''}>${f.label}</option>`).join('')}
                </select></label>
                <label><span>Intervalle</span><input type="number" name="interval_value" min="1" value="${isEdit && plan.interval_value ? plan.interval_value : ''}"></label>
              </div>
              <div class="form-row">
                <label><span>Date de début</span><input type="date" name="start_date" value="${isEdit && plan.start_date ? plan.start_date : ''}"></label>
                <label><span>Prochaine échéance</span><input type="date" name="next_due_date" value="${isEdit && plan.next_due_date ? plan.next_due_date : ''}"></label>
              </div>
              <div class="form-row">
                <label><span>Description</span><textarea name="description" rows="3">${isEdit ? (plan.description || '') : ''}</textarea></label>
              </div>
              <div class="form-row">
                <label><span>Actif</span><input type="checkbox" name="is_active" ${isEdit ? (plan.is_active ? 'checked' : '') : 'checked'}></label>
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
        if (v === '') continue;
        if (k === 'equipment_id' || k === 'interval_value') data[k] = parseInt(v, 10);
        else data[k] = v;
      }
      if (!data.name || !data.equipment_id || !data.frequency) { alert('Les champs Nom, Équipement et Fréquence sont obligatoires'); return; }
      try {
        if (isEdit) await updatePlan(plan.id, data);
        else await createPlan(data);
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

export function createMaintenancePreventivePage(router) { return new MaintenancePreventivePage(router); }
