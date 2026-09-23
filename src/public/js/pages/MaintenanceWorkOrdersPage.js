import { Table } from '../components/Table.js';
import { authStore } from '../stores/auth.js';
import { listWorkOrders, getWorkOrder, createWorkOrder, updateWorkOrder, addIntervenant, addIntervention, addWorkOrderPart, addCost } from '../services/maintenanceApi.js';
import { listEquipments } from '../services/equipmentApi.js';
import { listProviders } from '../services/maintenanceApi.js';

const STATUSES = [
  { value: 'draft', label: 'Brouillon' },
  { value: 'open', label: 'Ouvert' },
  { value: 'in_progress', label: 'En cours' },
  { value: 'waiting_parts', label: 'Attente pièces' },
  { value: 'completed', label: 'Clôturé' },
  { value: 'cancelled', label: 'Annulé' },
];

const PRIORITIES = [
  { value: 'low', label: 'Basse' },
  { value: 'medium', label: 'Moyenne' },
  { value: 'high', label: 'Haute' },
  { value: 'critical', label: 'Critique' },
];

const MAINTENANCE_TYPES = [
  { value: 'corrective', label: 'Corrective' },
  { value: 'preventive', label: 'Préventive' },
  { value: 'predictive', label: 'Prédictive' },
  { value: 'improvement', label: 'Amélioration' },
];

function getStatusLabel(s) { return (STATUSES.find(x => x.value === s) || {}).label || s; }
function getPriorityLabel(p) { return (PRIORITIES.find(x => x.value === p) || {}).label || p; }
function getTypeLabel(t) { return (MAINTENANCE_TYPES.find(x => x.value === t) || {}).label || t; }

