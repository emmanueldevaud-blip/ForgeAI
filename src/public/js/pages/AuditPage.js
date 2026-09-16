import { authStore } from '../stores/auth.js';
import { listAuditLogs } from '../services/adminApi.js';

export class AuditPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.loading = false;
    this.error = null;

    this.logs = [];
    this.total = 0;
    this.page = 1;
    this.pageSize = 50;
    this.totalPages = 1;
    this.sortBy = 'created_at';
    this.sortOrder = 'desc';

    this.filters = {
      username: '',
      action: '',
      module: '',
      object_type: '',
      status: '',
      start_date: '',
      end_date: '',
    };

    this.modules = [];
    this.actions = [];

    this._authUnsubscribe = null;
    this.selectedLog = null;
    this.detailModal = null;
  }

  async initialize() {
    this._authUnsubscribe = authStore.subscribe(() => {
      this.updateButtonVisibility();
    });

    await this.loadLogs();
  }

  async loadLogs() {
    this.loading = true;
    this.error = null;
    this.renderTableState();

    try {
      const params = {
        page: this.page,
        page_size: this.pageSize,
        sort_by: this.sortBy,
        sort_order: this.sortOrder,
      };

      if (this.filters.username) params.username = this.filters.username;
      if (this.filters.action) params.action = this.filters.action;
      if (this.filters.module) params.module = this.filters.module;
      if (this.filters.object_type) params.object_type = this.filters.object_type;
      if (this.filters.status) params.status = this.filters.status;
      if (this.filters.start_date) params.start_date = this.filters.start_date;
      if (this.filters.end_date) params.end_date = this.filters.end_date;

      const response = await listAuditLogs(params);

      this.logs = response.logs || [];
      this.total = response.total || 0;
      this.page = response.page || 1;
      this.pageSize = response.page_size || 50;
      this.totalPages = response.total_pages || 1;

      this.extractFilterOptions();
      this.error = null;
    } catch (error) {
      console.error('Erreur chargement audit:', error);
      this.error = error.message || 'Erreur lors du chargement des logs d\'audit';
      this.logs = [];
      this.total = 0;
      this.totalPages = 1;
    } finally {
      this.loading = false;
      this.renderTableState();
    }
  }

  extractFilterOptions() {
    const moduleSet = new Set();
    const actionSet = new Set();
    this.logs.forEach(log => {
      if (log.module) moduleSet.add(log.module);
      if (log.action) actionSet.add(log.action);
    });
    this.modules = Array.from(moduleSet).sort();
    this.actions = Array.from(actionSet).sort();
  }

  handleSearch(field, value) {
    this.filters[field] = value;
    this.page = 1;
    this.loadLogs();
  }

  handleDateFilter() {
    this.page = 1;
    this.loadLogs();
  }

  handleClearFilters() {
    this.filters = {
      username: '',
      action: '',
      module: '',
      object_type: '',
      status: '',
      start_date: '',
      end_date: '',
    };
    this.page = 1;
    this.loadLogs();
  }

  onPageChange(page) {
    if (page < 1 || page > this.totalPages) return;
    this.page = page;
    this.loadLogs();
  }

  onTabActivate() {
    this.loadLogs();
  }

  updateButtonVisibility() {
  }

  formatDateTime(dateStr) {
    if (!dateStr) return '-';
    const d = new Date(dateStr);
    return d.toLocaleString('fr-FR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  }

  formatAction(action) {
    const map = {
      login_success: 'Connexion',
      login_failed: 'Échec connexion',
      logout: 'Déconnexion',
      user_create: 'Création utilisateur',
      user_update: 'Modification utilisateur',
      user_toggle_active: 'Activation/Désactivation',
      user_deactivate: 'Désactivation',
      user_reset_password: 'Réinitialisation mot de passe',
      user_delete: 'Suppression utilisateur',
      user_groups_update: 'Mise à jour groupes',
      group_create: 'Création groupe',
      group_update: 'Modification groupe',
      group_delete: 'Suppression groupe',
      group_add_user: 'Ajout membre groupe',
      group_remove_user: 'Retrait membre groupe',
      group_role_assign: 'Assignation rôle groupe',
      group_role_remove: 'Retrait rôle groupe',
      role_create: 'Création rôle',
      role_update: 'Modification rôle',
      role_delete: 'Suppression rôle',
      role_permissions_replace: 'Remplacement permissions rôle',
      permission_create: 'Création permission',
      permission_update: 'Modification permission',
      permission_delete: 'Suppression permission',
      permission_assign: 'Assignation permission',
      permission_remove: 'Retrait permission',
      equipment_create: 'Création équipement',
      equipment_update: 'Modification équipement',
      equipment_delete: 'Suppression équipement',
      equipment_type_create: 'Création type équipement',
      equipment_type_update: 'Modification type équipement',
      equipment_type_delete: 'Suppression type équipement',
      building_create: 'Création bâtiment',
      building_update: 'Modification bâtiment',
      building_delete: 'Suppression bâtiment',
      site_create: 'Création site',
      site_update: 'Modification site',
      site_delete: 'Suppression site',
      level_create: 'Création niveau',
      level_update: 'Modification niveau',
      level_delete: 'Suppression niveau',
      room_create: 'Création local',
      room_update: 'Modification local',
      room_delete: 'Suppression local',
      ad_sync: 'Synchronisation AD',
    };
    return map[action] || action;
  }

  formatModule(module) {
    const map = {
      admin: 'Administration',
      auth: 'Authentification',
      buildings: 'Bâtiments',
      equipment: 'Équipements',
      audit: 'Audit',
      rbac: 'RBAC',
    };
    return map[module] || module;
  }

  getStatusBadge(status) {
    const cls = status === 'success' ? 'active' : 'error';
    const label = status === 'success' ? 'Succès' : 'Erreur';
    return `<span class="status-badge ${cls}">${label}</span>`;
  }

  showDetail(log) {
    this.selectedLog = log;
    this.openDetailModal();
  }

  openDetailModal() {
    const log = this.selectedLog;
    if (!log) return;

    let existing = this.element.querySelector('.modal-overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal" style="max-width:700px;">
        <div class="modal-content">
          <div class="modal-header">
            <h2>Détail de l'entrée d'audit #${log.id}</h2>
            <button class="modal-close" data-close>&times;</button>
          </div>
          <div class="modal-body" style="font-size:0.9em;">
            <table style="width:100%;border-collapse:collapse;">
              <tr><td style="padding:6px 12px;font-weight:600;width:140px;">Date</td><td style="padding:6px 12px;">${this.formatDateTime(log.created_at)}</td></tr>
              <tr><td style="padding:6px 12px;font-weight:600;">Utilisateur</td><td style="padding:6px 12px;">${this._escapeHtml(log.username)}</td></tr>
              <tr><td style="padding:6px 12px;font-weight:600;">Action</td><td style="padding:6px 12px;">${this.formatAction(log.action)}</td></tr>
              <tr><td style="padding:6px 12px;font-weight:600;">Module</td><td style="padding:6px 12px;">${this.formatModule(log.module)}</td></tr>
              <tr><td style="padding:6px 12px;font-weight:600;">Type objet</td><td style="padding:6px 12px;">${log.object_type || '-'}</td></tr>
              <tr><td style="padding:6px 12px;font-weight:600;">ID objet</td><td style="padding:6px 12px;">${log.object_id || '-'}</td></tr>
              <tr><td style="padding:6px 12px;font-weight:600;">Description</td><td style="padding:6px 12px;">${log.object_repr ? this._escapeHtml(log.object_repr) : '-'}</td></tr>
              <tr><td style="padding:6px 12px;font-weight:600;">Statut</td><td style="padding:6px 12px;">${this.getStatusBadge(log.status)}</td></tr>
              <tr><td style="padding:6px 12px;font-weight:600;">IP</td><td style="padding:6px 12px;">${log.ip_address || '-'}</td></tr>
              <tr><td style="padding:6px 12px;font-weight:600;">Request ID</td><td style="padding:6px 12px;font-family:monospace;font-size:0.85em;">${log.request_id || '-'}</td></tr>
              ${log.error_message ? `<tr><td style="padding:6px 12px;font-weight:600;color:var(--color-danger);">Erreur</td><td style="padding:6px 12px;">${this._escapeHtml(log.error_message)}</td></tr>` : ''}
            </table>
            ${log.old_values && Object.keys(log.old_values).length > 0 ? `
              <div style="margin-top:16px;">
                <h4 style="margin-bottom:8px;">Anciennes valeurs</h4>
                <pre style="background:var(--color-bg-secondary);padding:12px;border-radius:6px;overflow-x:auto;font-size:0.85em;max-height:200px;overflow-y:auto;">${JSON.stringify(log.old_values, null, 2)}</pre>
              </div>
            ` : ''}
            ${log.new_values && Object.keys(log.new_values).length > 0 ? `
              <div style="margin-top:16px;">
                <h4 style="margin-bottom:8px;">Nouvelles valeurs</h4>
                <pre style="background:var(--color-bg-secondary);padding:12px;border-radius:6px;overflow-x:auto;font-size:0.85em;max-height:200px;overflow-y:auto;">${JSON.stringify(log.new_values, null, 2)}</pre>
              </div>
            ` : ''}
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" data-close>Fermer</button>
          </div>
        </div>
      </div>
    `;

    this.element.appendChild(overlay);

    overlay.querySelectorAll('[data-close]').forEach(btn => {
      btn.addEventListener('click', () => overlay.remove());
    });

    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.remove();
    });
  }

  renderTableState() {
    if (!this.element) return;

    const tableContainer = this.element.querySelector('[data-audit-table]');
    if (!tableContainer) return;

    const countElement = this.element.querySelector('.users-count');
    if (countElement) {
      countElement.textContent = `${this.total} entrée${this.total > 1 ? 's' : ''}`;
    }

    const paginationInfo = this.element.querySelector('.pagination-info');
    if (paginationInfo) {
      paginationInfo.innerHTML = `
        Page <strong>${this.page}</strong>
        sur <strong>${this.totalPages}</strong>
        (${this.total} total)
      `;
    }

    const prevButton = this.element.querySelector('[data-page="prev"]');
    const nextButton = this.element.querySelector('[data-page="next"]');

    if (prevButton) prevButton.disabled = this.page <= 1;
    if (nextButton) nextButton.disabled = this.page >= this.totalPages;

    if (this.loading) {
      tableContainer.innerHTML = `
        <div class="table-loading">
          <div class="spinner"></div>
          <p>Chargement...</p>
        </div>
      `;
      return;
    }

    if (this.error) {
      tableContainer.innerHTML = `
        <div class="table-error">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          <h3>Erreur</h3>
          <p>${this._escapeHtml(this.error)}</p>
          <button class="btn btn-primary" data-action="retry">Réessayer</button>
        </div>
      `;
      tableContainer.querySelector('[data-action="retry"]')?.addEventListener('click', () => this.loadLogs());
      return;
    }

    if (this.logs.length === 0) {
      tableContainer.innerHTML = `
        <div class="table-empty">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
          </svg>
          <h3>Aucune entrée d'audit</h3>
          <p>Aucun log d'audit ne correspond aux filtres sélectionnés.</p>
        </div>
      `;
      return;
    }

    const rows = this.logs.map(log => `
      <tr class="audit-row" data-log-id="${log.id}" style="cursor:pointer;">
        <td style="font-family:monospace;font-size:0.85em;color:var(--color-text-secondary);">${log.id}</td>
        <td>${this.formatDateTime(log.created_at)}</td>
        <td><strong>${this._escapeHtml(log.username)}</strong></td>
        <td>${this.formatAction(log.action)}</td>
        <td>${this.formatModule(log.module)}</td>
        <td>${log.object_type || '-'}</td>
        <td>${log.object_id || '-'}</td>
        <td>${this.getStatusBadge(log.status)}</td>
        <td>${log.ip_address || '-'}</td>
      </tr>
    `).join('');

    tableContainer.innerHTML = `
      <div class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width:60px;">ID</th>
              <th style="width:160px;">Date</th>
              <th style="width:120px;">Utilisateur</th>
              <th style="width:160px;">Action</th>
              <th style="width:100px;">Module</th>
              <th style="width:100px;">Type</th>
              <th style="width:80px;">Objet ID</th>
              <th style="width:80px;">Statut</th>
              <th style="width:120px;">IP</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;

    tableContainer.querySelectorAll('.audit-row').forEach(row => {
      row.addEventListener('click', () => {
        const logId = parseInt(row.dataset.logId);
        const log = this.logs.find(l => l.id === logId);
        if (log) this.showDetail(log);
      });
    });
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'users-page';

    this.element.innerHTML = `
      <div class="users-header">
        <div class="users-title-area">
          <h1 class="users-title">Journal d'audit</h1>
          <p class="users-count" aria-live="polite">
            ${this.total} entrée${this.total > 1 ? 's' : ''}
          </p>
        </div>
      </div>

      <div class="users-toolbar" style="display:flex;flex-wrap:wrap;gap:8px;padding:12px 0;align-items:center;">
        <input type="text" class="form-input" placeholder="Utilisateur..." data-filter="username" value="${this._escapeHtml(this.filters.username)}" style="width:140px;" />
        <select class="form-select" data-filter="module" style="width:140px;">
          <option value="">Tous modules</option>
        </select>
        <select class="form-select" data-filter="action" style="width:180px;">
          <option value="">Toutes actions</option>
        </select>
        <select class="form-select" data-filter="status" style="width:120px;">
          <option value="">Tous statuts</option>
          <option value="success">Succès</option>
          <option value="error">Erreur</option>
        </select>
        <input type="datetime-local" class="form-input" data-filter="start_date" title="Date début" style="width:180px;" />
        <input type="datetime-local" class="form-input" data-filter="end_date" title="Date fin" style="width:180px;" />
        <button class="btn btn-sm btn-secondary" data-action="clear-filters">Effacer</button>
      </div>

      <div class="table-wrapper" data-audit-table></div>

      <div class="users-pagination" data-pagination aria-label="Pagination">
        <div class="pagination-info">
          Page <strong>${this.page}</strong> sur <strong>${this.totalPages}</strong> (${this.total} total)
        </div>
        <div class="pagination-controls">
          <button class="btn btn-sm btn-secondary" data-page="prev" ${this.page <= 1 ? 'disabled' : ''} aria-label="Page précédente">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="15 18 9 12 15 6"></polyline>
            </svg>
          </button>
          <button class="btn btn-sm btn-secondary" data-page="next" ${this.page >= this.totalPages ? 'disabled' : ''} aria-label="Page suivante">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6"></polyline>
            </svg>
          </button>
        </div>
      </div>
    `;

    this.element.querySelector('[data-filter="username"]')?.addEventListener('change', (e) => this.handleSearch('username', e.target.value));
    this.element.querySelector('[data-filter="module"]')?.addEventListener('change', (e) => this.handleSearch('module', e.target.value));
    this.element.querySelector('[data-filter="action"]')?.addEventListener('change', (e) => this.handleSearch('action', e.target.value));
    this.element.querySelector('[data-filter="status"]')?.addEventListener('change', (e) => this.handleSearch('status', e.target.value));
    this.element.querySelector('[data-filter="start_date"]')?.addEventListener('change', () => this.handleDateFilter());
    this.element.querySelector('[data-filter="end_date"]')?.addEventListener('change', () => this.handleDateFilter());
    this.element.querySelector('[data-action="clear-filters"]')?.addEventListener('click', () => this.handleClearFilters());

    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => this.onPageChange(this.page - 1));
    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => this.onPageChange(this.page + 1));

    this.renderTableState();
    this.populateFilterDropdowns();

    return this.element;
  }

  populateFilterDropdowns() {
    if (this.modules.length > 0) {
      const moduleSelect = this.element?.querySelector('[data-filter="module"]');
      if (moduleSelect) {
        const current = this.filters.module;
        moduleSelect.innerHTML = `<option value="">Tous modules</option>` +
          this.modules.map(m => `<option value="${m}" ${m === current ? 'selected' : ''}>${this.formatModule(m)}</option>`).join('');
      }
    }

    if (this.actions.length > 0) {
      const actionSelect = this.element?.querySelector('[data-filter="action"]');
      if (actionSelect) {
        const current = this.filters.action;
        actionSelect.innerHTML = `<option value="">Toutes actions</option>` +
          this.actions.map(a => `<option value="${a}" ${a === current ? 'selected' : ''}>${this.formatAction(a)}</option>`).join('');
      }
    }
  }

  mount(container) {
    if (!this.element) this.render();
    container.innerHTML = '';
    container.appendChild(this.element);
    return this;
  }

  destroy() {
    this._authUnsubscribe?.();
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}

export function createAuditPage(router) {
  return new AuditPage(router);
}
