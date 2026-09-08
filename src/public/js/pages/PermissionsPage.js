import { authStore } from '../stores/auth.js';
import { Table } from '../components/Table.js';
import { UserFilters } from '../components/UserFilters.js';
import { UserModal } from '../components/UserModal.js';
import { ConfirmDialog } from '../components/ConfirmDialog.js';
import {
  listPermissions,
  createPermission,
  getPermission,
  updatePermission,
  deletePermission,
} from '../services/adminApi.js';

export class PermissionsPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.loading = false;
    this.error = null;

    this.permissions = [];
    this.total = 0;
    this.page = 1;
    this.pageSize = 20;
    this.totalPages = 1;
    this.sortBy = 'created_at';
    this.sortOrder = 'desc';

    this.filters = {
      search: '',
      module: '',
      is_system: null,
    };

    this.modules = [];

    this.permissionTable = null;
    this.permissionFilters = null;
    this.permissionModal = null;
    this.confirmDialog = null;

    this._authUnsubscribe = null;
    this.selectedPermission = null;
    this.pendingAction = null;
  }

  async initialize() {
    this.permissionTable = new Table({
      columns: [
        {
          key: 'code',
          label: 'Code',
          sortable: true,
          width: '150px',
        },
        {
          key: 'name',
          label: 'Nom',
          sortable: true,
        },
        {
          key: 'module',
          label: 'Module',
          sortable: true,
          width: '120px',
        },
        {
          key: 'description',
          label: 'Description',
          sortable: false,
        },
        {
          key: 'is_system',
          label: 'Système',
          sortable: true,
          width: '80px',
          render: (item) => `
            <span class="status-badge ${item.is_system ? 'active' : 'inactive'}">
              ${item.is_system ? 'Oui' : 'Non'}
            </span>
          `,
        },
      ],

      actions: [
        {
          key: 'edit',
          label: 'Modifier',
          icon: 'edit',
        },
        {
          key: 'delete',
          label: 'Supprimer',
          icon: 'trash',
          variant: 'danger',
        },
      ],

      getItemId: (item) => item.id,

      onAction: (action, item) => {
        this.handleAction(action, item);
      },

      onSort: (column, order) => {
        this.sortBy = column;
        this.sortOrder = order;
        this.loadPermissions();
      },
    });

    this.permissionFilters = new UserFilters({
      onSearch: (search) => this.handleSearch(search),
      onModuleFilter: (module) => this.handleModuleFilter(module),
      onSystemFilter: (system) => this.handleSystemFilter(system),
      onClearFilters: () => this.handleClearFilters(),
      modules: this.modules,
    });

    this.permissionModal = new UserModal({
      onSubmit: (data, isEdit) =>
        this.handlePermissionSubmit(data, isEdit),
      onClose: () => this.closeModal(),
    });

    this.confirmDialog = new ConfirmDialog({
      onConfirm: () => this.executeConfirmedAction(),
      onCancel: () => this.closeConfirmDialog(),
    });

    this._authUnsubscribe = authStore.subscribe(() => {
      this.updateButtonVisibility();
    });

    await this.loadModules();
    await this.loadPermissions();
  }

  async loadModules() {
    try {
      const response = await listPermissions({
        page_size: 1000,
      });

      const permissions = response.permissions || [];

      const moduleSet = new Set();

      permissions.forEach((permission) => {
        if (permission.module) {
          moduleSet.add(permission.module);
        }
      });

      this.modules = Array.from(moduleSet).sort();

      if (this.permissionFilters) {
        this.permissionFilters.modules = this.modules;
      }
    } catch (error) {
      console.error(
        'Erreur chargement modules:',
        error
      );

      this.modules = [];
    }
  }

  async loadPermissions() {
    this.loading = true;
    this.error = null;
    this.renderTableState();

    try {
      const params = {
        page: this.page,
        page_size: this.pageSize,
        search: this.filters.search || undefined,
        module: this.filters.module || undefined,
        is_system: this.filters.is_system,
        sort_by: this.sortBy,
        sort_order: this.sortOrder,
      };

      const response =
        await listPermissions(params);

      this.permissions =
        response.permissions || [];

      this.total =
        response.total || 0;

      this.page =
        response.page || 1;

      this.pageSize =
        response.page_size || 20;

      this.totalPages =
        response.total_pages || 1;

      this.error = null;
    } catch (error) {
      console.error(
        'Erreur chargement permissions:',
        error
      );

      this.error =
        error.message ||
        'Erreur lors du chargement des permissions';

      this.permissions = [];
      this.total = 0;
      this.totalPages = 1;
    } finally {
      this.loading = false;
      this.renderTableState();
    }
  }

  handleSearch(search) {
    this.filters.search = search;
    this.page = 1;
    this.loadPermissions();
  }

  handleModuleFilter(module) {
    this.filters.module = module;
    this.page = 1;
    this.loadPermissions();
  }

  handleSystemFilter(system) {
    this.filters.is_system =
      system === '' ? null : system === 'true';

    this.page = 1;
    this.loadPermissions();
  }

  handleClearFilters() {
    this.filters = {
      search: '',
      module: '',
      is_system: null,
    };

    this.page = 1;

    this.permissionFilters?.reset();

    this.loadPermissions();
  }

  handleAction(action, permission) {
    switch (action) {
      case 'edit':
        this.openEditModal(permission);
        break;

      case 'delete':
        this.confirmDelete(permission);
        break;

      default:
        break;
    }
  }

  async handlePermissionSubmit(data, isEdit) {
    this.loading = true;

    try {
      if (isEdit) {
        await updatePermission(
          this.selectedPermission.id,
          data
        );
      } else {
        await createPermission(data);
      }

      this.closeModal();
      await this.loadPermissions();

      this.showToast(
        isEdit
          ? 'Permission modifiée'
          : 'Permission créée',
        'success'
      );
    } catch (error) {
      console.error(
        'Erreur enregistrement permission:',
        error
      );

      this.showToast(
        error.message || 'Erreur',
        'error'
      );
    } finally {
      this.loading = false;
    }
  }

  openCreateModal() {
    this.selectedPermission = null;

    this.permissionModal.open({
      mode: 'create-permission',
      modules: this.modules,
    });
  }

  openEditModal(permission) {
    this.selectedPermission = permission;

    this.permissionModal.open({
      mode: 'edit-permission',
      user: permission,
      modules: this.modules,
    });
  }

  confirmDelete(permission) {
    if (permission.is_system) {
      this.showToast(
        'Impossible de supprimer une permission système',
        'error'
      );
      return;
    }

    this.pendingAction = {
      type: 'delete',
      permission,
    };

    this.confirmDialog.open({
      title: 'Confirmer la suppression',
      message:
        `Êtes-vous sûr de vouloir supprimer la permission "${permission.name}" ? Cette action est irréversible.`,
      confirmText: 'Supprimer',
      variant: 'danger',
    });
  }

  async executeDelete(permission) {
    try {
      await deletePermission(permission.id);

      this.showToast(
        'Permission supprimée',
        'success'
      );

      await this.loadPermissions();
    } catch (error) {
      console.error(
        'Erreur suppression permission:',
        error
      );

      this.showToast(
        error.message || 'Erreur suppression',
        'error'
      );
    }
  }

  async executeConfirmedAction() {
    if (!this.pendingAction) {
      return;
    }

    const {
      type,
      permission,
    } = this.pendingAction;

    this.closeConfirmDialog();

    if (type === 'delete') {
      await this.executeDelete(permission);
    }

    this.pendingAction = null;
  }

  closeModal() {
    this.permissionModal?.close();
    this.selectedPermission = null;
  }

  closeConfirmDialog() {
    this.confirmDialog?.close();
    this.pendingAction = null;
  }

  onPageChange(page) {
    if (
      page < 1 ||
      page > this.totalPages
    ) {
      return;
    }

    this.page = page;
    this.loadPermissions();
  }

  onSortChange(sortBy, sortOrder) {
    this.sortBy = sortBy;
    this.sortOrder = sortOrder;
    this.page = 1;
    this.loadPermissions();
  }

  onTabActivate() {
    this.loadPermissions();
  }

  updateButtonVisibility() {
    if (this.element) {
      const createBtn =
        this.element.querySelector(
          '[data-action="create-permission"]'
        );

      if (createBtn) {
        createBtn.style.display =
          authStore.hasPermission(
            'permission_create'
          )
            ? ''
            : 'none';
      }
    }

    this.permissionTable?.setActionVisibility(
      'edit',
      authStore.hasPermission(
        'permission_update'
      )
    );

    this.permissionTable?.setActionVisibility(
      'delete',
      authStore.hasPermission(
        'permission_delete'
      )
    );
  }

  showToast(
    message,
    type = 'info'
  ) {
    const toast =
      document.createElement('div');

    toast.className =
      `toast toast--${type}`;

    toast.textContent =
      message;

    toast.setAttribute(
      'role',
      'alert'
    );

    toast.setAttribute(
      'aria-live',
      'polite'
    );

    let container =
      document.getElementById(
        'toast-container'
      );

    if (!container) {
      container =
        document.createElement('div');

      container.id =
        'toast-container';

      container.className =
        'toast-container';

      document.body.appendChild(
        container
      );
    }

    container.appendChild(toast);

    requestAnimationFrame(() => {
      toast.classList.add(
        'toast--visible'
      );
    });

    setTimeout(() => {
      toast.classList.remove(
        'toast--visible'
      );

      setTimeout(() => {
        toast.remove();
      }, 300);
    }, 3000);
  }

  renderTableState() {
    if (!this.element) {
      return;
    }

    const tableContainer =
      this.element.querySelector(
        '[data-permission-table]'
      );

    if (!tableContainer) {
      return;
    }

    // Rafraîchissement du compteur
    const countElement =
      this.element.querySelector(
        '.users-count'
      );

    if (countElement) {
      countElement.textContent =
        `${this.total} permission${this.total > 1 ? 's' : ''}`;
    }

    // Rafraîchissement des informations de pagination
    const paginationInfo =
      this.element.querySelector(
        '.pagination-info'
      );

    if (paginationInfo) {
      paginationInfo.innerHTML = `
        Page <strong>${this.page}</strong>
        sur <strong>${this.totalPages}</strong>
        (${this.total} total)
      `;
    }

    // Rafraîchissement des boutons de pagination
    const prevButton =
      this.element.querySelector(
        '[data-page="prev"]'
      );

    const nextButton =
      this.element.querySelector(
        '[data-page="next"]'
      );

    if (prevButton) {
      prevButton.disabled =
        this.page <= 1;
    }

    if (nextButton) {
      nextButton.disabled =
        this.page >= this.totalPages;
    }

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

          <svg
            width="48"
            height="48"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2">

            <circle
              cx="12"
              cy="12"
              r="10">
            </circle>

            <line
              x1="12"
              y1="8"
              x2="12"
              y2="12">
            </line>

            <line
              x1="12"
              y1="16"
              x2="12.01"
              y2="16">
            </line>

          </svg>

          <h3>Erreur</h3>

          <p>
            ${this._escapeHtml(
              this.error
            )}
          </p>

          <button
            class="btn btn-primary"
            data-action="retry">

            Réessayer

          </button>

        </div>
      `;

      tableContainer
        .querySelector(
          '[data-action="retry"]'
        )
        ?.addEventListener(
          'click',
          () => this.loadPermissions()
        );

      return;
    }

    this.permissionTable.setData({
      items: this.permissions,
      total: this.total,
      page: this.page,
      pageSize: this.pageSize,
      totalPages: this.totalPages,
      sortBy: this.sortBy,
      sortOrder: this.sortOrder,
    });

    tableContainer.innerHTML = '';

    tableContainer.appendChild(
      this.permissionTable.render()
    );

    this.updateButtonVisibility();
  }

  render() {
    this.element =
      document.createElement('div');

    this.element.className =
      'users-page';

    this.element.innerHTML = `
      <div class="users-header">

        <div class="users-title-area">

          <h1 class="users-title">
            Permissions
          </h1>

          <p
            class="users-count"
            aria-live="polite">

            ${this.total}
            permission${this.total > 1 ? 's' : ''}

          </p>

        </div>

        <button
          class="btn btn-primary"
          data-action="create-permission">

          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2">

            <line
              x1="12"
              y1="5"
              x2="12"
              y2="19">
            </line>

            <line
              x1="5"
              y1="12"
              x2="19"
              y2="12">
            </line>

          </svg>

          Nouvelle permission

        </button>

      </div>

      <div
        class="users-toolbar"
        data-permission-filters>
      </div>

      <div
        class="table-wrapper"
        data-permission-table>
      </div>

      <div
        class="users-pagination"
        data-pagination
        aria-label="Pagination">

        <div class="pagination-info">

          Page
          <strong>${this.page}</strong>
          sur
          <strong>${this.totalPages}</strong>

          (${this.total} total)

        </div>

        <div class="pagination-controls">

          <button
            class="btn btn-sm btn-secondary"
            data-page="prev"
            ${this.page <= 1 ? 'disabled' : ''}
            aria-label="Page précédente">

            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2">

              <polyline
                points="15 18 9 12 15 6">
              </polyline>

            </svg>

          </button>

          <button
            class="btn btn-sm btn-secondary"
            data-page="next"
            ${this.page >= this.totalPages ? 'disabled' : ''}
            aria-label="Page suivante">

            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2">

              <polyline
                points="9 18 15 12 9 6">
              </polyline>

            </svg>

          </button>

        </div>
      </div>
    `;

    this.element
      .querySelector(
        '[data-action="create-permission"]'
      )
      ?.addEventListener(
        'click',
        () => this.openCreateModal()
      );

    this.element
      .querySelector(
        '[data-page="prev"]'
      )
      ?.addEventListener(
        'click',
        () =>
          this.onPageChange(
            this.page - 1
          )
      );

    this.element
      .querySelector(
        '[data-page="next"]'
      )
      ?.addEventListener(
        'click',
        () =>
          this.onPageChange(
            this.page + 1
          )
      );

    const filtersContainer =
      this.element.querySelector(
        '[data-permission-filters]'
      );

    if (filtersContainer) {
      filtersContainer.appendChild(
        this.permissionFilters.render()
      );
    }

    this.renderTableState();

    return this.element;
  }

  mount(container) {
    if (!this.element) {
      this.render();
    }

    container.innerHTML = '';

    container.appendChild(
      this.element
    );

    return this;
  }

  destroy() {
    this._authUnsubscribe?.();

    this.permissionTable?.destroy?.();
    this.permissionFilters?.destroy?.();
    this.permissionModal?.destroy?.();
    this.confirmDialog?.destroy?.();
  }

  _escapeHtml(text) {
    const div =
      document.createElement('div');

    div.textContent =
      text;

    return div.innerHTML;
  }
}

export function createPermissionsPage(router) {
  return new PermissionsPage(router);
}