export class MaintenanceWorkOrdersPage {
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
    this.filters = { status: '', priority: '', maintenance_type: '' };
    this.table = null;
    this.equipments = [];
    this.providers = [];
    this._authUnsubscribe = null;
  }

  async initialize() {
    this.table = new Table({
      columns: [
        { key: 'reference', label: 'Référence', sortable: true },
        { key: 'title', label: 'Titre', sortable: true },
        { key: 'status', label: 'Statut', sortable: true, render: (item) => `<span class="status-badge status-${item.status === 'completed' ? 'active' : 'inactive'}">${getStatusLabel(item.status)}</span>` },
        { key: 'priority', label: 'Priorité', sortable: true, render: (item) => `<span class="priority-badge priority-${item.priority}">${getPriorityLabel(item.priority)}</span>` },
        { key: 'maintenance_type', label: 'Type', sortable: true, render: (item) => getTypeLabel(item.maintenance_type) },
        { key: 'equipment', label: 'Équipement', sortable: false, render: (item) => item.equipment ? item.equipment.name : '-' },
        { key: 'responsible', label: 'Responsable', sortable: false, render: (item) => item.responsible ? item.responsible.full_name || item.responsible.username : '-' },
        { key: 'planned_date', label: 'Prévu le', sortable: true, render: (item) => item.planned_date ? new Date(item.planned_date).toLocaleDateString('fr-FR') : '-' },
      ],
      actions: [
        { key: 'view', label: 'Voir', icon: 'eye' },
        { key: 'edit', label: 'Modifier', icon: 'edit', disabled: (item) => !authStore.hasPermission('maintenance.update') },
      ],
      onAction: (action, item) => this._handleAction(action, item),
      emptyMessage: 'Aucun ordre de travail trouvé',
    });
    this._authUnsubscribe = authStore.subscribe(() => { if (this.element) this.renderTableState(); });
    await Promise.all([this._loadEquipments(), this._loadProviders()]);
  }

  async _loadEquipments() { try { const r = await listEquipments({ page_size: 1000, is_active: true }); this.equipments = r.items || []; } catch (e) { this.equipments = []; } }
  async _loadProviders() { try { const r = await listProviders({ page_size: 1000, is_active: true }); this.providers = r.items || []; } catch (e) { this.providers = []; } }

  async loadData() {
    try {
      const params = { page: this.page, page_size: this.pageSize, sort_by: this.sortBy, sort_order: this.sortOrder };
      if (this.search) params.search = this.search;
      if (this.filters.status) params.status = this.filters.status;
      if (this.filters.priority) params.priority = this.filters.priority;
      if (this.filters.maintenance_type) params.maintenance_type = this.filters.maintenance_type;
      const r = await listWorkOrders(params);
      this.items = r.items || [];
      this.total = r.total || 0;
      this.totalPages = r.total_pages || 1;
      this.renderTableState();
    } catch (e) { console.error('Erreur chargement OT:', e); }
  }

  renderTableState() {
    if (!this.element) return;
    const countEl = this.element.querySelector('[data-count]');
    if (countEl) countEl.textContent = `${this.total} ordre${this.total > 1 ? 's' : ''} de travail`;
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
          <h1>Ordres de travail</h1>
          <p class="page-subtitle">Gestion des ordres de travail</p>
        </div>
        <div class="page-header-right">
          ${authStore.hasPermission('maintenance.create') ? '<button class="btn btn-primary" data-action="create">+ Nouvel OT</button>' : ''}
        </div>
      </div>
      <div class="page-filters">
        <input type="text" class="form-input" placeholder="Rechercher..." data-filter="search" value="${this.search}">
        <select class="form-select" data-filter="status">
          <option value="">Tous les statuts</option>
          ${STATUSES.map(s => `<option value="${s.value}" ${this.filters.status === s.value ? 'selected' : ''}>${s.label}</option>`).join('')}
        </select>
        <select class="form-select" data-filter="priority">
          <option value="">Toutes les priorités</option>
          ${PRIORITIES.map(p => `<option value="${p.value}" ${this.filters.priority === p.value ? 'selected' : ''}>${p.label}</option>`).join('')}
        </select>
        <select class="form-select" data-filter="maintenance_type">
          <option value="">Tous les types</option>
          ${MAINTENANCE_TYPES.map(t => `<option value="${t.value}" ${this.filters.maintenance_type === t.value ? 'selected' : ''}>${t.label}</option>`).join('')}
        </select>
      </div>
      <div class="page-info"><span data-count>${this.total} ordre${this.total > 1 ? 's' : ''} de travail</span></div>
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
    this.element.querySelector('[data-action="create"]')?.addEventListener('click', () => this._showCreateModal());
    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => { if (this.page > 1) { this.page--; this.loadData(); } });
    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => { if (this.page < this.totalPages) { this.page++; this.loadData(); } });
  }

  async _handleAction(action, item) {
    if (action === 'view') await this._showDetailModal(item);
    else if (action === 'edit') await this._showEditModal(item);
  }

  async _showDetailModal(item) {
    try {
      const full = await getWorkOrder(item.id);
      const modal = document.createElement('div');
      modal.className = 'modal-overlay';
      modal.innerHTML = `
        <div class="modal modal-lg">
          <div class="modal-content">
            <div class="modal-header">
              <h2>OT ${full.reference || ''}</h2>
              <button class="modal-close" data-action="close" aria-label="Fermer">&times;</button>
            </div>
            <div class="modal-body">
              <div class="detail-grid">
                <div class="detail-item"><label>Titre</label><span>${full.title}</span></div>
                <div class="detail-item"><label>Statut</label><span class="status-badge">${getStatusLabel(full.status)}</span></div>
                <div class="detail-item"><label>Priorité</label><span class="priority-badge priority-${full.priority}">${getPriorityLabel(full.priority)}</span></div>
                <div class="detail-item"><label>Type</label><span>${getTypeLabel(full.maintenance_type)}</span></div>
                <div class="detail-item"><label>Équipement</label><span>${full.equipment ? full.equipment.name : '-'}</span></div>
                <div class="detail-item"><label>Responsable</label><span>${full.responsible ? full.responsible.full_name || full.responsible.username : '-'}</span></div>
                <div class="detail-item"><label>Prévu le</label><span>${full.planned_date ? new Date(full.planned_date).toLocaleDateString('fr-FR') : '-'}</span></div>
                <div class="detail-item"><label>Clôturé le</label><span>${full.closed_at ? new Date(full.closed_at).toLocaleDateString('fr-FR') : '-'}</span></div>
              </div>
              ${full.description ? `<div class="detail-section"><label>Description</label><p>${full.description}</p></div>` : ''}
              ${full.intervenants?.length ? `
                <div class="detail-section"><label>Intervenants</label>
                  <table class="data-table compact"><thead><tr><th>Nom</th><th>Rôle</th><th>Heures</th></tr></thead><tbody>
                    ${full.intervenants.map(i => `<tr><td>${i.user ? i.user.full_name || i.user.username : '-'}</td><td>${i.role_on_intervention || '-'}</td><td>${i.hours_worked || '-'}</td></tr>`).join('')}
                  </tbody></table>
                </div>
              ` : ''}
              ${full.interventions?.length ? `
                <div class="detail-section"><label>Interventions</label>
                  <table class="data-table compact"><thead><tr><th>Date</th><th>Description</th><th>Durée (h)</th></tr></thead><tbody>
                    ${full.interventions.map(i => `<tr><td>${i.date ? new Date(i.date).toLocaleDateString('fr-FR') : '-'}</td><td>${i.description || '-'}</td><td>${i.duration_hours || '-'}</td></tr>`).join('')}
                  </tbody></table>
                </div>
              ` : ''}
              ${full.costs?.length ? `
                <div class="detail-section"><label>Coûts</label>
                  <table class="data-table compact"><thead><tr><th>Type</th><th>Description</th><th>Montant</th></tr></thead><tbody>
                    ${full.costs.map(c => `<tr><td>${c.cost_type || '-'}</td><td>${c.description || '-'}</td><td>${c.amount ? c.amount.toFixed(2) + ' €' : '-'}</td></tr>`).join('')}
                  </tbody></table>
                </div>
              ` : ''}
            </div>
            <div class="modal-footer">
              <button class="btn btn-secondary" data-action="close">Fermer</button>
              ${full.status !== 'completed' && full.status !== 'cancelled' && authStore.hasPermission('maintenance.update') ? `<button class="btn btn-primary" data-action="edit">Modifier</button>` : ''}
            </div>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
      modal.querySelector('[data-action="close"]')?.addEventListener('click', () => modal.remove());
      modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
      modal.querySelector('[data-action="edit"]')?.addEventListener('click', async () => { modal.remove(); await this._showEditModal(full); });
    } catch (e) { alert(e.message || 'Erreur lors du chargement'); }
  }

  async _showCreateModal() { await this._showFormModal(null); }
  async _showEditModal(item) {
    try { const full = await getWorkOrder(item.id); await this._showFormModal(full); } catch (e) { alert(e.message || 'Erreur'); }
  }

  async _showFormModal(wo) {
    const isEdit = !!wo;
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal">
        <div class="modal-content">
          <div class="modal-header">
            <h2>${isEdit ? 'Modifier OT' : 'Nouvel ordre de travail'}</h2>
              <button class="modal-close" data-action="close" aria-label="Fermer">&times;</button>
          </div>
          <div class="modal-body">
            <form data-form>
              <div class="form-row">
                <label><span>Titre *</span><input name="title" value="${isEdit ? wo.title : ''}" required maxlength="200"></label>
              </div>
              <div class="form-row">
                <label><span>Priorité *</span><select name="priority" required>
                  ${PRIORITIES.map(p => `<option value="${p.value}" ${isEdit && wo.priority === p.value ? 'selected' : ''}>${p.label}</option>`).join('')}
                </select></label>
                <label><span>Type maintenance *</span><select name="maintenance_type" required>
                  ${MAINTENANCE_TYPES.map(t => `<option value="${t.value}" ${isEdit && wo.maintenance_type === t.value ? 'selected' : ''}>${t.label}</option>`).join('')}
                </select></label>
              </div>
              <div class="form-row">
                <label><span>Statut *</span><select name="status" required>
                  ${STATUSES.map(s => `<option value="${s.value}" ${isEdit && wo.status === s.value ? 'selected' : ''}>${s.label}</option>`).join('')}
                </select></label>
                <label><span>Équipement</span><select name="equipment_id">
                  <option value="">-- Sélectionner --</option>
                  ${this.equipments.map(e => `<option value="${e.id}" ${isEdit && wo.equipment_id == e.id ? 'selected' : ''}>${e.reference} - ${e.name}</option>`).join('')}
                </select></label>
              </div>
              <div class="form-row">
                <label><span>Date prévue</span><input type="date" name="planned_date" value="${isEdit && wo.planned_date ? wo.planned_date : ''}"></label>
                <label><span>Date fin prévue</span><input type="date" name="planned_end_date" value="${isEdit && wo.planned_end_date ? wo.planned_end_date : ''}"></label>
              </div>
              <div class="form-row">
                <label><span>Description</span><textarea name="description" rows="4">${isEdit ? (wo.description || '') : ''}</textarea></label>
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
        if (v === '') continue;
        if (k === 'equipment_id') data[k] = parseInt(v, 10);
        else data[k] = v;
      }
      if (!data.title) { alert('Le titre est obligatoire'); return; }
      try {
        if (isEdit) await updateWorkOrder(wo.id, data);
        else await createWorkOrder(data);
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

export function createMaintenanceWorkOrdersPage(router) { return new MaintenanceWorkOrdersPage(router); }
