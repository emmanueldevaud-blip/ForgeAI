import { Table } from '../components/Table.js';
import { authStore } from '../stores/auth.js';
import {
  listUnavailabilities,
  createUnavailability,
  deleteUnavailability,
  listHousings,
} from '../services/housingApi.js';

const REASONS = [
  { value: 'maintenance', label: 'Maintenance' },
  { value: 'works', label: 'Travaux' },
  { value: 'breakdown', label: 'Panne' },
  { value: 'administrative', label: 'Administratif' },
  { value: 'other', label: 'Autre' },
];

function getReasonLabel(r) {
  return (REASONS.find(x => x.value === r) || {}).label || r;
}

function formatDate(d) {
  return d ? new Date(d).toLocaleDateString('fr-FR') : '-';
}

export class HousingUnavailabilitiesPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.items = [];
    this.housings = [];
    this.total = 0;
    this.page = 1;
    this.pageSize = 20;
    this.totalPages = 1;
    this.sortBy = 'start_date';
    this.sortOrder = 'desc';
    this.filters = {
      housing_id: '',
      reason: '',
      date_from: '',
      date_to: '',
    };
    this.table = null;
    this._authUnsubscribe = null;
  }

  async initialize() {
    this.table = new Table({
      columns: [
        {
          key: 'housing',
          label: 'Logement',
          sortable: false,
          render: (item) => item.housing ? item.housing.name : '-',
        },
        {
          key: 'start_date',
          label: 'Date debut',
          sortable: true,
          render: (item) => formatDate(item.start_date),
        },
        {
          key: 'end_date',
          label: 'Date fin',
          sortable: true,
          render: (item) => formatDate(item.end_date),
        },
        {
          key: 'reason',
          label: 'Motif',
          sortable: true,
          render: (item) => `<span class="status-badge status-inactive">${getReasonLabel(item.reason)}</span>`,
        },
        { key: 'comment', label: 'Commentaire', sortable: false },
      ],
      actions: [
        {
          key: 'delete',
          label: 'Supprimer',
          icon: 'trash',
          disabled: (item) => !authStore.hasPermission('housing.delete'),
        },
      ],
      onAction: (action, item) => this._handleAction(action, item),
      emptyMessage: 'Aucune indisponibilite trouvee',
    });
    this._authUnsubscribe = authStore.subscribe(() => {
      if (this.element) this.renderTableState();
    });
    await this._loadHousings();
  }

  async _loadHousings() {
    try {
      const resp = await listHousings({ page_size: 1000, is_active: true });
      this.housings = resp.items || [];
    } catch (e) {
      this.housings = [];
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
      if (this.filters.housing_id) params.housing_id = this.filters.housing_id;
      if (this.filters.reason) params.reason = this.filters.reason;
      if (this.filters.date_from) params.date_from = this.filters.date_from;
      if (this.filters.date_to) params.date_to = this.filters.date_to;

      const response = await listUnavailabilities(params);
      this.items = response.items || [];
      this.total = response.total || 0;
      this.totalPages = response.total_pages || 1;
      this.renderTableState();
    } catch (error) {
      console.error('Erreur chargement indisponibilites:', error);
    }
  }

  renderTableState() {
    if (!this.element) return;

    const countEl = this.element.querySelector('[data-count]');
    if (countEl) countEl.textContent = `${this.total} indisponibilite${this.total > 1 ? 's' : ''}`;

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
          <h1>Indisponibilites</h1>
          <p class="page-subtitle">Gestion des periodes d'indisponibilite</p>
        </div>
        <div class="page-header-right">
          ${authStore.hasPermission('housing.create') ? '<button class="btn btn-primary" data-action="create">+ Nouvelle indisponibilite</button>' : ''}
        </div>
      </div>
      <div class="page-filters">
        <select class="form-select" data-filter="housing_id">
          <option value="">Tous les logements</option>
          ${this.housings.map(h => `<option value="${h.id}" ${this.filters.housing_id == h.id ? 'selected' : ''}>${h.name}</option>`).join('')}
        </select>
        <select class="form-select" data-filter="reason">
          <option value="">Tous les motifs</option>
          ${REASONS.map(r => `<option value="${r.value}" ${this.filters.reason === r.value ? 'selected' : ''}>${r.label}</option>`).join('')}
        </select>
        <input type="date" class="form-input" data-filter="date_from" value="${this.filters.date_from}" title="Date debut">
        <input type="date" class="form-input" data-filter="date_to" value="${this.filters.date_to}" title="Date fin">
      </div>
      <div class="page-info"><span data-count>${this.total} indisponibilite${this.total > 1 ? 's' : ''}</span></div>
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
    this.element.querySelectorAll('.form-select[data-filter], .form-input[data-filter]').forEach(el => {
      el.addEventListener('change', (e) => {
        this.filters[el.dataset.filter] = e.target.value;
        this.page = 1;
        this.loadData();
      });
    });

    this.element.querySelector('[data-action="create"]')?.addEventListener('click', () => this._showCreateModal());

    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => {
      if (this.page > 1) { this.page--; this.loadData(); }
    });
    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => {
      if (this.page < this.totalPages) { this.page++; this.loadData(); }
    });
  }

  async _handleAction(action, item) {
    if (action === 'delete') {
      await this._delete(item);
    }
  }

  async _showCreateModal() {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal">
        <div class="modal-content">
          <div class="modal-header">
            <h2>Nouvelle indisponibilite</h2>
            <button class="modal-close" data-action="close">&times;</button>
          </div>
          <div class="modal-body">
            <form data-form>
              <div class="form-row">
                <label><span>Logement *</span>
                  <select name="housing_id" required>
                    <option value="">-- Selectionner --</option>
                    ${this.housings.map(h => `<option value="${h.id}">${h.name}</option>`).join('')}
                  </select>
                </label>
              </div>
              <div class="form-row">
                <label><span>Date debut *</span><input type="date" name="start_date" required></label>
                <label><span>Date fin *</span><input type="date" name="end_date" required></label>
              </div>
              <div class="form-row">
                <label><span>Motif *</span>
                  <select name="reason" required>
                    <option value="">-- Selectionner --</option>
                    ${REASONS.map(r => `<option value="${r.value}">${r.label}</option>`).join('')}
                  </select>
                </label>
              </div>
              <div class="form-row">
                <label><span>Commentaire</span><textarea name="comment" rows="3"></textarea></label>
              </div>
            </form>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" data-action="close">Annuler</button>
            <button class="btn btn-primary" data-action="save">Creer</button>
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
        if (k === 'housing_id') data[k] = parseInt(v, 10);
        else data[k] = v;
      }
      if (!data.housing_id || !data.start_date || !data.end_date || !data.reason) {
        alert('Les champs Logement, Date debut, Date fin et Motif sont obligatoires');
        return;
      }
      if (data.end_date < data.start_date) {
        alert('La date de fin doit etre posterieure a la date de debut');
        return;
      }
      try {
        await createUnavailability(data);
        modal.remove();
        this.loadData();
        this._showToast('Indisponibilite creee');
      } catch (e) {
        alert(e.message || 'Erreur lors de la creation');
      }
    });
  }

  async _delete(item) {
    if (!confirm(`Supprimer cette indisponibilite du ${formatDate(item.start_date)} au ${formatDate(item.end_date)} ?`)) return;
    try {
      await deleteUnavailability(item.id);
      this.loadData();
      this._showToast('Indisponibilite supprimee');
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

export function createHousingUnavailabilitiesPage(router) {
  return new HousingUnavailabilitiesPage(router);
}
