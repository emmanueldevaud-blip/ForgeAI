import { Table } from '../components/Table.js';
import { authStore } from '../stores/auth.js';
import { ConfirmDialog } from '../components/ConfirmDialog.js';
import {
  listEquipments,
  getEquipment,
  createEquipment,
  updateEquipment,
  deactivateEquipment,
  deleteEquipment,
} from '../services/equipmentApi.js';
import {
  listSites,
  listBuildings,
  listLevels,
  listRooms,
} from '../services/buildingsApi.js';
import { listEquipmentTypes } from '../services/equipmentApi.js';

const EQUIPMENT_STATUSES = [
  { value: 'en_service', label: 'En service' },
  { value: 'hors_service', label: 'Hors service' },
  { value: 'en_panne', label: 'En panne' },
  { value: 'en_maintenance', label: 'En maintenance' },
  { value: 'reforme', label: 'Réformé' },
];

function getStatusLabel(status) {
  const s = EQUIPMENT_STATUSES.find(s => s.value === status);
  return s ? s.label : status;
}

function getLocationString(equipment) {
  const parts = [];
  if (equipment.site) parts.push(equipment.site.name);
  if (equipment.building) parts.push(equipment.building.name);
  if (equipment.level) parts.push(equipment.level.name);
  if (equipment.room) parts.push(equipment.room.name);
  return parts.join(' > ') || '-';
}

