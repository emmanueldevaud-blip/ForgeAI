export class UserModal {
  constructor(options = {}) {
    this.onSubmit = options.onSubmit || (() => {});
    this.onClose = options.onClose || (() => {});
    this.onAddRole = options.onAddRole || (() => {});
    this.onRemoveRole = options.onRemoveRole || (() => {});
    this.roles = options.roles || [];
    this.element = null;
    this.overlay = null;
    this.currentMode = 'create';
    this.currentUser = null;
    this.form = null;
  }

  async open(options = {}) {
    this.currentMode = options.mode || 'create';
    this.currentUser = options.user || null;
    this.roles = options.roles || this.roles;

    const { UserForm } = await import('./UserForm.js');

    this._createModal();
    this._renderForm(options, UserForm);

    document.body.appendChild(this.overlay);
    requestAnimationFrame(() => {
      this.overlay.classList.add('open');
      this.element.classList.add('open');
    });

    document.addEventListener('keydown', this._handleKeydown.bind(this));
    this.overlay.addEventListener('click', this._handleOverlayClick.bind(this));
  }

  _createModal() {
    this.overlay = document.createElement('div');
    this.overlay.className = 'modal-overlay';

    this.element = document.createElement('div');
    this.element.className = 'modal';
    this.element.setAttribute('role', 'dialog');
    this.element.setAttribute('aria-modal', 'true');
    this.element.setAttribute('aria-labelledby', 'modal-title');

    this.modalContent = document.createElement('div');
    this.modalContent.className = 'modal-content';
    this.element.appendChild(this.modalContent);

    this.overlay.appendChild(this.element);
  }

  _renderForm(options, UserForm) {
    const titles = {
      create: 'Nouvel utilisateur',
      edit: 'Modifier l\'utilisateur',
      'reset-password': 'Réinitialiser le mot de passe',
      'manage-roles': 'Gérer les rôles',
      'create-group': 'Nouveau groupe',
      'edit-group': 'Modifier le groupe',
      'create-role': 'Nouveau rôle',
      'edit-role': 'Modifier le rôle',
      'create-permission': 'Nouvelle permission',
      'edit-permission': 'Modifier la permission',
      'manage-users': 'Gérer les utilisateurs du groupe',
      'manage-roles': 'Gérer les rôles',
    };

    const isManageRoles = this.currentMode === 'manage-roles';
    const isManageUsers = this.currentMode === 'manage-users';
    const userRoles = options.userRoles || [];

    this.modalContent.innerHTML = `
      <div class="modal-header">
        <h2 id="modal-title">${titles[this.currentMode] || 'Utilisateur'}</h2>
        <button type="button" class="modal-close" aria-label="Fermer" data-action="close">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
      <div class="modal-body" data-modal-body></div>
    `;

    this.modalContent.querySelector('[data-action="close"]').addEventListener('click', () => this.close());

    const body = this.modalContent.querySelector('[data-modal-body]');
    this.form = new UserForm({
      mode: this.currentMode,
      user: this.currentUser,
      roles: this.roles,
      userRoles: userRoles,
      onSubmit: (data, isEdit) => this.onSubmit(data, isEdit),
      onClose: () => this.close(),
    });
    body.appendChild(this.form.render());

    if (this.currentMode === 'manage-roles') {
      this.form.element.addEventListener('add-role', (e) => this.onAddRole(e.detail.roleId));
      this.form.element.addEventListener('remove-role', (e) => this.onRemoveRole(e.detail.roleId));
    }
  }

  close() {
    if (!this.overlay) return;

    this.overlay.classList.remove('open');
    this.element.classList.remove('open');

    setTimeout(() => {
      this.overlay?.remove();
      this.overlay = null;
      this.element = null;
      this.form = null;
      this.onClose();
    }, 200);
  }

  _handleKeydown(e) {
    if (e.key === 'Escape') {
      this.close();
    }
  }

  _handleOverlayClick(e) {
    if (e.target === this.overlay) {
      this.close();
    }
  }

  updateRoles(roles) {
    this.roles = roles;
    if (this.form) {
      this.form.updateRoles(roles);
    }
  }

  updateUserRoles(userRoles) {
    if (this.form) {
      this.form.setUserRoles(userRoles);
    }
  }

  destroy() {
    this.close();
  }
}