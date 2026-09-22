import { Table } from '../components/Table.js';
import { authStore } from '../stores/auth.js';
import { listHousings, getHousing, updateHousing } from '../services/housingApi.js';
import { listSites } from '../services/buildingsApi.js';

function getStatusColor(s) { return s === 'confirmed' || s === 'in_progress' ? '#f59e0b' : '#10b981'; }

function parseBedConfig(str) {
  if (!str) return [];
  try { return JSON.parse(str); } catch { return []; }
}

function renderBedSummary(nbRooms, bedConfig) {
  const beds = parseBedConfig(bedConfig);
  if (beds.length === 0) return `<span class="status-badge inactive">${nbRooms} chambre${nbRooms > 1 ? 's' : ''}</span>`;
  const simples = beds.filter(b => b === 'simple').length;
  const doubles = beds.filter(b => b === 'double').length;
  let parts = [];
  if (simples) parts.push(`${simples} simple${simples > 1 ? 's' : ''}`);
  if (doubles) parts.push(`${doubles} double${doubles > 1 ? 's' : ''}`);
  return `<span class="status-badge active">${nbRooms} ch. — ${parts.join(', ')}</span>`;
}

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
        { key: 'room', label: 'Référence', sortable: false, render: (item) => item.room ? `<code>${item.room.reference}</code> ${item.room.name}` : '-' },
        { key: 'site', label: 'Site', sortable: false, render: (item) => item.site ? item.site.name : '-' },
        { key: 'building', label: 'Bâtiment', sortable: false, render: (item) => item.building ? item.building.name : '-' },
        { key: 'rooms', label: 'Chambres', sortable: false, render: (item) => renderBedSummary(item.nb_rooms || 1, item.bed_configuration) },
        { key: 'capacity', label: 'Capacité', sortable: true, render: (item) => `${item.capacity} pers.` },
        { key: 'current_occupancy', label: 'Occupation', sortable: false, render: (item) => item.current_occupancy ? `<span class="status-badge" style="background:${getStatusColor(item.current_occupancy)}">${item.current_occupancy}</span>` : '<span class="status-badge" style="background:#10b981">Libre</span>' },
        { key: 'is_active', label: 'Statut', sortable: true, render: (item) => `<span class="status-badge status-${item.is_active ? 'active' : 'inactive'}">${item.is_active ? 'Actif' : 'Inactif'}</span>` },
      ],
      actions: [
        { key: 'edit', label: 'Configurer', icon: 'edit', disabled: (item) => !authStore.hasPermission('housing.manage') },
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
    this.element.style.cssText = 'display:flex;flex-direction:column;min-height:calc(100vh - var(--header-height) - var(--spacing-6) * 2);';
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left"><h1>Hébergements</h1><p class="page-subtitle">Configuration des hébergements — chambres, lits et capacités</p></div>
      </div>
      <div class="page-filters">
        <input type="text" class="form-input" placeholder="Rechercher..." data-filter="search" value="${this.search}">
        <select class="form-select" data-filter="site_id"><option value="">Tous les sites</option>${this.sites.map(s => `<option value="${s.id}" ${this.filters.site_id == s.id ? 'selected' : ''}>${s.name}</option>`).join('')}</select>
        <select class="form-select" data-filter="is_active"><option value="">Tous</option><option value="true" ${this.filters.is_active === 'true' ? 'selected' : ''}>Actif</option><option value="false" ${this.filters.is_active === 'false' ? 'selected' : ''}>Inactif</option></select>
      </div>
      <div class="page-info"><span data-count>${this.total} hébergement${this.total > 1 ? 's' : ''}</span></div>
      <div data-table style="flex:1;"></div>
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
    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => { if (this.page > 1) { this.page--; this.loadData(); } });
    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => { if (this.page < this.totalPages) { this.page++; this.loadData(); } });
  }

  async _handleAction(action, item) {
    if (action === 'edit') {
      try { const full = await getHousing(item.id); await this._showEditModal(full); } catch (e) { alert(e.message || 'Erreur'); }
    }
  }

  async _showEditModal(housing) {
    const nbRooms = housing.nb_rooms || 1;
    const bedConfig = parseBedConfig(housing.bed_configuration);
    while (bedConfig.length < nbRooms) bedConfig.push('simple');

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal modal-lg"><div class="modal-content">
        <div class="modal-header">
          <h2>Configurer — ${housing.room?.reference || ''} ${housing.room?.name || ''}</h2>
          <button class="modal-close" data-action="close">&times;</button>
        </div>
        <div class="modal-body">
          <form data-form>
            <div class="form-section">
              <h3>Chambres et lits</h3>
              <div class="form-row">
                <label><span>Nombre de chambres</span><input type="number" name="nb_rooms" min="0" max="50" value="${nbRooms}" data-nb-rooms></label>
              </div>
              <div class="bed-rooms-list" data-bed-rooms>
                ${bedConfig.map((type, i) => `
                  <div class="form-row bed-room-row">
                    <label class="bed-room-label">Chambre ${i + 1}</label>
                    <select name="bed_${i}" data-bed-idx="${i}">
                      <option value="simple" ${type === 'simple' ? 'selected' : ''}>Lit simple</option>
                      <option value="double" ${type === 'double' ? 'selected' : ''}>Lit double</option>
                    </select>
                  </div>
                `).join('')}
              </div>
            </div>

            <div class="form-section">
              <h3>Capacité</h3>
              <div class="form-row">
                <label><span>Nombre total d'occupants</span><input type="number" name="capacity" min="1" value="${housing.capacity}" required data-capacity></label>
              </div>
            </div>

            <div class="form-section">
              <h3>Informations</h3>
              <div class="form-row">
                <label><span>Notes</span><textarea name="notes" rows="2">${housing.notes || ''}</textarea></label>
              </div>
              <div class="form-row">
                <label class="checkbox-label"><input type="checkbox" name="is_active" ${housing.is_active ? 'checked' : ''}> Actif</label>
              </div>
            </div>

            <input type="hidden" name="bed_configuration" data-bed-config value="${this._escapeAttr(housing.bed_configuration || '[]')}">
          </form>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" data-action="close">Annuler</button>
          <button class="btn btn-primary" data-action="save">Enregistrer</button>
        </div>
      </div></div>
    `;
    document.body.appendChild(modal);

    const bedsListEl = modal.querySelector('[data-bed-rooms]');
    const nbRoomsInput = modal.querySelector('[data-nb-rooms]');
    const bedConfigInput = modal.querySelector('[data-bed-config]');

    const syncBedRows = () => {
      const n = parseInt(nbRoomsInput.value) || 0;
      const currentBeds = parseBedConfig(bedConfigInput.value);
      while (currentBeds.length < n) currentBeds.push('simple');
      currentBeds.length = n;
      bedConfigInput.value = JSON.stringify(currentBeds);
      bedsListEl.innerHTML = currentBeds.map((type, i) => `
        <div class="form-row bed-room-row">
          <label class="bed-room-label">Chambre ${i + 1}</label>
          <select name="bed_${i}" data-bed-idx="${i}">
            <option value="simple" ${type === 'simple' ? 'selected' : ''}>Lit simple</option>
            <option value="double" ${type === 'double' ? 'selected' : ''}>Lit double</option>
          </select>
        </div>
      `).join('');
      bedsListEl.querySelectorAll('select[data-bed-idx]').forEach(sel => {
        sel.addEventListener('change', () => {
          const idx = parseInt(sel.dataset.bedIdx);
          const beds = parseBedConfig(bedConfigInput.value);
          beds[idx] = sel.value;
          bedConfigInput.value = JSON.stringify(beds);
        });
      });
    };

    nbRoomsInput.addEventListener('input', syncBedRows);
    bedsListEl.querySelectorAll('select[data-bed-idx]').forEach(sel => {
      sel.addEventListener('change', () => {
        const idx = parseInt(sel.dataset.bedIdx);
        const beds = parseBedConfig(bedConfigInput.value);
        beds[idx] = sel.value;
        bedConfigInput.value = JSON.stringify(beds);
      });
    });

    modal.querySelector('[data-action="close"]')?.addEventListener('click', () => modal.remove());
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    modal.querySelector('[data-action="save"]')?.addEventListener('click', async () => {
      const fd = new FormData(modal.querySelector('[data-form]'));
      const data = {};
      data.nb_rooms = parseInt(fd.get('nb_rooms')) || 1;
      data.bed_configuration = fd.get('bed_configuration') || '[]';
      data.capacity = parseInt(fd.get('capacity')) || 1;
      data.is_active = fd.has('is_active');
      data.notes = fd.get('notes') || null;
      try {
        await updateHousing(housing.id, data);
        modal.remove();
        this.loadData();
      } catch (e) { alert(e.message || 'Erreur'); }
    });
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text ?? '';
    return div.innerHTML;
  }

  _escapeAttr(text) {
    return (text ?? '').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  destroy() { if (this.element) this.element.remove(); this.element = null; }
}

export function createHousingListPage(router) { return new HousingListPage(router); }
