export class UserTable {
  constructor(options = {}) {
    this.onEdit = options.onEdit || (() => {});
    this.onToggleActive = options.onToggleActive || (() => {});
    this.onResetPassword = options.onResetPassword || (() => {});
    this.onManageRoles = options.onManageRoles || (() => {});
    this.onDelete = options.onDelete || (() => {});
    this.onSort = options.onSort || (() => {});
    this.data = {
      users: [],
      total: 0,
      page: 1,
      pageSize: 20,
      totalPages: 1,
      sortBy: 'created_at',
      sortOrder: 'desc',
    };
    this.element = null;
    this.sortableColumns = ['username', 'email', 'first_name', 'last_name', 'role', 'source', 'last_login', 'created_at', 'updated_at'];
  }

  setData(data) {
    this.data = { ...this.data, ...data };
  }

  updateActionVisibility(authStore) {
    if (!this.element) return;
    const rows = this.element.querySelectorAll('tbody tr');
    rows.forEach(row => {
      const userId = parseInt(row.dataset.userId, 10);
      const user = this.data.users.find(u => u.id === userId);
      if (!user) return;

      const editBtn = row.querySelector('[data-action="edit"]');
      const toggleBtn = row.querySelector('[data-action="toggle"]');
      const resetBtn = row.querySelector('[data-action="reset-password"]');
      const rolesBtn = row.querySelector('[data-action="roles"]');
      const deleteBtn = row.querySelector('[data-action="delete"]');

      if (editBtn) editBtn.style.display = authStore.hasPermission('user_update') ? '' : 'none';
      if (toggleBtn) toggleBtn.style.display = authStore.hasPermission('user_update') ? '' : 'none';
      if (resetBtn) resetBtn.style.display = authStore.hasPermission('user_update') ? '' : 'none';
      if (rolesBtn) rolesBtn.style.display = authStore.hasPermission('user_manage_roles') ? '' : 'none';
      if (deleteBtn) deleteBtn.style.display = authStore.hasPermission('user_delete') ? '' : 'none';
    });
  }

