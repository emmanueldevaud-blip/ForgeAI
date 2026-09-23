import { Table } from '../components/Table.js';
import { authStore } from '../stores/auth.js';
import {
  listOccupants,
  getOccupant,
  createOccupant,
  updateOccupant,
  deleteOccupant,
} from '../services/housingApi.js';

export class HousingOccupantsPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.items = [];
    this.total = 0;
    this.page = 1;
    this.pageSize = 20;
    this.totalPages = 1;
    this.sortBy = 'last_name';
    this.sortOrder = 'asc';
    this.search = '';
    this.table = null;
    this._authUnsubscribe = null;
  }

  async initialize() {
    this.table = new Table({
      columns: [
        { key: 'last_name', label: 'Nom', sortable: true },
        { key: 'first_name', label: 'Prenom', sortable: true },
        { key: 'email', label: 'Email', sortable: true },
        { key: 'phone', label: 'Telephone', sortable: false },
      ],
      actions: [
        {
          key: 'edit',
          label: 'Modifier',
          icon: 'edit',
          disabled: (item) => !authStore.hasPermission('housing.manage_occupants'),
        },
        {
          key: 'delete',
          label: 'Supprimer',
          icon: 'trash',
          variant: 'danger',
          disabled: (item) => !authStore.hasPermission('housing.manage_occupants'),
        },
      ],
      onAction: (action, item) => this._handleAction(action, item),
      emptyMessage: 'Aucun occupant trouve',
    });
    this._authUnsubscribe = authStore.subscribe(() => {
      if (this.element) this.renderTableState();
    });
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

      const response = await listOccupants(params);
      this.items = response.items || [];
      this.total = response.total || 0;
      this.totalPages = response.total_pages || 1;
      this.renderTableState();
    } catch (error) {
      console.error('Erreur chargement occupants:', error);
    }
  }

  renderTableState() {
    if (!this.element) return;

    const countEl = this.element.querySelector('[data-count]');
    if (countEl) countEl.textContent = `${this.total} occupant${this.total > 1 ? 's' : ''}`;

    const tableContainer = this.element.querySelector('[data-table]');
    if (tableContainer) {
      this.table.setData({
        items: this.items,
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
    if (pageInfo) pageInfo.textContent = `Page ${this.page} / ${this.totalPages}`;

    const prevBtn = this.element.querySelector('[data-page="prev"]');
    const nextBtn = this.element.querySelector('[data-page="next"]');
    if (prevBtn) prevBtn.disabled = this.page <= 1;
    if (nextBtn) nextBtn.disabled = this.page >= this.totalPages;
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content housing-page';
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>Occupants</h1>
          <p class="page-subtitle">Gestion des occupants</p>
        </div>
        <div class="page-header-right">
          ${authStore.hasPermission('housing.manage_occupants') ? '<button class="btn btn-primary" data-action="create">+ Nouvel occupant</button>' : ''}
        </div>
      </div>
      <div class="page-filters">
        <input type="text" class="form-input" placeholder="Rechercher..." data-filter="search" value="${this.search}">
      </div>
      <div class="page-info"><span data-count>${this.total} occupant${this.total > 1 ? 's' : ''}</span></div>
      <div data-table></div>
      <div class="pagination">
        <button class="btn btn-secondary" data-page="prev" ${this.page <= 1 ? 'disabled' : ''}>Precedent</button>
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

    this.element.querySelector('[data-action="create"]')?.addEventListener('click', () => this._showCreateModal());

    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => {
      if (this.page > 1) { this.page--; this.loadData(); }
    });
    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => {
      if (this.page < this.totalPages) { this.page++; this.loadData(); }
    });
  }

  async _handleAction(action, item) {
    if (action === 'edit') {
      await this._showEditModal(item);
    } else if (action === 'delete') {
      await this._deleteOccupant(item);
    }
  }

  async _showCreateModal() {
    await this._showOccupantModal(null);
  }

  async _showEditModal(item) {
    try {
      const full = await getOccupant(item.id);
      await this._showOccupantModal(full);
    } catch (e) {
      alert(e.message || 'Erreur lors du chargement');
    }
  }

  async _showOccupantModal(occupant) {
    const isEdit = !!occupant;
    const title = isEdit ? `Modifier: ${occupant.first_name} ${occupant.last_name}` : 'Nouvel occupant';

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal">
        <div class="modal-content">
          <div class="modal-header">
            <h2>${title}</h2>
            <button class="modal-close" data-action="close" aria-label="Fermer">&times;</button>
          </div>
          <div class="modal-body">
            <form data-form>
              <div class="form-row">
                <label><span>Prenom *</span><input name="first_name" value="${isEdit ? (occupant.first_name || '') : ''}" required maxlength="100"></label>
                <label><span>Nom *</span><input name="last_name" value="${isEdit ? (occupant.last_name || '') : ''}" required maxlength="100" style="text-transform:uppercase"></label>
              </div>
              <div class="form-row">
                <label><span>Email *</span><input type="email" name="email" value="${isEdit ? (occupant.email || '') : ''}" required maxlength="200"></label>
                <label><span>Telephone *</span><input name="phone" value="${isEdit ? (occupant.phone || '') : ''}" required maxlength="50"></label>
              </div>
            </form>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" data-action="close">Annuler</button>
            <button class="btn btn-primary" data-action="save">${isEdit ? 'Enregistrer' : 'Creer'}</button>
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
        data[k] = v;
      }
      if (!data.first_name || !data.last_name || !data.email || !data.phone) {
        alert('Les champs Nom, Prenom, Telephone et Email sont obligatoires');
        return;
      }
      try {
        if (isEdit) {
          await updateOccupant(occupant.id, data);
        } else {
          await createOccupant(data);
        }
        modal.remove();
        this.loadData();
        this._showToast(isEdit ? 'Occupant modifie' : 'Occupant cree');
      } catch (e) {
        alert(e.message || 'Erreur lors de la sauvegarde');
      }
    });
  }

  async _deleteOccupant(occupant) {
    if (!confirm(`Supprimer l'occupant ${occupant.first_name} ${occupant.last_name} ?`)) return;
    try {
      await deleteOccupant(occupant.id);
      await this.loadData();
      this._showToast('Occupant supprimé');
    } catch (e) {
      alert(e.message || 'Erreur lors de la suppression');
    }
  }

  _showToast(message) {
    const toast = document.createElement('div');
    toast.className = 'toast toast-success';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }

  destroy() {
    this._authUnsubscribe?.();
    if (this.element) this.element.remove();
    this.element = null;
  }
}

export function createHousingOccupantsPage(router) {
  return new HousingOccupantsPage(router);
}
