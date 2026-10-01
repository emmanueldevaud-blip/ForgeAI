import { authStore } from '../stores/auth.js';

export class ProfilePage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.user = null;
  }

  async initialize() {
    this.user = authStore.currentUser;
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content';
    
    if (!this.user) {
      this.element.innerHTML = `
        <div class="card" role="alert">
          <div class="card-body">
            <h2>Impossible de charger le profil</h2>
            <p>Les données utilisateur ne sont pas disponibles pour le moment.</p>
          </div>
        </div>
      `;
      return this.element;
    }

    const displayName = this.user.full_name || this.user.username;
    const email = this.user.email || '';
    const roles = this.user.roles || [];

    this.element.innerHTML = `
      <div class="page-header">
        <div>
          <h1>Mon profil</h1>
          <p class="page-subtitle">Informations personnelles</p>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div><span class="eyebrow">Informations générales</span></div>
        </div>
        <div class="card-body">
          <div class="form-row">
            <div class="form-group">
              <label>Nom d'utilisateur</label>
              <input type="text" class="form-control" value="${this._escapeHtml(this.user.username)}" readonly>
            </div>
            <div class="form-group">
              <label>Nom complet</label>
              <input type="text" class="form-control" value="${this._escapeHtml(displayName)}" readonly>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Email</label>
              <input type="email" class="form-control" value="${this._escapeHtml(email)}" readonly>
            </div>
          </div>

          ${roles.length > 0 ? `
          <div class="form-row">
            <div class="form-group">
              <label>Rôle(s)</label>
              <div style="display: flex; gap: 8px;">
                ${roles.map(r => `<span class="badge badge--${r === 'admin' ? 'primary' : 'secondary'}">${this._getRoleLabel(r)}</span>`).join('')}
              </div>
            </div>
          </div>
          ` : ''}

          <hr style="margin: 24px 0; border: 0; border-top: 1px solid var(--border-color);">

          <div class="form-row" style="display: flex; gap: 12px;">
            <button class="btn btn-primary" data-action="edit-profile">Modifier mon profil</button>
            <button class="btn btn-secondary" data-action="change-password">Changer de mot de passe</button>
          </div>
        </div>
      </div>
    `;

    this._bindEvents();
    return this.element;
  }

  _bindEvents() {
    this.element.querySelector('[data-action="edit-profile"]')?.addEventListener('click', () => {
      alert('La modification du profil sera disponible prochainement.');
    });

    this.element.querySelector('[data-action="change-password"]')?.addEventListener('click', () => {
      alert('Le changement de mot de passe sera disponible prochainement.');
    });
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
  }

  _getRoleLabel(role) {
    if (role === 'admin') return 'Administrateur';
    return role.charAt(0).toUpperCase() + role.slice(1);
  }
}

export function createProfilePage(router) {
  const page = new ProfilePage(router);
  page.initialize();
  return page;
}
