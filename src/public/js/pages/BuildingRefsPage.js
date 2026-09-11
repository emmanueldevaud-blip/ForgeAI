import { authStore } from '../stores/auth.js';
import { Table } from '../components/Table.js';
import { ConfirmDialog } from '../components/ConfirmDialog.js';
import {
  listUsageTypes,
  createUsageType,
  updateUsageType,
  listRoomTypes,
  createRoomType,
  updateRoomType,
} from '../services/buildingsApi.js';

export class BuildingRefsPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.loading = false;
    this.error = null;

    this.currentTab = 'usage-types';
    this.data = [];
    this.total = 0;
    this.page = 1;
    this.pageSize = 20;
    this.totalPages = 1;
    this.sortBy = 'sort_order';
    this.sortOrder = 'asc';
    this.search = '';

    this.table = null;
    this.confirmDialog = null;
    this._authUnsubscribe = null;
    this.pendingAction = null;
    this._searchTimeout = null;

    this.modalOverlay = null;
    this.editingItem = null;
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
  }

  _getColumns() {
    return [
      { key: 'code', label: 'Code', sortable: true },
      { key: 'name', label: 'Nom', sortable: true },
      { key: 'description', label: 'Description', sortable: false },
      {
        key: 'is_active',
        label: 'Statut',
        sortable: true,
        render: (item) => item.is_active
          ? '<span class="status-badge active">Actif</span>'
          : '<span class="status-badge inactive">Inactif</span>',
      },
    ];
  }

  _getActions() {
    const canManage = authStore.hasPermission('building.manage_refs');
    if (!canManage) return [];

    return [
      {
        key: 'edit',
        label: 'Modifier',
        icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>',
        variant: 'secondary',
      },
      {
        key: 'toggle-active',
        label: (item) => item.is_active ? 'Désactiver' : 'Activer',
        icon: (item) => item.is_active
          ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"></line></svg>'
          : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>',
        variant: (item) => item.is_active ? 'danger' : 'success',
      },
    ];
  }

  _handleTableAction(action, item) {
    if (action === 'edit') {
      this._openModal(item);
    } else if (action === 'toggle-active') {
      this._confirmToggleActive(item);
    }
  }

  _confirmToggleActive(item) {
    const action = item.is_active ? 'deactivate' : 'activate';
    this.pendingAction = { type: action, item };
    this.confirmDialog.open({
      title: item.is_active ? 'Désactiver' : 'Activer',
      message: `Voulez-vous vraiment ${item.is_active ? 'désactiver' : 'activer'} "${item.name}" ?`,
      confirmText: item.is_active ? 'Désactiver' : 'Activer',
      variant: item.is_active ? 'danger' : 'primary',
    });
  }

  async _executeConfirmedAction() {
    if (!this.pendingAction) return;

    const { type, item } = this.pendingAction;
    this.pendingAction = null;

    try {
      if (type === 'deactivate' || type === 'activate') {
        const updateFn = this.currentTab === 'usage-types' ? updateUsageType : updateRoomType;
        await updateFn(item.id, { is_active: type === 'activate' });
        await this.loadData();
      }
    } catch (error) {
      this.showToast(error.message || 'Erreur lors de l\'opération', 'error');
    }
  }

  _openModal(item = null) {
    this.editingItem = item;
    const isEdit = !!item;
    const title = isEdit ? 'Modifier' : 'Créer';
    const refLabel = this.currentTab === 'usage-types' ? 'Type de local' : 'Type de pièce';

    this.modalOverlay = document.createElement('div');
    this.modalOverlay.className = 'modal-overlay';

    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-labelledby', 'ref-modal-title');

    modal.innerHTML = `
      <div class="modal-content">
        <div class="modal-header">
          <h2 id="ref-modal-title">${title} — ${refLabel}</h2>
          <button type="button" class="modal-close" aria-label="Fermer" data-action="close-modal">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <form id="ref-form" class="modal-form">
            <div class="form-group">
              <label for="ref-code">Code <span class="required">*</span></label>
              <input
                type="text"
                id="ref-code"
                name="code"
                required
                maxlength="50"
                pattern="[A-Z0-9_]+"
                title="Majuscules, chiffres et underscores uniquement"
                value="${this._escapeHtml(item?.code || '')}"
                ${isEdit ? 'readonly' : ''}
                placeholder="EX: BUREAUX"
              >
            </div>
            <div class="form-group">
              <label for="ref-name">Nom <span class="required">*</span></label>
              <input
                type="text"
                id="ref-name"
                name="name"
                required
                maxlength="100"
                value="${this._escapeHtml(item?.name || '')}"
                placeholder="Nom du référentiel"
              >
            </div>
            <div class="form-group">
              <label for="ref-description">Description</label>
              <textarea
                id="ref-description"
                name="description"
                rows="3"
                placeholder="Description optionnelle"
              >${this._escapeHtml(item?.description || '')}</textarea>
            </div>
            <div class="form-group">
              <label for="ref-sort_order">Ordre d'affichage</label>
              <input
                type="number"
                id="ref-sort_order"
                name="sort_order"
                min="0"
                value="${item?.sort_order ?? 0}"
              >
            </div>
            ${isEdit ? `
              <div class="form-group">
                <label class="checkbox-label">
                  <input
                    type="checkbox"
                    name="is_active"
                    ${item?.is_active ? 'checked' : ''}
                  >
                  Actif
                </label>
              </div>
            ` : ''}
          </form>
        </div>
        <div class="form-actions">
          <button type="button" class="btn btn-secondary" data-action="close-modal">Annuler</button>
          <button type="submit" class="btn btn-primary" form="ref-form">${isEdit ? 'Enregistrer' : 'Créer'}</button>
        </div>
      </div>
    `;

    this.modalOverlay.appendChild(modal);
    document.body.appendChild(this.modalOverlay);

    requestAnimationFrame(() => {
      this.modalOverlay.classList.add('open');
      modal.classList.add('open');
    });

    modal.querySelectorAll('[data-action="close-modal"]').forEach(btn => {
      btn.addEventListener('click', () => this._closeModal());
    });

    this.modalOverlay.addEventListener('click', (e) => {
      if (e.target === this.modalOverlay) this._closeModal();
    });

    document.addEventListener('keydown', this._handleModalKeydown);

    const form = modal.querySelector('#ref-form');
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      this._handleFormSubmit(form);
    });
  }

  _handleModalKeydown = (e) => {
    if (e.key === 'Escape') this._closeModal();
  };

  _closeModal() {
    if (!this.modalOverlay) return;
    document.removeEventListener('keydown', this._handleModalKeydown);
    this.modalOverlay.classList.remove('open');
    const modal = this.modalOverlay.querySelector('.modal');
    if (modal) modal.classList.remove('open');
    setTimeout(() => {
      this.modalOverlay?.remove();
      this.modalOverlay = null;
      this.editingItem = null;
    }, 200);
  }

  async _handleFormSubmit(form) {
    const formData = new FormData(form);
    const data = {
      code: formData.get('code')?.trim().toUpperCase(),
      name: formData.get('name')?.trim(),
      description: formData.get('description')?.trim() || null,
      sort_order: parseInt(formData.get('sort_order') || '0', 10),
    };

    if (!data.code || !data.name) {
      this.showToast('Code et Nom sont requis', 'error');
      return;
    }

    if (this.editingItem) {
      data.is_active = form.querySelector('[name="is_active"]')?.checked ?? true;
    }

    const createFn = this.currentTab === 'usage-types' ? createUsageType : createRoomType;
    const updateFn = this.currentTab === 'usage-types' ? updateUsageType : updateRoomType;

    try {
      if (this.editingItem) {
        await updateFn(this.editingItem.id, data);
      } else {
        await createFn(data);
      }
      this._closeModal();
      await this.loadData();
    } catch (error) {
      this.showToast(error.message || 'Erreur lors de l\'enregistrement', 'error');
    }
  }

  async loadData() {
    this.loading = true;
    this.error = null;
    this._renderTable();

    const listFn = this.currentTab === 'usage-types' ? listUsageTypes : listRoomTypes;

    try {
      const params = {
        page: this.page,
        page_size: this.pageSize,
        sort_by: this.sortBy,
        sort_order: this.sortOrder,
      };
      if (this.search) params.search = this.search;

      const response = await listFn(params);
      this.data = response.items || [];
      this.total = response.total || 0;
      this.totalPages = response.total_pages || Math.ceil(this.total / this.pageSize) || 1;
    } catch (error) {
      this.error = error.message || 'Erreur de chargement';
      this.data = [];
      this.total = 0;
    } finally {
      this.loading = false;
      this._renderTable();
    }
  }

  _renderTable() {
    if (!this.element) return;
    const tableContainer = this.element.querySelector('[data-refs-table]');
    if (!tableContainer) return;

    this.table.setData({
      items: this.data,
      total: this.total,
      page: this.page,
      pageSize: this.pageSize,
      totalPages: this.totalPages,
      sortBy: this.sortBy,
      sortOrder: this.sortOrder,
    });

    tableContainer.innerHTML = '';
    tableContainer.appendChild(this.table.render());
  }

  _updateButtonVisibility() {
    if (!this.element) return;
    const createBtn = this.element.querySelector('[data-action="create-ref"]');
    if (createBtn) {
      const canManage = authStore.hasPermission('building.manage_refs');
      createBtn.style.display = canManage ? '' : 'none';
    }
  }

  _switchTab(tabId) {
    this.currentTab = tabId;
    this.page = 1;
    this.search = '';
    this.sortBy = 'sort_order';
    this.sortOrder = 'asc';

    this.element?.querySelectorAll('[data-ref-tab]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.refTab === tabId);
      btn.setAttribute('aria-selected', btn.dataset.refTab === tabId);
    });

    const searchInput = this.element?.querySelector('[data-search-input]');
    if (searchInput) searchInput.value = '';

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

    this.loadData();
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'building-refs-page';

    const canManage = authStore.hasPermission('building.manage_refs');

    this.element.innerHTML = `
      <div class="users-header">
        <div class="users-title-area">
          <h1 class="users-title">Référentiels Bâtiment</h1>
          <p class="users-count" aria-live="polite">
            ${this.total} élément${this.total > 1 ? 's' : ''}
          </p>
        </div>
        ${canManage ? `
          <button class="btn btn-primary" data-action="create-ref">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
            Nouveau
          </button>
        ` : ''}
      </div>

      <div class="admin-tabs" role="tablist" aria-label="Types de référentiels">
        <button
          class="admin-tab ${this.currentTab === 'usage-types' ? 'active' : ''}"
          role="tab"
          data-ref-tab="usage-types"
          aria-selected="${this.currentTab === 'usage-types'}"
        >
          Types de locaux
        </button>
        <button
          class="admin-tab ${this.currentTab === 'room-types' ? 'active' : ''}"
          role="tab"
          data-ref-tab="room-types"
          aria-selected="${this.currentTab === 'room-types'}"
        >
          Types de pièces
        </button>
      </div>

      <div class="users-toolbar">
        <div class="search-box">
          <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <input
            type="search"
            class="search-input"
            placeholder="Rechercher..."
            data-search-input
            aria-label="Rechercher"
          >
        </div>
      </div>

      <div class="table-wrapper" data-refs-table></div>

      <div class="users-pagination" data-pagination aria-label="Pagination">
        <div class="pagination-info">
          Page <strong>${this.page}</strong>
          sur <strong>${this.totalPages}</strong>
          (${this.total} total)
        </div>
        <div class="pagination-controls">
          <button
            class="btn btn-sm btn-secondary"
            data-page="prev"
            ${this.page <= 1 ? 'disabled' : ''}
            aria-label="Page précédente"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="15 18 9 12 15 6"></polyline>
            </svg>
          </button>
          <button
            class="btn btn-sm btn-secondary"
            data-page="next"
            ${this.page >= this.totalPages ? 'disabled' : ''}
            aria-label="Page suivante"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6"></polyline>
            </svg>
          </button>
        </div>
      </div>
    `;

    this.element.querySelectorAll('[data-ref-tab]').forEach(btn => {
      btn.addEventListener('click', () => this._switchTab(btn.dataset.refTab));
    });

    this.element.querySelector('[data-action="create-ref"]')?.addEventListener('click', () => this._openModal());

    this.element.querySelector('[data-search-input]')?.addEventListener('input', (e) => {
      clearTimeout(this._searchTimeout);
      this._searchTimeout = setTimeout(() => {
        this.search = e.target.value;
        this.page = 1;
        this.loadData();
      }, 300);
    });

    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => {
      if (this.page > 1) { this.page--; this.loadData(); }
    });

    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => {
      if (this.page < this.totalPages) { this.page++; this.loadData(); }
    });

    this.loadData();

    return this.element;
  }

  mount(container) {
    if (!this.element) this.render();
    container.innerHTML = '';
    container.appendChild(this.element);
    return this;
  }

  destroy() {
    this._authUnsubscribe?.();
    this.confirmDialog?.destroy?.();
    clearTimeout(this._searchTimeout);
    this._closeModal();
  }

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

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text ?? '';
    return div.innerHTML;
  }
}

export function createBuildingRefsPage(router) {
  return new BuildingRefsPage(router);
}