export class EquipmentPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.equipments = [];
    this.total = 0;
    this.page = 1;
    this.pageSize = 20;
    this.totalPages = 1;
    this.sortBy = 'created_at';
    this.sortOrder = 'desc';
    this.search = '';
    this.filters = {
      equipment_type_id: '',
      status: '',
      is_active: '',
    };
    this.equipmentTypes = [];
    this.equipmentTable = null;
    this._authUnsubscribe = null;
  }

  async initialize() {
    this.equipmentTable = new Table({
      columns: [
        { key: 'reference', label: 'Référence', sortable: true },
        { key: 'name', label: 'Désignation', sortable: true },
        {
          key: 'equipment_type',
          label: 'Type',
          sortable: false,
          render: (item) => item.equipment_type ? item.equipment_type.name : '-',
        },
        { key: 'manufacturer', label: 'Fabricant', sortable: false },
        { key: 'model', label: 'Modèle', sortable: false },
        {
          key: 'status',
          label: 'Statut',
          sortable: true,
          render: (item) => `<span class="status-badge status-${item.status === 'en_service' ? 'active' : 'inactive'}">${getStatusLabel(item.status)}</span>`,
        },
        {
          key: 'location',
          label: 'Localisation',
          sortable: false,
          render: (item) => `<small>${getLocationString(item)}</small>`,
        },
      ],
      actions: [
        {
          key: 'edit',
          label: 'Modifier',
          icon: 'edit',
          disabled: (item) => !authStore.hasPermission('equipment.update'),
        },
        {
          key: 'deactivate',
          label: 'Désactiver',
          icon: 'power',
          disabled: (item) => !item.is_active || !authStore.hasPermission('equipment.update'),
        },
        {
          key: 'delete',
          label: 'Supprimer',
          icon: 'trash',
          disabled: (item) => !authStore.hasPermission('equipment.delete'),
        },
      ],
      onAction: (action, item) => this._handleAction(action, item),
      emptyMessage: 'Aucun équipement trouvé',
    });

    this._authUnsubscribe = authStore.subscribe(() => {
      if (this.element) this.renderTableState();
    });

    await this._loadEquipmentTypes();
  }

  async _loadEquipmentTypes() {
    try {
      const response = await listEquipmentTypes({ page_size: 1000, is_active: true });
      this.equipmentTypes = response.items || [];
    } catch (e) {
      console.error('Erreur chargement types:', e);
    }
  }

  async loadData() {
    try {
      const params = {
        page: this.page,
        page_size: this.pageSize,
        sort_by: this.sortBy,
        sort_order: this.sortOrder,
      };
      if (this.search) params.search = this.search;
      if (this.filters.equipment_type_id) params.equipment_type_id = this.filters.equipment_type_id;
      if (this.filters.status) params.status = this.filters.status;
      if (this.filters.is_active !== '') params.is_active = this.filters.is_active;

      const response = await listEquipments(params);
      this.equipments = response.items || [];
      this.total = response.total || 0;
      this.totalPages = response.total_pages || 1;
      this.renderTableState();
    } catch (error) {
      console.error('Erreur chargement équipements:', error);
    }
  }

  renderTableState() {
    if (!this.element) return;

    const countEl = this.element.querySelector('[data-equipment-count]');
    if (countEl) {
      countEl.textContent = `${this.total} équipement${this.total > 1 ? 's' : ''}`;
    }

    const tableContainer = this.element.querySelector('[data-equipment-table]');
    if (tableContainer) {
      this.equipmentTable.setData({
        items: this.equipments,
        total: this.total,
        page: this.page,
        pageSize: this.pageSize,
        totalPages: this.totalPages,
        sortBy: this.sortBy,
        sortOrder: this.sortOrder,
      });
      tableContainer.innerHTML = '';
      tableContainer.appendChild(this.equipmentTable.render());
    }

    const pageInfo = this.element.querySelector('[data-page-info]');
    if (pageInfo) {
      pageInfo.textContent = `Page ${this.page} / ${this.totalPages}`;
    }

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
          <h1>Équipements</h1>
          <p class="page-subtitle">Gestion du patrimoine des équipements</p>
        </div>
        <div class="page-header-right">
          ${authStore.hasPermission('equipment.create') ? '<button class="btn btn-primary" data-action="create">+ Nouvel équipement</button>' : ''}
        </div>
      </div>

      <div class="page-filters">
        <div class="filter-group">
          <input type="text" class="form-input" placeholder="Rechercher..." data-filter="search" value="${this.search}">
        </div>
        <div class="filter-group">
          <select class="form-select" data-filter="equipment_type_id">
            <option value="">Tous les types</option>
            ${this.equipmentTypes.map(t => `<option value="${t.id}" ${this.filters.equipment_type_id == t.id ? 'selected' : ''}>${t.name}</option>`).join('')}
          </select>
        </div>
        <div class="filter-group">
          <select class="form-select" data-filter="status">
            <option value="">Tous les statuts</option>
            ${EQUIPMENT_STATUSES.map(s => `<option value="${s.value}" ${this.filters.status === s.value ? 'selected' : ''}>${s.label}</option>`).join('')}
          </select>
        </div>
        <div class="filter-group">
          <select class="form-select" data-filter="is_active">
            <option value="">Tous</option>
            <option value="true" ${this.filters.is_active === 'true' ? 'selected' : ''}>Actif</option>
            <option value="false" ${this.filters.is_active === 'false' ? 'selected' : ''}>Inactif</option>
          </select>
        </div>
      </div>

      <div class="page-info">
        <span data-equipment-count>${this.total} équipement${this.total > 1 ? 's' : ''}</span>
      </div>

      <div data-equipment-table></div>

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
    let searchTimeout;
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
          this.search = e.target.value;
          this.page = 1;
          this.loadData();
        }, 300);
      });
    }

    this.element.querySelectorAll('.form-select[data-filter]').forEach(select => {
      select.addEventListener('change', (e) => {
        const filter = select.dataset.filter;
        if (filter === 'is_active') {
          this.filters[filter] = e.target.value;
        } else {
          this.filters[filter] = e.target.value;
        }
        this.page = 1;
        this.loadData();
      });
    });

    const createBtn = this.element.querySelector('[data-action="create"]');
    if (createBtn) {
      createBtn.addEventListener('click', () => this._showCreateModal());
    }

    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => {
      if (this.page > 1) {
        this.page--;
        this.loadData();
      }
    });

    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => {
      if (this.page < this.totalPages) {
        this.page++;
        this.loadData();
      }
    });
  }

  async _handleAction(action, item) {
    switch (action) {
      case 'edit':
        await this._showEditModal(item);
        break;
      case 'deactivate':
        await this._deactivate(item);
        break;
      case 'delete':
        await this._delete(item);
        break;
    }
  }

  async _showCreateModal() {
    await this._showEquipmentModal(null);
  }

  async _showEditModal(item) {
    await this._showEquipmentModal(item);
  }

  async _showEquipmentModal(equipment) {
    const isEdit = !!equipment;
    const title = isEdit ? `Modifier: ${equipment.reference}` : 'Nouvel équipement';

    const sites = await this._loadSites();
    let buildings = [];
    let levels = [];
    let rooms = [];

    if (isEdit && equipment.room) {
      const room = equipment.room;
      if (room.level) {
        levels = [room.level];
        if (room.level.building) {
          buildings = [room.level.building];
          if (room.level.building.site) {
            sites = [room.level.building.site, ...sites.filter(s => s.id !== room.level.building.site.id)];
          }
        }
      }
    }

    const statusOptions = EQUIPMENT_STATUSES.map(s =>
      `<option value="${s.value}" ${isEdit && equipment.status === s.value ? 'selected' : ''}>${s.label}</option>`
    ).join('');

    const typeOptions = this.equipmentTypes.map(t =>
      `<option value="${t.id}" ${isEdit && equipment.equipment_type_id === t.id ? 'selected' : ''}>${t.name}</option>`
    ).join('');

    const siteOptions = sites.map(s =>
      `<option value="${s.id}" ${isEdit && equipment.room?.level?.building?.site?.id === s.id ? 'selected' : ''}>${s.name}</option>`
    ).join('');

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal">
        <div class="modal-content">
          <div class="modal-header">
            <h2>${title}</h2>
            <button class="modal-close" data-action="close-modal">&times;</button>
          </div>
          <div class="modal-body">
            <form data-equipment-form>
            ${isEdit ? `
            <div class="form-row">
              <label><span>Référence</span><input name="reference" value="${equipment.reference}" readonly></label>
            </div>
            ` : ''}
            <div class="form-row">
              <label><span>Désignation *</span><input name="name" value="${isEdit ? equipment.name : ''}" required maxlength="200"></label>
            </div>
            <div class="form-row">
              <label><span>Type</span><select name="equipment_type_id"><option value="">-- Sélectionner --</option>${typeOptions}</select></label>
              <label><span>Statut *</span><select name="status" required>${statusOptions}</select></label>
            </div>
            <div class="form-row">
              <label><span>Fabricant</span><input name="manufacturer" value="${isEdit ? (equipment.manufacturer || '') : ''}" maxlength="200"></label>
              <label><span>Modèle</span><input name="model" value="${isEdit ? (equipment.model || '') : ''}" maxlength="200"></label>
            </div>
            <div class="form-row">
              <label><span>Numéro de série</span><input name="serial_number" value="${isEdit ? (equipment.serial_number || '') : ''}" maxlength="200"></label>
            </div>
            <div class="form-row">
              <label><span>Date d'achat</span><input type="date" name="purchase_date" value="${isEdit && equipment.purchase_date ? equipment.purchase_date : ''}"></label>
              <label><span>Prix d'achat</span><input type="number" name="purchase_price" step="0.01" min="0" value="${isEdit && equipment.purchase_price ? equipment.purchase_price : ''}"></label>
            </div>
            <div class="form-row">
              <label><span>Date d'installation</span><input type="date" name="installation_date" value="${isEdit && equipment.installation_date ? equipment.installation_date : ''}"></label>
              <label><span>Date de mise en service</span><input type="date" name="commissioning_date" value="${isEdit && equipment.commissioning_date ? equipment.commissioning_date : ''}"></label>
            </div>
            <div class="form-row">
              <label><span>Fin de garantie</span><input type="date" name="warranty_end_date" value="${isEdit && equipment.warranty_end_date ? equipment.warranty_end_date : ''}"></label>
            </div>

            <h3>Localisation</h3>
            <div class="form-row">
              <label><span>Site *</span><select name="site_id" required><option value="">-- Sélectionner --</option>${siteOptions}</select></label>
              <label><span>Bâtiment *</span><select name="building_id" required><option value="">-- Sélectionner --</option></select></label>
            </div>
            <div class="form-row">
              <label><span>Niveau *</span><select name="level_id" required><option value="">-- Sélectionner --</option></select></label>
              <label><span>Pièce *</span><select name="room_id" required><option value="">-- Sélectionner --</option></select></label>
            </div>

            <label><span>Notes</span><textarea name="notes" rows="3">${isEdit ? (equipment.notes || '') : ''}</textarea></label>
          </form>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" data-action="close-modal">Annuler</button>
          <button class="btn btn-primary" data-action="save-equipment">${isEdit ? 'Enregistrer' : 'Créer'}</button>
        </div>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    modal.querySelector('[data-action="close-modal"]').addEventListener('click', () => modal.remove());
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });

    const form = modal.querySelector('[data-equipment-form]');
    const siteSelect = form.querySelector('[name="site_id"]');
    const buildingSelect = form.querySelector('[name="building_id"]');
    const levelSelect = form.querySelector('[name="level_id"]');
    const roomSelect = form.querySelector('[name="room_id"]');

    siteSelect.addEventListener('change', async () => {
      buildingSelect.innerHTML = '<option value="">Chargement...</option>';
      levelSelect.innerHTML = '<option value="">-- Sélectionner --</option>';
      roomSelect.innerHTML = '<option value="">-- Sélectionner --</option>';
      if (siteSelect.value) {
        const resp = await listBuildings({ site_id: siteSelect.value, is_active: true, page_size: 1000 });
        buildings = resp.items || [];
        buildingSelect.innerHTML = '<option value="">-- Sélectionner --</option>' +
          buildings.map(b => `<option value="${b.id}" ${isEdit && equipment.room?.level?.building?.id === b.id ? 'selected' : ''}>${b.name}</option>`).join('');
        if (isEdit && equipment.room?.level?.building) {
          buildingSelect.value = equipment.room.level.building.id;
          buildingSelect.dispatchEvent(new Event('change'));
        }
      } else {
        buildingSelect.innerHTML = '<option value="">-- Sélectionner --</option>';
      }
    });

    buildingSelect.addEventListener('change', async () => {
      levelSelect.innerHTML = '<option value="">Chargement...</option>';
      roomSelect.innerHTML = '<option value="">-- Sélectionner --</option>';
      if (buildingSelect.value) {
        const resp = await listLevels({ building_id: buildingSelect.value, is_active: true, page_size: 1000 });
        levels = resp.items || [];
        levelSelect.innerHTML = '<option value="">-- Sélectionner --</option>' +
          levels.map(l => `<option value="${l.id}" ${isEdit && equipment.room?.level?.id === l.id ? 'selected' : ''}>${l.name}</option>`).join('');
        if (isEdit && equipment.room?.level) {
          levelSelect.value = equipment.room.level.id;
          levelSelect.dispatchEvent(new Event('change'));
        }
      } else {
        levelSelect.innerHTML = '<option value="">-- Sélectionner --</option>';
      }
    });

    levelSelect.addEventListener('change', async () => {
      roomSelect.innerHTML = '<option value="">Chargement...</option>';
      if (levelSelect.value) {
        const resp = await listRooms({ level_id: levelSelect.value, is_active: true, page_size: 1000 });
        rooms = resp.items || [];
        roomSelect.innerHTML = '<option value="">-- Sélectionner --</option>' +
          rooms.map(r => `<option value="${r.id}" ${isEdit && equipment.room_id === r.id ? 'selected' : ''}>${r.name}</option>`).join('');
        if (isEdit && equipment.room_id) {
          roomSelect.value = equipment.room_id;
        }
      } else {
        roomSelect.innerHTML = '<option value="">-- Sélectionner --</option>';
      }
    });

    if (isEdit && equipment.room?.level?.building?.site) {
      siteSelect.value = equipment.room.level.building.site.id;
      siteSelect.dispatchEvent(new Event('change'));
    }

    modal.querySelector('[data-action="save-equipment"]').addEventListener('click', async () => {
      const formData = new FormData(form);
      const data = {};
      for (const [key, value] of formData.entries()) {
        if (value === '' || value === null) continue;
        if (key === 'equipment_type_id' || key === 'room_id' || key === 'site_id' || key === 'building_id' || key === 'level_id') {
          data[key] = parseInt(value, 10);
        } else if (key === 'purchase_price') {
          data[key] = parseFloat(value);
        } else {
          data[key] = value;
        }
      }

      if (!data.reference || !data.name || !data.room_id) {
        alert('Les champs Référence, Désignation et Pièce sont obligatoires');
        return;
      }

      try {
        if (isEdit) {
          await updateEquipment(equipment.id, data);
        } else {
          await createEquipment(data);
        }
        modal.remove();
        this.loadData();
        this._showToast(isEdit ? 'Équipement modifié' : 'Équipement créé');
      } catch (error) {
        alert(error.message || 'Erreur lors de la sauvegarde');
      }
    });
  }

  async _loadSites() {
    try {
      const resp = await listSites({ is_active: true, page_size: 1000 });
      return resp.items || [];
    } catch (e) {
      return [];
    }
  }

  async _deactivate(item) {
    if (!confirm(`Désactiver l'équipement "${item.reference}" ?`)) return;
    try {
      await deactivateEquipment(item.id);
      this.loadData();
      this._showToast('Équipement désactivé');
    } catch (error) {
      alert(error.message || 'Erreur lors de la désactivation');
    }
  }

  async _delete(item) {
    if (!confirm(`Supprimer définitivement l'équipement "${item.reference}" ?`)) return;
    try {
      await deleteEquipment(item.id);
      this.loadData();
      this._showToast('Équipement supprimé');
    } catch (error) {
      alert(error.message || 'Erreur lors de la suppression');
    }
  }

  _showToast(message) {
    const toast = document.createElement('div');
    toast.className = 'toast toast-success';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }

  mount(container) {
    if (!this.element) this.render();
    container.innerHTML = '';
    container.appendChild(this.element);
    return this;
  }

  destroy() {
    this._authUnsubscribe?.();
    if (this.element) this.element.remove();
    this.element = null;
  }
}

export function createEquipmentPage(router) {
  return new EquipmentPage(router);
}
