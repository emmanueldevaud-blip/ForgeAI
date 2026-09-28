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
  listRooms,
} from '../services/buildingsApi.js';
import {
  listEquipmentTypes,
  createEquipmentType,
  updateEquipmentType,
  deleteEquipmentType,
} from '../services/equipmentApi.js';

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
  if (equipment.room) parts.push(equipment.room.name);
  return parts.join(' > ') || '-';
}

export class EquipmentPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.currentView = 'equipments';
    this.equipments = [];
    this.equipmentTypes = [];
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
    this.equipmentTable = null;
    this.typeTable = null;
    this.confirmDialog = null;
    this._authUnsubscribe = null;
    this.pendingAction = null;
    this._searchTimeout = null;
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
          permission: 'equipment.update',
        },
        {
          key: 'deactivate',
          label: 'Désactiver',
          icon: 'power',
          disabled: (item) => !item.is_active,
          permission: 'equipment.update',
        },
        {
          key: 'delete',
          label: 'Supprimer',
          icon: 'trash',
          permission: 'equipment.delete',
        },
      ],
      onAction: (action, item) => this._handleAction(action, item),
      emptyMessage: 'Aucun équipement trouvé',
    });

    this.typeTable = new Table({
      columns: [
        { key: 'code', label: 'Code', sortable: true },
        { key: 'name', label: 'Nom', sortable: true },
        { key: 'sort_order', label: 'Ordre', sortable: true },
      ],
      actions: [
        {
          key: 'edit',
          label: 'Modifier',
          icon: 'edit',
          permission: 'equipment.manage_referentials',
        },
        {
          key: 'delete',
          label: 'Supprimer',
          icon: 'trash',
          permission: 'equipment.manage_referentials',
        },
      ],
      onAction: (action, item) => this._handleTypeAction(action, item),
      emptyMessage: 'Aucun type d\'équipement trouvé',
    });

    this.confirmDialog = new ConfirmDialog({
      onConfirm: () => this._executeConfirmedAction(),
      onCancel: () => { this.pendingAction = null; },
    });

    this._authUnsubscribe = authStore.subscribe(() => this._updateButtonVisibility());
  }

  _getColumns() {
    return this.currentView === 'params' ? this.typeTable.columns : this.equipmentTable.columns;
  }

  _getActions() {
    return this.currentView === 'params' ? this.typeTable.actions : this.equipmentTable.actions;
  }

  _handleAction(action, item) {
    switch (action) {
      case 'edit':
        this._showEquipmentModal(item);
        break;
      case 'deactivate':
        this._deactivate(item);
        break;
      case 'delete':
        this.pendingAction = { type: 'delete', item, view: 'equipments' };
        this.confirmDialog.open({
          title: 'Supprimer',
          message: `Voulez-vous vraiment supprimer l'équipement "${item.reference}" ?`,
          confirmText: 'Supprimer',
          variant: 'danger',
        });
        break;
    }
  }

  _handleTypeAction(action, item) {
    if (action === 'edit') {
      this._showTypeModal(item);
    } else if (action === 'delete') {
      this.pendingAction = { type: 'delete', item, view: 'params' };
      this.confirmDialog.open({
        title: 'Supprimer',
        message: `Voulez-vous vraiment supprimer "${item.name}" ?`,
        confirmText: 'Supprimer',
        variant: 'danger',
      });
    }
  }

  async loadData() {
    this.page = 1;
    await this._loadDataForView();
  }

  async _loadDataForView() {
    try {
      if (this.currentView === 'equipments') {
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
        this.equipmentTable.setData({
          items: this.equipments,
          total: this.total,
          page: this.page,
          pageSize: this.pageSize,
          totalPages: this.totalPages,
          sortBy: this.sortBy,
          sortOrder: this.sortOrder,
        });
      } else if (this.currentView === 'params') {
        const params = {
          page: this.page,
          page_size: this.pageSize,
          sort_by: this.sortBy,
          sort_order: this.sortOrder,
        };
        if (this.search) params.search = this.search;

        const response = await listEquipmentTypes(params);
        this.equipmentTypes = response.items || [];
        this.total = response.total || 0;
        this.totalPages = response.total_pages || 1;
        this.typeTable.setData({
          items: this.equipmentTypes,
          total: this.total,
          page: this.page,
          pageSize: this.pageSize,
          totalPages: this.totalPages,
          sortBy: this.sortBy,
          sortOrder: this.sortOrder,
        });
      }
      this._updatePagination();
    } catch (error) {
      console.error('Erreur chargement:', error);
    }
  }

  _updatePagination() {
    if (!this.element) return;

    const countEl = this.element.querySelector('[data-count]');
    if (countEl) {
      const label = this.currentView === 'params' ? 'type' : 'équipement';
      countEl.textContent = `${this.total} ${label}${this.total > 1 ? 's' : ''}`;
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
    const isParamsView = this.currentView === 'params';
    const canCreateEquip = authStore.hasPermission('equipment.create');
    const canManageRefs = authStore.hasPermission('equipment.manage_referentials');

    const html = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>${isParamsView ? 'Paramètres — Types d\'équipements' : 'Équipements'}</h1>
          <p class="page-subtitle">${isParamsView ? 'Référentiel des types d\'équipements' : 'Gestion du patrimoine des équipements'}</p>
        </div>
        <div class="page-header-right">
          ${!isParamsView && canCreateEquip ? '<button class="btn btn-primary" data-action="create">+ Nouvel équipement</button>' : ''}
          ${isParamsView && canManageRefs ? '<button class="btn btn-primary" data-action="create-type">+ Nouveau type</button>' : ''}
        </div>
      </div>

      <div class="buildings-tabs" role="tablist" aria-label="Navigation équipements">
        <button role="tab" class="tab-button ${!isParamsView ? 'tab-button--active' : ''}" data-tab="equipments" aria-selected="${!isParamsView}" aria-controls="panel-equipments">Équipements</button>
        ${canManageRefs ? `<button role="tab" class="tab-button ${isParamsView ? 'tab-button--active' : ''}" data-tab="params" aria-selected="${isParamsView}" aria-controls="panel-params">Paramètres</button>` : ''}
      </div>

      <div class="page-filters">
        <div class="filter-group">
           <label class="sr-only" for="equipment-search">Rechercher dans les ${isParamsView ? 'types' : 'équipements'}</label>
           <input id="equipment-search" type="text" class="form-input" placeholder="Rechercher..." data-filter="search" value="${this.search}">
        </div>
        ${!isParamsView ? `
        <div class="filter-group">
           <label class="sr-only" for="equipment-type-filter">Filtrer par type</label>
           <select id="equipment-type-filter" class="form-select" data-filter="equipment_type_id">
            <option value="">Tous les types</option>
            ${this.equipmentTypes.map(t => `<option value="${t.id}" ${this.filters.equipment_type_id == t.id ? 'selected' : ''}>${t.name}</option>`).join('')}
          </select>
        </div>
        <div class="filter-group">
           <label class="sr-only" for="equipment-status-filter">Filtrer par statut</label>
           <select id="equipment-status-filter" class="form-select" data-filter="status">
            <option value="">Tous les statuts</option>
            ${EQUIPMENT_STATUSES.map(s => `<option value="${s.value}" ${this.filters.status === s.value ? 'selected' : ''}>${s.label}</option>`).join('')}
          </select>
        </div>
        <div class="filter-group">
           <label class="sr-only" for="equipment-active-filter">Filtrer par état</label>
           <select id="equipment-active-filter" class="form-select" data-filter="is_active">
            <option value="">Tous</option>
            <option value="true" ${this.filters.is_active === 'true' ? 'selected' : ''}>Actif</option>
            <option value="false" ${this.filters.is_active === 'false' ? 'selected' : ''}>Inactif</option>
          </select>
        </div>
        ` : ''}
      </div>

      <div class="page-info">
        <span data-count>${this.total} ${isParamsView ? 'type' : 'équipement'}${this.total > 1 ? 's' : ''}</span>
      </div>

      <div data-table-container></div>

      <div class="pagination">
        <button class="btn btn-secondary" data-page="prev" ${this.page <= 1 ? 'disabled' : ''}>Précédent</button>
        <span data-page-info>Page ${this.page} / ${this.totalPages}</span>
        <button class="btn btn-secondary" data-page="next" ${this.page >= this.totalPages ? 'disabled' : ''}>Suivant</button>
      </div>
    `;

    if (!this.element) {
      this.element = document.createElement('div');
      this.element.className = 'page-content equipment-page';
    }
    this.element.innerHTML = html;

    this._setupEventListeners();
    return this.element;
  }

  _setupEventListeners() {
    const searchInput = this.element.querySelector('[data-filter="search"]');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        clearTimeout(this._searchTimeout);
        this._searchTimeout = setTimeout(() => {
          this.search = e.target.value;
          this.page = 1;
          this._loadDataForView();
        }, 300);
      });
    }

    if (this.currentView === 'equipments') {
      this.element.querySelectorAll('.form-select[data-filter]').forEach(select => {
        select.addEventListener('change', (e) => {
          const filter = select.dataset.filter;
          this.filters[filter] = e.target.value;
          this.page = 1;
          this._loadDataForView();
        });
      });
    }

    this.element.querySelector('[data-action="create"]')?.addEventListener('click', () => this._showEquipmentModal(null));
    this.element.querySelector('[data-action="create-type"]')?.addEventListener('click', () => this._showTypeModal(null));

    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => {
      if (this.page > 1) { this.page--; this._loadDataForView(); }
    });
    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => {
      if (this.page < this.totalPages) { this.page++; this._loadDataForView(); }
    });

    this.element.querySelectorAll('.tab-button')?.forEach((btn) => {
      btn.addEventListener('click', (e) => {
        const tab = btn.dataset.tab;
        this.currentView = tab;
        this.page = 1;
        this.search = '';
        this._refresh();
        e.preventDefault();
        e.stopPropagation();
      });
    });
  }

  _refresh() {
    this.render();
    this._loadDataForView();
  }

  async _showEquipmentModal(equipment) {
    const isEdit = !!equipment;
    const title = isEdit ? `Modifier: ${equipment.reference}` : 'Nouvel équipement';

    const sites = await this._loadSites();
    let buildings = [];
    let rooms = [];

    if (isEdit && equipment.room) {
      const room = equipment.room;
      if (room.building) {
        buildings = [room.building];
        if (room.building.site) {
          sites = [room.building.site, ...sites.filter(s => s.id !== room.building.site.id)];
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
      `<option value="${s.id}" ${isEdit && equipment.room?.building?.site?.id === s.id ? 'selected' : ''}>${s.name}</option>`
    ).join('');

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal">
        <div class="modal-content">
          <div class="modal-header">
            <h2>${title}</h2>
            <button class="modal-close" data-action="close-modal" aria-label="Fermer">&times;</button>
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
    const roomSelect = form.querySelector('[name="room_id"]');

    siteSelect.addEventListener('change', async () => {
      buildingSelect.innerHTML = '<option value="">Chargement...</option>';
      roomSelect.innerHTML = '<option value="">-- Sélectionner --</option>';
      if (siteSelect.value) {
        const resp = await listBuildings({ site_id: siteSelect.value, is_active: true, page_size: 1000 });
        buildings = resp.items || [];
        buildingSelect.innerHTML = '<option value="">-- Sélectionner --</option>' +
          buildings.map(b => `<option value="${b.id}" ${isEdit && equipment.room?.building?.id === b.id ? 'selected' : ''}>${b.name}</option>`).join('');
        if (isEdit && equipment.room?.building) {
          buildingSelect.value = equipment.room.building.id;
          buildingSelect.dispatchEvent(new Event('change'));
        }
      } else {
        buildingSelect.innerHTML = '<option value="">-- Sélectionner --</option>';
      }
    });

    buildingSelect.addEventListener('change', async () => {
      roomSelect.innerHTML = '<option value="">Chargement...</option>';
      if (buildingSelect.value) {
        const resp = await listRooms({ building_id: buildingSelect.value, is_active: true, page_size: 1000 });
        rooms = resp.items || [];
        roomSelect.innerHTML = '<option value="">-- Sélectionner --</option>' +
          rooms.map(r => `<option value="${r.id}" ${isEdit && equipment.room_id === r.id ? 'selected' : ''}>${r.reference} - ${r.name}</option>`).join('');
        if (isEdit && equipment.room_id) {
          roomSelect.value = equipment.room_id;
        }
      } else {
        roomSelect.innerHTML = '<option value="">-- Sélectionner --</option>';
      }
    });

    if (isEdit && equipment.room?.building?.site) {
      siteSelect.value = equipment.room.building.site.id;
      siteSelect.dispatchEvent(new Event('change'));
    }

    modal.querySelector('[data-action="save-equipment"]').addEventListener('click', async () => {
      const formData = new FormData(form);
      const data = {};
      for (const [key, value] of formData.entries()) {
        if (value === '' || value === null) continue;
        if (key === 'equipment_type_id' || key === 'room_id' || key === 'site_id' || key === 'building_id') {
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
        this._loadDataForView();
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

  async _showTypeModal(item) {
    const isEdit = !!item;
    const title = isEdit ? `Modifier: ${item.name}` : 'Nouveau type d\'équipement';

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal">
        <div class="modal-content">
          <div class="modal-header">
            <h2>${title}</h2>
            <button class="modal-close" data-action="close-modal" aria-label="Fermer">&times;</button>
          </div>
          <div class="modal-body">
            <form data-type-form>
            ${isEdit ? `
            <label><span>Code</span><input name="code" value="${item.code}" readonly></label>
            ` : `
            <input type="hidden" name="code" data-code-input value="">
            `}
            <label><span>Nom *</span><input name="name" value="${isEdit ? item.name : ''}" required maxlength="100" data-name-input></label>
            <label><span>Description</span><textarea name="description" rows="3">${isEdit ? (item.description || '') : ''}</textarea></label>
            <label><span>Ordre d'affichage</span><input type="number" name="sort_order" min="0" value="${isEdit ? item.sort_order : 0}"></label>
            ${isEdit ? `
            <label class="checkbox-label">
              <input type="checkbox" name="is_active" ${item.is_active ? 'checked' : ''}>
              Actif
            </label>
            ` : ''}
          </form>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" data-action="close-modal">Annuler</button>
          <button class="btn btn-primary" data-action="save-type">${isEdit ? 'Enregistrer' : 'Créer'}</button>
        </div>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    modal.querySelector('[data-action="close-modal"]').addEventListener('click', () => modal.remove());
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });

    if (!isEdit) {
      const nameInput = modal.querySelector('[data-name-input]');
      const codeInput = modal.querySelector('[data-code-input]');
      if (nameInput && codeInput) {
        nameInput.addEventListener('input', () => {
          const code = nameInput.value
            .trim()
            .toUpperCase()
            .replace(/[^A-Z0-9\s]/g, '')
            .replace(/\s+/g, '_')
            .substring(0, 50);
          codeInput.value = code;
        });
      }
    }

    modal.querySelector('[data-action="save-type"]').addEventListener('click', async () => {
      const formData = new FormData(modal.querySelector('[data-type-form]'));
      const data = {
        name: formData.get('name'),
        description: formData.get('description') || null,
        sort_order: parseInt(formData.get('sort_order') || '0', 10),
      };

      if (!data.name) {
        alert('Le champ Nom est obligatoire');
        return;
      }

      if (isEdit) {
        data.is_active = modal.querySelector('[name="is_active"]')?.checked ?? true;
      }

      try {
        if (isEdit) {
          await updateEquipmentType(item.id, data);
        } else {
          data.code = formData.get('code')?.trim().toUpperCase();
          await createEquipmentType(data);
        }
        modal.remove();
        this._loadDataForView();
        this._showToast(isEdit ? 'Type modifié' : 'Type créé');
      } catch (error) {
        alert(error.message || 'Erreur lors de la sauvegarde');
      }
    });
  }

  async _deactivate(item) {
    if (!confirm(`Désactiver l'équipement "${item.reference}" ?`)) return;
    try {
      await deactivateEquipment(item.id);
      this._loadDataForView();
      this._showToast('Équipement désactivé');
    } catch (error) {
      alert(error.message || 'Erreur lors de la désactivation');
    }
  }

  async _executeConfirmedAction() {
    if (!this.pendingAction) return;
    const { type, item, view } = this.pendingAction;
    this.pendingAction = null;

    try {
      if (type === 'delete') {
        if (view === 'equipments') {
          await deleteEquipment(item.id);
        } else if (view === 'params') {
          await deleteEquipmentType(item.id);
        }
        await this._loadDataForView();
        this._showToast('Supprimé');
      }
    } catch (error) {
      this._showToast(error.message || 'Erreur lors de l\'opération', 'error');
    }
  }

  _showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }

  _updateButtonVisibility() {
    if (!this.element) return;
    const canCreateEquip = authStore.hasPermission('equipment.create');
    const canManageRefs = authStore.hasPermission('equipment.manage_referentials');
    const isParamsView = this.currentView === 'params';
    const createBtn = this.element.querySelector('[data-action="create"]');
    const createTypeBtn = this.element.querySelector('[data-action="create-type"]');

    if (createBtn) createBtn.style.display = !isParamsView && canCreateEquip ? '' : 'none';
    if (createTypeBtn) createTypeBtn.style.display = isParamsView && canManageRefs ? '' : 'none';
  }

  mount(container) {
    if (!this.element) this.render();
    container.innerHTML = '';
    container.appendChild(this.element);
    this._loadDataForView();
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