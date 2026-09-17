import { Table } from '../components/Table.js';
import { authStore } from '../stores/auth.js';
import { listRequests, getRequest, createRequest, updateRequest, createWorkOrderFromRequest } from '../services/maintenanceApi.js';
import { listEquipments } from '../services/equipmentApi.js';

const STATUSES = [
  { value: 'open', label: 'Ouverte' },
  { value: 'in_progress', label: 'En cours' },
  { value: 'waiting_parts', label: 'Attente pièces' },
  { value: 'waiting_intervention', label: 'Attente intervention' },
  { value: 'completed', label: 'Clôturée' },
  { value: 'cancelled', label: 'Annulée' },
];

const PRIORITIES = [
  { value: 'low', label: 'Basse' },
  { value: 'medium', label: 'Moyenne' },
  { value: 'high', label: 'Haute' },
  { value: 'critical', label: 'Critique' },
];

function getStatusLabel(s) { return (STATUSES.find(x => x.value === s) || {}).label || s; }
function getPriorityLabel(p) { return (PRIORITIES.find(x => x.value === p) || {}).label || p; }

export class MaintenanceRequestsPage {
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
    this.filters = { status: '', priority: '' };
    this.table = null;
    this.equipments = [];
    this._authUnsubscribe = null;
  }

  async initialize() {
    this.table = new Table({
      columns: [
        { key: 'reference', label: 'Référence', sortable: true },
        { key: 'title', label: 'Titre', sortable: true },
        { key: 'status', label: 'Statut', sortable: true, render: (item) => `<span class="status-badge status-${item.status === 'completed' ? 'active' : 'inactive'}">${getStatusLabel(item.status)}</span>` },
        { key: 'priority', label: 'Priorité', sortable: true, render: (item) => `<span class="priority-badge priority-${item.priority}">${getPriorityLabel(item.priority)}</span>` },
        { key: 'equipment', label: 'Équipement', sortable: false, render: (item) => item.equipment ? item.equipment.name : '-' },
        { key: 'requested_by_user', label: 'Demandeur', sortable: false, render: (item) => item.requested_by_user ? item.requested_by_user.full_name || item.requested_by_user.username : '-' },
        { key: 'created_at', label: 'Date', sortable: true, render: (item) => item.created_at ? new Date(item.created_at).toLocaleDateString('fr-FR') : '-' },
      ],
      actions: [
        { key: 'view', label: 'Voir', icon: 'eye' },
        { key: 'edit', label: 'Modifier', icon: 'edit', disabled: (item) => !authStore.hasPermission('maintenance.update') },
        { key: 'create_wo', label: 'Créer OT', icon: 'tool', disabled: (item) => !authStore.hasPermission('maintenance.create') || item.status === 'completed' || item.status === 'cancelled' },
      ],
      onAction: (action, item) => this._handleAction(action, item),
      emptyMessage: 'Aucune demande trouvée',
    });
    this._authUnsubscribe = authStore.subscribe(() => { if (this.element) this.renderTableState(); });
    await this._loadEquipments();
  }

  async _loadEquipments() {
    try { const r = await listEquipments({ page_size: 1000, is_active: true }); this.equipments = r.items || []; } catch (e) { this.equipments = []; }
  }

  async loadData() {
    try {
      const params = { page: this.page, page_size: this.pageSize, sort_by: this.sortBy, sort_order: this.sortOrder };
      if (this.search) params.search = this.search;
      if (this.filters.status) params.status = this.filters.status;
      if (this.filters.priority) params.priority = this.filters.priority;
      const r = await listRequests(params);
      this.items = r.items || [];
      this.total = r.total || 0;
      this.totalPages = r.total_pages || 1;
      this.renderTableState();
    } catch (e) { console.error('Erreur chargement demandes:', e); }
  }

  renderTableState() {
    if (!this.element) return;
    const countEl = this.element.querySelector('[data-count]');
    if (countEl) countEl.textContent = `${this.total} demande${this.total > 1 ? 's' : ''}`;
    const tableContainer = this.element.querySelector('[data-table]');
    if (tableContainer) {
      this.table.setData({ items: this.items, total: this.total, page: this.page, pageSize: this.pageSize, totalPages: this.totalPages, sortBy: this.sortBy, sortOrder: this.sortOrder });
      tableContainer.innerHTML = '';
      tableContainer.appendChild(this.table.render());
    }
    const pageInfo = this.element.querySelector('[data-page-info]');
    if (pageInfo) pageInfo.textContent = `Page ${this.page} / ${this.totalPages}`;
    const prevBtn = this.element.querySelector('[data-page="prev"]');
    const nextBtn = this.element.querySelector('[data-page="next"]');
    if (prevBtn) prevBtn.disabled = this.page <= 1;
    if (nextBtn) nextBtn.disabled = this.page >= this.totalPages;
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content';
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>Demandes de maintenance</h1>
          <p class="page-subtitle">Gestion des demandes d'intervention</p>
        </div>
        <div class="page-header-right">
          ${authStore.hasPermission('maintenance.create') ? '<button class="btn btn-primary" data-action="create">+ Nouvelle demande</button>' : ''}
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
      </div>
      <div class="page-info"><span data-count>${this.total} demande${this.total > 1 ? 's' : ''}</span></div>
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
    else if (action === 'create_wo') await this._createWorkOrder(item);
  }

  async _showDetailModal(item) {
    try {
      const full = await getRequest(item.id);
      const modal = document.createElement('div');
      modal.className = 'modal-overlay';
      modal.innerHTML = `
        <div class="modal modal-lg">
          <div class="modal-content">
            <div class="modal-header">
              <h2>Demande ${full.reference || ''}</h2>
              <button class="modal-close" data-action="close">&times;</button>
            </div>
            <div class="modal-body">
              <div class="detail-grid">
                <div class="detail-item"><label>Titre</label><span>${full.title}</span></div>
                <div class="detail-item"><label>Statut</label><span class="status-badge status-${full.status === 'completed' ? 'active' : 'inactive'}">${getStatusLabel(full.status)}</span></div>
                <div class="detail-item"><label>Priorité</label><span class="priority-badge priority-${full.priority}">${getPriorityLabel(full.priority)}</span></div>
                <div class="detail-item"><label>Équipement</label><span>${full.equipment ? full.equipment.name : '-'}</span></div>
                <div class="detail-item"><label>Demandeur</label><span>${full.requested_by_user ? full.requested_by_user.full_name || full.requested_by_user.username : '-'}</span></div>
                <div class="detail-item"><label>Date</label><span>${full.created_at ? new Date(full.created_at).toLocaleDateString('fr-FR') : '-'}</span></div>
              </div>
              ${full.description ? `<div class="detail-section"><label>Description</label><p>${full.description}</p></div>` : ''}
              ${full.work_order ? `<div class="detail-section"><label>Ordre de travail</label><p><a href="#" data-link="wo">${full.work_order.reference}</a></p></div>` : ''}
            </div>
            <div class="modal-footer">
              <button class="btn btn-secondary" data-action="close">Fermer</button>
              ${full.status !== 'completed' && full.status !== 'cancelled' && authStore.hasPermission('maintenance.create') ? `<button class="btn btn-primary" data-action="create_wo">Créer OT</button>` : ''}
            </div>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
      modal.querySelector('[data-action="close"]')?.addEventListener('click', () => modal.remove());
      modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
      modal.querySelector('[data-action="create_wo"]')?.addEventListener('click', async () => { modal.remove(); await this._createWorkOrder(full); });
    } catch (e) { alert(e.message || 'Erreur lors du chargement'); }
  }

  async _showCreateModal() { await this._showFormModal(null); }
  async _showEditModal(item) {
    try { const full = await getRequest(item.id); await this._showFormModal(full); } catch (e) { alert(e.message || 'Erreur'); }
  }

  async _showFormModal(request) {
    const isEdit = !!request;
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal">
        <div class="modal-content">
          <div class="modal-header">
            <h2>${isEdit ? 'Modifier la demande' : 'Nouvelle demande'}</h2>
            <button class="modal-close" data-action="close">&times;</button>
          </div>
          <div class="modal-body">
            <form data-form>
              <div class="form-row">
                <label><span>Titre *</span><input name="title" value="${isEdit ? request.title : ''}" required maxlength="200"></label>
              </div>
              <div class="form-row">
                <label><span>Priorité *</span><select name="priority" required>
                  ${PRIORITIES.map(p => `<option value="${p.value}" ${isEdit && request.priority === p.value ? 'selected' : ''}>${p.label}</option>`).join('')}
                </select></label>
                <label><span>Équipement</span><select name="equipment_id">
                  <option value="">-- Sélectionner --</option>
                  ${this.equipments.map(e => `<option value="${e.id}" ${isEdit && request.equipment_id == e.id ? 'selected' : ''}>${e.reference} - ${e.name}</option>`).join('')}
                </select></label>
              </div>
              <div class="form-row">
                <label><span>Description</span><textarea name="description" rows="4">${isEdit ? (request.description || '') : ''}</textarea></label>
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
      const form = modal.querySelector('[data-form]');
      const fd = new FormData(form);
      const data = {};
      for (const [k, v] of fd.entries()) {
        if (v === '') continue;
        if (k === 'equipment_id') data[k] = parseInt(v, 10);
        else data[k] = v;
      }
      if (!data.title) { alert('Le titre est obligatoire'); return; }
      try {
        if (isEdit) await updateRequest(request.id, data);
        else await createRequest(data);
        modal.remove();
        this.loadData();
      } catch (e) { alert(e.message || 'Erreur lors de la sauvegarde'); }
    });
  }

  async _createWorkOrder(item) {
    if (!confirm(`Créer un ordre de travail pour la demande "${item.title}" ?`)) return;
    try {
      const wo = await createWorkOrderFromRequest(item.id, {});
      this.loadData();
      alert(`Ordre de travail ${wo.reference || ''} créé`);
    } catch (e) { alert(e.message || 'Erreur lors de la création'); }
  }

  destroy() {
    this._authUnsubscribe?.();
    if (this.element) this.element.remove();
    this.element = null;
  }
}

export function createMaintenanceRequestsPage(router) { return new MaintenanceRequestsPage(router); }
