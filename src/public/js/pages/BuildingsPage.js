import { authStore } from '../stores/auth.js';
import { Table } from '../components/Table.js';
import { ConfirmDialog } from '../components/ConfirmDialog.js';
import {
  listSites,
  createSite,
  updateSite,
  deleteSite,
  listBuildings,
  createBuilding,
  updateBuilding,
  deleteBuilding,
  listRooms,
  createRoom,
  updateRoom,
  deleteRoom,
  listUsageTypes,
} from '../services/buildingsApi.js';

export class BuildingsPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.loading = false;
    this.error = null;

    this.currentView = 'sites';
    this.currentSiteId = null;
    this.currentBuildingId = null;

    this.currentSite = null;
    this.currentBuilding = null;

    this.data = [];
    this.total = 0;
    this.page = 1;
    this.pageSize = 20;
    this.totalPages = 1;

    this.sortBy = 'created_at';
    this.sortOrder = 'desc';
    this.search = '';

    this.table = null;
    this.confirmDialog = null;
    this._authUnsubscribe = null;
    this.pendingAction = null;
    this._searchTimeout = null;

    this.usageTypes = [];
  }

  async initialize() {
    this.table = new Table({
      columns: this._getColumns(),
      actions: this._getActions(),
      onAction: (action, item) => this._handleTableAction(action, item),
      onSort: (sortBy, sortOrder) => {
        this.sortBy = sortBy;
        this.sortOrder = sortOrder;
        this.loadData();
      },
    });

    this.confirmDialog = new ConfirmDialog({
      onConfirm: () => this._executeConfirmedAction(),
      onCancel: () => { this.pendingAction = null; },
    });

    this._authUnsubscribe = authStore.subscribe(() => this._updateButtonVisibility());

    try {
      const utResp = await listUsageTypes({ page_size: 1000 });
      this.usageTypes = utResp.items || [];
    } catch (_) {
      // reference data optional
    }
  }

  _getColumns() {
    switch (this.currentView) {
      case 'sites':
        return [
          { key: 'reference', label: 'Référence', sortable: true },
          { key: 'name', label: 'Nom', sortable: true },
          { key: 'city', label: 'Ville', sortable: true },
          { key: 'building_count', label: 'Bâtiments', sortable: false },
        ];
      case 'buildings':
        return [
          { key: 'reference', label: 'Référence', sortable: true },
          { key: 'name', label: 'Nom', sortable: true },
          { key: 'building_number', label: 'N°', sortable: false },
          { key: 'room_count', label: 'Locaux', sortable: false },
        ];
      case 'rooms':
        return [
          { key: 'reference', label: 'Référence', sortable: true },
          { key: 'name', label: 'Nom', sortable: true },
          { key: 'usage_type.name', label: 'Usage', sortable: false, render: (item) => item.usage_type?.name || '—' },
          { key: 'area', label: 'Surface', sortable: true, render: (item) => item.area ? `${item.area} m²` : '—' },
          { key: 'used_for_accommodation', label: 'Hébergement', sortable: false, render: (item) =>
            item.used_for_accommodation
              ? '<span class="status-badge active">Oui</span>'
              : '<span class="status-badge inactive">Non</span>'
          },
        ];
      default:
        return [];
    }
  }

  _getActions() {
    if (this.currentView === 'rooms') {
      return [
        { key: 'edit', label: 'Modifier', icon: 'edit', permission: 'building.update' },
        { key: 'delete', label: 'Supprimer', icon: 'trash', permission: 'building.delete' },
      ];
    }

    const deleteAction = this.currentView === 'sites'
      ? {
          label: item => item.building_count > 0
            ? `Suppression impossible (${item.building_count} bâtiment${item.building_count > 1 ? 's' : ''})`
            : 'Supprimer',
          disabled: item => item.building_count > 0,
        }
      : {
          label: item => item.room_count > 0
            ? `Suppression impossible (${item.room_count} local${item.room_count > 1 ? 'aux' : ''})`
            : 'Supprimer',
          disabled: item => item.room_count > 0,
        };

    return [
      { key: 'view', label: 'Ouvrir', icon: 'edit', permission: 'building.view' },
      { key: 'edit', label: 'Modifier', icon: 'edit', permission: 'building.update' },
      { key: 'delete', icon: 'trash', permission: 'building.delete', ...deleteAction },
    ];
  }

  _handleTableAction(action, item) {
    switch (action) {
      case 'view':
        if (this.currentView === 'sites') this._openSite(item);
        else if (this.currentView === 'buildings') this._openBuilding(item);
        break;
      case 'edit':
        if (!authStore.hasPermission('building.update')) {
          const labelEdit = { sites: 'ce site', buildings: 'ce bâtiment', rooms: 'ce local' }[this.currentView];
          this.showToast(`Vous n'avez pas la permission de modifier ${labelEdit}.`, 'error');
          return;
        }
        this._openEditModal(item);
        break;
      case 'delete':
        if (!authStore.hasPermission('building.delete')) {
          const labelDelete = { sites: 'ce site', buildings: 'ce bâtiment', rooms: 'ce local' }[this.currentView];
          this.showToast(`Vous n'avez pas la permission de supprimer ${labelDelete}.`, 'error');
          return;
        }
        this._confirmDelete(item);
        break;
    }
  }

  async loadData() {
    this.loading = true;
    this.error = null;
    this._renderTable();

    try {
      let response;
      switch (this.currentView) {
        case 'sites':
          response = await listSites({ page: this.page, page_size: this.pageSize, search: this.search || undefined, sort_by: this.sortBy, sort_order: this.sortOrder });
          break;
        case 'buildings':
          response = await listBuildings({ page: this.page, page_size: this.pageSize, search: this.search || undefined, site_id: this.currentSiteId, sort_by: this.sortBy, sort_order: this.sortOrder });
          break;
        case 'rooms':
          response = await listRooms({ page: this.page, page_size: this.pageSize, search: this.search || undefined, building_id: this.currentBuildingId, sort_by: this.sortBy, sort_order: this.sortOrder });
          break;
      }
      this.data = response.items || [];
      this.total = response.total || 0;
      this.page = response.page || 1;
      this.totalPages = response.total_pages || 1;
    } catch (error) {
      this.error = error.message || 'Erreur lors du chargement';
      this.data = [];
      this.total = 0;
    } finally {
      this.loading = false;
      this._renderTable();
      this._updatePagination();
    }
  }

  _openSite(site) {
    this.currentView = 'buildings';
    this.currentSiteId = site.id;
    this.currentSite = site;
    this._resetPaging();
    this._refresh();
  }

  _openBuilding(building) {
    this.currentView = 'rooms';
    this.currentBuildingId = building.id;
    this.currentBuilding = building;
    this._resetPaging();
    this._refresh();
  }

  _goBack() {
    if (this.currentView === 'rooms') {
      this.currentView = 'buildings';
      this.currentBuildingId = null;
      this.currentBuilding = null;
    } else if (this.currentView === 'buildings') {
      this.currentView = 'sites';
      this.currentSiteId = null;
      this.currentSite = null;
    }
    this._resetPaging();
    this._refresh();
  }

  _goToRoot() {
    this.currentView = 'sites';
    this.currentSiteId = null;
    this.currentSite = null;
    this.currentBuildingId = null;
    this.currentBuilding = null;
    this._resetPaging();
    this._refresh();
  }

  _resetPaging() {
    this.page = 1;
    this.search = '';
    this.sortBy = 'created_at';
    this.sortOrder = 'desc';
  }

  _refresh() {
    this.table = new Table({
      columns: this._getColumns(),
      actions: this._getActions(),
      onAction: (action, item) => this._handleTableAction(action, item),
      onSort: (sortBy, sortOrder) => {
        this.sortBy = sortBy;
        this.sortOrder = sortOrder;
        this.loadData();
      },
    });
    this.render();
    this.loadData();
  }

  _confirmDelete(item) {
    const typeLabel = {
      sites: 'ce site',
      buildings: 'ce bâtiment',
      rooms: 'ce local',
    }[this.currentView];

    this.confirmDialog.open({
      title: 'Confirmer la suppression',
      message: this.currentView === 'rooms' && (item.equipment_count > 0 || item.occupancy_count > 0)
        ? `Ce local contient ${item.equipment_count} équipement(s) et ${item.occupancy_count} réservation(s) / occupation(s). Ils seront tous supprimés.`
        : `Êtes-vous sûr de vouloir supprimer ${typeLabel} ? Cette action est irréversible.`,
      confirmText: this.currentView === 'rooms' && (item.equipment_count > 0 || item.occupancy_count > 0)
        ? 'Supprimer définitivement'
        : 'Supprimer',
      variant: 'danger',
      requireCheckbox: this.currentView === 'rooms' && (item.equipment_count > 0 || item.occupancy_count > 0),
      checkboxLabel: 'Je confirme la suppression du local et de toutes ses données associées.',
    });
    this.pendingAction = { item, type: 'delete' };
  }

  async _executeConfirmedAction() {
    if (!this.pendingAction) return;
    const { item, type } = this.pendingAction;
    this.pendingAction = null;

    try {
      if (type === 'delete') {
        const deleteFn = {
          sites: deleteSite,
          buildings: deleteBuilding,
          rooms: deleteRoom,
        }[this.currentView];
        if (deleteFn) {
          const force = this.currentView === 'rooms'
            && (item.equipment_count > 0 || item.occupancy_count > 0);
          await deleteFn(item.id, force);
          this.showToast('Supprimé', 'success');
          this.loadData();
        }
      }
    } catch (error) {
      this.showToast(error?.data?.detail || error.message || 'Erreur', 'error');
    }
  }

  async _openEditModal(item) {
    const isEdit = !!item;
    const type = this.currentView === 'sites' ? 'site'
      : this.currentView === 'buildings' ? 'building'
      : 'room';

    if (type === 'room') {
      try {
        const utResp = await listUsageTypes({ page_size: 1000 });
        this.usageTypes = utResp.items || [];
      } catch (_) {
        // Keep the last loaded referential if it is temporarily unavailable.
      }
    }

    const typeLabel = {
      site: 'un site',
      building: 'un bâtiment',
      room: 'un local',
    }[type];

    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';

    const modal = document.createElement('div');
    modal.className = 'modal open';

    const content = document.createElement('div');
    content.className = 'modal-content';

    const v = (field, def = '') => item?.[field] ?? def;

    let fields = '';
    if (type === 'site') {
      fields = `
        <div class="form-group"><label>Nom</label><input name="name" value="${this._escapeHtml(v('name'))}" required></div>
        <div class="form-group"><label>Adresse</label><input name="address" value="${this._escapeHtml(v('address'))}"></div>
        <div class="form-group"><label>Code postal</label><input name="postal_code" value="${this._escapeHtml(v('postal_code'))}"></div>
        <div class="form-group"><label>Ville</label><input name="city" value="${this._escapeHtml(v('city'))}"></div>
        <div class="form-group"><label>Pays</label><input name="country" value="${this._escapeHtml(v('country'))}"></div>
        <div class="form-group"><label>Description</label><textarea name="description">${this._escapeHtml(v('description'))}</textarea></div>
      `;
    } else if (type === 'building') {
      fields = `
        <div class="form-group"><label>Nom</label><input name="name" value="${this._escapeHtml(v('name'))}" required></div>
        <div class="form-group"><label>N° bâtiment</label><input name="building_number" value="${this._escapeHtml(v('building_number'))}"></div>
        <div class="form-group"><label>Nombre d'étages (info)</label><input name="floors_count" type="number" value="${v('floors_count')}"></div>
        <div class="form-group"><label>Description</label><textarea name="description">${this._escapeHtml(v('description'))}</textarea></div>
        ${!isEdit ? `<input type="hidden" name="site_id" value="${this.currentSiteId}">` : ''}
      `;
    } else if (type === 'room') {
      const usageOptions = this.usageTypes.map(ut =>
        `<option value="${ut.id}" ${v('usage_type_id') == ut.id ? 'selected' : ''}>${this._escapeHtml(ut.name)}</option>`
      ).join('');
      fields = `
        <div class="form-group"><label>Nom</label><input name="name" value="${this._escapeHtml(v('name'))}" required></div>
        <div class="form-group"><label>Type d'utilisation</label><select name="usage_type_id"><option value="">—</option>${usageOptions}</select></div>
        <div class="form-group"><label>Surface (m²)</label><input name="area" type="number" step="0.01" value="${v('area')}"></div>
        <div class="form-group"><label>Hébergement</label><select name="used_for_accommodation"><option value="false" ${!v('used_for_accommodation') ? 'selected' : ''}>Non</option><option value="true" ${v('used_for_accommodation') ? 'selected' : ''}>Oui</option></select></div>
        <div class="form-group"><label>Description</label><textarea name="description">${this._escapeHtml(v('description'))}</textarea></div>
        ${!isEdit ? `<input type="hidden" name="building_id" value="${this.currentBuildingId}">` : ''}
      `;
    }

    content.innerHTML = `
      <div class="modal-header">
        <h2>${isEdit ? 'Modifier' : 'Créer'} ${typeLabel}</h2>
        <button type="button" class="modal-close" data-action="close" aria-label="Fermer">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
      <div class="modal-body">
        <form id="building-edit-form">${fields}</form>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-secondary" data-action="close">Annuler</button>
        <button type="button" class="btn btn-primary" data-action="save">Enregistrer</button>
      </div>
    `;

    modal.appendChild(content);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    requestAnimationFrame(() => overlay.classList.add('open'));

    const close = () => {
      overlay.classList.remove('open');
      setTimeout(() => overlay.remove(), 200);
    };

    overlay.querySelectorAll('[data-action="close"]').forEach(btn => btn.addEventListener('click', close));

    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

    content.querySelector('[data-action="save"]').addEventListener('click', async () => {
      const form = content.querySelector('#building-edit-form');
      const formData = new FormData(form);
      const data = Object.fromEntries(formData.entries());

      if (form.elements['area']) {
        data.area = data.area ? parseFloat(data.area) : null;
      }
      if (form.elements['floors_count']) {
        data.floors_count = data.floors_count ? parseInt(data.floors_count, 10) : null;
      }
      if (data.site_id) data.site_id = parseInt(data.site_id, 10);
      if (data.building_id) data.building_id = parseInt(data.building_id, 10);
      if (form.elements['usage_type_id']) {
        data.usage_type_id = data.usage_type_id ? parseInt(data.usage_type_id, 10) : null;
      }
      if (form.elements['used_for_accommodation']) {
        data.used_for_accommodation = data.used_for_accommodation === 'true';
      }

      try {
        const createFn = {
          site: createSite,
          building: createBuilding,
          room: createRoom,
        }[type];
        const updateFn = {
          site: updateSite,
          building: updateBuilding,
          room: updateRoom,
        }[type];
        if (isEdit) {
          await updateFn(item.id, data);
        } else {
          await createFn(data);
        }
        close();
        this.showToast(isEdit ? 'Modifié' : 'Créé', 'success');
        this.loadData();
      } catch (error) {
        this.showToast(error.message || 'Erreur', 'error');
      }
    });
  }

  _updatePagination() {
    if (!this.element) return;
    const info = this.element.querySelector('.pagination-info');
    if (info) {
      info.innerHTML = `Page <strong>${this.page}</strong> sur <strong>${this.totalPages}</strong> (${this.total} total)`;
    }
    const prev = this.element.querySelector('[data-page="prev"]');
    const next = this.element.querySelector('[data-page="next"]');
    if (prev) prev.disabled = this.page <= 1;
    if (next) next.disabled = this.page >= this.totalPages;

    const count = this.element.querySelector('.users-count');
    if (count) {
      const labels = {
        sites: 'site',
        buildings: 'bâtiment',
        rooms: 'local',
      };
      count.textContent = `${this.total} ${labels[this.currentView]}${this.total > 1 ? 's' : ''}`;
    }
  }

  render() {
    if (!this.element) {
      this.element = document.createElement('div');
      this.element.className = 'buildings-page';
    }

    const canCreate = authStore.hasPermission('building.create');
    const breadcrumbs = this._getBreadcrumbs();

    this.element.innerHTML = `
      <div class="users-header">
        <div class="users-title-area">
          ${breadcrumbs.length > 0 ? `
            <div class="breadcrumb">
              <a href="#" data-action="breadcrumb-root" class="breadcrumb-link">Sites</a>
              ${breadcrumbs.map((b, i) => `<span class="breadcrumb-separator">›</span>${i < breadcrumbs.length - 1 ? `<a href="#" data-action="breadcrumb" data-index="${i}" class="breadcrumb-link">${this._escapeHtml(b.label)}</a>` : `<span>${this._escapeHtml(b.label)}</span>`}`).join('')}
            </div>
          ` : ''}
          <h1 class="users-title">${this._getTitle()}</h1>
          <p class="users-count">${this._getCountText()}</p>
        </div>
        <div class="users-header-actions">
          ${breadcrumbs.length > 0 ? `<button type="button" class="btn btn-secondary" data-action="back">← Retour</button>` : ''}
          ${canCreate ? `<button type="button" class="btn btn-primary" data-action="create">+ Nouveau</button>` : ''}
        </div>
      </div>
      <div class="users-toolbar">
        <input type="search" class="form-input" placeholder="Rechercher..." value="${this._escapeHtml(this.search)}" data-action="search">
      </div>
      <div data-table-container></div>
      <div class="users-pagination" data-pagination>
        <div class="pagination-info">Page <strong>${this.page}</strong> sur <strong>${this.totalPages}</strong> (${this.total} total)</div>
        <div class="pagination-controls">
          <button class="btn btn-sm btn-secondary" data-page="prev" ${this.page <= 1 ? 'disabled' : ''}>‹ Précédent</button>
          <button class="btn btn-sm btn-secondary" data-page="next" ${this.page >= this.totalPages ? 'disabled' : ''}>Suivant ›</button>
        </div>
      </div>
    `;

    this.element.querySelectorAll('[data-action="back"]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        this._goBack();
      });
    });

    this.element.querySelector('[data-action="breadcrumb-root"]')?.addEventListener('click', (e) => {
      e.preventDefault();
      this._goToRoot();
    });

    this.element.querySelector('[data-action="create"]')?.addEventListener('click', () => this._openEditModal(null));

    this.element.querySelectorAll('[data-action="breadcrumb"]').forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        const idx = parseInt(link.dataset.index);
        this._navigateToBreadcrumb(idx);
      });
    });

    this.element.querySelector('[data-action="search"]')?.addEventListener('input', (e) => {
      this.search = e.target.value;
      clearTimeout(this._searchTimeout);
      this._searchTimeout = setTimeout(() => { this.page = 1; this.loadData(); }, 300);
    });

    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => { if (this.page > 1) { this.page--; this.loadData(); } });
    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => { if (this.page < this.totalPages) { this.page++; this.loadData(); } });

    this._renderTable();

    return this.element;
  }

  _navigateToBreadcrumb(index) {
    if (index === 0) {
      this.currentView = 'buildings';
      this.currentBuildingId = null;
      this.currentBuilding = null;
    }
    this._resetPaging();
    this._refresh();
  }

  _renderTable() {
    if (!this.element) return;
    const container = this.element.querySelector('[data-table-container]');
    if (!container) return;

    if (this.loading) {
      container.innerHTML = '<div class="table-loading"><div class="spinner"></div><p>Chargement...</p></div>';
      return;
    }

    if (this.error) {
      container.innerHTML = `<div class="table-error"><h3>Erreur</h3><p>${this._escapeHtml(this.error)}</p><button class="btn btn-primary" data-action="retry">Réessayer</button></div>`;
      container.querySelector('[data-action="retry"]')?.addEventListener('click', () => this.loadData());
      return;
    }

    this.table.setData({
      items: this.data,
      total: this.total,
      page: this.page,
      pageSize: this.pageSize,
      totalPages: this.totalPages,
      sortBy: this.sortBy,
      sortOrder: this.sortOrder,
    });

    container.innerHTML = '';
    container.appendChild(this.table.render());
    this.table.updateActionVisibility(authStore);
  }

  _getTitle() {
    if (this.currentView === 'buildings' && this.currentSite) return `Bâtiments — ${this.currentSite.name}`;
    if (this.currentView === 'rooms' && this.currentBuilding) return `Locaux — ${this.currentBuilding.name}`;
    return 'Sites';
  }

  _getCountText() {
    const labels = {
      sites: 'site',
      buildings: 'bâtiment',
      rooms: 'local',
    };
    return `${this.total} ${labels[this.currentView]}${this.total > 1 ? 's' : ''}`;
  }

  _getBreadcrumbs() {
    const crumbs = [];
    if (['buildings', 'rooms'].includes(this.currentView)) {
      crumbs.push({ label: this.currentSite?.name || 'Site', view: 'buildings', siteId: this.currentSiteId });
    }
    if (this.currentView === 'rooms') {
      crumbs.push({ label: this.currentBuilding?.name || 'Bâtiment', view: 'buildings', buildingId: this.currentBuildingId });
    }
    return crumbs;
  }

  _updateButtonVisibility() {}

  showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;
    toast.textContent = message;
    toast.setAttribute('role', 'alert');
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('toast--visible'));
    setTimeout(() => {
      toast.classList.remove('toast--visible');
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  mount(container) {
    this.render();
    container.innerHTML = '';
    container.appendChild(this.element);
    this.loadData();
    return this;
  }

  destroy() {
    this._authUnsubscribe?.();
    this.confirmDialog?.destroy?.();
    clearTimeout(this._searchTimeout);
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text ?? '';
    return div.innerHTML;
  }
}

export function createBuildingsPage(router) {
  return new BuildingsPage(router);
}
