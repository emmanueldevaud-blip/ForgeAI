import { Table } from '../components/Table.js';
import { authStore } from '../stores/auth.js';
import {
  listEquipmentTypes,
  createEquipmentType,
  updateEquipmentType,
} from '../services/equipmentApi.js';

export class EquipmentRefsPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.equipmentTypes = [];
    this.total = 0;
    this.page = 1;
    this.pageSize = 20;
    this.totalPages = 1;
    this.sortBy = 'sort_order';
    this.sortOrder = 'asc';
    this.search = '';
    this.table = null;
    this._authUnsubscribe = null;
  }

  async initialize() {
    this.table = new Table({
      columns: [
        { key: 'code', label: 'Code', sortable: true },
        { key: 'name', label: 'Nom', sortable: true },
        { key: 'sort_order', label: 'Ordre', sortable: true },
        {
          key: 'is_active',
          label: 'Statut',
          sortable: true,
          render: (item) => item.is_active
            ? '<span class="status-badge active">Actif</span>'
            : '<span class="status-badge inactive">Inactif</span>',
        },
      ],
      actions: [
        {
          key: 'edit',
          label: 'Modifier',
          icon: 'edit',
          disabled: () => !authStore.hasPermission('equipment.manage_referentials'),
        },
      ],
      onAction: (action, item) => this._handleAction(action, item),
      emptyMessage: 'Aucun type d\'équipement trouvé',
    });

    this._authUnsubscribe = authStore.subscribe(() => {
      if (this.element) this.renderTableState();
    });

    await this.loadData();
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

      const response = await listEquipmentTypes(params);
      this.equipmentTypes = response.items || [];
      this.total = response.total || 0;
      this.totalPages = response.total_pages || 1;
      this.renderTableState();
    } catch (error) {
      console.error('Erreur chargement types:', error);
    }
  }

  renderTableState() {
    if (!this.element) return;

    const countEl = this.element.querySelector('[data-type-count]');
    if (countEl) {
      countEl.textContent = `${this.total} type${this.total > 1 ? 's' : ''}`;
    }

    const tableContainer = this.element.querySelector('[data-type-table]');
    if (tableContainer) {
      this.table.setData({
        items: this.equipmentTypes,
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
          <h1>Types d'équipements</h1>
          <p class="page-subtitle">Référentiel des types d'équipements</p>
        </div>
        <div class="page-header-right">
          ${authStore.hasPermission('equipment.manage_referentials') ? '<button class="btn btn-primary" data-action="create">+ Nouveau type</button>' : ''}
        </div>
      </div>

      <div class="page-filters">
        <div class="filter-group">
          <input type="text" class="form-input" placeholder="Rechercher..." data-filter="search" value="${this.search}">
        </div>
      </div>

      <div class="page-info">
        <span data-type-count>${this.total} type${this.total > 1 ? 's' : ''}</span>
      </div>

      <div data-type-table></div>

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

    const createBtn = this.element.querySelector('[data-action="create"]');
    if (createBtn) {
      createBtn.addEventListener('click', () => this._showModal(null));
    }

    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => {
      if (this.page > 1) { this.page--; this.loadData(); }
    });

    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => {
      if (this.page < this.totalPages) { this.page++; this.loadData(); }
    });
  }

  async _handleAction(action, item) {
    if (action === 'edit') {
      await this._showModal(item);
    }
  }

  async _showModal(item) {
    const isEdit = !!item;
    const title = isEdit ? `Modifier: ${item.name}` : 'Nouveau type d\'équipement';

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
            <form data-type-form>
            ${isEdit ? `
            <label><span>Code</span><input name="code" value="${item.code}" readonly></label>
            ` : ''}
            <label><span>Nom *</span><input name="name" value="${isEdit ? item.name : ''}" required maxlength="100"></label>
            <label><span>Description</span><textarea name="description" rows="3">${isEdit ? (item.description || '') : ''}</textarea></label>
            <label><span>Ordre d'affichage</span><input type="number" name="sort_order" min="0" value="${isEdit ? item.sort_order : 0}"></label>
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

      try {
        if (isEdit) {
          await updateEquipmentType(item.id, data);
        } else {
          await createEquipmentType(data);
        }
        modal.remove();
        this.loadData();
        this._showToast(isEdit ? 'Type modifié' : 'Type créé');
      } catch (error) {
        alert(error.message || 'Erreur lors de la sauvegarde');
      }
    });
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

export function createEquipmentRefsPage(router) {
  return new EquipmentRefsPage(router);
}
