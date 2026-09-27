import { connectGarmin, disconnectGarmin, generateVapidKeys, getGarminConnection, getSportNotificationConfig, syncGarmin, updateSportNotificationConfig } from '../services/sportApi.js?v=6';
import { enablePhoneNotifications, isPushSupported, sendTestNotification } from '../services/notificationsApi.js?v=2';

export class SportGarminPage {
  constructor() { this.element = null; this.connection = null; this.notifications = null; this.pushSupported = false; this.pushMessage = null; }

  async initialize() {
    const [connection, notifications, pushSupported] = await Promise.all([
      getGarminConnection(),
      getSportNotificationConfig(),
      isPushSupported(),
    ]);
    this.connection = connection;
    this.notifications = notifications;
    this.pushSupported = pushSupported;
  }

  render() {
    const connection = this.connection || {};
    const notifications = this.notifications || {};
    const browserSupport = [
      `serviceWorker ${'serviceWorker' in navigator ? '✓' : '✗'}`,
      `PushManager ${'PushManager' in window ? '✓' : '✗'}`,
      `Notification ${'Notification' in window ? '✓' : '✗'}`,
      `HTTPS ${window.isSecureContext ? '✓' : '✗'}`,
    ].join(' · ');
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
      || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const standalone = window.matchMedia?.('(display-mode: standalone)').matches || navigator.standalone === true;
    const pushHelp = (!this.pushSupported && isIOS && !standalone)
      ? 'Sur iPhone : ajoutez le site via Safari (Partager → « Sur l’écran d’accueil ») puis ouvrez-le depuis cette NOUVELLE icône — un raccourci Edge/Chrome ne suffit pas.'
      : (!this.pushSupported
        ? `Notifications web non supportées par ce navigateur (${browserSupport}). Essayez Chrome ou Firefox.`
        : '');
    const notificationStatus = notifications.configured
      ? 'Clés VAPID configurées. Après toute génération ou modification, réabonnez les notifications depuis votre téléphone.'
      : 'Aucune clé configurée : les notifications push sont désactivées sur le serveur.';
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
            <div style="display:flex;gap:8px;flex-wrap:wrap;"><button class="btn btn-primary" data-action="sync">Synchroniser maintenant</button><button class="btn btn-secondary" data-action="sync-history">Tout l'historique</button><button class="btn btn-secondary" data-action="disconnect">Déconnecter</button></div>
          ` : `
            <form data-garmin-form>
              <div class="form-row"><label><span>E-mail Garmin</span><input name="email" type="email" required autocomplete="username"></label><label><span>Mot de passe Garmin</span><input name="password" type="password" required autocomplete="current-password"></label></div>
              <div class="form-row"><label><span>Code MFA, si demandé</span><input name="mfa_code" inputmode="numeric" autocomplete="one-time-code"></label><label><span>Première synchronisation</span><select name="initial_sync_days"><option value="30">30 derniers jours</option><option value="90">90 derniers jours</option><option value="365">365 derniers jours</option></select></label></div>
              <button class="btn btn-primary" type="submit">Connecter Garmin</button>
            </form>
          `}
        </div>
      </div>
      <div class="card">
        <div class="card-header"><h2>Notifications téléphone</h2></div>
        <div class="card-body">
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
            <button class="btn btn-primary" data-action="enable-push" ${this.pushSupported ? '' : 'disabled'}>Activer sur ce téléphone</button>
            <button class="btn btn-secondary" data-action="test-push" ${notifications.configured ? '' : 'disabled'}>Envoyer une notification test</button>
            ${pushHelp ? `<span class="text-muted" style="align-self:center;">${pushHelp}</span>` : ''}
          </div>
          <p data-notification-message class="text-muted">${this._escape(this.pushMessage || notificationStatus)}</p>
          <small data-push-diagnostic class="text-muted">État : support ${this.pushSupported ? '✓' : '✗'} · ${browserSupport} · mode app ${standalone ? '✓' : '✗'} · clés ${notifications.configured ? '✓' : '✗'} · bouton activer ${this.pushSupported ? 'actif' : 'désactivé'}</small>
          <form data-vapid-form>
            <label><span>Contact de l'émetteur (sujet VAPID)</span>
              <input name="subject" type="text" value="${this._escape(notifications.subject || '')}" placeholder="mailto:votre.email@exemple.com">
              <small class="text-muted">Adresse email ou URL identifiant ForgeAI auprès des services de notification (obligatoire, pré-rempli automatiquement à la génération).</small>
            </label>
            <label><span>Clé privée existante (facultatif)</span><textarea name="private_key" rows="3" placeholder="Coller une clé privée existante, ou laisser vide"></textarea></label>
            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;">
              <button class="btn btn-primary" type="submit">Enregistrer</button>
              <button class="btn btn-secondary" type="button" data-action="generate-keys">Générer les clés</button>
            </div>
          </form>
          ${notifications.configured && notifications.public_key ? `<p class="text-muted" style="margin-top:8px;">Clé publique : <code>${this._escape(notifications.public_key)}</code></p>` : ''}
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
    this.element.querySelector('[data-action="sync-history"]')?.addEventListener('click', async () => {
      if (!window.confirm("Importer tout l'historique Garmin disponible ? Cette opération peut prendre plusieurs minutes.")) return;
      this._message("Import de l'historique Garmin en cours...");
      try { const result = await syncGarmin(true); this.connection = await getGarminConnection(); this._message(`${result.imported_count || 0} nouvelle(s) activité(s) importée(s).`); }
      catch (error) { this._message(error.data?.detail || error.message || 'Synchronisation impossible'); }
    });
    this.element.querySelector('[data-action="disconnect"]')?.addEventListener('click', async () => {
      if (!window.confirm('Déconnecter Garmin et supprimer la session enregistrée ?')) return;
      try { await disconnectGarmin(); this.connection = { connected: false }; this._rerender(); }
      catch (error) { this._message(error.data?.detail || error.message || 'Déconnexion impossible'); }
    });
    this.element.querySelector('[data-vapid-form]')?.addEventListener('submit', async event => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.currentTarget).entries());
      try {
        this.notifications = await updateSportNotificationConfig({ private_key: data.private_key || null, subject: data.subject });
        this._rerender();
        this._notificationMessage('Configuration enregistrée.');
      }
      catch (error) { this._notificationMessage(error.data?.detail || error.message || 'Enregistrement impossible'); }
    });
    this.element.querySelector('[data-action="generate-keys"]')?.addEventListener('click', async () => {
      this._notificationMessage('Génération des clés en cours...');
      try {
        this.notifications = await generateVapidKeys();
        this.pushMessage = null;
        this._rerender();
        this._notificationMessage('Clés générées et appliquées. Réabonnez les notifications depuis votre téléphone.');
      }
      catch (error) { this._notificationMessage(error.data?.detail || error.message || 'Génération impossible'); }
    });
    this.element.querySelector('[data-action="enable-push"]')?.addEventListener('click', async () => {
      this._notificationMessage('Activation en cours…');
      const result = await enablePhoneNotifications();
      this.pushMessage = result.enabled
        ? 'Notifications activées : les analyses Sport arriveront sur ce téléphone (et sur votre montre Garmin via l’application Connect).'
        : (result.reason || 'Activation impossible.');
      this._notificationMessage(this.pushMessage);
    });
    this.element.querySelector('[data-action="test-push"]')?.addEventListener('click', async () => {
      this._notificationMessage('Envoi du test en cours…');
      try {
        const result = await sendTestNotification();
        this.pushMessage = result.push_sent
          ? 'Notification de test envoyée sur ce téléphone.'
          : 'Test créé mais non délivré : aucun abonnement actif sur ce téléphone (ou clés VAPID non configurées).';
      }
      catch (error) { this.pushMessage = error.data?.detail || error.message || 'Envoi du test impossible.'; }
      this._notificationMessage(this.pushMessage);
    });
  }

  _rerender() { const oldElement = this.element; const parent = oldElement?.parentElement; if (parent) { const rendered = this.render(); parent.replaceChild(rendered, oldElement); } }
  _message(message) { const node = this.element.querySelector('[data-message]'); if (node) node.textContent = message; }
  _notificationMessage(message) { const node = this.element.querySelector('[data-notification-message]'); if (node) node.textContent = message; }
  _escape(value) { const node = document.createElement('div'); node.textContent = value || ''; return node.innerHTML; }
}

export function createSportGarminPage() { return new SportGarminPage(); }
