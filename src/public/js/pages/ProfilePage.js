import { getSportAthleteProfile, getSportDashboard, updateSportHeartRateConfig } from '../services/sportApi.js?v=6';

export class ProfilePage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.user = null;
  }

  async initialize() {
    try {
      this.user = await getSportAthleteProfile();
    } catch (error) {
      this.user = null;
    }
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
        <div><h1>Mon profil</h1><p class="page-subtitle">Informations personnelles</p></div>
      </div>

      <div class="card">
        <div class="card-header">
          <div><span class="sport-eyebrow">Informations générales</span></div>
        </div>
        <div class="card-body sport-profile-card">
          <div class="form-row">
            <div class="form-group">
              <label>Nom complet</label>
              <input type="text" class="form-control" value="${this._escapeHtml(displayName)}" readonly>
            </div>
            <div class="form-group">
              <label>Email</label>
              <input type="email" class="form-control" value="${this._escapeHtml(email)}" readonly>
            </div>
          </div>

          ${roles.length > 0 ? `
          <div class="form-row">
            <div class="form-group">
              <label>Rôle(s)</label>
              <span>${roles.map(r => `<span class="sport-badge sport-badge--${r === 'admin' ? 'admin' : 'user'}">${this._getRoleLabel(r)}</span>`).join(' ')}</span>
            </div>
          </div>
          ` : ''}

          <hr>

          <div class="form-row">
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
      alert('Fonctionnalité de modification de profil à venir');
    });

    this.element.querySelector('[data-action="change-password"]')?.addEventListener('click', () => {
      alert('Fonctionnalité de changement de mot de passe à venir');
    });
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
  }

  _getRoleLabel(role) {
    if (role === 'admin') return 'Administrateur';
    return 'Utilisateur';
  }
}

export function createProfilePage(router) {
  const page = new ProfilePage(router);
  page.initialize();
  return page;
}