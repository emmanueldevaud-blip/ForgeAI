import { Table } from '../components/Table.js';
import { authStore } from '../stores/auth.js';
import { listHousings, updateHousing } from '../services/housingApi.js';

const CLEANING_STATUSES = [
  { value: 'to_clean', label: 'A nettoyer', color: '#ef4444' },
  { value: 'cleaning', label: 'En cours', color: '#f59e0b' },
  { value: 'to_check', label: 'A verifier', color: '#8b5cf6' },
  { value: 'checked', label: 'Verifie', color: '#06b6d4' },
  { value: 'clean', label: 'Propre', color: '#10b981' },
];

function getCleaningLabel(s) {
  return (CLEANING_STATUSES.find(x => x.value === s) || {}).label || s;
}

function getCleaningColor(s) {
  return (CLEANING_STATUSES.find(x => x.value === s) || {}).color || '#6b7280';
}

function formatDate(d) {
  return d ? new Date(d).toLocaleDateString('fr-FR') : '-';
}

export class HousingCleaningPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.items = [];
    this.total = 0;
    this.page = 1;
    this.pageSize = 20;
    this.totalPages = 1;
    this.sortBy = 'name';
    this.sortOrder = 'asc';
    this.search = '';
    this.filters = { cleaning_status: '' };
    this.table = null;
    this._authUnsubscribe = null;
  }

  async initialize() {
    this.table = new Table({
      columns: [
        { key: 'name', label: 'Logement', sortable: true },
        {
          key: 'cleaning_status',
          label: 'Statut nettoyage',
          sortable: true,
          render: (item) => {
            const s = item.cleaning_status || 'to_clean';
            return `<span class="status-badge" style="background:${getCleaningColor(s)}22;color:${getCleaningColor(s)};border:1px solid ${getCleaningColor(s)}44">${getCleaningLabel(s)}</span>`;
          },
        },
        {
          key: 'last_departure',
          label: 'Dernier depart',
          sortable: true,
          render: (item) => formatDate(item.last_departure_date),
        },
        {
          key: 'housing_type',
          label: 'Type',
          sortable: false,
          render: (item) => item.housing_type || '-',
        },
      ],
      actions: [
        {
          key: 'change_status',
          label: 'Changer statut',
          icon: 'edit',
          disabled: (item) => !authStore.hasPermission('housing.update'),
        },
      ],
      onAction: (action, item) => this._handleAction(action, item),
      emptyMessage: 'Aucun logement trouve',
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
      if (this.filters.cleaning_status) params.cleaning_status = this.filters.cleaning_status;

      const response = await listHousings(params);
      this.items = response.items || [];
      this.total = response.total || 0;
      this.totalPages = response.total_pages || 1;
      this.renderTableState();
    } catch (error) {
      console.error('Erreur chargement logements:', error);
    }
  }

  renderTableState() {
    if (!this.element) return;

    const countEl = this.element.querySelector('[data-count]');
    if (countEl) countEl.textContent = `${this.total} logement${this.total > 1 ? 's' : ''}`;

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
    this.element.className = 'page-content';
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>Nettoyage</h1>
          <p class="page-subtitle">Gestion de l'etat de nettoyage des logements</p>
        </div>
      </div>
      <div class="page-filters">
        <input type="text" class="form-input" placeholder="Rechercher..." data-filter="search" value="${this.search}">
        <select class="form-select" data-filter="cleaning_status">
          <option value="">Tous les statuts</option>
          ${CLEANING_STATUSES.map(s => `<option value="${s.value}" ${this.filters.cleaning_status === s.value ? 'selected' : ''}>${s.label}</option>`).join('')}
        </select>
      </div>
      <div class="page-info"><span data-count>${this.total} logement${this.total > 1 ? 's' : ''}</span></div>
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

    this.element.querySelectorAll('.form-select[data-filter]').forEach(select => {
      select.addEventListener('change', (e) => {
        this.filters[select.dataset.filter] = e.target.value;
        this.page = 1;
        this.loadData();
      });
    });

    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => {
      if (this.page > 1) { this.page--; this.loadData(); }
    });
    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => {
      if (this.page < this.totalPages) { this.page++; this.loadData(); }
    });
  }

  async _handleAction(action, item) {
    if (action === 'change_status') {
      this._showChangeStatusModal(item);
    }
  }

  _showChangeStatusModal(item) {
    const currentStatus = item.cleaning_status || 'to_clean';
    const nextStatuses = CLEANING_STATUSES.filter(s => s.value !== currentStatus);

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal">
        <div class="modal-content">
          <div class="modal-header">
            <h2>Changer le statut - ${item.name}</h2>
            <button class="modal-close" data-action="close">&times;</button>
          </div>
          <div class="modal-body">
            <p>Statut actuel : <strong>${getCleaningLabel(currentStatus)}</strong></p>
            <div class="form-row">
              <label><span>Nouveau statut</span>
                <select data-new-status>
                  ${nextStatuses.map(s => `<option value="${s.value}">${s.label}</option>`).join('')}
                </select>
              </label>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" data-action="close">Annuler</button>
            <button class="btn btn-primary" data-action="save">Enregistrer</button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    modal.querySelector('[data-action="close"]')?.addEventListener('click', () => modal.remove());
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });

    modal.querySelector('[data-action="save"]')?.addEventListener('click', async () => {
      const newStatus = modal.querySelector('[data-new-status]').value;
      try {
        await updateHousing(item.id, { cleaning_status: newStatus });
        modal.remove();
        this.loadData();
        this._showToast('Statut mis a jour');
      } catch (e) {
        alert(e.message || 'Erreur lors de la mise a jour');
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

  destroy() {
    this._authUnsubscribe?.();
    if (this.element) this.element.remove();
    this.element = null;
  }
}

export function createHousingCleaningPage(router) {
  return new HousingCleaningPage(router);
}
