import { authStore } from '../stores/auth.js';
import { listAuditLogs, getAuditFilterValues } from '../services/adminApi.js';

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

    this.filterValues = { modules: [], actions: [], usernames: [] };
    this._authUnsubscribe = null;
    this.selectedLog = null;
    this._searchTimeout = null;
  }

  async initialize() {
    this._authUnsubscribe = authStore.subscribe(() => {
      this.updateButtonVisibility();
    });

    try {
      this.filterValues = await getAuditFilterValues();
    } catch (e) {
      console.warn('Erreur chargement filtres audit:', e);
    }

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
      this.updatePagination();
      this.updateCount();
    }
  }

  handleSearch(field, value) {
    this.filters[field] = value;
    this.page = 1;
    if (this._searchTimeout) clearTimeout(this._searchTimeout);
    this._searchTimeout = setTimeout(() => this.loadLogs(), 300);
  }

  handleSelectFilter(field, value) {
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
    this._populateFilterValues();
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

  formatDateShort(dateStr) {
    if (!dateStr) return '-';
    const d = new Date(dateStr);
    return d.toLocaleString('fr-FR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
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
      user_reset_password: 'Réinitialisation MDP',
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
      role_permissions_replace: 'Remplacement permissions',
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
      room_create: 'Création local',
      room_update: 'Modification local',
      room_delete: 'Suppression local',
      housing_create: 'Création hébergement',
      housing_update: 'Modification hébergement',
      housing_delete: 'Suppression hébergement',
      maintenance_request_create: 'Création demande',
      maintenance_request_update: 'Modification demande',
      maintenance_request_delete: 'Suppression demande',
      maintenance_intervention_create: 'Création intervention',
      maintenance_intervention_update: 'Modification intervention',
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
      housing: 'Hébergements',
      maintenance: 'Maintenance',
      audit: 'Audit',
      rbac: 'RBAC',
      ai: 'Assistant IA',
    };
    return map[module] || module;
  }

  getStatusBadge(status) {
    const cls = status === 'success' ? 'badge-active' : 'badge-inactive';
    const label = status === 'success' ? 'Succès' : 'Erreur';
    return `<span class="badge ${cls}">${label}</span>`;
  }

  getActionBadgeClass(action) {
    if (action.startsWith('login') || action === 'logout') return 'badge-default';
    if (action.includes('create')) return 'badge-active';
    if (action.includes('delete')) return 'badge-inactive';
    if (action.includes('update') || action.includes('toggle') || action.includes('reset')) return 'badge-warning';
    return 'badge-default';
  }

  showDetail(log) {
    this.selectedLog = log;
    this.openDetailModal();
  }

  openDetailModal() {
    const log = this.selectedLog;
    if (!log) return;

    let existing = document.querySelector('.modal-overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal" style="max-width:720px;">
        <div class="modal-content">
          <div class="modal-header">
            <h2 class="modal-title">Détail de l'entrée d'audit #${log.id}</h2>
            <button class="modal-close" data-close>&times;</button>
          </div>
          <div class="modal-body">
            <div class="audit-detail-grid">
              <div class="audit-detail-item">
                <span class="audit-detail-label">Date</span>
                <span class="audit-detail-value">${this.formatDateTime(log.created_at)}</span>
              </div>
              <div class="audit-detail-item">
                <span class="audit-detail-label">Utilisateur</span>
                <span class="audit-detail-value"><strong>${this._escapeHtml(log.username)}</strong></span>
              </div>
              <div class="audit-detail-item">
                <span class="audit-detail-label">Action</span>
                <span class="audit-detail-value"><span class="badge ${this.getActionBadgeClass(log.action)}">${this.formatAction(log.action)}</span></span>
              </div>
              <div class="audit-detail-item">
                <span class="audit-detail-label">Module</span>
                <span class="audit-detail-value">${this.formatModule(log.module)}</span>
              </div>
              <div class="audit-detail-item">
                <span class="audit-detail-label">Type objet</span>
                <span class="audit-detail-value">${log.object_type || '-'}</span>
              </div>
              <div class="audit-detail-item">
                <span class="audit-detail-label">ID objet</span>
                <span class="audit-detail-value" style="font-family:monospace;">${log.object_id || '-'}</span>
              </div>
              <div class="audit-detail-item" style="grid-column:1/-1;">
                <span class="audit-detail-label">Description</span>
                <span class="audit-detail-value">${log.object_repr ? this._escapeHtml(log.object_repr) : '-'}</span>
              </div>
              <div class="audit-detail-item">
                <span class="audit-detail-label">Statut</span>
                <span class="audit-detail-value">${this.getStatusBadge(log.status)}</span>
              </div>
              <div class="audit-detail-item">
                <span class="audit-detail-label">Adresse IP</span>
                <span class="audit-detail-value" style="font-family:monospace;">${log.ip_address || '-'}</span>
              </div>
              <div class="audit-detail-item" style="grid-column:1/-1;">
                <span class="audit-detail-label">Request ID</span>
                <span class="audit-detail-value" style="font-family:monospace;font-size:var(--font-size-xs);color:var(--color-text-secondary);">${log.request_id || '-'}</span>
              </div>
              ${log.error_message ? `
                <div class="audit-detail-item" style="grid-column:1/-1;">
                  <span class="audit-detail-label" style="color:var(--color-danger);">Erreur</span>
                  <span class="audit-detail-value" style="color:var(--color-danger);background:var(--color-danger-light);padding:var(--spacing-2) var(--spacing-3);border-radius:var(--radius-md);">${this._escapeHtml(log.error_message)}</span>
                </div>
              ` : ''}
            </div>

            ${log.old_values && Object.keys(log.old_values).length > 0 ? `
              <div class="audit-diff-section">
                <h4 class="audit-diff-title">Anciennes valeurs</h4>
                <pre class="audit-json-block">${this._escapeHtml(JSON.stringify(log.old_values, null, 2))}</pre>
              </div>
            ` : ''}
            ${log.new_values && Object.keys(log.new_values).length > 0 ? `
              <div class="audit-diff-section">
                <h4 class="audit-diff-title">Nouvelles valeurs</h4>
                <pre class="audit-json-block">${this._escapeHtml(JSON.stringify(log.new_values, null, 2))}</pre>
              </div>
            ` : ''}
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" data-close>Fermer</button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    overlay.querySelectorAll('[data-close]').forEach(btn => {
      btn.addEventListener('click', () => overlay.remove());
    });

    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.remove();
    });

    const handleEsc = (e) => {
      if (e.key === 'Escape') {
        overlay.remove();
        document.removeEventListener('keydown', handleEsc);
      }
    };
    document.addEventListener('keydown', handleEsc);
  }

  updateCount() {
    if (!this.element) return;
    const countEl = this.element.querySelector('.audit-count');
    if (countEl) {
      countEl.textContent = `${this.total} entrée${this.total !== 1 ? 's' : ''}`;
    }
  }

  updatePagination() {
    if (!this.element) return;

    const info = this.element.querySelector('.pagination-info');
    if (info) {
      info.innerHTML = `Page <strong>${this.page}</strong> sur <strong>${this.totalPages}</strong> (${this.total} total)`;
    }

    const prevBtn = this.element.querySelector('[data-page="prev"]');
    const nextBtn = this.element.querySelector('[data-page="next"]');
    if (prevBtn) prevBtn.disabled = this.page <= 1;
    if (nextBtn) nextBtn.disabled = this.page >= this.totalPages;

    const pagesContainer = this.element.querySelector('.pagination-pages');
    if (pagesContainer) {
      pagesContainer.innerHTML = this._renderPageNumbers();
      pagesContainer.querySelectorAll('[data-goto]').forEach(btn => {
        btn.addEventListener('click', () => this.onPageChange(parseInt(btn.dataset.goto)));
      });
    }
  }

  _renderPageNumbers() {
    const pages = [];
    const maxVisible = 5;
    let start = Math.max(1, this.page - Math.floor(maxVisible / 2));
    let end = Math.min(this.totalPages, start + maxVisible - 1);
    if (end - start < maxVisible - 1) start = Math.max(1, end - maxVisible + 1);

    if (start > 1) {
      pages.push(`<button class="btn btn-sm btn-secondary pagination-page" data-goto="1">1</button>`);
      if (start > 2) pages.push(`<span class="pagination-ellipsis">...</span>`);
    }

    for (let i = start; i <= end; i++) {
      const active = i === this.page ? 'btn-primary' : 'btn-secondary';
      pages.push(`<button class="btn btn-sm ${active} pagination-page" data-goto="${i}">${i}</button>`);
    }

    if (end < this.totalPages) {
      if (end < this.totalPages - 1) pages.push(`<span class="pagination-ellipsis">...</span>`);
      pages.push(`<button class="btn btn-sm btn-secondary pagination-page" data-goto="${this.totalPages}">${this.totalPages}</button>`);
    }

    return pages.join('');
  }

  renderTableState() {
    if (!this.element) return;

    const tableContainer = this.element.querySelector('[data-audit-table]');
    if (!tableContainer) return;

    if (this.loading) {
      tableContainer.innerHTML = `
        <div class="table-loading">
          <div class="spinner"></div>
          <p>Chargement des logs d'audit...</p>
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
          <h3>Erreur de chargement</h3>
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
      <tr class="audit-row" data-log-id="${log.id}">
        <td><span class="audit-id">${log.id}</span></td>
        <td><span class="audit-date">${this.formatDateTime(log.created_at)}</span></td>
        <td><strong>${this._escapeHtml(log.username)}</strong></td>
        <td><span class="badge ${this.getActionBadgeClass(log.action)}">${this.formatAction(log.action)}</span></td>
        <td>${this.formatModule(log.module)}</td>
        <td>${log.object_type || '-'}</td>
        <td>${log.object_id || '-'}</td>
        <td>${this.getStatusBadge(log.status)}</td>
        <td><span class="audit-ip">${log.ip_address || '-'}</span></td>
      </tr>
    `).join('');

    tableContainer.innerHTML = `
      <div class="table-wrapper">
        <table class="users-table">
          <thead>
            <tr>
              <th style="width:60px;">ID</th>
              <th style="width:160px;">Date</th>
              <th style="width:120px;">Utilisateur</th>
              <th style="width:180px;">Action</th>
              <th style="width:110px;">Module</th>
              <th style="width:100px;">Type</th>
              <th style="width:80px;">Objet</th>
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

  _populateFilterValues() {
    if (!this.element) return;

    const moduleSelect = this.element.querySelector('[data-filter="module"]');
    if (moduleSelect && this.filterValues.modules.length > 0) {
      const current = this.filters.module;
      moduleSelect.innerHTML = `<option value="">Tous modules</option>` +
        this.filterValues.modules.map(m => `<option value="${m}" ${m === current ? 'selected' : ''}>${this.formatModule(m)}</option>`).join('');
    }

    const actionSelect = this.element.querySelector('[data-filter="action"]');
    if (actionSelect && this.filterValues.actions.length > 0) {
      const current = this.filters.action;
      actionSelect.innerHTML = `<option value="">Toutes actions</option>` +
        this.filterValues.actions.map(a => `<option value="${a}" ${a === current ? 'selected' : ''}>${this.formatAction(a)}</option>`).join('');
    }

    const usernameInput = this.element.querySelector('[data-filter="username"]');
    if (usernameInput && this.filterValues.usernames.length > 0 && !usernameInput.list) {
      const datalist = document.createElement('datalist');
      datalist.id = 'audit-usernames-list';
      datalist.innerHTML = this.filterValues.usernames.map(u => `<option value="${this._escapeHtml(u)}">`).join('');
      document.body.appendChild(datalist);
      usernameInput.setAttribute('list', 'audit-usernames-list');
    }
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'administration-page';

    this.element.innerHTML = `
      <div class="users-header">
        <div class="users-title-area">
          <h1 class="users-title">Journal d'audit</h1>
          <p class="users-count audit-count" aria-live="polite">
            ${this.total} entrée${this.total !== 1 ? 's' : ''}
          </p>
        </div>
      </div>

      <div class="users-toolbar">
        <div class="filters-row">
          <div class="filter-group filter-search">
            <label class="filter-label">Utilisateur</label>
            <div class="search-input-wrapper">
              <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="11" cy="11" r="8"></circle>
                <path d="m21 21-4.35-4.35"></path>
              </svg>
              <input type="text" class="form-input" placeholder="Rechercher un utilisateur..." data-filter="username" value="${this._escapeHtml(this.filters.username)}" />
            </div>
          </div>

          <div class="filter-group">
            <label class="filter-label">Module</label>
            <select class="form-select" data-filter="module">
              <option value="">Tous modules</option>
            </select>
          </div>

          <div class="filter-group">
            <label class="filter-label">Action</label>
            <select class="form-select" data-filter="action">
              <option value="">Toutes actions</option>
            </select>
          </div>

          <div class="filter-group">
            <label class="filter-label">Statut</label>
            <select class="form-select" data-filter="status">
              <option value="">Tous statuts</option>
              <option value="success" ${this.filters.status === 'success' ? 'selected' : ''}>Succès</option>
              <option value="error" ${this.filters.status === 'error' ? 'selected' : ''}>Erreur</option>
            </select>
          </div>

          <div class="filter-group">
            <label class="filter-label">Date début</label>
            <input type="datetime-local" class="form-input" data-filter="start_date" title="Date début" />
          </div>

          <div class="filter-group">
            <label class="filter-label">Date fin</label>
            <input type="datetime-local" class="form-input" data-filter="end_date" title="Date fin" />
          </div>

          <div class="filter-group" style="justify-content:flex-end;">
            <label class="filter-label">&nbsp;</label>
            <button class="btn btn-sm btn-outline" data-action="clear-filters">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 6 6 18"></path>
                <path d="m6 6 12 12"></path>
              </svg>
              Effacer
            </button>
          </div>
        </div>
      </div>

      <div data-audit-table></div>

      <div class="users-pagination" data-pagination aria-label="Pagination">
        <div class="pagination-info">
          Page <strong>${this.page}</strong> sur <strong>${this.totalPages}</strong> (${this.total} total)
        </div>
        <div class="pagination-pages"></div>
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

    this.element.querySelector('[data-filter="username"]')?.addEventListener('input', (e) => this.handleSearch('username', e.target.value));
    this.element.querySelector('[data-filter="module"]')?.addEventListener('change', (e) => this.handleSelectFilter('module', e.target.value));
    this.element.querySelector('[data-filter="action"]')?.addEventListener('change', (e) => this.handleSelectFilter('action', e.target.value));
    this.element.querySelector('[data-filter="status"]')?.addEventListener('change', (e) => this.handleSelectFilter('status', e.target.value));
    this.element.querySelector('[data-filter="start_date"]')?.addEventListener('change', () => this.handleDateFilter());
    this.element.querySelector('[data-filter="end_date"]')?.addEventListener('change', () => this.handleDateFilter());
    this.element.querySelector('[data-action="clear-filters"]')?.addEventListener('click', () => this.handleClearFilters());

    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => this.onPageChange(this.page - 1));
    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => this.onPageChange(this.page + 1));

    this._populateFilterValues();
    this.renderTableState();

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
    if (this._searchTimeout) clearTimeout(this._searchTimeout);
    const dl = document.getElementById('audit-usernames-list');
    if (dl) dl.remove();
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
