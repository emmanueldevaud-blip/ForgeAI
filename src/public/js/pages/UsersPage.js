import { authStore } from '../stores/auth.js';
import { UserTable } from '../components/UserTable.js';
import { UserFilters } from '../components/UserFilters.js';
import { UserModal } from '../components/UserModal.js';
import { ConfirmDialog } from '../components/ConfirmDialog.js';
import {
  listUsers,
  createUser,
  updateUser,
  deleteUser,
  toggleUserActive,
  resetUserPassword,
  listRoles,
  assignRoleToUser,
  removeRoleFromUser,
  getUser,
} from '../services/adminApi.js';

export class UsersPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.loading = false;
    this.error = null;
    this.users = [];
    this.total = 0;
    this.page = 1;
    this.pageSize = 20;
    this.totalPages = 1;
    this.sortBy = 'created_at';
    this.sortOrder = 'desc';

    this.filters = {
      search: '',
      role: '',
      is_active: null,
      source: '',
    };

    this.roles = [];
    this.userTable = null;
    this.userFilters = null;
    this.userModal = null;
    this.confirmDialog = null;
    this._authUnsubscribe = null;
    this.selectedUser = null;
    this.selectedUserRoles = [];
    this.pendingAction = null;
  }

  async initialize() {
    this.userTable = new UserTable({
      onEdit: (user) => this.openEditModal(user),
      onToggleActive: (user) =>
        this.confirmToggleActive(user),
      onResetPassword: (user) =>
        this.openResetPasswordModal(user),
      onManageRoles: (user) =>
        this.openManageRolesModal(user),
      onDelete: (user) =>
        this.confirmDelete(user),
      onSort: (sortBy, sortOrder) =>
        this.onSortChange(sortBy, sortOrder),
    });

    this.userFilters = new UserFilters({
      onSearch: (search) =>
        this.handleSearch(search),

      onRoleFilter: (role) =>
        this.handleRoleFilter(role),

      onStatusFilter: (status) =>
        this.handleStatusFilter(status),

      onSourceFilter: (source) =>
        this.handleSourceFilter(source),

      onClearFilters: () =>
        this.handleClearFilters(),

      roles: this.roles,
    });

    this.userModal = new UserModal({
      onSubmit: (data, isEdit) =>
        this.handleUserSubmit(data, isEdit),

      onClose: () =>
        this.closeModal(),

      onAddRole: (roleId) =>
        this.assignRole(
          this.selectedUser.id,
          roleId
        ),

      onRemoveRole: (roleId) =>
        this.removeRole(
          this.selectedUser.id,
          roleId
        ),

      roles: this.roles,
    });

    this.confirmDialog = new ConfirmDialog({
      onConfirm: () =>
        this.executeConfirmedAction(),

      onCancel: () =>
        this.closeConfirmDialog(),
    });

    this._authUnsubscribe =
      authStore.subscribe(() => {
        this.updateButtonVisibility();
      });

    await this.loadRoles();
    await this.loadUsers();
  }

  async loadRoles() {
    try {
      this.roles = await listRoles();

      this.userFilters?.updateRoles(
        this.roles
      );

      this.userModal?.updateRoles(
        this.roles
      );
    } catch (error) {
      console.error(
        'Erreur chargement rôles:',
        error
      );
    }
  }

  async loadUsers() {
    this.loading = true;
    this.error = null;

    this.renderTableState();

    try {
      const params = {
        page: this.page,
        page_size: this.pageSize,
        search:
          this.filters.search || undefined,
        role:
          this.filters.role || undefined,
        is_active:
          this.filters.is_active,
        source:
          this.filters.source || undefined,
        sort_by: this.sortBy,
        sort_order: this.sortOrder,
      };

      const response =
        await listUsers(params);

      this.users =
        response.users || [];

      this.total =
        Number(response.total) || 0;

      this.page =
        Number(response.page) || 1;

      this.pageSize =
        Number(response.page_size) || 20;

      this.totalPages =
        Number(response.total_pages) || 1;

      this.error = null;

    } catch (error) {
      console.error(
        'Erreur chargement utilisateurs:',
        error
      );

      this.error =
        error.message ||
        'Erreur lors du chargement des utilisateurs';

      this.users = [];
      this.total = 0;
      this.totalPages = 1;

    } finally {
      this.loading = false;

      this.renderTableState();

      // Force le rafraîchissement des informations
      // en dehors du tableau.
      this.updateSummary();
    }
  }

  updateSummary() {
    if (!this.element) {
      return;
    }

    // Compteur
    const countElement =
      this.element.querySelector(
        '.users-count'
      );

    if (countElement) {
      countElement.textContent =
        `${this.total} utilisateur${this.total > 1 ? 's' : ''}`;
    }

    // Informations de pagination
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

    // Bouton précédent
    const prevButton =
      this.element.querySelector(
        '[data-page="prev"]'
      );

    if (prevButton) {
      prevButton.disabled =
        this.page <= 1;
    }

    // Bouton suivant
    const nextButton =
      this.element.querySelector(
        '[data-page="next"]'
      );

    if (nextButton) {
      nextButton.disabled =
        this.page >= this.totalPages;
    }
  }

  handleSearch(search) {
    this.filters.search = search;
    this.page = 1;

    this.loadUsers();
  }

  handleRoleFilter(role) {
    this.filters.role = role;
    this.page = 1;

    this.loadUsers();
  }

  handleStatusFilter(status) {
    this.filters.is_active =
      status === ''
        ? null
        : status === 'true';

    this.page = 1;

    this.loadUsers();
  }

  handleSourceFilter(source) {
    this.filters.source = source;
    this.page = 1;

    this.loadUsers();
  }

  handleClearFilters() {
    this.filters = {
      search: '',
      role: '',
      is_active: null,
      source: '',
    };

    this.page = 1;

    this.userFilters?.reset();

    this.loadUsers();
  }

  async handleUserSubmit(data, isEdit) {
    this.loading = true;

    try {
      if (isEdit) {
        await updateUser(
          this.selectedUser.id,
          data
        );
      } else {
        await createUser(data);
      }

      this.closeModal();

      // Recharge complète : tableau + total + pagination
      await this.loadUsers();

      this.showToast(
        isEdit
          ? 'Utilisateur modifié'
          : 'Utilisateur créé',
        'success'
      );

    } catch (error) {
      console.error(
        'Erreur utilisateur:',
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
    this.selectedUser = null;

    this.userModal.open({
      mode: 'create',
      roles: this.roles,
    });
  }

  openEditModal(user) {
    this.selectedUser = user;

    this.userModal.open({
      mode: 'edit',
      user,
      roles: this.roles,
    });
  }

  openResetPasswordModal(user) {
    this.selectedUser = user;

    this.userModal.open({
      mode: 'reset-password',
      user,
    });
  }

  openManageRolesModal(user) {
    this.selectedUser = user;

    this.loadUserRoles(user.id)
      .then(() => {
        this.userModal.open({
          mode: 'manage-roles',
          user,
          roles: this.roles,
          userRoles:
            this.selectedUserRoles,
        });
      });
  }

  async loadUserRoles(userId) {
    try {
      const user =
        await getUser(userId);

      this.selectedUserRoles =
        user.roles || [];

    } catch (error) {
      console.error(
        'Erreur chargement rôles utilisateur:',
        error
      );

      this.selectedUserRoles = [];
    }
  }

  async assignRole(userId, roleId) {
    this.userModal.form?.setSubmitting(
      true
    );

    try {
      await assignRoleToUser(
        userId,
        roleId
      );

      this.showToast(
        'Rôle attribué',
        'success'
      );

      await this.loadUserRoles(
        userId
      );

      this.userModal.updateUserRoles(
        this.selectedUserRoles
      );

    } catch (error) {
      this.showToast(
        error.message ||
        'Erreur attribution rôle',
        'error'
      );

    } finally {
      this.userModal.form?.setSubmitting(
        false
      );
    }
  }

  async removeRole(userId, roleId) {
    this.userModal.form?.setSubmitting(
      true
    );

    try {
      await removeRoleFromUser(
        userId,
        roleId
      );

      this.showToast(
        'Rôle retiré',
        'success'
      );

      await this.loadUserRoles(
        userId
      );

      this.userModal.updateUserRoles(
        this.selectedUserRoles
      );

    } catch (error) {
      this.showToast(
        error.message ||
        'Erreur retrait rôle',
        'error'
      );

    } finally {
      this.userModal.form?.setSubmitting(
        false
      );
    }
  }

  confirmToggleActive(user) {
    const action =
      user.is_active
        ? 'désactiver'
        : 'réactiver';

    this.confirmDialog.open({
      title: `Confirmer la ${action}`,

      message:
        `Êtes-vous sûr de vouloir ${action} l'utilisateur "${user.username}" ?`,

      confirmText:
        action.charAt(0).toUpperCase() +
        action.slice(1),

      variant:
        user.is_active
          ? 'danger'
          : 'primary',
    });

    this.pendingAction = {
      type: 'toggle',
      user,
    };
  }

  async executeToggleActive(user) {
    try {
      await toggleUserActive(
        user.id,
        !user.is_active
      );

      this.showToast(
        user.is_active
          ? 'Utilisateur désactivé'
          : 'Utilisateur réactivé',
        'success'
      );

      await this.loadUsers();

    } catch (error) {
      console.error(
        'Erreur activation/désactivation:',
        error
      );

      this.showToast(
        error.message || 'Erreur',
        'error'
      );
    }
  }

  confirmDelete(user) {
    this.confirmDialog.open({
      title:
        'Confirmer la suppression',

      message:
        `Êtes-vous sûr de vouloir supprimer l'utilisateur "${user.username}" ? Cette action est irréversible.`,

      confirmText:
        'Supprimer',

      variant:
        'danger',
    });

    this.pendingAction = {
      type: 'delete',
      user,
    };
  }

  async executeDelete(user) {
    try {
      await deleteUser(
        user.id
      );

      // Recharge complète :
      // tableau + total + pagination
      await this.loadUsers();

      this.showToast(
        'Utilisateur supprimé',
        'success'
      );

    } catch (error) {
      console.error(
        'Erreur suppression utilisateur:',
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
    if (!this.pendingAction) {
      return;
    }

    const {
      type,
      user,
    } = this.pendingAction;

    this.closeConfirmDialog();

    if (type === 'toggle') {
      await this.executeToggleActive(
        user
      );
    } else if (type === 'delete') {
      await this.executeDelete(
        user
      );
    }

    this.pendingAction = null;
  }

  closeModal() {
    this.userModal?.close();
    this.selectedUser = null;
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

    this.loadUsers();
  }

  onSortChange(
    sortBy,
    sortOrder
  ) {
    this.sortBy = sortBy;
    this.sortOrder = sortOrder;

    this.page = 1;

    this.loadUsers();
  }

  onTabActivate() {
    this.loadUsers();
  }

  updateButtonVisibility() {
    if (this.element) {
      const createBtn =
        this.element.querySelector(
          '[data-action="create-user"]'
        );

      if (createBtn) {
        createBtn.style.display =
          authStore.hasPermission(
            'user_create'
          )
            ? ''
            : 'none';
      }
    }

    this.userTable?.updateActionVisibility(
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
        document.createElement(
          'div'
        );

      container.id =
        'toast-container';

      container.className =
        'toast-container';

      document.body.appendChild(
        container
      );
    }

    container.appendChild(
      toast
    );

    requestAnimationFrame(
      () => {
        toast.classList.add(
          'toast--visible'
        );
      }
    );

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
        '[data-user-table]'
      );

    if (!tableContainer) {
      return;
    }

    // Mise à jour immédiate du résumé
    this.updateSummary();

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
          () => this.loadUsers()
        );

      return;
    }

    this.userTable.setData({
      users: this.users,
      total: this.total,
      page: this.page,
      pageSize: this.pageSize,
      totalPages: this.totalPages,
      sortBy: this.sortBy,
      sortOrder: this.sortOrder,
    });

    tableContainer.innerHTML = '';

    tableContainer.appendChild(
      this.userTable.render()
    );

    this.updateButtonVisibility();
  }

  render() {
    this.element =
      document.createElement(
        'div'
      );

    this.element.className =
      'users-page';

    const canCreate =
      authStore.hasPermission(
        'user_create'
      );

    this.element.innerHTML = `
      <div class="users-header">

        <div class="users-title-area">

          <h1 class="users-title">
            Utilisateurs
          </h1>

          <p
            class="users-count"
            aria-live="polite">

            ${this.total}
            utilisateur${this.total > 1 ? 's' : ''}

          </p>

        </div>

        ${canCreate ? `
          <button
            class="btn btn-primary"
            data-action="create-user">

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

            Nouvel utilisateur

          </button>
        ` : ''}

      </div>

      <div
        class="users-toolbar"
        data-user-filters>
      </div>

      <div
        class="table-wrapper"
        data-user-table>
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
        '[data-action="create-user"]'
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
        '[data-user-filters]'
      );

    if (filtersContainer) {
      filtersContainer.appendChild(
        this.userFilters.render()
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

    this.userTable?.destroy?.();
    this.userFilters?.destroy?.();
    this.userModal?.destroy?.();
    this.confirmDialog?.destroy?.();
  }

  _escapeHtml(text) {
    const div =
      document.createElement(
        'div'
      );

    div.textContent =
      text ?? '';

    return div.innerHTML;
  }
}

export function createUsersPage(router) {
  return new UsersPage(router);
}
