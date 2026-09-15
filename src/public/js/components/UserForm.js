export class UserForm {
  constructor(options = {}) {
    this.mode = options.mode || 'create';
    this.user = options.user || null;
    this.roles = options.roles || [];
    this.groups = options.groups || [];
    this.userRoles = options.userRoles || [];
    this.onSubmit = options.onSubmit || (() => {});
    this.onClose = options.onClose || (() => {});
    this.onSavePermissions = options.onSavePermissions || (() => {});
    this.element = null;
    this.submitting = false;


  }

  _getRoleOptions(selectedRole = '') {
    return this.roles.map(role => `
      <option value="${this._escapeHtml(role.code)}" ${role.code === selectedRole ? 'selected' : ''}>
        ${this._escapeHtml(role.name)}
      </option>
    `).join('');
  }

  _getGroupSelectHtml() {
    const localGroups = (this.groups || []).filter(g => g.source !== 'ad');
    const userGroupIds = (this.user?.groups || []).map(g => g.id);
    const selectedGroups = localGroups.filter(g => userGroupIds.includes(g.id));

    if (localGroups.length === 0) {
      return '<p class="form-hint">Aucun groupe local disponible</p>';
    }

    const tagsHtml = selectedGroups.map(g => `
      <span class="multiselect-tag" data-group-id="${g.id}">
        ${this._escapeHtml(g.name)}
        <button type="button" class="multiselect-tag-remove" data-action="remove-group" data-group-id="${g.id}" aria-label="Retirer ${this._escapeHtml(g.name)}">&times;</button>
      </span>
    `).join('');

    const optionsHtml = localGroups.map(g => `
      <div class="multiselect-option${userGroupIds.includes(g.id) ? ' multiselect-option--selected' : ''}" data-group-id="${g.id}" data-group-name="${this._escapeHtml(g.name)}">
        <span class="multiselect-option-check">${userGroupIds.includes(g.id) ? '&#10003;' : ''}</span>
        <span class="multiselect-option-name">${this._escapeHtml(g.name)}</span>
      </div>
    `).join('');

    return `
      <div class="multiselect" data-field="groups">
        <div class="multiselect-control" data-action="toggle-dropdown">
          <div class="multiselect-tags">
            ${tagsHtml || '<span class="multiselect-placeholder">Sélectionner des groupes...</span>'}
          </div>
          <svg class="multiselect-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
        </div>
        <div class="multiselect-dropdown">
          <div class="multiselect-search">
            <input type="text" class="multiselect-search-input" placeholder="Rechercher..." data-action="search-groups">
          </div>
          <div class="multiselect-options">
            ${optionsHtml}
          </div>
        </div>
      </div>
    `;
  }

  _getAssignedRolesHtml() {
    if (!this.userRoles || this.userRoles.length === 0) {
      return '<p class="form-hint">Aucun rôle assigné</p>';
    }

    return this.userRoles.map(r => `
      <div class="assigned-role">
        <span class="role-badge ${r.code === 'admin' ? 'admin' : 'user'}">
          ${this._escapeHtml(r.name)}
        </span>

        <button
          type="button"
          class="action-btn"
          data-action="remove-role"
          data-role-id="${r.id}"
          aria-label="Retirer le rôle ${this._escapeHtml(r.name)}">

          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2">

            <line
              x1="18"
              y1="6"
              x2="6"
              y2="18">
            </line>

            <line
              x1="6"
              y1="6"
              x2="18"
              y2="18">
            </line>

          </svg>
        </button>
      </div>
    `).join('');
  }

  _getAvailableRolesHtml() {
    const assignedIds = new Set(
      this.userRoles?.map(r => r.id) || []
    );

    const available = this.roles.filter(
      r => !assignedIds.has(r.id)
    );

    if (available.length === 0) {
      return '<p class="form-hint">Tous les rôles sont déjà assignés</p>';
    }

    return available.map(r => `
      <div class="available-role">

        <span>
          ${this._escapeHtml(r.name)}
        </span>

        <button
          type="button"
          class="btn btn-sm btn-outline"
          data-action="add-role"
          data-role-id="${r.id}">

          Ajouter

        </button>

      </div>
    `).join('');
  }

  _getCreateFieldsHtml() {
    const entityType =
      this.mode === 'create-group'
        ? 'groupe'
        : this.mode === 'create-role'
        ? 'rôle'
        : this.mode === 'create-permission'
        ? 'permission'
        : 'utilisateur';

    const entityName =
      this.mode === 'create-group'
        ? 'Nom du groupe'
        : this.mode === 'create-role'
        ? 'Nom du rôle'
        : this.mode === 'create-permission'
        ? 'Code de la permission'
        : "Nom d'utilisateur";

    const entityNameField =
      this.mode === 'create-group'
        ? 'name'
        : this.mode === 'create-role'
        ? 'name'
        : this.mode === 'create-permission'
        ? 'code'
        : 'username';

    const entityNamePlaceholder =
      this.mode === 'create-group'
        ? 'Nom du groupe'
        : this.mode === 'create-role'
        ? 'Nom du rôle'
        : this.mode === 'create-permission'
        ? 'Code (ex: users.view)'
        : "Nom d'utilisateur";

    let fieldsHtml = `
      <div class="form-row">

        <div class="form-group">

          <label for="${entityNameField}">
            ${entityName}
            <span class="required">*</span>
          </label>

          <input
            type="text"
            id="${entityNameField}"
            name="${entityNameField}"
            placeholder="${entityNamePlaceholder}"
            required
            minlength="${
              this.mode === 'create-group'
                ? '1'
                : this.mode === 'create-role'
                ? '1'
                : this.mode === 'create-permission'
                ? '1'
                : '3'
            }"
            maxlength="${
              this.mode === 'create-group'
                ? '100'
                : this.mode === 'create-role'
                ? '100'
                : this.mode === 'create-permission'
                ? '100'
                : '50'
            }"
            autocomplete="${
              this.mode === 'create-permission'
                ? 'off'
                : 'username'
            }"
            ${!this.mode.includes('create') ? 'disabled' : ''}>

        </div>
    `;

    if (
      this.mode === 'create-group' ||
      this.mode === 'create-role'
    ) {
      fieldsHtml += `
        <div class="form-group">

          <label for="description">
            Description
          </label>

          <textarea
            id="description"
            name="description"
            maxlength="500"
            rows="3">
          </textarea>

        </div>
      `;
    } else if (this.mode === 'create-permission') {
      fieldsHtml += `
        <div class="form-group">

          <label for="name">
            Nom
            <span class="required">*</span>
          </label>

          <input
            type="text"
            id="name"
            name="name"
            required
            maxlength="150"
            autocomplete="off">

        </div>

        <div class="form-group">

          <label for="module">
            Module
          </label>

          <select
            id="module"
            name="module">

            <option value="">
              -- Sélectionner --
            </option>

            <option value="rbac">
              RBAC
            </option>

            <option value="module">
              Module
            </option>

            <option value="ad">
              Active Directory
            </option>

            <option value="audit">
              Audit
            </option>

            <option value="settings">
              Paramètres
            </option>

            <option value="dashboard">
              Tableau de bord
            </option>

          </select>

        </div>
      `;
    } else {
      /*
       * UTILISATEUR
       *
       * Pas de case "Administrateur"
       * Pas de case "Actif"
       *
       * Le rôle détermine les permissions.
       * Le statut actif est géré ailleurs.
       */
      fieldsHtml += `
        <div class="form-group">

          <label for="email">
            Email
            <span class="required">*</span>
          </label>

          <input
            type="email"
            id="email"
            name="email"
            required
            maxlength="255"
            autocomplete="email">

        </div>

        <div class="form-group">

          <label for="first_name">
            Prénom
          </label>

          <input
            type="text"
            id="first_name"
            name="first_name"
            maxlength="100"
            autocomplete="given-name">

        </div>

        <div class="form-group">

          <label for="last_name">
            Nom
          </label>

          <input
            type="text"
            id="last_name"
            name="last_name"
            maxlength="100"
            autocomplete="family-name">

        </div>

        <div class="form-row">

          <div class="form-group">

            <label for="password">
              Mot de passe
              <span class="required">*</span>
            </label>

            <input
              type="password"
              id="password"
              name="password"
              required
              minlength="8"
              maxlength="128"
              autocomplete="new-password">

            <p class="form-hint">
              Minimum 8 caractères
            </p>

          </div>

          <div class="form-group">

            <label for="confirm_password">
              Confirmer le mot de passe
              <span class="required">*</span>
            </label>

            <input
              type="password"
              id="confirm_password"
              name="confirm_password"
              required
              autocomplete="new-password">

          </div>

        </div>

        <div class="form-group">

          <label for="role">
            Rôle
            <span class="required">*</span>
          </label>

          <select
            id="role"
            name="role"
            required>

            <option value="">
              Sélectionner un rôle
            </option>

            ${this._getRoleOptions()}

          </select>

        </div>
      `;
    }

    fieldsHtml += `
      </div>
    `;

    return fieldsHtml;
  }

  _getEditFieldsHtml() {
    if (this.mode === 'edit-role') {
      return `
        <div class="form-row">
          <div class="form-group">
            <label for="name">Nom</label>
            <input
              type="text"
              id="name"
              name="name"
              value="${this._escapeHtml(this.user?.name || '')}"
              maxlength="100">
          </div>
        </div>
        <div class="form-group">
          <label for="description">Description</label>
          <textarea
            id="description"
            name="description"
            maxlength="500"
            rows="3">${this._escapeHtml(this.user?.description || '')}</textarea>
        </div>
      `;
    }

    if (this.mode === 'edit-group') {
      return `
        <div class="form-row">
          <div class="form-group">
            <label for="name">Nom</label>
            <input
              type="text"
              id="name"
              name="name"
              value="${this._escapeHtml(this.user?.name || '')}"
              maxlength="100">
          </div>
        </div>
        <div class="form-group">
          <label for="description">Description</label>
          <textarea
            id="description"
            name="description"
            maxlength="500"
            rows="3">${this._escapeHtml(this.user?.description || '')}</textarea>
        </div>
      `;
    }

    if (this.mode === 'edit-permission') {
      return `
        <div class="form-row">
          <div class="form-group">
            <label for="name">Nom <span class="required">*</span></label>
            <input
              type="text"
              id="name"
              name="name"
              value="${this._escapeHtml(this.user?.name || '')}"
              required
              maxlength="150"
              autocomplete="off">
          </div>
        </div>
        <div class="form-group">
          <label for="module">Module</label>
          <select id="module" name="module">
            <option value="">-- Sélectionner --</option>
            <option value="rbac">RBAC</option>
            <option value="module">Module</option>
            <option value="ad">Active Directory</option>
            <option value="audit">Audit</option>
            <option value="settings">Paramètres</option>
            <option value="dashboard">Tableau de bord</option>
          </select>
        </div>
      `;
    }

    let fieldsHtml = `
      <div class="form-row">
        <div class="form-group">
          <label for="username">Nom d'utilisateur</label>
          <input
            type="text"
            id="username"
            name="username"
            value="${this._escapeHtml(this.user?.username || '')}"
            disabled>
          <p class="form-hint">Le nom d'utilisateur ne peut pas être modifié</p>
        </div>
        <div class="form-group">
          <label for="email">Email <span class="required">*</span></label>
          <input
            type="email"
            id="email"
            name="email"
            value="${this._escapeHtml(this.user?.email || '')}"
            required
            maxlength="255">
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label for="first_name">Prénom</label>
          <input
            type="text"
            id="first_name"
            name="first_name"
            value="${this._escapeHtml(this.user?.first_name || '')}"
            maxlength="100">
        </div>
        <div class="form-group">
          <label for="last_name">Nom</label>
          <input
            type="text"
            id="last_name"
            name="last_name"
            value="${this._escapeHtml(this.user?.last_name || '')}"
            maxlength="100">
        </div>
      </div>
      ${this.user?.source !== 'ad' ? `
      <div class="form-group">
        <label>Groupes locaux</label>
        ${this._getGroupSelectHtml()}
        <p class="form-hint">Assignez cet utilisateur à des groupes locaux uniquement</p>
      </div>
      ` : ''}
    `;

    return fieldsHtml;
  }

  _getResetPasswordFieldsHtml() {
    return `
      <div class="ad-status ad-status--warning">

        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2">

          <path
            d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z">
          </path>

          <line
            x1="12"
            y1="9"
            x2="12"
            y2="13">
          </line>

          <line
            x1="12"
            y1="17"
            x2="12.01"
            y2="17">
          </line>

        </svg>

        <div>

          <strong>
            Réinitialisation du mot de passe
          </strong>

          <p>
            L'utilisateur
            <strong>
              ${this._escapeHtml(this.user?.username || '')}
            </strong>
            recevra un nouveau mot de passe.
            L'ancien mot de passe ne fonctionnera plus.
          </p>

        </div>

      </div>

      <div class="form-row">

        <div class="form-group">

          <label for="new_password">
            Nouveau mot de passe
            <span class="required">*</span>
          </label>

          <input
            type="password"
            id="new_password"
            name="new_password"
            required
            minlength="8"
            maxlength="128"
            autocomplete="new-password">

          <p class="form-hint">
            Minimum 8 caractères
          </p>

        </div>

        <div class="form-group">

          <label for="confirm_password">
            Confirmer le mot de passe
            <span class="required">*</span>
          </label>

          <input
            type="password"
            id="confirm_password"
            name="confirm_password"
            required
            autocomplete="new-password">

        </div>

      </div>
    `;
  }

  _getManageRolesFieldsHtml() {
    return `
      <div class="ad-status ad-status--info">

        <svg
          width="20"
          height="20"
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
            y1="16"
            x2="12"
            y2="12">
          </line>

          <line
            x1="12"
            y1="8"
            x2="12.01"
            y2="8">
          </line>

        </svg>

        <div>

          <strong>
            Gestion des rôles pour
            ${this._escapeHtml(this.user?.name || this.user?.username || '')}
          </strong>

          <p>
            Les rôles assignés déterminent les permissions de l'utilisateur.
          </p>

        </div>

      </div>

      <div class="form-group">

        <label>
          Rôles assignés
        </label>

        <div
          class="roles-list assigned"
          data-assigned-roles>

          ${this._getAssignedRolesHtml()}

        </div>

      </div>

      <div class="form-group">

        <label>
          Rôles disponibles
        </label>

        <div
          class="roles-list available"
          data-available-roles>

          ${this._getAvailableRolesHtml()}

        </div>

      </div>
    `;
  }

  _getManageUsersFieldsHtml() {
    return `
      <div class="ad-status ad-status--info">

        <svg
          width="20"
          height="20"
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
            y1="16"
            x2="12"
            y2="12">
          </line>

          <line
            x1="12"
            y1="8"
            x2="12.01"
            y2="8">
          </line>

        </svg>

        <div>

          <strong>
            Gestion des utilisateurs du groupe
            ${this._escapeHtml(this.user?.name || this.user?.username || '')}
          </strong>

          <p>
            Ajoutez ou retirez des utilisateurs du groupe.
          </p>

        </div>

      </div>
    `;
  }

  _getManagePermissionsFieldsHtml() {
    const roleName = this.user?.name || this.user?.code || '';
    const rolePermissions = this.userRoles || [];
    const assignedIds = new Set(rolePermissions.map(p => p.id));

    const permissions = this.roles || [];

    const modules = {};
    permissions.forEach(p => {
      const mod = p.module || 'Non assigné';
      if (!modules[mod]) modules[mod] = [];
      modules[mod].push(p);
    });

    const sortedModules = Object.keys(modules).sort();

    let html = `
      <div class="ad-status ad-status--info">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="16" x2="12" y2="12"></line>
          <line x1="12" y1="8" x2="12.01" y2="8"></line>
        </svg>
        <div>
          <strong>
            Gestion des permissions pour ${this._escapeHtml(roleName)}
          </strong>
          <p>
            ${rolePermissions.length} permission(s) assignée(s) sur ${permissions.length} disponible(s).
          </p>
        </div>
      </div>

      <div class="form-group">
        <div class="module-filters" data-module-filters>
          <button type="button" class="module-filter-btn active" data-module-filter="all">
            Tous
            <span class="permission-count">(${permissions.length})</span>
          </button>
          ${sortedModules.map(mod => {
            const modPerms = modules[mod];
            const modAssigned = modPerms.filter(p => assignedIds.has(p.id)).length;
            return `
              <button type="button" class="module-filter-btn" data-module-filter="${this._escapeHtml(mod)}">
                ${this._escapeHtml(mod)}
                <span class="permission-count">(${modAssigned}/${modPerms.length})</span>
              </button>
            `;
          }).join('')}
        </div>
      </div>

      <div class="form-group" data-permissions-list>
    `;

    sortedModules.forEach(mod => {
      const modPerms = modules[mod];
      const modAssigned = modPerms.filter(p => assignedIds.has(p.id)).length;
      const allChecked = modAssigned === modPerms.length;

      html += `
        <div class="permission-module" data-module="${this._escapeHtml(mod)}">
          <div class="permission-module-header">
            <label class="checkbox-group">
              <input
                type="checkbox"
                data-action="toggle-module"
                data-module="${this._escapeHtml(mod)}"
                ${allChecked ? 'checked' : ''}>
              <span>
                ${this._escapeHtml(mod)}
                <span class="permission-count">(${modAssigned}/${modPerms.length})</span>
              </span>
            </label>
          </div>
          <div class="permission-module-items">
      `;

      modPerms.forEach(p => {
        const isChecked = assignedIds.has(p.id);
        html += `
          <label class="checkbox-group permission-item">
            <input
              type="checkbox"
              name="permission"
              value="${p.id}"
              data-permission-id="${p.id}"
              data-module="${this._escapeHtml(mod)}"
              ${isChecked ? 'checked' : ''}>
            <span>
              <span class="permission-code">${this._escapeHtml(p.code)}</span>
              <span class="permission-name">${this._escapeHtml(p.name || '')}</span>
            </span>
          </label>
        `;
      });

      html += `
          </div>
        </div>
      `;
    });

    html += `
      </div>
    `;

    return html;
  }

  render() {
    this.element =
      document.createElement('form');

    this.element.className =
      'user-form';

    this.element.noValidate =
      true;

    const isCreate =
      this.mode === 'create' ||
      this.mode === 'create-group' ||
      this.mode === 'create-role' ||
      this.mode === 'create-permission';

    const isEdit =
      this.mode === 'edit' ||
      this.mode === 'edit-group' ||
      this.mode === 'edit-role' ||
      this.mode === 'edit-permission';

    const isResetPassword =
      this.mode === 'reset-password';

    const isManageRoles =
      this.mode === 'manage-roles';

    const isManageUsers =
      this.mode === 'manage-users';

    const isManagePermissions =
      this.mode === 'manage-permissions';

    let fieldsHtml = '';

    if (
      this.mode === 'create' ||
      this.mode === 'create-group' ||
      this.mode === 'create-role' ||
      this.mode === 'create-permission'
    ) {
      fieldsHtml =
        this._getCreateFieldsHtml();
    } else if (
      this.mode === 'edit' ||
      this.mode === 'edit-group' ||
      this.mode === 'edit-role' ||
      this.mode === 'edit-permission'
    ) {
      fieldsHtml =
        this._getEditFieldsHtml();
    } else if (
      this.mode === 'reset-password'
    ) {
      fieldsHtml =
        this._getResetPasswordFieldsHtml();
    } else if (
      this.mode === 'manage-roles'
    ) {
      fieldsHtml =
        this._getManageRolesFieldsHtml();
    } else if (
      this.mode === 'manage-users'
    ) {
      fieldsHtml =
        this._getManageUsersFieldsHtml();
    } else if (
      this.mode === 'manage-permissions'
    ) {
      fieldsHtml =
        this._getManagePermissionsFieldsHtml();
    }

    this.element.innerHTML = `
      <div class="modal-form">
        ${fieldsHtml}
      </div>

      ${isManageRoles ? `
        <div class="form-actions">
          <button
            type="button"
            class="btn btn-secondary"
            data-action="cancel">
            Fermer
          </button>
        </div>
      ` : isManagePermissions ? `
        <div class="form-actions">
          <button
            type="button"
            class="btn btn-secondary"
            data-action="cancel">
            Annuler
          </button>
          <button
            type="submit"
            class="btn btn-primary"
            ${this.submitting ? 'disabled' : ''}>
            <span class="btn-text">
              Enregistrer
            </span>
            <span class="btn-loading">
              <div class="spinner"></div>
            </span>
          </button>
        </div>
      ` : `
        <div class="form-actions">
          <button
            type="button"
            class="btn btn-secondary"
            data-action="cancel">
            Annuler
          </button>
          <button
            type="submit"
            class="btn btn-${isResetPassword ? 'danger' : 'primary'}"
            ${this.submitting ? 'disabled' : ''}>
            <span class="btn-text">
              ${isResetPassword
                ? 'Réinitialiser'
                : this.mode.startsWith('edit')
                ? 'Enregistrer'
                : 'Créer'}
            </span>
            <span class="btn-loading">
              <div class="spinner"></div>
            </span>
          </button>
        </div>
      `}
    `;

    this.element.addEventListener(
      'submit',
      (e) => this._handleSubmit(e)
    );

    this.element
      .querySelector(
        '[data-action="cancel"]'
      )
      ?.addEventListener(
        'click',
        () => this.onClose()
      );

    if (
      isManageRoles ||
      isManageUsers
    ) {
      this._bindRoleEvents();
    }

    if (isManagePermissions) {
      this._bindPermissionEvents();
    }

    if (
      (this.mode === 'edit' || this.mode === 'create') &&
      this.user?.source !== 'ad'
    ) {
      this._bindGroupSelectEvents();
    }

    const firstInput =
      this.element.querySelector(
        'input:not([disabled]), select:not([disabled])'
      );

    if (firstInput) {
      setTimeout(
        () => firstInput.focus(),
        100
      );
    }

    return this.element;
  }

  _handleSubmit(e) {
    e.preventDefault();

    if (this.submitting) {
      return;
    }

    if (
      this.mode === 'manage-roles' ||
      this.mode === 'manage-users'
    ) {
      return;
    }

    if (this.mode === 'manage-permissions') {
      const checked =
        this.element.querySelectorAll(
          '.permission-item input[type="checkbox"]:checked'
        );

      const permissionIds =
        Array.from(checked).map(
          cb => parseInt(cb.value, 10)
        );

      this.onSavePermissions(permissionIds);
      return;
    }

    const formData =
      new FormData(this.element);

    const data = {};

    if (
      this.mode === 'create' ||
      this.mode === 'create-group' ||
      this.mode === 'create-role' ||
      this.mode === 'create-permission'
    ) {
      if (
        this.mode === 'create-group'
      ) {
        data.name =
          formData.get('name');

        data.description =
          formData.get('description') ||
          null;

      } else if (
        this.mode === 'create-role'
      ) {
        data.name =
          formData.get('name');

        data.description =
          formData.get('description') ||
          null;

      } else if (
        this.mode === 'create-permission'
      ) {
        data.code =
          formData.get('code');

        data.name =
          formData.get('name');

        data.description =
          formData.get('description') ||
          null;

        data.module =
          formData.get('module') ||
          null;

      } else {
        data.username =
          formData.get('username');

        data.email =
          formData.get('email');

        data.first_name =
          formData.get('first_name') ||
          null;

        data.last_name =
          formData.get('last_name') ||
          null;

        data.password =
          formData.get('password');

        data.confirm_password =
          formData.get('confirm_password');

        /*
         * Pas de is_admin
         * Pas de is_active
         *
         * Le backend gère le statut par défaut
         * et le rôle gère les permissions.
         */
        data.source = 'local';

        if (
          data.password !==
          data.confirm_password
        ) {
          this.showError(
            'Les mots de passe ne correspondent pas'
          );
          return;
        }

        if (
          data.password.length < 8
        ) {
          this.showError(
            'Le mot de passe doit contenir au moins 8 caractères'
          );
          return;
        }

        if (
          data.password.length > 128
        ) {
          this.showError(
            'Le mot de passe ne doit pas dépasser 128 caractères'
          );
          return;
        }

        if (
          !data.username ||
          data.username.length < 3
        ) {
          this.showError(
            "Le nom d'utilisateur doit contenir au moins 3 caractères"
          );
          return;
        }

        if (
          data.username.length > 50
        ) {
          this.showError(
            "Le nom d'utilisateur ne doit pas dépasser 50 caractères"
          );
          return;
        }

        if (
          !data.email ||
          !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(
            data.email
          )
        ) {
          this.showError(
            "L'email est invalide"
          );
          return;
        }

        if (
          data.first_name &&
          data.first_name.length > 100
        ) {
          this.showError(
            'Le prénom ne doit pas dépasser 100 caractères'
          );
          return;
        }

        if (
          data.last_name &&
          data.last_name.length > 100
        ) {
          this.showError(
            'Le nom ne doit pas dépasser 100 caractères'
          );
          return;
        }

        delete data.confirm_password;
      }

    } else if (
      this.mode === 'edit' ||
      this.mode === 'edit-group' ||
      this.mode === 'edit-role' ||
      this.mode === 'edit-permission'
    ) {
      if (
        this.mode === 'edit-group'
      ) {
        data.name =
          formData.get('name');

        data.description =
          formData.get('description') ||
          null;

      } else if (
        this.mode === 'edit-role'
      ) {
        data.name =
          formData.get('name');

        data.description =
          formData.get('description') ||
          null;

      } else if (
        this.mode === 'edit-permission'
      ) {
        data.name =
          formData.get('name');

        data.description =
          formData.get('description') ||
          null;

        data.module =
          formData.get('module') ||
          null;

      } else {
        data.email =
          formData.get('email');

        data.first_name =
          formData.get('first_name') ||
          null;

        data.last_name =
          formData.get('last_name') ||
          null;

        /*
         * Pas de is_active
         * Pas de is_admin
         */

        if (
          !data.email ||
          !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(
            data.email
          )
        ) {
          this.showError(
            "L'email est invalide"
          );
          return;
        }

        const groupTags = this.element.querySelectorAll('.multiselect-tag');
        data.group_ids = Array.from(groupTags).map(tag => parseInt(tag.dataset.groupId, 10));
      }

    } else if (
      this.mode === 'reset-password'
    ) {
      data.new_password =
        formData.get('new_password');

      data.confirm_password =
        formData.get('confirm_password');

      if (
        data.new_password !==
        data.confirm_password
      ) {
        this.showError(
          'Les mots de passe ne correspondent pas'
        );
        return;
      }

      if (
        data.new_password.length < 8
      ) {
        this.showError(
          'Le mot de passe doit contenir au moins 8 caractères'
        );
        return;
      }
    }

    this.submitting = true;

    const submitButton =
      this.element.querySelector(
        '[type="submit"]'
      );

    if (submitButton) {
      submitButton.disabled =
        true;

      submitButton.querySelector(
        '.btn-text'
      ).style.display =
        'none';

      submitButton.querySelector(
        '.btn-loading'
      ).style.display =
        'flex';
    }

    const isEdit =
      this.mode === 'edit' ||
      this.mode === 'edit-group' ||
      this.mode === 'edit-role' ||
      this.mode === 'edit-permission';

    this.onSubmit(
      data,
      isEdit
    );
  }

  _removeRole(roleId) {
    this.element.dispatchEvent(
      new CustomEvent(
        'remove-role',
        {
          detail: {
            roleId,
          },
        }
      )
    );
  }

  _addRole(roleId) {
    this.element.dispatchEvent(
      new CustomEvent(
        'add-role',
        {
          detail: {
            roleId,
          },
        }
      )
    );
  }

  showError(message) {
    let errorEl =
      this.element.querySelector(
        '.form-error'
      );

    if (!errorEl) {
      errorEl =
        document.createElement(
          'div'
        );

      errorEl.className =
        'form-error error-message';

      this.element
        .querySelector(
          '.modal-form'
        )
        .prepend(errorEl);
    }

    errorEl.textContent =
      message;

    errorEl.classList.remove(
      'hidden'
    );
  }

  setSubmitting(submitting) {
    this.submitting =
      submitting;

    if (this.element) {
      const submitBtn =
        this.element.querySelector(
          '[type="submit"]'
        );

      if (submitBtn) {
        submitBtn.disabled =
          submitting;

        submitBtn.querySelector(
          '.btn-text'
        ).style.display =
          submitting
            ? 'none'
            : '';

        submitBtn.querySelector(
          '.btn-loading'
        ).style.display =
          submitting
            ? 'flex'
            : 'none';
      }
    }
  }

  updateRoles(roles) {
    this.roles = roles;

    if (this.element) {
      const roleSelect =
        this.element.querySelector(
          '#role'
        );

      if (roleSelect) {
        const currentValue =
          roleSelect.value;

        roleSelect.innerHTML =
          `<option value="">Sélectionner un rôle</option>` +
          this._getRoleOptions(
            currentValue
          );
      }
    }
  }

  setUserRoles(userRoles) {
    this.userRoles =
      userRoles;

    if (
      this.element &&
      this.mode === 'manage-roles'
    ) {
      this.element
        .querySelector(
          '[data-assigned-roles]'
        ).innerHTML =
        this._getAssignedRolesHtml();

      this.element
        .querySelector(
          '[data-available-roles]'
        ).innerHTML =
        this._getAvailableRolesHtml();

      this._bindRoleEvents();
    }
  }

  _bindRoleEvents() {
    this.element
      .querySelectorAll(
        '[data-action="remove-role"]'
      )
      .forEach(btn => {
        btn.addEventListener(
          'click',
          () =>
            this._removeRole(
              parseInt(
                btn.dataset.roleId,
                10
              )
            )
        );
      });

    this.element
      .querySelectorAll(
        '[data-action="add-role"]'
      )
      .forEach(btn => {
        btn.addEventListener(
          'click',
          () =>
            this._addRole(
              parseInt(
                btn.dataset.roleId,
                10
              )
            )
        );
      });
  }

  _bindPermissionEvents() {
    const filterButtons = this.element.querySelectorAll('[data-module-filter]');

    filterButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        filterButtons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        const filter = btn.dataset.moduleFilter;

        this.element.querySelectorAll('.permission-module').forEach(mod => {
          if (filter === 'all' || mod.dataset.module === filter) {
            mod.style.display = '';
          } else {
            mod.style.display = 'none';
          }
        });
      });
    });

    this.element
      .querySelectorAll(
        '[data-action="toggle-module"]'
      )
      .forEach(checkbox => {
        checkbox.addEventListener(
          'change',
          () => {
            const mod =
              checkbox.dataset.module;
            const checked =
              checkbox.checked;

            this.element
              .querySelectorAll(
                `[data-module="${mod}"].permission-item input[type="checkbox"]`
              )
              .forEach(cb => {
                if (
                  cb.offsetParent !== null
                ) {
                  cb.checked = checked;
                }
              });

            this._updateModuleCounts();
          }
        );
      });

    this.element
      .querySelectorAll(
        '.permission-item input[type="checkbox"]'
      )
      .forEach(cb => {
        cb.addEventListener(
          'change',
          () => {
            this._updateModuleCounts();
          }
        );
      });
  }

  _updateModuleCounts() {
    this.element
      .querySelectorAll(
        '[data-action="toggle-module"]'
      )
      .forEach(checkbox => {
        const mod =
          checkbox.dataset.module;
        const items =
          this.element.querySelectorAll(
            `[data-module="${mod}"].permission-item input[type="checkbox"]`
          );

        let checkedCount = 0;
        let visibleCount = 0;

        items.forEach(cb => {
          if (
            cb.offsetParent !== null
          ) {
            visibleCount++;
            if (cb.checked) {
              checkedCount++;
            }
          }
        });

        checkbox.checked =
          visibleCount > 0 &&
          checkedCount === visibleCount;

        const countEl =
          checkbox.parentElement.querySelector(
            '.permission-count'
          );

        if (countEl) {
          countEl.textContent =
            `(${checkedCount}/${visibleCount})`;
        }
      });
  }

  _bindGroupSelectEvents() {
    const multiselect = this.element.querySelector('.multiselect');
    if (!multiselect) return;

    const control = multiselect.querySelector('.multiselect-control');
    const dropdown = multiselect.querySelector('.multiselect-dropdown');
    const searchInput = multiselect.querySelector('.multiselect-search-input');
    const optionsContainer = multiselect.querySelector('.multiselect-options');

    control.addEventListener('click', (e) => {
      if (e.target.closest('[data-action="remove-group"]')) return;
      dropdown.classList.toggle('multiselect-dropdown--open');
      if (dropdown.classList.contains('multiselect-dropdown--open')) {
        searchInput.value = '';
        this._filterGroupOptions(optionsContainer, '');
        searchInput.focus();
      }
    });

    searchInput.addEventListener('input', (e) => {
      this._filterGroupOptions(optionsContainer, e.target.value.toLowerCase());
    });

    searchInput.addEventListener('click', (e) => e.stopPropagation());

    optionsContainer.addEventListener('click', (e) => {
      e.stopPropagation();
      const option = e.target.closest('.multiselect-option');
      if (!option) return;
      const groupId = parseInt(option.dataset.groupId, 10);
      this._toggleGroupSelection(groupId);
    });

    multiselect.querySelectorAll('[data-action="remove-group"]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const groupId = parseInt(btn.dataset.groupId, 10);
        this._toggleGroupSelection(groupId);
      });
    });

    document.addEventListener('click', (e) => {
      if (!multiselect.contains(e.target)) {
        dropdown.classList.remove('multiselect-dropdown--open');
      }
    });
  }

  _filterGroupOptions(container, query) {
    container.querySelectorAll('.multiselect-option').forEach(option => {
      const name = (option.dataset.groupName || '').toLowerCase();
      option.style.display = name.includes(query) ? '' : 'none';
    });
  }

  _toggleGroupSelection(groupId) {
    const multiselect = this.element.querySelector('.multiselect');
    if (!multiselect) return;

    const allGroups = (this.groups || []).filter(g => g.source !== 'ad');
    const group = allGroups.find(g => g.id === groupId);
    if (!group) return;

    const option = multiselect.querySelector(`.multiselect-option[data-group-id="${groupId}"]`);
    const isSelected = option?.classList.contains('multiselect-option--selected');

    if (isSelected) {
      option.classList.remove('multiselect-option--selected');
      option.querySelector('.multiselect-option-check').innerHTML = '';
      const tag = multiselect.querySelector(`.multiselect-tag[data-group-id="${groupId}"]`);
      if (tag) tag.remove();
    } else {
      option.classList.add('multiselect-option--selected');
      option.querySelector('.multiselect-option-check').innerHTML = '&#10003;';
      const tagsContainer = multiselect.querySelector('.multiselect-tags');
      const placeholder = tagsContainer.querySelector('.multiselect-placeholder');
      if (placeholder) placeholder.remove();
      const tagHtml = `
        <span class="multiselect-tag" data-group-id="${groupId}">
          ${this._escapeHtml(group.name)}
          <button type="button" class="multiselect-tag-remove" data-action="remove-group" data-group-id="${groupId}" aria-label="Retirer ${this._escapeHtml(group.name)}">&times;</button>
        </span>
      `;
      tagsContainer.insertAdjacentHTML('beforeend', tagHtml);
      const newTag = tagsContainer.querySelector(`.multiselect-tag[data-group-id="${groupId}"]`);
      newTag.querySelector('[data-action="remove-group"]').addEventListener('click', (e) => {
        e.stopPropagation();
        this._toggleGroupSelection(groupId);
      });
    }

    if (multiselect.querySelector('.multiselect-tags .multiselect-tag') === null) {
      const tagsContainer = multiselect.querySelector('.multiselect-tags');
      tagsContainer.innerHTML = '<span class="multiselect-placeholder">Sélectionner des groupes...</span>';
    }
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
    if (this.element) {
      this.element.innerHTML = '';
    }
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