import { authStore } from '../stores/auth.js';
import { api } from '../services/api.js';

export class UserSettingsPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.user = null;
  }

  async initialize() {
    try {
      await authStore.loadCurrentUser();
    } catch (error) {
      console.error('Erreur chargement utilisateur:', error);
    }
    this.user = authStore.currentUser;
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content';

    if (!this.user) {
      this.element.innerHTML = `
        <div class="card" role="alert">
          <div class="card-body">
            <h2>Impossible de charger les paramètres</h2>
            <p>Les préférences utilisateur ne sont pas disponibles pour le moment.</p>
          </div>
        </div>
      `;
      return this.element;
    }

    const needsWorkstation = !!this.user.default_needs_workstation;

    this.element.innerHTML = `
      <div class="page-header">
        <div>
          <h1>Paramètres</h1>
          <p class="page-subtitle">Préférences personnelles</p>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div><span class="eyebrow">Agenda — Ma présence</span></div>
        </div>
        <div class="card-body">
          <form data-form="user-preferences">
            <p>
              <label>
                <input type="checkbox" name="default_needs_workstation" ${needsWorkstation ? 'checked' : ''}>
                <span>M'inscrire avec un poste de travail</span>
              </label>
            </p>
            <p class="page-subtitle">
              La case « Poste » est cochée automatiquement à chaque inscription sur le
              planning. Désactivée par défaut ; vous pouvez toujours la décocher
              journée par journée.
            </p>
            <div style="display: flex; gap: 12px; align-items: center;">
              <button type="submit" class="btn btn-primary">Enregistrer</button>
              <span class="page-subtitle" data-role="status"></span>
            </div>
          </form>
        </div>
      </div>
    `;

    this._bindEvents();
    return this.element;
  }

  _bindEvents() {
    const form = this.element.querySelector('[data-form="user-preferences"]');
    const status = this.element.querySelector('[data-role="status"]');
    form?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const checkbox = form.querySelector('input[name="default_needs_workstation"]');
      const button = form.querySelector('button[type="submit"]');
      if (button) button.disabled = true;
      try {
        await api.patch('/me', { default_needs_workstation: !!checkbox.checked });
        await authStore.loadCurrentUser();
        status.textContent = 'Préférence enregistrée';
      } catch (error) {
        console.error('Erreur enregistrement préférence:', error);
        status.textContent = error?.message || 'Enregistrement impossible';
      } finally {
        if (button) button.disabled = false;
      }
    });
  }
}

export function createSettingsPage(router) {
  return new UserSettingsPage(router);
}
