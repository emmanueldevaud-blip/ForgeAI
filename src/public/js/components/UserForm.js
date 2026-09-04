export class UserForm {
  constructor(options = {}) {
    this.mode = options.mode || 'create';
    this.user = options.user || null;
    this.roles = options.roles || [];
    this.userRoles = options.userRoles || [];
    this.onSubmit = options.onSubmit || (() => {});
    this.onClose = options.onClose || (() => {});
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
    let fieldsHtml = `
      <div class="form-row">

        <div class="form-group">

          <label for="username">
            Nom d'utilisateur
          </label>

          <input
            type="text"
            id="username"
            name="username"
            value="${this._escapeHtml(this.user?.username || '')}"
            disabled>

          <p class="form-hint">
            Le nom d'utilisateur ne peut pas être modifié
          </p>

        </div>

        <div class="form-group">

          <label for="email">
            Email
            <span class="required">*</span>
          </label>

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

          <label for="first_name">
            Prénom
          </label>

          <input
            type="text"
            id="first_name"
            name="first_name"
            value="${this._escapeHtml(this.user?.first_name || '')}"
            maxlength="100">

        </div>

        <div class="form-group">

          <label for="last_name">
            Nom
          </label>

          <input
            type="text"
            id="last_name"
            name="last_name"
            value="${this._escapeHtml(this.user?.last_name || '')}"
            maxlength="100">

        </div>

      </div>
    `;

    if (this.mode === 'edit-permission') {
      fieldsHtml += `
        <div class="form-row">

          <div class="form-group">

            <label for="name">
              Nom
              <span class="required">*</span>
            </label>

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
    } else if (
      this.mode === 'edit-group' ||
      this.mode === 'edit-role'
    ) {
      fieldsHtml += `
        <div class="form-row">

          <div class="form-group">

            <label for="name">
              Nom
            </label>

            <input
              type="text"
              id="name"
              name="name"
              value="${this._escapeHtml(this.user?.name || '')}"
              maxlength="100">

          </div>

        </div>

        <div class="form-group">

          <label for="description">
            Description
          </label>

          <textarea
            id="description"
            name="description"
            maxlength="500"
            rows="3">${this._escapeHtml(this.user?.description || '')}</textarea>

        </div>
      `;
    }

    /*
     * UTILISATEUR EN MODIFICATION
     *
     * Pas de case "Actif"
     * Pas de case "Administrateur"
     */
    if (
      this.mode !== 'edit-group' &&
      this.mode !== 'edit-role' &&
      this.mode !== 'edit-permission'
    ) {
      fieldsHtml += `
        <div class="form-group">

          <label for="role">
            Rôle
          </label>

          <select
            id="role"
            name="role">

            <option value="">
              Sélectionner un rôle
            </option>

            ${this._getRoleOptions(
              this.user?.role
            )}

          </select>

        </div>
      `;
    }

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
            ${this._escapeHtml(this.user?.username || '')}
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
            ${this._escapeHtml(this.user?.username || '')}
          </strong>

          <p>
            Ajoutez ou retirez des utilisateurs du groupe.
          </p>

        </div>

      </div>
    `;
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
    }

    this.element.innerHTML = `
      <div class="modal-form">
        ${fieldsHtml}
      </div>

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

        data.role =
          formData.get('role');

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
          !data.role ||
          data.role === ''
        ) {
          this.showError(
            'Veuillez sélectionner un rôle'
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

        data.role =
          formData.get('role') ||
          null;

        /*
         * Pas de is_active
         * Pas de is_admin
         */
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