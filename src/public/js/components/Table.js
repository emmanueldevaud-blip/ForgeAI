export class Table {
  constructor(options = {}) {
    this.columns = options.columns || [];
    this.actions = options.actions || [];
    this.data = {
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
      totalPages: 1,
      sortBy: '',
      sortOrder: 'desc',
    };
    this.element = null;
    this.onSort = options.onSort || (() => {});
    this.onAction = options.onAction || (() => {});
    this.getItemId = options.getItemId || (item => item.id);
    this.getItemKey = options.getItemKey || (item => item.id);
    this.element = null;
    this.emptyMessage = options.emptyMessage || 'Aucun élément trouvé';
    this.emptyIcon = options.emptyIcon || '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"></rect><path d="M9 12h6"></path><path d="M12 9v6"></path></svg>';
    this.emptyText = options.emptyText || 'Aucun élément trouvé';
    this.loading = false;
    this.error = null;
    this.sortableColumns = options.sortableColumns || [];
  }

  setData(data) {
    this.data = { ...this.data, ...data };
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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

  _getSortIcon(column) {
    if (this.data.sortBy !== column) {
      return '<svg class="sort-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline><polyline points="6 9 12 15 18 9"></polyline></svg>';
    }
    return '<svg class="sort-icon sort-icon--active" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="' + (this.data.sortOrder === 'asc' ? '18 15 12 9 6 15' : '6 9 12 15 18 9') + '"></polyline></svg>';
  }

  _renderHeader() {
  const headers = this.columns.map(col => {
    const sortable =
      this.sortableColumns.includes(col.key) || col.sortable;

    return '<th scope="col" ' +
      (sortable ? 'data-sort="' + col.key + '"' : '') +
      ' style="' + (col.width ? 'width: ' + col.width + ';' : '') + '">' +
      '<div class="th-content">' +
      '<span>' + this._escapeHtml(col.label) + '</span>' +
      (sortable ? this._getSortIcon(col.key) : '') +
      '</div>' +
      '</th>';
  }).join('');

  if (this.actions.length > 0) {
    return headers +
      '<th scope="col"><div class="th-content"><span>Actions</span></div></th>';
  }

  return headers;
}

  _renderRow(item) {
    const cells = this.columns.map(col => {
      let value = this._getNestedValue(item, col.key);
      if (col.render) {
        return '<td>' + col.render(item, this._escapeHtml) + '</td>';
      }
      if (value instanceof Date) {
        return '<td>' + this._formatDate(value) + '</td>';
      }
      if (typeof value === 'boolean') {
        return '<td><span class="status-badge ' + (value ? 'active' : 'inactive') + '">' + (value ? 'Actif' : 'Inactif') + '</span></td>';
      }
      if (value === null || value === undefined) {
        return '<td>—</td>';
      }
      return '<td>' + this._escapeHtml(String(value)) + '</td>';
    }).join('');

    const actions = this.actions.length > 0 ? this._renderActions(item) : '';

    return '<tr data-id="' + this.getItemId(item) + '">' + cells + (actions ? '<td><div class="action-buttons">' + this._renderActions(item) + '</div></td>' : '') + '</tr>';
  }

  _getItem(item) {
    return item;
  }

  _getItemId(item) {
    return this.getItemId(item);
  }

  _getNestedValue(obj, path) {
    return path.split('.').reduce((obj, key) => obj?.[key], obj);
  }


updateActionVisibility(authStore) {
  if (!this.element) return;

  this.actions.forEach(action => {
    if (!action.permission) return;

    const visible = authStore.hasPermission(action.permission);

    this.element
      .querySelectorAll(`[data-action="${action.key}"]`)
      .forEach(btn => {
        btn.style.display = visible ? '' : 'none';
      });
  });
}

_renderActions(item) {
  const icons = {
    edit: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>',

    power: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"></path><line x1="12" y1="2" x2="12" y2="12"></line></svg>',

    users: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>',

    trash: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"></path><path d="M10 11v6"></path><path d="M14 11v6"></path><path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"></path></svg>',
  };

  return this.actions.map(action => {
    const visible = !action.visible || action.visible(item);
    if (!visible) return '';

    const title = action.title || action.label;
    const icon = icons[action.icon] || this._escapeHtml(action.icon || '');

    return '<button type="button" class="action-btn ' +
      (action.variant ? 'btn-' + action.variant : '') +
      '" data-action="' + action.key +
      '" data-id="' + this.getItemId(item) +
      '" aria-label="' + this._escapeHtml(title) +
      '" title="' + this._escapeHtml(title) + '"' +
      (action.disabled ? ' disabled' : '') +
      '>' + icon + '</button>';
  }).join('');
}
  _renderEmptyState() {
    const colspan = this.columns.length + (this.actions.length > 0 ? 1 : 0);
    return '<tbody><tr><td colspan="' + colspan + '" class="table-empty"><svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"></rect><path d="M9 12h6"></path><path d="M12 9v6"></path></svg><p>Aucun élément trouvé</p></td></tr></tbody>';
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'table-wrapper';

    const hasItems = this.data.items.length > 0;

    this.element.innerHTML = '<table class="users-table" role="grid"><thead><tr>' + this._renderHeader() + '</tr></thead>' + (hasItems ? '<tbody>' + this.data.items.map(item => this._renderRow(item)).join('') + '</tbody>' : this._renderEmptyState()) + '</table>';

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
      btn.addEventListener('click', () => {
        const id = parseInt(btn.dataset.id, 10);
        const item = this.data.items.find(u => u.id === id);
        if (item) this.onAction('edit', item);
      });
    });

    this.element.querySelectorAll('[data-action="toggle"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = parseInt(btn.dataset.id, 10);
        const item = this.data.items.find(u => u.id === id);
        if (item) this.onAction('toggle', item);
      });
    });

    this.element.querySelectorAll('[data-action="roles"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = parseInt(btn.dataset.id, 10);
        const item = this.data.items.find(u => u.id === id);
        if (item) this.onAction('roles', item);
      });
    });

    this.element.querySelectorAll('[data-action="delete"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = parseInt(btn.dataset.id, 10);
        const item = this.data.items.find(u => u.id === id);
        if (item) this.onAction('delete', item);
      });
    });

    return this.element;
  }

  setData(data) {
    this.data = { ...this.data, ...data };
    if (this.element) this.render();
  }

  setActionVisibility(action, show) {
    if (!this.element) return;
    this.element.querySelectorAll('[data-action="' + action + '"]').forEach(btn => {
      btn.style.display = show ? '' : 'none';
    });
  }

  destroy() {
    if (this.element) {
      this.element.innerHTML = '';
    }
  }
}
