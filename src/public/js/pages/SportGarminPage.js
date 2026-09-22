import { connectGarmin, disconnectGarmin, getGarminConnection, syncGarmin } from '../services/sportApi.js?v=2';

export class SportGarminPage {
  constructor() { this.element = null; this.connection = null; }

  async initialize() { this.connection = await getGarminConnection(); }

  render() {
    const connection = this.connection || {};
    this.element = document.createElement('div');
    this.element.className = 'page-content';
    this.element.innerHTML = `
      <div class="page-header"><div><h1>Garmin Connect</h1><p class="page-subtitle">Synchronisation en lecture seule avec votre compte Garmin.</p></div></div>
      <div class="card">
        <div class="card-header"><h2>${connection.connected ? 'Compte connecté' : 'Connecter Garmin Connect'}</h2></div>
        <div class="card-body">
          <p data-message class="text-muted">${connection.connected ? `Compte : ${this._escape(connection.garmin_email)}<br>Dernière synchronisation : ${connection.last_sync_at ? new Date(connection.last_sync_at).toLocaleString('fr-FR') : 'Jamais'}` : 'Le mot de passe est utilisé uniquement pour obtenir une session Garmin et n’est jamais enregistré.'}</p>
          ${connection.last_error ? `<p class="text-danger">${this._escape(connection.last_error)}</p>` : ''}
          ${connection.connected ? `
            <div style="display:flex;gap:8px;flex-wrap:wrap;"><button class="btn btn-primary" data-action="sync">Synchroniser maintenant</button><button class="btn btn-secondary" data-action="disconnect">Déconnecter</button></div>
          ` : `
            <form data-garmin-form>
              <div class="form-row"><label><span>E-mail Garmin</span><input name="email" type="email" required autocomplete="username"></label><label><span>Mot de passe Garmin</span><input name="password" type="password" required autocomplete="current-password"></label></div>
              <div class="form-row"><label><span>Code MFA, si demandé</span><input name="mfa_code" inputmode="numeric" autocomplete="one-time-code"></label><label><span>Première synchronisation</span><select name="initial_sync_days"><option value="30">30 derniers jours</option><option value="90">90 derniers jours</option><option value="365">365 derniers jours</option></select></label></div>
              <button class="btn btn-primary" type="submit">Connecter Garmin</button>
            </form>
          `}
        </div>
      </div>`;
    this._bindEvents();
    return this.element;
  }

  _bindEvents() {
    this.element.querySelector('[data-garmin-form]')?.addEventListener('submit', async event => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.currentTarget).entries());
      data.initial_sync_days = Number(data.initial_sync_days);
      try { this.connection = await connectGarmin(data); this._rerender(); }
      catch (error) { this._message(error.data?.detail || error.message || 'Connexion Garmin impossible'); }
    });
    this.element.querySelector('[data-action="sync"]')?.addEventListener('click', async () => {
      this._message('Synchronisation en cours...');
      try { const result = await syncGarmin(); this.connection = await getGarminConnection(); this._message(`${result.imported_count || 0} nouvelle(s) activité(s) importée(s).`); }
      catch (error) { this._message(error.data?.detail || error.message || 'Synchronisation impossible'); }
    });
    this.element.querySelector('[data-action="disconnect"]')?.addEventListener('click', async () => {
      if (!window.confirm('Déconnecter Garmin et supprimer la session enregistrée ?')) return;
      try { await disconnectGarmin(); this.connection = { connected: false }; this._rerender(); }
      catch (error) { this._message(error.data?.detail || error.message || 'Déconnexion impossible'); }
    });
  }

  _rerender() { const oldElement = this.element; const parent = oldElement?.parentElement; if (parent) { const rendered = this.render(); parent.replaceChild(rendered, oldElement); } }
  _message(message) { const node = this.element.querySelector('[data-message]'); if (node) node.textContent = message; }
  _escape(value) { const node = document.createElement('div'); node.textContent = value || ''; return node.innerHTML; }
}

export function createSportGarminPage() { return new SportGarminPage(); }
