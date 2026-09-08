import { GroupModal } from '../components/GroupModal.js';
import { authStore } from '../stores/auth.js';
import { Table } from '../components/Table.js';
import { UserFilters } from '../components/UserFilters.js';
import { UserModal } from '../components/UserModal.js';
import { ConfirmDialog } from '../components/ConfirmDialog.js';
import {
  listGroups,
  createGroup,
  getGroup,
  updateGroup,
  deleteGroup,
  addUserToGroup,
  removeUserFromGroup,
  addRoleToGroup,
  removeRoleFromGroup,
  listRoles,
  listUsers,
} from '../services/adminApi.js';

export class GroupsPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.loading = false;
    this.error = null;
    this.groups = [];
    this.total = 0;
    this.page = 1;
    this.pageSize = 20;
    this.totalPages = 1;
    this.sortBy = 'created_at';
    this.sortOrder = 'desc';

    this.filters = {
      search: '',
      is_active: null,
    };

    this.roles = [];
    this.users = [];

    this.groupTable = null;
    this.groupFilters = null;
    this.groupModal = null;
    this.groupUserModal = null;
    this.groupRoleModal = null;
    this.confirmDialog = null;

    this._authUnsubscribe = null;
    this.selectedGroup = null;
    this.selectedGroupUsers = [];
    this.selectedGroupRoles = [];
    this.pendingAction = null;
  }

  async initialize() {
    this.groupTable = new Table({
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
          key: 'source',
          label: 'Source',
          sortable: false,
          render: (group) => group.source === 'ad'
            ? '<span class="status-badge status-active">AD</span>'
            : '<span class="status-badge status-inactive">Local</span>',
        },
        {
          key: 'description',
          label: 'Description',
          sortable: false,
        },
        {
          key: 'is_active',
          label: 'Statut',
          sortable: true,
			render: (group) => group.is_active
			  ? '<span class="status-badge active">Actif</span>'
			  : '<span class="status-badge inactive">Inactif</span>',
        },
        {
          key: 'user_count',
          label: 'Utilisateurs',
          sortable: true,
        },
      ],

      actions: [
        {
          key: 'edit',
          label: 'Modifier',
          icon: 'edit',
          disabled: (group) => group.source === 'ad',
        },
        {
          key: 'toggle',
          label: 'Activer/Désactiver',
          icon: 'power',
          disabled: (group) => group.source === 'ad',
        },
        {
          key: 'roles',
          label: 'Gérer les rôles',
          icon: 'users',
        },
        {
          key: 'delete',
          label: 'Supprimer',
          icon: 'trash',
          disabled: (group) => group.source === 'ad',
        },
      ],

      onAction: (action, group) => {
        switch (action) {
          case 'edit':
            this.openEditModal(group);
            break;

          case 'toggle':
            this.confirmToggleActive(group);
            break;

          case 'roles':
            this.openManageRolesModal(group);
            break;

          case 'delete':
            this.confirmDelete(group);
            break;

          default:
            break;
        }
      },

      onSort: (sortBy, sortOrder) => {
        this.onSortChange(sortBy, sortOrder);
      },
    });

    this.groupFilters = new UserFilters({
      onSearch: (search) => this.handleSearch(search),
      onStatusFilter: (status) => this.handleStatusFilter(status),
      onClearFilters: () => this.handleClearFilters(),
    });

	this.groupModal = new GroupModal({
	  onSubmit: (data, isEdit) => this.handleGroupSubmit(data, isEdit),
	  onClose: () => this.closeModal(),
	});

    this.groupUserModal = new UserModal({
      onSubmit: (data) => this.handleGroupUserSubmit(data),
      onClose: () => this.closeGroupUserModal(),
    });

    this.groupRoleModal = new UserModal({
      onSubmit: (data) => this.handleGroupRoleSubmit(data),
      onClose: () => this.closeGroupRoleModal(),
      onAddRole: (roleId) => this.handleGroupRoleAdd(roleId),
      onRemoveRole: (roleId) => this.handleGroupRoleRemove(roleId),
    });

    this.confirmDialog = new ConfirmDialog({
      onConfirm: () => this.executeConfirmedAction(),
      onCancel: () => this.closeConfirmDialog(),
    });

    this._authUnsubscribe = authStore.subscribe(() => {
      this.updateButtonVisibility();
    });

    await this.loadRoles();
    await this.loadUsers();
    await this.loadGroups();
  }

  async loadRoles() {
    try {
      this.roles = await listRoles();
    } catch (error) {
      console.error('Erreur chargement rôles:', error);
    }
  }

  async loadUsers() {
    try {
      const response = await listUsers({ page_size: 1000 });
      this.users = response.users || [];
    } catch (error) {
      console.error('Erreur chargement utilisateurs:', error);
      this.users = [];
    }
  }

  async loadGroups() {
    this.loading = true;
    this.error = null;
    this.renderTableState();

    try {
      const params = {
        page: this.page,
        page_size: this.pageSize,
        search: this.filters.search || undefined,
        is_active: this.filters.is_active,
        sort_by: this.sortBy,
        sort_order: this.sortOrder,
      };

      const response = await listGroups(params);

      this.groups = response.groups || [];
      this.total = response.total || 0;
      this.page = response.page || 1;
      this.pageSize = response.page_size || 20;
      this.totalPages = response.total_pages || 1;

      this.error = null;
    } catch (error) {
      this.error = error.message || 'Erreur lors du chargement des groupes';
      this.groups = [];
      this.total = 0;
    } finally {
      this.loading = false;
      this.renderTableState();
    }
  }

  handleSearch(search) {
    this.filters.search = search;
    this.page = 1;
    this.loadGroups();
  }

  handleStatusFilter(status) {
    this.filters.is_active = status === '' ? null : status === 'true';
    this.page = 1;
    this.loadGroups();
  }

  handleClearFilters() {
    this.filters = {
      search: '',
      is_active: null,
    };

    this.page = 1;
    this.groupFilters.reset();
    this.loadGroups();
  }

  async handleGroupSubmit(data, isEdit) {
    this.loading = true;

    try {
      if (isEdit) {
        await updateGroup(this.selectedGroup.id, data);
      } else {
        await createGroup(data);
      }

      this.closeModal();
      await this.loadGroups();

      this.showToast(
        isEdit ? 'Groupe modifié' : 'Groupe créé',
        'success'
      );
    } catch (error) {
      this.showToast(error.message || 'Erreur', 'error');
    } finally {
      this.loading = false;
    }
  }

  async handleGroupUserSubmit(data) {
    this.loading = true;

    try {
      await addUserToGroup(this.selectedGroup.id, data.user_id);

      this.closeGroupUserModal();
      await this.loadGroupDetails(this.selectedGroup.id);

      this.showToast('Utilisateur ajouté au groupe', 'success');
    } catch (error) {
      this.showToast(error.message || 'Erreur', 'error');
    } finally {
      this.loading = false;
    }
  }

  async handleGroupRoleSubmit(data) {
    this.loading = true;

    try {
      await addRoleToGroup(this.selectedGroup.id, data.role_id);

      this.closeGroupRoleModal();
      await this.loadGroupDetails(this.selectedGroup.id);

      this.showToast('Rôle ajouté au groupe', 'success');
    } catch (error) {
      this.showToast(error.message || 'Erreur', 'error');
    } finally {
      this.loading = false;
    }
  }

  async handleGroupRoleAdd(roleId) {
    try {
      await addRoleToGroup(this.selectedGroup.id, roleId);

      const addedRole = this.roles.find(r => r.id === roleId);
      if (addedRole && !this.selectedGroupRoles.some(r => r.id === roleId)) {
        this.selectedGroupRoles.push(addedRole);
      }

      this.groupRoleModal.updateUserRoles(this.selectedGroupRoles);
      this.showToast('Rôle ajouté au groupe', 'success');
    } catch (error) {
      this.showToast(error.message || 'Erreur lors de l\'ajout du rôle', 'error');
    }
  }

  async handleGroupRoleRemove(roleId) {
    try {
      await removeRoleFromGroup(this.selectedGroup.id, roleId);

      this.selectedGroupRoles = this.selectedGroupRoles.filter(r => r.id !== roleId);

      this.groupRoleModal.updateUserRoles(this.selectedGroupRoles);
      this.showToast('Rôle retiré du groupe', 'success');
    } catch (error) {
      this.showToast(error.message || 'Erreur lors du retrait du rôle', 'error');
    }
  }

  async loadGroupDetails(groupId) {
    try {
      const group = await getGroup(groupId);

      this.selectedGroup = group;
      this.selectedGroupUsers = group.users || [];
      this.selectedGroupRoles = group.roles || [];
    } catch (error) {
      console.error('Erreur chargement détails groupe:', error);
      this.selectedGroupUsers = [];
      this.selectedGroupRoles = [];
    }
  }

  openCreateModal() {
    this.selectedGroup = null;

    this.groupModal.open({
      mode: 'create-group',
      roles: this.roles,
    });
  }

  openEditModal(group) {
    this.selectedGroup = group;

    this.groupModal.open({
      mode: 'edit-group',
      group,
      roles: this.roles,
    });
  }

  openManageUsersModal(group) {
    this.selectedGroup = group;

    this.loadGroupDetails(group.id).then(() => {
      this.groupUserModal.open({
        mode: 'manage-users',
        group,
        users: this.users,
        groupUsers: this.selectedGroupUsers,
      });
    });
  }

  async openManageRolesModal(group) {
    this.selectedGroup = group;

    await this.loadGroupDetails(group.id);

    this.groupRoleModal.open({
      mode: 'manage-roles',
      group,
      roles: this.roles,
      userRoles: this.selectedGroupRoles,
    });
  }

  confirmToggleActive(group) {
    const action = group.is_active ? 'désactiver' : 'réactiver';

    this.confirmDialog.open({
      title: `Confirmer la ${action}`,
      message: `Êtes-vous sûr de vouloir ${action} le groupe "${group.name}" ?`,
      confirmText: action.charAt(0).toUpperCase() + action.slice(1),
      variant: group.is_active ? 'danger' : 'primary',
    });

    this.pendingAction = {
      type: 'toggle',
      group,
    };
  }

  async executeToggleActive(group) {
    try {
      await updateGroup(group.id, {
        is_active: !group.is_active,
      });

      this.showToast(
        group.is_active
          ? 'Groupe désactivé'
          : 'Groupe réactivé',
        'success'
      );

      await this.loadGroups();
    } catch (error) {
      this.showToast(error.message || 'Erreur', 'error');
    }
  }

