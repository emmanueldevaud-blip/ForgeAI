import { Table } from '../components/Table.js';
import { authStore } from '../stores/auth.js';
import {
  listVolunteers,
  createVolunteer,
  updateVolunteer,
  deleteVolunteer,
} from '../services/housingApi.js';
import {
  listAdministrativeCapabilities,
  listVolunteerCapabilities,
  assignVolunteerCapability,
  deleteVolunteerCapability,
} from '../services/administrativeApi.js';

const USAGE_LABELS = {
  cleaning: { label: 'Ménage', color: '#f59e0b' },
  maintenance: { label: 'Maintenance', color: '#3b82f6' },
};

function renderUsageTypes(value) {
  const usages = String(value || 'cleaning').split(',').filter(Boolean);
  return usages.map(usage => {
    const config = USAGE_LABELS[usage] || { label: usage, color: '#6b7280' };
    return `<span style="display:inline-block;padding:3px 8px;margin:2px;border-radius:999px;font-size:11px;background:${config.color}18;color:${config.color};border:1px solid ${config.color}33;">${config.label}</span>`;
  }).join('');
}

export class CleaningVolunteersPage {
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
    this.usageFilter = 'all';
    this.table = null;
    this._authUnsubscribe = null;
  }

  async initialize() {
    this.table = new Table({
      columns: [
        { key: 'last_name', label: 'Nom', sortable: true },
        { key: 'first_name', label: 'Prénom', sortable: true },
        {
          key: 'usage_type',
          label: 'Utilisé pour',
          sortable: true,
          render: (item) => renderUsageTypes(item.usage_type),
        },
        { key: 'phone', label: 'Téléphone', sortable: false },
        { key: 'email', label: 'Email', sortable: true },
      ],
      actions: [
        {
          key: 'edit',
          label: 'Modifier',
          icon: 'edit',
          disabled: (item) => !authStore.hasPermission('volunteers.manage'),
        },
        {
          key: 'delete',
          label: 'Supprimer',
          icon: 'trash',
          disabled: (item) => !authStore.hasPermission('volunteers.manage'),
        },
      ],
      onAction: (action, item) => this._handleAction(action, item),
      emptyMessage: 'Aucun volontaire trouvé',
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
      if (this.usageFilter !== 'all') params.usage_type = this.usageFilter;

      const response = await listVolunteers(params);
      this.items = Array.isArray(response) ? response : (response.items || []);
      this.total = Array.isArray(response) ? this.items.length : (response.total || 0);
      this.totalPages = Array.isArray(response) ? 1 : (response.total_pages || 1);
      this.renderTableState();
    } catch (error) {
      console.error('Erreur chargement volontaires:', error);
    }
  }

  renderTableState() {
    if (!this.element) return;

    const countEl = this.element.querySelector('[data-count]');
    if (countEl) countEl.textContent = `${this.total} volontaire${this.total > 1 ? 's' : ''}`;

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
          <h1>Volontaires</h1>
          <p class="page-subtitle">Gestion des volontaires ménage et maintenance</p>
        </div>
        <div class="page-header-right">
          <button class="btn btn-primary" data-action="create">+ Ajouter un volontaire</button>
        </div>
      </div>
      <div class="page-filters" style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
        <div style="display:flex;gap:0;border:1px solid var(--color-border-light);border-radius:var(--radius-md);overflow:hidden;">
          <button class="btn btn-sm" data-filter-usage="all" style="border:none;border-radius:0;padding:6px 14px;${this.usageFilter === 'all' ? 'background:var(--color-primary);color:white;' : 'background:var(--color-bg-secondary);'}">Tous</button>
          <button class="btn btn-sm" data-filter-usage="cleaning" style="border:none;border-radius:0;padding:6px 14px;border-left:1px solid var(--color-border-light);${this.usageFilter === 'cleaning' ? 'background:var(--color-primary);color:white;' : 'background:var(--color-bg-secondary);'}">🧹 Ménage</button>
          <button class="btn btn-sm" data-filter-usage="maintenance" style="border:none;border-radius:0;padding:6px 14px;border-left:1px solid var(--color-border-light);${this.usageFilter === 'maintenance' ? 'background:var(--color-primary);color:white;' : 'background:var(--color-bg-secondary);'}">🔧 Maintenance</button>
        </div>
        <input type="text" class="form-input" placeholder="Rechercher..." data-filter="search" value="${this.search}" style="max-width:280px;">
      </div>
      <div class="page-info"><span data-count>${this.total} volontaire${this.total > 1 ? 's' : ''}</span></div>
      <div data-table></div>
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

    this.element.querySelectorAll('[data-filter-usage]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.usageFilter = btn.dataset.filterUsage;
        this.page = 1;
        this._updateFilterButtons();
        this.loadData();
      });
    });

    this.element.querySelector('[data-action="create"]')?.addEventListener('click', () => {
      this._showFormModal();
    });

    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => {
      if (this.page > 1) { this.page--; this.loadData(); }
    });
    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => {
      if (this.page < this.totalPages) { this.page++; this.loadData(); }
    });
  }

  _updateFilterButtons() {
    if (!this.element) return;
    this.element.querySelectorAll('[data-filter-usage]').forEach(btn => {
      const isActive = btn.dataset.filterUsage === this.usageFilter;
      btn.style.background = isActive ? 'var(--color-primary)' : 'var(--color-bg-secondary)';
      btn.style.color = isActive ? 'white' : '';
    });
  }

  async _handleAction(action, item) {
    if (action === 'edit') {
      this._showFormModal(item);
    } else if (action === 'delete') {
      if (!confirm(`Supprimer le volontaire "${item.first_name} ${item.last_name}" ?`)) return;
      try {
        await deleteVolunteer(item.id);
        this.loadData();
      } catch (e) {
        alert('Erreur: ' + (e.message || 'Suppression échouée'));
      }
    }
  }

  _showFormModal(item = null) {
    const isEdit = !!item;
    const currentUsage = item?.usage_type || 'cleaning';
    const modal = document.createElement('div');
    modal.className = 'modal-overlay open';
    modal.style.cssText = 'position:fixed;inset:0;z-index:2000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.5);';
    modal.innerHTML = `
      <div class="modal-content" style="max-width:500px;width:95%;background:var(--color-bg-primary);border-radius:var(--radius-lg);">
        <div class="modal-header">
          <h2>${isEdit ? 'Modifier' : 'Ajouter'} un volontaire</h2>
          <button class="modal-close" data-dismiss>&times;</button>
        </div>
        <div class="modal-body">
          <div class="modal-form">
            <div class="form-row">
              <div class="form-group">
                <label>Nom <span style="color:red;">*</span></label>
                <input type="text" id="vol-lastname" class="form-control" value="${isEdit ? (item.last_name || '') : ''}" required>
              </div>
              <div class="form-group">
                <label>Prénom <span style="color:red;">*</span></label>
                <input type="text" id="vol-firstname" class="form-control" value="${isEdit ? (item.first_name || '') : ''}" required>
              </div>
            </div>
            <div class="form-group">
              <label>Préférence de communication</label>
              <select id="vol-communication-preference" class="form-control">
                <option value="both" ${!isEdit || item.communication_preference === 'both' ? 'selected' : ''}>E-mail et SMS</option>
                <option value="email" ${isEdit && item.communication_preference === 'email' ? 'selected' : ''}>E-mail uniquement</option>
                <option value="sms" ${isEdit && item.communication_preference === 'sms' ? 'selected' : ''}>SMS uniquement</option>
              </select>
            </div>
            <div class="form-group">
              <label>Utilisé pour <span style="color:red;">*</span></label>
              <div class="form-check form-check-flat form-check-inline">
                <input class="form-check-input" type="checkbox" id="vol-usage-cleaning" value="cleaning"${currentUsage === 'cleaning' || (currentUsage.includes && currentUsage.includes('cleaning')) ? ' checked' : ''}>
                <label class="form-check-label" for="vol-usage-cleaning">🧹 Ménage</label>
              </div>
              <div class="form-check form-check-flat form-check-inline">
                <input class="form-check-input" type="checkbox" id="vol-usage-maintenance" value="maintenance"${currentUsage === 'maintenance' || (currentUsage.includes && currentUsage.includes('maintenance')) ? ' checked' : ''}>
                <label class="form-check-label" for="vol-usage-maintenance">🔧 Maintenance</label>
              </div>
            </div>
            ${isEdit && authStore.hasPermission('administration.programs.view') ? `
            <div class="form-group">
              <label>Capacités administratives</label>
              <div data-volunteer-capabilities>Chargement...</div>
            </div>` : ''}
            <div class="form-row">
              <div class="form-group">
                <label>Téléphone</label>
                <input type="tel" id="vol-phone" class="form-control" value="${isEdit ? (item.phone || '') : ''}">
              </div>
              <div class="form-group">
                <label>Email</label>
                <input type="email" id="vol-email" class="form-control" value="${isEdit ? (item.email || '') : ''}">
              </div>
            </div>
          </div>
        </div>
        <div class="modal-footer" style="display:flex;gap:8px;justify-content:flex-end;">
          <button class="btn btn-secondary" data-dismiss>Annuler</button>
          <button class="btn btn-primary" data-action="save">Enregistrer</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    modal.querySelectorAll('[data-dismiss]').forEach(btn => btn.addEventListener('click', () => modal.remove()));
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    if (isEdit && authStore.hasPermission('administration.programs.view')) {
      this._loadVolunteerCapabilities(modal, item.id);
    }

    modal.querySelector('[data-action="save"]')?.addEventListener('click', async () => {
      const lastname = modal.querySelector('#vol-lastname').value.trim();
      const firstname = modal.querySelector('#vol-firstname').value.trim();
      let usageType = '';
      const volUsageCleaning = modal.querySelector('#vol-usage-cleaning');
      const volUsageMaintenance = modal.querySelector('#vol-usage-maintenance');
      if (volUsageCleaning.checked) usageType += 'cleaning';
      if (volUsageMaintenance.checked) usageType += usageType ? ',maintenance' : 'maintenance';
      const phone = modal.querySelector('#vol-phone').value.trim() || null;
      const email = modal.querySelector('#vol-email').value.trim() || null;
      const communicationPreference = modal.querySelector('#vol-communication-preference').value;

      if (!lastname || !firstname) {
        alert('Nom et prénom requis');
        return;
      }
      if (!usageType) {
        alert('Sélectionnez au moins un usage');
        return;
      }

      try {
        const data = { last_name: lastname, first_name: firstname, usage_type: usageType, phone, email, communication_preference: communicationPreference };
        if (isEdit) {
          await updateVolunteer(item.id, data);
        } else {
          await createVolunteer(data);
        }
        modal.remove();
        this.loadData();
      } catch (e) {
        alert('Erreur: ' + (e.message || 'Enregistrement échoué'));
      }
    });
  }

  async _loadVolunteerCapabilities(modal, volunteerId) {
    const container = modal.querySelector('[data-volunteer-capabilities]');
    if (!container) return;
    try {
      const [capabilities, assigned] = await Promise.all([
        listAdministrativeCapabilities(),
        listVolunteerCapabilities(volunteerId),
      ]);
      const assignedIds = new Set((assigned || []).map(item => item.capability_id));
      const canManage = authStore.hasPermission('administration.programs.manage');
      container.innerHTML = (capabilities || []).map(capability => `
        <label style="display:inline-flex;align-items:center;gap:6px;margin:0 12px 8px 0;">
          <input type="checkbox" data-volunteer-capability="${capability.id}" ${assignedIds.has(capability.id) ? 'checked' : ''} ${canManage ? '' : 'disabled'}>
          <span>${capability.name}</span>
        </label>`).join('') || '<span>Aucune capacité configurée.</span>';
      container.querySelectorAll('[data-volunteer-capability]').forEach(input => input.addEventListener('change', async () => {
        try {
          if (input.checked) await assignVolunteerCapability(volunteerId, { capability_id: Number(input.dataset.volunteerCapability) });
          else await deleteVolunteerCapability(volunteerId, Number(input.dataset.volunteerCapability));
        } catch (error) {
          input.checked = !input.checked;
          alert(error?.data?.detail || error.message || 'Modification de la capacité impossible');
        }
      }));
    } catch (error) {
      container.textContent = error?.data?.detail || 'Capacités indisponibles';
    }
  }

  destroy() {
    this._authUnsubscribe?.();
    if (this.element) this.element.remove();
    this.element = null;
  }
}

export function createCleaningVolunteersPage(router) {
  return new CleaningVolunteersPage(router);
}
