import { Table } from '../components/Table.js';
import { authStore } from '../stores/auth.js';
import { listOccupancies, getOccupancy, createOccupancy, updateOccupancy, changeOccupancyStatus } from '../services/housingApi.js';
import { listHousings } from '../services/housingApi.js';
import { listOccupants } from '../services/housingApi.js';

const STATUSES = [
  { value: 'pre_reserved', label: 'Pré-réservé' },
  { value: 'confirmed', label: 'Confirmé' },
  { value: 'in_progress', label: 'En cours' },
  { value: 'completed', label: 'Terminé' },
  { value: 'cancelled', label: 'Annulé' },
];

function getStatusLabel(s) { return (STATUSES.find(x => x.value === s) || {}).label || s; }
function getStatusColor(s) { return { pre_reserved: '#6b7280', confirmed: '#f59e0b', in_progress: '#3b82f6', completed: '#10b981', cancelled: '#ef4444' }[s] || '#6b7280'; }
function formatDate(d) { return d ? new Date(d).toLocaleDateString('fr-FR') : '-'; }

export class HousingOccupanciesPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.items = [];
    this.total = 0;
    this.page = 1;
    this.pageSize = 20;
    this.totalPages = 1;
    this.sortBy = 'arrival_date';
    this.sortOrder = 'desc';
    this.filters = { status: '' };
    this.table = null;
    this.housings = [];
    this.occupants = [];
  }

  async initialize() {
    this.table = new Table({
      columns: [
        { key: 'housing', label: 'Hébergement', sortable: false, render: (item) => item.housing && item.housing.room ? item.housing.room.name : '-' },
        { key: 'occupant', label: 'Occupant', sortable: false, render: (item) => item.occupant ? `${item.occupant.last_name} ${item.occupant.first_name}` : '-' },
        { key: 'status', label: 'Statut', sortable: true, render: (item) => `<span class="status-badge" style="background:${getStatusColor(item.status)}">${getStatusLabel(item.status)}</span>` },
        { key: 'arrival_date', label: 'Arrivée', sortable: true, render: (item) => formatDate(item.arrival_date) },
        { key: 'departure_date', label: 'Départ', sortable: true, render: (item) => formatDate(item.departure_date) },
        { key: 'nb_persons', label: 'Pers.', sortable: true },
        { key: 'purpose', label: 'Motif', sortable: false },
      ],
      actions: [
        { key: 'view', label: 'Voir', icon: 'eye' },
        { key: 'edit', label: 'Modifier', icon: 'edit', disabled: (item) => !authStore.hasPermission('housing.manage_occupancies') },
      ],
      onAction: (action, item) => this._handleAction(action, item),
      emptyMessage: 'Aucune occupation trouvée',
    });
    await Promise.all([this._loadHousings(), this._loadOccupants()]);
  }

  async _loadHousings() { try { const r = await listHousings({ page_size: 1000, is_active: true }); this.housings = r.items || []; } catch (e) { this.housings = []; } }
  async _loadOccupants() { try { const r = await listOccupants({ page_size: 1000, is_active: true }); this.occupants = r.items || []; } catch (e) { this.occupants = []; } }

  async loadData() {
    try {
      const params = { page: this.page, page_size: this.pageSize, sort_by: this.sortBy, sort_order: this.sortOrder };
      if (this.filters.status) params.status = this.filters.status;
      const r = await listOccupancies(params);
      this.items = r.items || [];
      this.total = r.total || 0;
      this.totalPages = r.total_pages || 1;
      this.renderTableState();
    } catch (e) { console.error('Erreur chargement occupations:', e); }
  }

  renderTableState() {
    if (!this.element) return;
    const countEl = this.element.querySelector('[data-count]');
    if (countEl) countEl.textContent = `${this.total} occupation${this.total > 1 ? 's' : ''}`;
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
        <div class="page-header-left"><h1>Occupations / Réservations</h1><p class="page-subtitle">Gestion des occupations</p></div>
        <div class="page-header-right">${authStore.hasPermission('housing.manage_occupancies') ? '<button class="btn btn-primary" data-action="create">+ Nouvelle occupation</button>' : ''}</div>
      </div>
      <div class="page-filters">
        <select class="form-select" data-filter="status"><option value="">Tous les statuts</option>${STATUSES.map(s => `<option value="${s.value}" ${this.filters.status === s.value ? 'selected' : ''}>${s.label}</option>`).join('')}</select>
      </div>
      <div class="page-info"><span data-count>${this.total} occupation${this.total > 1 ? 's' : ''}</span></div>
      <div data-table></div>
      <div class="pagination"><button class="btn btn-secondary" data-page="prev" ${this.page <= 1 ? 'disabled' : ''}>Précédent</button><span data-page-info>Page ${this.page} / ${this.totalPages}</span><button class="btn btn-secondary" data-page="next" ${this.page >= this.totalPages ? 'disabled' : ''}>Suivant</button></div>
    `;
    this._setupEvents();
    this.renderTableState();
    return this.element;
  }

  _setupEvents() {
    this.element.querySelector('[data-filter="status"]')?.addEventListener('change', (e) => { this.filters.status = e.target.value; this.page = 1; this.loadData(); });
    this.element.querySelector('[data-action="create"]')?.addEventListener('click', () => this._showFormModal(null));
    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => { if (this.page > 1) { this.page--; this.loadData(); } });
    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => { if (this.page < this.totalPages) { this.page++; this.loadData(); } });
  }

  async _handleAction(action, item) {
    if (action === 'view' || action === 'edit') {
      try { const full = await getOccupancy(item.id); await this._showFormModal(full); } catch (e) { alert(e.message || 'Erreur'); }
    }
  }

  async _showFormModal(occupancy) {
    const isEdit = !!occupancy;
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal"><div class="modal-content">
        <div class="modal-header"><h2>${isEdit ? 'Modifier occupation' : 'Nouvelle occupation'}</h2><button class="modal-close" data-action="close">&times;</button></div>
        <div class="modal-body"><form data-form>
          <div class="form-row"><label><span>Hébergement *</span><select name="housing_id" required><option value="">-- Sélectionner --</option>${this.housings.map(h => `<option value="${h.id}" ${isEdit && occupancy.housing_id == h.id ? 'selected' : ''}>${h.room ? h.room.name : 'H' + h.id}</option>`).join('')}</select></label></div>
          <div class="form-row"><label><span>Occupant *</span><select name="occupant_id" required><option value="">-- Sélectionner --</option>${this.occupants.map(o => `<option value="${o.id}" ${isEdit && occupancy.occupant_id == o.id ? 'selected' : ''}>${o.last_name} ${o.first_name}</option>`).join('')}</select></label></div>
          <div class="form-row"><label><span>Arrivée *</span><input type="datetime-local" name="arrival_date" value="${isEdit && occupancy.arrival_date ? occupancy.arrival_date.slice(0, 16) : ''}" required></label>
          <label><span>Départ *</span><input type="datetime-local" name="departure_date" value="${isEdit && occupancy.departure_date ? occupancy.departure_date.slice(0, 16) : ''}" required></label></div>
          <div class="form-row"><label><span>Nombre de personnes</span><input type="number" name="nb_persons" min="1" value="${isEdit ? occupancy.nb_persons : 1}"></label>
          <label><span>Motif</span><input name="purpose" value="${isEdit ? (occupancy.purpose || '') : ''}" maxlength="200"></label></div>
          <div class="form-row"><label><span>Observations</span><textarea name="observations" rows="3">${isEdit ? (occupancy.observations || '') : ''}</textarea></label></div>
          ${isEdit ? `
          <div class="form-row"><label><span>Statut</span><select name="status">${STATUSES.map(s => `<option value="${s.value}" ${occupancy.status === s.value ? 'selected' : ''}>${s.label}</option>`).join('')}</select></label></div>
          ` : ''}
        </form></div>
        <div class="modal-footer">
          <button class="btn btn-secondary" data-action="close">Annuler</button>
          ${isEdit && authStore.hasPermission('housing.manage_occupancies') ? `
            <button class="btn btn-warning" data-action="status-in_progress">Arrivée</button>
            <button class="btn btn-success" data-action="status-completed">Départ</button>
          ` : ''}
          <button class="btn btn-primary" data-action="save">${isEdit ? 'Enregistrer' : 'Créer'}</button>
        </div>
      </div></div>
    `;
    document.body.appendChild(modal);
    modal.querySelector('[data-action="close"]')?.addEventListener('click', () => modal.remove());
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    modal.querySelector('[data-action="save"]')?.addEventListener('click', async () => {
      const fd = new FormData(modal.querySelector('[data-form]'));
      const data = {};
      for (const [k, v] of fd.entries()) {
        if (v === '') continue;
        if (k === 'housing_id' || k === 'occupant_id' || k === 'nb_persons') data[k] = parseInt(v, 10);
        else data[k] = v;
      }
      if (!data.housing_id || !data.occupant_id) { alert('Hébergement et occupant requis'); return; }
      try {
        if (isEdit) await updateOccupancy(occupancy.id, data);
        else await createOccupancy(data);
        modal.remove(); this.loadData();
      } catch (e) { alert(e.message || 'Erreur'); }
    });
    modal.querySelector('[data-action="status-in_progress"]')?.addEventListener('click', async () => {
      try { await changeOccupancyStatus(occupancy.id, 'in_progress'); modal.remove(); this.loadData(); } catch (e) { alert(e.message || 'Erreur'); }
    });
    modal.querySelector('[data-action="status-completed"]')?.addEventListener('click', async () => {
      try { await changeOccupancyStatus(occupancy.id, 'completed'); modal.remove(); this.loadData(); } catch (e) { alert(e.message || 'Erreur'); }
    });
  }

  destroy() { if (this.element) this.element.remove(); this.element = null; }
}

export function createHousingOccupanciesPage(router) { return new HousingOccupanciesPage(router); }
