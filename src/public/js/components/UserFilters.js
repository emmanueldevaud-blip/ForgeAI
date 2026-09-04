export class UserFilters {
  constructor(options = {}) {
    this.onSearch = options.onSearch || (() => {});
    this.onRoleFilter = options.onRoleFilter || (() => {});
    this.onStatusFilter = options.onStatusFilter || (() => {});
    this.onSourceFilter = options.onSourceFilter || (() => {});
    this.onClearFilters = options.onClearFilters || (() => {});
    this.roles = options.roles || [];
    this.element = null;
    this.searchDebounce = null;
    this.currentValues = {
      search: '',
      role: '',
      is_active: '',
      source: '',
    };
  }

  updateRoles(roles) {
    this.roles = roles;
    if (this.element) {
      const roleSelect = this.element.querySelector('[data-filter="role"]');
      if (roleSelect) {
        const currentValue = roleSelect.value;
        roleSelect.innerHTML = this._renderRoleOptions();
        roleSelect.value = currentValue;
      }
    }
  }

  _renderRoleOptions() {
    return `
      <option value="">Tous les rôles</option>
      ${this.roles.map(role => `<option value="${this._escapeHtml(role.code)}">${this._escapeHtml(role.name)}</option>`).join('')}
    `;
  }

  reset() {
    this.currentValues = { search: '', role: '', is_active: '', source: '' };
    if (this.element) {
      this.element.querySelector('[data-filter="search"]').value = '';
      this.element.querySelector('[data-filter="role"]').value = '';
      this.element.querySelector('[data-filter="status"]').value = '';
      this.element.querySelector('[data-filter="source"]').value = '';
    }
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'user-filters';
    this.element.innerHTML = `
      <div class="filters-row">
        <div class="filter-group filter-search">
          <label for="filter-search" class="visually-hidden">Rechercher</label>
          <div class="search-input-wrapper">
            <svg class="search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
            <input
              type="search"
              id="filter-search"
              class="filter-input"
              placeholder="Rechercher (nom, email, prénom...)"
              value="${this._escapeHtml(this.currentValues.search)}"
              data-filter="search"
              aria-label="Rechercher un utilisateur"
            >
            ${this.currentValues.search ? `
              <button type="button" class="search-clear" data-action="clear-search" aria-label="Effacer la recherche">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="18" y1="6" x2="6" y2="18"></line>
                  <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
              </button>
            ` : ''}
          </div>
        </div>

        <div class="filter-group">
          <label for="filter-role" class="visually-hidden">Filtrer par rôle</label>
          <select id="filter-role" class="filter-select" data-filter="role" aria-label="Filtrer par rôle">
            ${this._renderRoleOptions()}
          </select>
        </div>

        <div class="filter-group">
          <label for="filter-status" class="visually-hidden">Filtrer par statut</label>
          <select id="filter-status" class="filter-select" data-filter="status" aria-label="Filtrer par statut">
            <option value="">Tous les statuts</option>
            <option value="true">Actif</option>
            <option value="false">Inactif</option>
          </select>
        </div>

        <div class="filter-group">
          <label for="filter-source" class="visually-hidden">Filtrer par source</label>
          <select id="filter-source" class="filter-select" data-filter="source" aria-label="Filtrer par source">
            <option value="">Toutes les sources</option>
            <option value="local">Local</option>
            <option value="ad">Active Directory</option>
          </select>
        </div>

        <div class="filter-group filter-actions">
          <button type="button" class="btn btn-secondary btn-sm" data-action="clear-all" ${!this._hasActiveFilters() ? 'disabled' : ''}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
            Réinitialiser
          </button>
        </div>
      </div>
    `;

    const searchInput = this.element.querySelector('[data-filter="search"]');
    searchInput.addEventListener('input', (e) => {
      clearTimeout(this.searchDebounce);
      this.searchDebounce = setTimeout(() => {
        this.currentValues.search = e.target.value;
        this.onSearch(e.target.value);
        this._updateClearButton();
      }, 300);
    });

    this.element.querySelector('[data-filter="role"]').addEventListener('change', (e) => {
      this.currentValues.role = e.target.value;
      this.onRoleFilter(e.target.value);
      this._updateClearButton();
    });

    this.element.querySelector('[data-filter="status"]').addEventListener('change', (e) => {
      this.currentValues.is_active = e.target.value;
      this.onStatusFilter(e.target.value);
      this._updateClearButton();
    });

    this.element.querySelector('[data-filter="source"]').addEventListener('change', (e) => {
      this.currentValues.source = e.target.value;
      this.onSourceFilter(e.target.value);
      this._updateClearButton();
    });

    this.element.querySelector('[data-action="clear-search"]')?.addEventListener('click', () => {
      searchInput.value = '';
      this.currentValues.search = '';
      this.onSearch('');
      this._updateClearButton();
      searchInput.focus();
    });

    this.element.querySelector('[data-action="clear-all"]').addEventListener('click', () => {
      this.reset();
      this.onClearFilters();
      this._updateClearButton();
    });

    return this.element;
  }

  _hasActiveFilters() {
    return this.currentValues.search || this.currentValues.role || this.currentValues.is_active || this.currentValues.source;
  }

  _updateClearButton() {
    const clearBtn = this.element?.querySelector('[data-action="clear-all"]');
    if (clearBtn) {
      clearBtn.disabled = !this._hasActiveFilters();
    }
  }

  mount(container) {
    if (!this.element) this.render();
    container.innerHTML = '';
    container.appendChild(this.element);
    return this;
  }

  destroy() {
    clearTimeout(this.searchDebounce);
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