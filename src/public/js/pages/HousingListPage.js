import { Table } from '../components/Table.js';
import { authStore } from '../stores/auth.js';
import { listHousings, getHousing, updateHousing } from '../services/housingApi.js';

function parseBedConfig(str) {
  if (!str) return [];
  try { return JSON.parse(str); } catch { return []; }
}

function parseRoomNames(str, count) {
  let names = [];
  try { names = JSON.parse(str || '[]'); } catch { names = []; }
  return Array.from({ length: count }, (_, i) => names[i] || `Chambre ${i + 1}`);
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
    this.table = null;
  }

  async initialize() {
    this.table = new Table({
      columns: [
        { key: 'room', label: 'Nom du logement', sortable: false, render: (item) => item.room?.name || '-' },
        { key: 'rooms', label: 'Nombre de chambres', sortable: false, render: (item) => renderBedSummary(item.nb_rooms || 1, item.bed_configuration) },
        { key: 'capacity', label: 'Capacité', sortable: true, render: (item) => `${item.capacity} pers.` },
      ],
      actions: [
        { key: 'edit', label: 'Configurer', icon: 'edit', disabled: (item) => !authStore.hasPermission('housing.manage') },
      ],
      onAction: (action, item) => this._handleAction(action, item),
      emptyMessage: 'Aucun hébergement trouvé',
    });
  }

  async loadData() {
    try {
      const params = { page: this.page, page_size: this.pageSize, sort_by: this.sortBy, sort_order: this.sortOrder };
      if (this.search) params.search = this.search;
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
    this.element.className = 'page-content housing-page';
    this.element.style.cssText = 'display:flex;flex-direction:column;min-height:calc(100vh - var(--header-height) - var(--spacing-6) * 2);';
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left"><h1>Configuration des logements</h1><p class="page-subtitle">Configuration des logements — chambres, lits et capacités</p></div>
      </div>
      <div class="page-filters">
        <input type="text" class="form-input" placeholder="Rechercher..." data-filter="search" value="${this.search}">
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
    const roomNames = parseRoomNames(housing.room_names, nbRooms);
    while (bedConfig.length < nbRooms) bedConfig.push('simple');

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal modal-lg"><div class="modal-content">
        <div class="modal-header">
          <h2>Configurer — ${housing.room?.reference || ''} ${housing.room?.name || ''}</h2>
          <button class="modal-close" data-action="close" aria-label="Fermer">&times;</button>
        </div>
        <div class="modal-body">
          <form data-form>
            <div class="form-section">
              <h3>Chambres et lits</h3>
              <div class="form-row">
                <label><span>Nombre de chambres</span><input type="number" name="nb_rooms" min="1" max="50" value="${nbRooms}" data-nb-rooms></label>
              </div>
              <div class="bed-rooms-list" data-bed-rooms>
                ${bedConfig.map((type, i) => `
                  <div class="form-row bed-room-row">
                    <label class="bed-room-label"><input type="text" name="room_name_${i}" value="${this._escapeAttr(roomNames[i])}" maxlength="100" placeholder="Nom de la chambre"></label>
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
            <input type="hidden" name="room_names" data-room-names value="${this._escapeAttr(housing.room_names || '[]')}">
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
    const syncRoomNames = () => {
      const names = Array.from(modal.querySelectorAll('input[name^="room_name_"]')).map(input => input.value.trim());
      const roomNamesInput = modal.querySelector('[data-room-names]');
      if (roomNamesInput) roomNamesInput.value = JSON.stringify(names);
    };

    const syncBedRows = () => {
      const n = parseInt(nbRoomsInput.value) || 0;
      const currentBeds = parseBedConfig(bedConfigInput.value);
      const currentNames = Array.from(modal.querySelectorAll('input[name^="room_name_"]')).map(input => input.value);
      while (currentBeds.length < n) currentBeds.push('simple');
      currentBeds.length = n;
      bedConfigInput.value = JSON.stringify(currentBeds);
      bedsListEl.innerHTML = currentBeds.map((type, i) => `
        <div class="form-row bed-room-row">
          <label class="bed-room-label"><input type="text" name="room_name_${i}" value="${this._escapeAttr(currentNames[i] || `Chambre ${i + 1}`)}" maxlength="100" placeholder="Nom de la chambre"></label>
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
      bedsListEl.querySelectorAll('input[name^="room_name_"]').forEach(input => input.addEventListener('input', syncRoomNames));
      syncRoomNames();
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
    bedsListEl.querySelectorAll('input[name^="room_name_"]').forEach(input => input.addEventListener('input', syncRoomNames));

    modal.querySelector('[data-action="close"]')?.addEventListener('click', () => modal.remove());
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    modal.querySelector('[data-action="save"]')?.addEventListener('click', async () => {
      const fd = new FormData(modal.querySelector('[data-form]'));
      const data = {};
      data.nb_rooms = parseInt(fd.get('nb_rooms')) || 1;
      data.bed_configuration = fd.get('bed_configuration') || '[]';
      data.room_names = fd.get('room_names') || '[]';
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
