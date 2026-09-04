import { authStore } from '../stores/auth.js';
import { Table } from '../components/Table.js';
import { UserFilters } from '../components/UserFilters.js';
import { UserModal } from '../components/UserModal.js';
import { ConfirmDialog } from '../components/ConfirmDialog.js';

import {
  listRolesAdmin,
  createRole,
  getRole,
  updateRole,
  deleteRole,
  addPermissionToRole,
  listPermissions,
} from '../services/adminApi.js';

export class RolesPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.loading = false;
    this.error = null;

    this.roles = [];
    this.total = 0;
    this.page = 1;
    this.pageSize = 20;
    this.totalPages = 1;

    this.sortBy = 'created_at';
    this.sortOrder = 'desc';

    this.filters = {
      search: '',
      is_active: null,
      is_system: null,
    };

    // Permet de distinguer un filtre réellement choisi
    // par l'utilisateur d'une valeur envoyée automatiquement
    // par UserFilters lors de son initialisation.
    this.statusFilterInitialized = false;
    this.systemFilterInitialized = false;

    this.permissions = [];

    this.roleTable = null;
    this.roleFilters = null;
    this.roleModal = null;
    this.rolePermissionModal = null;
    this.confirmDialog = null;

    this._authUnsubscribe = null;

    this.selectedRole = null;
    this.selectedRolePermissions = [];
    this.pendingAction = null;
  }

  async initialize() {
    this.roleTable = new Table({
      columns: [
        {
          key: 'name',
          label: 'Nom',
          sortable: true,
        },
        {
          key: 'code',
          label: 'Code',
          sortable: true,
        },
        {
          key: 'description',
          label: 'Description',
          sortable: false,
        },
        {
          key: 'is_system',
          label: 'Type',
          sortable: true,
          render: (role) => role.is_system
            ? '<span class="status-badge status-active">Système</span>'
            : '<span class="status-badge status-inactive">Personnalisé</span>',
        },
        {
          key: 'is_active',
          label: 'Statut',
          sortable: true,
          render: (role) => role.is_active
            ? '<span class="status-badge active">Actif</span>'
            : '<span class="status-badge inactive">Inactif</span>',
        },
      ],

      actions: [
        {
          key: 'edit',
          label: 'Modifier',
          icon: 'edit',
          permission: 'role_update',
        },
        {
          key: 'toggle',
          label: 'Activer/Désactiver',
          icon: 'power',
          permission: 'role_update',
        },
        {
          key: 'permissions',
          label: 'Gérer les permissions',
          icon: 'users',
          permission: 'role_update',
        },
        {
          key: 'delete',
          label: 'Supprimer',
          icon: 'trash',
          permission: 'role_delete',
          visible: (role) => !role.is_system,
        },
      ],

      onAction: (action, role) => {
        switch (action) {
          case 'edit':
            this.openEditModal(role);
            break;

          case 'toggle':
            this.confirmToggleActive(role);
            break;

          case 'permissions':
            this.openManagePermissionsModal(role);
            break;

          case 'delete':
            this.confirmDelete(role);
            break;

          default:
            break;
        }
      },

      onSort: (sortBy, sortOrder) => {
        this.onSortChange(sortBy, sortOrder);
      },
    });

    this.roleFilters = new UserFilters({
      onSearch: (search) => this.handleSearch(search),

      onStatusFilter: (status) => {
        this.handleStatusFilter(status);
      },

      onSystemFilter: (system) => {
        this.handleSystemFilter(system);
      },

      onClearFilters: () => this.handleClearFilters(),
    });

    this.roleModal = new UserModal({
      onSubmit: (data, isEdit) =>
        this.handleRoleSubmit(data, isEdit),

      onClose: () => this.closeModal(),
    });

    this.rolePermissionModal = new UserModal({
      onSubmit: (data) =>
        this.handleRolePermissionSubmit(data),

      onClose: () =>
        this.closeRolePermissionModal(),
    });

    this.confirmDialog = new ConfirmDialog({
      onConfirm: () =>
        this.executeConfirmedAction(),

      onCancel: () =>
        this.closeConfirmDialog(),
    });

    this._authUnsubscribe = authStore.subscribe(() => {
      this.updateButtonVisibility();
    });

    await this.loadPermissions();
    await this.loadRoles();
  }

  async loadPermissions() {
    try {
      const response = await listPermissions({
        page_size: 1000,
      });

      this.permissions =
        response.permissions ||
        response.items ||
        [];

    } catch (error) {
      console.error(
        'Erreur chargement permissions:',
        error
      );

      this.permissions = [];
    }
  }

  async loadRoles() {
    this.loading = true;
    this.error = null;

    this.renderTableState();

    try {
      const params = {
        page: this.page,
        page_size: this.pageSize,
        search:
          this.filters.search || undefined,

        is_active:
          this.filters.is_active,

        is_system:
          this.filters.is_system,

        sort_by: this.sortBy,
        sort_order: this.sortOrder,
      };

      const response =
        await listRolesAdmin(params);

      if (Array.isArray(response)) {
        this.roles = response;
        this.total = response.length;

        this.page = 1;
        this.pageSize = 20;
        this.totalPages = 1;

      } else {
        this.roles =
          response.roles ||
          response.items ||
          [];

        this.total =
          response.total ||
          this.roles.length;

        this.page =
          response.page ||
          1;

        this.pageSize =
          response.page_size ||
          20;

        this.totalPages =
          response.total_pages ||
          1;
      }

      this.error = null;

    } catch (error) {
      console.error(
        'Erreur chargement rôles:',
        error
      );

      this.error =
        error.message ||
        'Erreur lors du chargement des rôles';

      this.roles = [];
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

    this.loadRoles();
  }

  handleStatusFilter(status) {
    /*
     * UserFilters peut envoyer une valeur lors de son
     * initialisation.
     *
     * On accepte :
     *   '' / null / undefined = Tous
     *   'true'                = Actifs
     *   'false'               = Inactifs
     */

    if (
      status === '' ||
      status === null ||
      status === undefined
    ) {
      this.filters.is_active = null;
    } else {
      this.filters.is_active =
        status === true ||
        status === 'true';
    }

    this.statusFilterInitialized = true;

    console.log(
      'STATUS FILTER',
      status,
      '=>',
      this.filters.is_active
    );

    this.page = 1;
    this.loadRoles();
  }

  handleSystemFilter(system) {
    if (
      system === '' ||
      system === null ||
      system === undefined
    ) {
      this.filters.is_system = null;
    } else {
      this.filters.is_system =
        system === true ||
        system === 'true';
    }

    this.systemFilterInitialized = true;

    this.page = 1;
    this.loadRoles();
  }

  handleClearFilters() {
    this.filters = {
      search: '',
      is_active: null,
      is_system: null,
    };

    this.statusFilterInitialized = false;
    this.systemFilterInitialized = false;

    this.page = 1;

    this.roleFilters?.reset();

    this.loadRoles();
  }

  async handleRoleSubmit(data, isEdit) {
    this.loading = true;

    try {
      if (isEdit) {
        await updateRole(
          this.selectedRole.id,
          data
        );
      } else {
        await createRole(data);
      }

      this.closeModal();

      await this.loadRoles();

      this.showToast(
        isEdit
          ? 'Rôle modifié'
          : 'Rôle créé',
        'success'
      );

    } catch (error) {
      console.error(
        'Erreur rôle:',
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

  async handleRolePermissionSubmit(data) {
    this.loading = true;

    try {
      await addPermissionToRole(
        this.selectedRole.id,
        data.permission_id
      );

      this.closeRolePermissionModal();

      await this.loadRoleDetails(
        this.selectedRole.id
      );

      this.showToast(
        'Permission ajoutée au rôle',
        'success'
      );

    } catch (error) {
      console.error(
        'Erreur permission:',
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

  async loadRoleDetails(roleId) {
    try {
      const role = await getRole(roleId);

      this.selectedRole = role;

      this.selectedRolePermissions =
        role.permissions || [];

    } catch (error) {
      console.error(
        'Erreur chargement détails rôle:',
        error
      );

      this.selectedRolePermissions = [];
    }
  }

  openCreateModal() {
    this.selectedRole = null;

    this.roleModal.open({
      mode: 'create-role',
    });
  }

  openEditModal(role) {
    this.selectedRole = role;

    this.roleModal.open({
      mode: 'edit-role',
      role,
    });
  }

  openManagePermissionsModal(role) {
    this.selectedRole = role;

    this.loadRoleDetails(role.id)
      .then(() => {
        this.rolePermissionModal.open({
          mode: 'manage-permissions',
          role,
          permissions: this.permissions,
          rolePermissions:
            this.selectedRolePermissions,
        });
      });
  }

  confirmToggleActive(role) {
    const action = role.is_active
      ? 'désactiver'
      : 'réactiver';

    this.confirmDialog.open({
      title: `Confirmer la ${action}`,

      message:
        `Êtes-vous sûr de vouloir ${action} le rôle "${role.name}" ?`,

      confirmText:
        action.charAt(0).toUpperCase() +
        action.slice(1),

      variant:
        role.is_active
          ? 'danger'
          : 'primary',
    });

    this.pendingAction = {
      type: 'toggle',
      role,
    };
  }

  async executeToggleActive(role) {
    console.log(
      'TOGGLE ROLE',
      role
    );

    try {
      const newStatus =
        !role.is_active;

      await updateRole(
        role.id,
        {
          is_active: newStatus,
        }
      );

      console.log(
        'ROLE UPDATED',
        role.id,
        newStatus
      );

      this.showToast(
        newStatus
          ? 'Rôle réactivé'
          : 'Rôle désactivé',
        'success'
      );

      /*
       * IMPORTANT :
       * On ne modifie PAS le filtre ici.
       *
       * Si "Tous" était sélectionné,
       * le rôle doit rester visible.
       */
      await this.loadRoles();

    } catch (error) {
      console.error(
        'Erreur activation/désactivation rôle:',
        error
      );

      this.showToast(
        error.message || 'Erreur',
        'error'
      );
    }
  }

  confirmDelete(role) {
    if (role.is_system) {
      this.showToast(
        'Impossible de supprimer un rôle système',
        'error'
      );

      return;
    }

    this.confirmDialog.open({
      title: 'Confirmer la suppression',

      message:
        `Êtes-vous sûr de vouloir supprimer le rôle "${role.name}" ? Cette action est irréversible.`,

      confirmText: 'Supprimer',

      variant: 'danger',
    });

    this.pendingAction = {
      type: 'delete',
      role,
    };
  }

  async executeDelete(role) {
    try {
      await deleteRole(role.id);

      this.showToast(
        'Rôle supprimé',
        'success'
      );

      await this.loadRoles();

    } catch (error) {
      console.error(
        'Erreur suppression rôle:',
        error
      );

      this.showToast(
        error.message ||
        'Erreur suppression',
        'error'
      );
    }
  }

  async executeConfirmedAction() {
    console.log(
      'CONFIRM ACTION',
      this.pendingAction
    );

    if (!this.pendingAction) {
      return;
    }

    const {
      type,
      role,
    } = this.pendingAction;

    this.closeConfirmDialog();

    if (type === 'toggle') {
      await this.executeToggleActive(role);
    }

    if (type === 'delete') {
      await this.executeDelete(role);
    }

    this.pendingAction = null;
  }

  closeModal() {
    this.roleModal?.close();
    this.selectedRole = null;
  }

  closeRolePermissionModal() {
    this.rolePermissionModal?.close();
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

    this.loadRoles();
  }

  onSortChange(
    sortBy,
    sortOrder
  ) {
    this.sortBy = sortBy;
    this.sortOrder = sortOrder;

    this.loadRoles();
  }

  onTabActivate() {
    this.loadRoles();
  }

  updateButtonVisibility() {
    if (this.element) {
      const createBtn =
        this.element.querySelector(
          '[data-action="create-role"]'
        );

      if (createBtn) {
        createBtn.style.display =
          authStore.hasPermission(
            'role_create'
          )
            ? ''
            : 'none';
      }
    }

    this.roleTable
      ?.updateActionVisibility(
        authStore
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

    toast.textContent = message;

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
        '[data-role-table]'
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
        `${this.total} rôle${this.total > 1 ? 's' : ''}`;
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

          <svg width="48"
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
          () => this.loadRoles()
        );

      return;
    }

    this.roleTable.setData({
      items: this.roles,
      total: this.total,
      page: this.page,
      pageSize: this.pageSize,
      totalPages: this.totalPages,
      sortBy: this.sortBy,
      sortOrder: this.sortOrder,
    });

    tableContainer.innerHTML = '';

    tableContainer.appendChild(
      this.roleTable.render()
    );

    this.updateButtonVisibility();
  }

  render() {
    this.element =
      document.createElement('div');

    this.element.className =
      'users-page';

    const canCreate =
      authStore.hasPermission(
        'role_create'
      );

    this.element.innerHTML = `
      <div class="users-header">

        <div class="users-title-area">

          <h1 class="users-title">
            Rôles
          </h1>

          <p
            class="users-count"
            aria-live="polite">

            ${this.total}
            rôle${this.total > 1 ? 's' : ''}

          </p>

        </div>

        ${canCreate ? `
          <button
            class="btn btn-primary"
            data-action="create-role">

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

            Nouveau rôle

          </button>
        ` : ''}

      </div>

      <div
        class="users-toolbar"
        data-role-filters>
      </div>

      <div
        class="table-wrapper"
        data-role-table>
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
        '[data-action="create-role"]'
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
        '[data-role-filters]'
      );

    if (filtersContainer) {
      filtersContainer.appendChild(
        this.roleFilters.render()
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

    this.roleTable?.destroy?.();
    this.roleFilters?.destroy?.();
    this.roleModal?.destroy?.();
    this.rolePermissionModal?.destroy?.();
    this.confirmDialog?.destroy?.();
  }

  _escapeHtml(text) {
    const div =
      document.createElement('div');

    div.textContent =
      text ?? '';

    return div.innerHTML;
  }
}

export function createRolesPage(router) {
  return new RolesPage(router);
}