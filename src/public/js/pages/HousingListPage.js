import { Table } from '../components/Table.js';
import { authStore } from '../stores/auth.js';
import { listHousings, getHousing, createHousing, updateHousing } from '../services/housingApi.js';
import { listSites, listBuildings, listLevels, listRooms } from '../services/buildingsApi.js';

const HOUSING_TYPES = [
  { value: 'apartment', label: 'Appartement' },
  { value: 'studio', label: 'Studio' },
  { value: 'room', label: 'Chambre' },
  { value: 'house', label: 'Maison' },
  { value: 'other', label: 'Autre' },
];

function getTypeLabel(t) { return (HOUSING_TYPES.find(x => x.value === t) || {}).label || t || '-'; }
function getStatusColor(s) { return s === 'confirmed' || s === 'in_progress' ? '#f59e0b' : '#10b981'; }

export class HousingListPage {
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
    this.filters = { is_active: '', site_id: '' };
    this.table = null;
    this.sites = [];
  }

  async initialize() {
    this.table = new Table({
      columns: [
        { key: 'room', label: 'Pièce', sortable: false, render: (item) => item.room ? `<code>${item.room.reference}</code> ${item.room.name}` : '-' },
        { key: 'site', label: 'Site', sortable: false, render: (item) => item.site ? item.site.name : '-' },
        { key: 'level', label: 'Niveau', sortable: false, render: (item) => item.level ? item.level.name : '-' },
        { key: 'housing_type', label: 'Type', sortable: true, render: (item) => getTypeLabel(item.housing_type) },
        { key: 'capacity', label: 'Capacité', sortable: true },
        { key: 'current_occupancy', label: 'Occupation', sortable: false, render: (item) => item.current_occupancy ? `<span class="status-badge" style="background:${getStatusColor(item.current_occupancy)}">${item.current_occupancy}</span>` : '<span class="status-badge" style="background:#10b981">Libre</span>' },
        { key: 'cleaning_status', label: 'Ménage', sortable: false, render: (item) => item.cleaning_status || '-' },
        { key: 'is_active', label: 'Statut', sortable: true, render: (item) => `<span class="status-badge status-${item.is_active ? 'active' : 'inactive'}">${item.is_active ? 'Actif' : 'Inactif'}</span>` },
      ],
      actions: [
        { key: 'edit', label: 'Modifier', icon: 'edit', disabled: (item) => !authStore.hasPermission('housing.manage') },
      ],
      onAction: (action, item) => this._handleAction(action, item),
      emptyMessage: 'Aucun hébergement trouvé',
    });
    await this._loadSites();
  }

  async _loadSites() {
    try { const r = await listSites({ page_size: 1000, is_active: true }); this.sites = r.items || []; } catch (e) { this.sites = []; }
  }

  async loadData() {
    try {
      const params = { page: this.page, page_size: this.pageSize, sort_by: this.sortBy, sort_order: this.sortOrder };
      if (this.search) params.search = this.search;
      if (this.filters.is_active !== '') params.is_active = this.filters.is_active;
      if (this.filters.site_id) params.site_id = this.filters.site_id;
      const r = await listHousings(params);
      this.items = r.items || [];
      this.total = r.total || 0;
      this.totalPages = r.total_pages || 1;
      this.renderTableState();
    } catch (e) { console.error('Erreur chargement hébergements:', e); }
  }

  renderTableState() {
    if (!this.element) return;
    const countEl = this.element.querySelector('[data-count]');
    if (countEl) countEl.textContent = `${this.total} hébergement${this.total > 1 ? 's' : ''}`;
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
        <div class="page-header-left"><h1>Hébergements</h1><p class="page-subtitle">Gestion des hébergements</p></div>
        <div class="page-header-right">${authStore.hasPermission('housing.manage') ? '<button class="btn btn-primary" data-action="create">+ Nouveau</button>' : ''}</div>
      </div>
      <div class="page-filters">
        <input type="text" class="form-input" placeholder="Rechercher..." data-filter="search" value="${this.search}">
        <select class="form-select" data-filter="site_id"><option value="">Tous les sites</option>${this.sites.map(s => `<option value="${s.id}" ${this.filters.site_id == s.id ? 'selected' : ''}>${s.name}</option>`).join('')}</select>
        <select class="form-select" data-filter="is_active"><option value="">Tous</option><option value="true" ${this.filters.is_active === 'true' ? 'selected' : ''}>Actif</option><option value="false" ${this.filters.is_active === 'false' ? 'selected' : ''}>Inactif</option></select>
      </div>
      <div class="page-info"><span data-count>${this.total} hébergement${this.total > 1 ? 's' : ''}</span></div>
      <div data-table></div>
      <div class="pagination"><button class="btn btn-secondary" data-page="prev" ${this.page <= 1 ? 'disabled' : ''}>Précédent</button><span data-page-info>Page ${this.page} / ${this.totalPages}</span><button class="btn btn-secondary" data-page="next" ${this.page >= this.totalPages ? 'disabled' : ''}>Suivant</button></div>
    `;
    this._setupEvents();
    this.renderTableState();
    return this.element;
  }

  _setupEvents() {
    const si = this.element.querySelector('[data-filter="search"]');
    let t;
    if (si) si.addEventListener('input', (e) => { clearTimeout(t); t = setTimeout(() => { this.search = e.target.value; this.page = 1; this.loadData(); }, 300); });
    this.element.querySelector('[data-filter="site_id"]')?.addEventListener('change', (e) => { this.filters.site_id = e.target.value; this.page = 1; this.loadData(); });
    this.element.querySelector('[data-filter="is_active"]')?.addEventListener('change', (e) => { this.filters.is_active = e.target.value; this.page = 1; this.loadData(); });
    this.element.querySelector('[data-action="create"]')?.addEventListener('click', () => this._showFormModal(null));
    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => { if (this.page > 1) { this.page--; this.loadData(); } });
    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => { if (this.page < this.totalPages) { this.page++; this.loadData(); } });
  }

  async _handleAction(action, item) {
    if (action === 'edit') {
      try { const full = await getHousing(item.id); await this._showFormModal(full); } catch (e) { alert(e.message || 'Erreur'); }
    }
  }

  async _showFormModal(housing) {
    const isEdit = !!housing;
    let rooms = [];
    try { const r = await listRooms({ page_size: 1000, is_active: true }); rooms = r.items || []; } catch (e) {}

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal"><div class="modal-content">
        <div class="modal-header"><h2>${isEdit ? 'Modifier hébergement' : 'Nouvel hébergement'}</h2><button class="modal-close" data-action="close">&times;</button></div>
        <div class="modal-body"><form data-form>
          <div class="form-row"><label><span>Pièce *</span><select name="room_id" required><option value="">-- Sélectionner --</option>${rooms.map(r => `<option value="${r.id}" ${isEdit && housing.room_id == r.id ? 'selected' : ''}>${r.reference} - ${r.name}</option>`).join('')}</select></label></div>
          <div class="form-row"><label><span>Type</span><select name="housing_type">${HOUSING_TYPES.map(t => `<option value="${t.value}" ${isEdit && housing.housing_type === t.value ? 'selected' : ''}>${t.label}</option>`).join('')}</select></label>
          <label><span>Capacité *</span><input type="number" name="capacity" min="1" value="${isEdit ? housing.capacity : 1}" required></label></div>
          <div class="form-row"><label><span>Lits</span><input type="number" name="beds" min="0" value="${isEdit && housing.beds ? housing.beds : ''}"></label>
          <label><span>Salles de bain</span><input type="number" name="bathrooms" min="0" value="${isEdit && housing.bathrooms ? housing.bathrooms : ''}"></label></div>
          <div class="form-row"><label><span>Cuisine</span><input type="checkbox" name="has_kitchen" ${isEdit && housing.has_kitchen ? 'checked' : ''}></label>
          <label><span>Balcon</span><input type="checkbox" name="has_balcony" ${isEdit && housing.has_balcony ? 'checked' : ''}></label></div>
          <div class="form-row"><label><span>Notes</span><textarea name="notes" rows="3">${isEdit ? (housing.notes || '') : ''}</textarea></label></div>
          <div class="form-row"><label><span>Actif</span><input type="checkbox" name="is_active" ${isEdit ? (housing.is_active ? 'checked' : '') : 'checked'}></label></div>
        </form></div>
        <div class="modal-footer"><button class="btn btn-secondary" data-action="close">Annuler</button><button class="btn btn-primary" data-action="save">${isEdit ? 'Enregistrer' : 'Créer'}</button></div>
      </div></div>
    `;
    document.body.appendChild(modal);
    modal.querySelector('[data-action="close"]')?.addEventListener('click', () => modal.remove());
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    modal.querySelector('[data-action="save"]')?.addEventListener('click', async () => {
      const fd = new FormData(modal.querySelector('[data-form]'));
      const data = {};
      for (const [k, v] of fd.entries()) {
        if (k === 'is_active' || k === 'has_kitchen' || k === 'has_balcony') { data[k] = true; continue; }
        if (v === '') continue;
        if (k === 'room_id' || k === 'capacity' || k === 'beds' || k === 'bathrooms') data[k] = parseInt(v, 10);
        else data[k] = v;
      }
      if (!data.room_id) { alert('La pièce est obligatoire'); return; }
      try {
        if (isEdit) await updateHousing(housing.id, data);
        else await createHousing(data);
        modal.remove(); this.loadData();
      } catch (e) { alert(e.message || 'Erreur'); }
    });
  }

  destroy() { if (this.element) this.element.remove(); this.element = null; }
}

export function createHousingListPage(router) { return new HousingListPage(router); }