confirmDelete(group) {
  this.confirmDialog.open({
    title: 'Confirmer la suppression',
    message: `Êtes-vous sûr de vouloir supprimer le groupe "${group.name}" ? Cette action est irréversible.`,
    confirmText: 'Supprimer',
    variant: 'danger',
  });

  this.pendingAction = {
    type: 'delete',
    group,
  };
}

  async executeDelete(group) {
    try {
      await deleteGroup(group.id);

      this.showToast('Groupe supprimé', 'success');

      await this.loadGroups();
    } catch (error) {
      this.showToast(error.message || 'Erreur suppression', 'error');
    }
  }

  async executeConfirmedAction() {
    if (!this.pendingAction) return;

    const {
      type,
      group,
    } = this.pendingAction;

    this.closeConfirmDialog();

    if (type === 'toggle') {
      await this.executeToggleActive(group);
    } else if (type === 'delete') {
      await this.executeDelete(group);
    }

    this.pendingAction = null;
  }

  closeModal() {
    this.groupModal.close();
    this.selectedGroup = null;
  }

  closeGroupUserModal() {
    this.groupUserModal.close();
  }

  closeGroupRoleModal() {
    this.groupRoleModal.close();
  }

  closeConfirmDialog() {
    this.confirmDialog.close();
    this.pendingAction = null;
  }

  onPageChange(page) {
    this.page = page;
    this.loadGroups();
  }

  onSortChange(sortBy, sortOrder) {
    this.sortBy = sortBy;
    this.sortOrder = sortOrder;
    this.loadGroups();
  }

  onTabActivate() {
    this.loadGroups();
  }

  updateButtonVisibility() {
    if (this.element) {
      const createBtn = this.element.querySelector(
        '[data-action="create-group"]'
      );

      if (createBtn) {
        createBtn.style.display = authStore.hasPermission('group_create')
          ? ''
          : 'none';
      }
    }

    this.groupTable?.updateActionVisibility(authStore);
  }

  showToast(message, type = 'info') {
    const toast = document.createElement('div');

    toast.className = `toast toast--${type}`;
    toast.textContent = message;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'polite');

    let container = document.getElementById('toast-container');

    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }

    container.appendChild(toast);

    requestAnimationFrame(() => {
      toast.classList.add('toast--visible');
    });

    setTimeout(() => {
      toast.classList.remove('toast--visible');

      setTimeout(() => {
        toast.remove();
      }, 300);
    }, 3000);
  }

  renderTableState() {
    if (!this.element) return;

    const tableContainer = this.element.querySelector(
      '[data-group-table]'
    );

    if (!tableContainer) return;
	
		const countElement = this.element.querySelector('.users-count');

		if (countElement) {
		  countElement.textContent =
			`${this.total} groupe${this.total > 1 ? 's' : ''}`;
		}

		const paginationInfo = this.element.querySelector('.pagination-info');

		if (paginationInfo) {
			const prevButton = this.element.querySelector('[data-page="prev"]');
				const nextButton = this.element.querySelector('[data-page="next"]');

				if (prevButton) {
				  prevButton.disabled = this.page <= 1;
				}

				if (nextButton) {
				  nextButton.disabled = this.page >= this.totalPages;
				}

		  paginationInfo.innerHTML = `
			Page <strong>${this.page}</strong>
			sur <strong>${this.totalPages}</strong>
			(${this.total} total)
		  `;
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
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>

          <h3>Erreur</h3>

          <p>${this._escapeHtml(this.error)}</p>

          <button class="btn btn-primary" data-action="retry">
            Réessayer
          </button>
        </div>
      `;

      tableContainer
        .querySelector('[data-action="retry"]')
        ?.addEventListener('click', () => this.loadGroups());

      return;
    }

    this.groupTable.setData({
      items: this.groups,
      total: this.total,
      page: this.page,
      pageSize: this.pageSize,
      totalPages: this.totalPages,
      sortBy: this.sortBy,
      sortOrder: this.sortOrder,
    });

    tableContainer.innerHTML = '';
    tableContainer.appendChild(this.groupTable.render());
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'users-page';

    const canCreate = authStore.hasPermission('group_create');

    this.element.innerHTML = `
      <div class="users-header">
        <div class="users-title-area">
          <h1 class="users-title">Groupes</h1>

          <p class="users-count" aria-live="polite">
            ${this.total} groupe${this.total > 1 ? 's' : ''}
          </p>
        </div>

        ${canCreate ? `
          <button class="btn btn-primary" data-action="create-group">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
            Nouveau groupe
          </button>
        ` : ''}
      </div>

      <div class="users-toolbar" data-group-filters></div>

      <div class="table-wrapper" data-group-table></div>

      <div class="users-pagination" data-pagination aria-label="Pagination">
        <div class="pagination-info">
          Page <strong>${this.page}</strong>
          sur <strong>${this.totalPages}</strong>
          (${this.total} total)
        </div>

        <div class="pagination-controls">
          <button
            class="btn btn-sm btn-secondary"
            data-page="prev"
            ${this.page <= 1 ? 'disabled' : ''}
            aria-label="Page précédente"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="15 18 9 12 15 6"></polyline>
            </svg>
          </button>

          <button
            class="btn btn-sm btn-secondary"
            data-page="next"
            ${this.page >= this.totalPages ? 'disabled' : ''}
            aria-label="Page suivante"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6"></polyline>
            </svg>
          </button>
        </div>
      </div>
    `;

    this.element
      .querySelector('[data-action="create-group"]')
      ?.addEventListener('click', () => this.openCreateModal());

    this.element
      .querySelector('[data-page="prev"]')
      ?.addEventListener('click', () => {
        this.onPageChange(this.page - 1);
      });

    this.element
      .querySelector('[data-page="next"]')
      ?.addEventListener('click', () => {
        this.onPageChange(this.page + 1);
      });

    const filtersContainer = this.element.querySelector(
      '[data-group-filters]'
    );

    if (filtersContainer) {
      filtersContainer.appendChild(this.groupFilters.render());
    }

    this.renderTableState();

    return this.element;
  }

  mount(container) {
    if (!this.element) {
      this.render();
    }

    container.innerHTML = '';
    container.appendChild(this.element);

    return this;
  }

  destroy() {
    this._authUnsubscribe?.();
    this.groupTable?.destroy?.();
    this.groupFilters?.destroy?.();
    this.groupModal?.destroy?.();
    this.groupUserModal?.destroy?.();
    this.groupRoleModal?.destroy?.();
    this.confirmDialog?.destroy?.();
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}

export function createGroupsPage(router) {
  return new GroupsPage(router);
}