  _formatDate(dateString) {
    if (!dateString) return '—';
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return '—';
    return date.toLocaleDateString('fr-FR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  _getRoleBadge(role) {
    const badgeClass = role === 'admin' ? 'role-badge admin' : 'role-badge user';
    return `<span class="${badgeClass}">${this._escapeHtml(role || 'user')}</span>`;
  }

  _getStatusBadge(isActive) {
    return `<span class="status-badge ${isActive ? 'active' : 'inactive'}">${isActive ? 'Actif' : 'Inactif'}</span>`;
  }

  _getSourceBadge(source) {
    return `<span class="source-badge" data-source="${this._escapeHtml(source)}">${this._escapeHtml(source === 'local' ? 'Local' : 'Active Directory')}</span>`;
  }

  _getSortIcon(column) {
    if (this.data.sortBy !== column) {
      return `<svg class="sort-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline><polyline points="6 9 12 15 18 9"></polyline></svg>`;
    }
    return `<svg class="sort-icon sort-icon--active" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <polyline points="${this.data.sortOrder === 'asc' ? '18 15 12 9 6 15' : '6 9 12 15 18 9'}"></polyline>
    </svg>`;
  }

  _renderHeader() {
    const columns = [
      { key: 'username', label: 'Utilisateur', sortable: true },
      { key: 'name', label: 'Nom', sortable: true },
      { key: 'email', label: 'Email', sortable: true },
      { key: 'role', label: 'Rôle', sortable: true },
      { key: 'source', label: 'Source', sortable: true },
      { key: 'status', label: 'Statut', sortable: true },
      { key: 'last_login', label: 'Dernière connexion', sortable: true },
      { key: 'actions', label: 'Actions', sortable: false },
    ];

    return columns.map(col => `
      <th scope="col" ${col.sortable ? `data-sort="${col.key}"` : ''} style="${col.key === 'actions' ? 'width: 180px;' : ''}">
        <div class="th-content">
          <span>${col.label}</span>
          ${col.sortable ? this._getSortIcon(col.key) : ''}
        </div>
      </th>
    `).join('');
  }

  _renderRow(user) {
    const fullName = [user.first_name, user.last_name].filter(Boolean).join(' ') || '—';
    const lastLogin = this._formatDate(user.last_login);
    const isAD = user.source !== 'local';

    return `
      <tr data-user-id="${user.id}">
        <td>
          <div class="user-info">
            <span class="username">${this._escapeHtml(user.username)}</span>
            ${(user.roles || []).includes('admin') ? `<span class="admin-indicator" title="Administrateur"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="12 2 15 8 9 8"></polyline><path d="M3 10h18"></path><path d="M5 10v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4"></path></svg></span>` : ''}
          </div>
        </td>
        <td>${this._escapeHtml(fullName)}</td>
        <td>${this._escapeHtml(user.email)}</td>
        <td>${this._getRoleBadge(user.roles?.[0] || user.role)}</td>
        <td>${this._getSourceBadge(user.source)}</td>
        <td>${this._getStatusBadge(user.is_active)}</td>
        <td>${lastLogin}</td>
        <td>
          <div class="action-buttons">
            <button type="button" class="action-btn" data-action="edit" data-user-id="${user.id}" ${isAD ? 'disabled' : ''} aria-label="Modifier ${this._escapeHtml(user.username)}" title="${isAD ? 'Non disponible (compte AD)' : 'Modifier'}">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
            </button>
            <button type="button" class="action-btn" data-action="toggle" data-user-id="${user.id}" ${isAD ? 'disabled' : ''} aria-label="${user.is_active ? 'Désactiver' : 'Réactiver'} ${this._escapeHtml(user.username)}" title="${isAD ? 'Non disponible (compte AD)' : (user.is_active ? 'Désactiver' : 'Réactiver')}">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                ${user.is_active ? '<circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line>' : '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline>'}
              </svg>
            </button>
            <button type="button" class="action-btn" data-action="reset-password" data-user-id="${user.id}" ${user.source !== 'local' ? 'disabled' : ''} aria-label="Réinitialiser le mot de passe" title="${user.source !== 'local' ? 'Non disponible (compte AD)' : 'Réinitialiser le mot de passe'}">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="9" width="20" height="12" rx="2"></rect><path d="M10 9v-4a2 2 0 0 1 4 0v4"></path></svg>
            </button>
            <button type="button" class="action-btn" data-action="roles" data-user-id="${user.id}" aria-label="Gérer les rôles" title="Gérer les rôles">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22c4.97 0 9-4.03 9-9s-4.03-9-9-9-9 4.03-9 9 4.03 9 9 9z"></path><path d="M9 12l2 2 4-4"></path></svg>
            </button>
            <button type="button" class="action-btn delete" data-action="delete" data-user-id="${user.id}" ${isAD ? 'disabled' : ''} aria-label="Supprimer ${this._escapeHtml(user.username)}" title="${isAD ? 'Non disponible (compte AD)' : 'Supprimer'}">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
            </button>
          </div>
        </td>
      </tr>
    `;
  }

  _renderEmptyState() {
    return `
      <tbody>
        <tr>
          <td colspan="8" class="table-empty">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"></rect><path d="M9 12h6"></path><path d="M12 9v6"></path></svg>
            <p>Aucun utilisateur trouvé</p>
          </td>
        </tr>
      </tbody>
    `;
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'table-wrapper';

    const hasUsers = this.data.users.length > 0;

    this.element.innerHTML = `
      <table class="users-table" role="grid">
        <thead>
          <tr>${this._renderHeader()}</tr>
        </thead>
        ${hasUsers ? `
          <tbody>
            ${this.data.users.map(user => this._renderRow(user)).join('')}
          </tbody>
        ` : this._renderEmptyState()}
      </table>
    `;

    this.element.querySelectorAll('th[data-sort]').forEach(th => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        const column = th.dataset.sort;
        let order = 'asc';
        if (this.data.sortBy === column && this.data.sortOrder === 'asc') {
          order = 'desc';
        }
        this.onSort(column, order);
      });
    });

    this.element.querySelectorAll('[data-action="edit"]').forEach(btn => {
      if (btn.disabled) return;
      btn.addEventListener('click', () => {
        const userId = parseInt(btn.dataset.userId, 10);
        const user = this.data.users.find(u => u.id === userId);
        if (user) this.onEdit(user);
      });
    });

    this.element.querySelectorAll('[data-action="toggle"]').forEach(btn => {
      if (btn.disabled) return;
      btn.addEventListener('click', () => {
        const userId = parseInt(btn.dataset.userId, 10);
        const user = this.data.users.find(u => u.id === userId);
        if (user) this.onToggleActive(user);
      });
    });

    this.element.querySelectorAll('[data-action="reset-password"]').forEach(btn => {
      if (btn.disabled) return;
      btn.addEventListener('click', () => {
        const userId = parseInt(btn.dataset.userId, 10);
        const user = this.data.users.find(u => u.id === userId);
        if (user) this.onResetPassword(user);
      });
    });

    this.element.querySelectorAll('[data-action="roles"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const userId = parseInt(btn.dataset.userId, 10);
        const user = this.data.users.find(u => u.id === userId);
        if (user) this.onManageRoles(user);
      });
    });

    this.element.querySelectorAll('[data-action="delete"]').forEach(btn => {
      if (btn.disabled) return;
      btn.addEventListener('click', () => {
        const userId = parseInt(btn.dataset.userId, 10);
        const user = this.data.users.find(u => u.id === userId);
        if (user) this.onDelete(user);
      });
    });

    return this.element;
  }

  mount(container) {
    if (!this.element) this.render();
    container.innerHTML = '';
    container.appendChild(this.element);
    return this;
  }

  destroy() {
    if (this.element) {
      this.element.innerHTML = '';
    }
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}