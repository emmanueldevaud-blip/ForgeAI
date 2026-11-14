import { authStore } from '../stores/auth.js';
import { api } from '../services/api.js';
import {
  getMetaSettings,
  updateMetaSettings,
  testMetaSettings,
} from '../services/adminApi.js?v=7';
import { createSportGarminPage } from './SportGarminPage.js?v=5';
import {
  getInstagramAuthUrl,
  getInstagramConnectionStatus,
  getInstagramPreflight,
  disconnectInstagram,
} from '../services/sportApi.js?v=3';

export class UserSettingsPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.user = null;
    this.metaSettings = null;
    this.instagramStatus = null;
    this.currentTab = 'preferences';
    this.garminPage = null;
    this.canSeeGarmin = false;
  }

  async initialize() {
    try {
      await authStore.loadCurrentUser();
    } catch (error) {
      console.error('Erreur chargement utilisateur:', error);
    }
    this.user = authStore.currentUser;
    this.canConfigureMeta = !!authStore?.authenticated && authStore.hasPermission('settings_view');
    this.showMetaTab = this.canConfigureMeta;

    this.canSeeGarmin = !!authStore?.authenticated && authStore.hasPermission('sport.activities.write');
    if (this.canSeeGarmin) {
      this.garminPage = createSportGarminPage(this.router);
      try { await this.garminPage.initialize(); } catch (error) { console.error('Erreur chargement parametres Garmin:', error); }
    }

    if (this.canConfigureMeta) {
      try {
        this.metaSettings = await getMetaSettings();
      } catch (error) {
        console.error('Erreur chargement paramètres Meta:', error);
      }
      try {
        this.instagramStatus = await getInstagramConnectionStatus();
      } catch (error) {
        console.error('Erreur chargement connexion Meta:', error);
      }
      // Retour du callback OAuth Meta : ouvrir l'onglet Meta.
      const igParams = new URLSearchParams(window.location.search);
      if ((igParams.has('connected') || igParams.has('error')) && this.showMetaTab) {
        this.currentTab = 'meta';
      }
    }
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
    const canMeta = !!this.showMetaTab;
    if (!canMeta && !this.canSeeGarmin) this.currentTab = 'preferences';
    const metaConfigured = !!(
      this.metaSettings?.app_id &&
      this.metaSettings?.app_secret_configured &&
      this.metaSettings?.config_id
    );
    const igConnected = !!this.instagramStatus?.connected;

    this.element.innerHTML = `
      <div class="page-header">
        <div>
          <h1>Paramètres</h1>
          <p class="page-subtitle">Préférences personnelles</p>
        </div>
      </div>

      <div class="admin-tabs" role="tablist" aria-label="Sections des paramètres">
        <button
          class="admin-tab ${this.currentTab === 'preferences' ? 'admin-tab--active' : ''}"
          role="tab"
          id="tab-preferences"
          data-tab="preferences"
          aria-selected="${this.currentTab === 'preferences'}"
        >Préférences</button>
        ${this.canSeeGarmin ? `
        <button
          class="admin-tab ${this.currentTab === 'garmin' ? 'admin-tab--active' : ''}"
          role="tab"
          id="tab-garmin"
          data-tab="garmin"
          aria-selected="${this.currentTab === 'garmin'}"
        >Garmin</button>` : ''}
        ${this.showMetaTab ? `
        <button
          class="admin-tab ${this.currentTab === 'meta' ? 'admin-tab--active' : ''}"
          role="tab"
          id="tab-meta"
          data-tab="meta"
          aria-selected="${this.currentTab === 'meta'}"
        >Meta</button>` : ''}
      </div>

      <div class="admin-tab-panels">
        <div
          class="admin-tab-panel ${this.currentTab === 'preferences' ? 'admin-tab-panel--active' : ''}"
          data-tab-panel="preferences"
          role="tabpanel"
          aria-labelledby="tab-preferences"
          ${this.currentTab !== 'preferences' ? 'hidden' : ''}
        >
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
        </div>

        ${this.canSeeGarmin ? `
        <div
          class="admin-tab-panel ${this.currentTab === 'garmin' ? 'admin-tab-panel--active' : ''}"
          data-tab-panel="garmin"
          role="tabpanel"
          aria-labelledby="tab-garmin"
          ${this.currentTab !== 'garmin' ? 'hidden' : ''}
        >
        </div>` : ''}

        ${this.showMetaTab ? `
        <div
          class="admin-tab-panel ${this.currentTab === 'meta' ? 'admin-tab-panel--active' : ''}"
          data-tab-panel="meta"
          role="tabpanel"
          aria-labelledby="tab-meta"
          ${this.currentTab !== 'meta' ? 'hidden' : ''}
        >
          ${this.canConfigureMeta ? `
          <div class="card">
            <div class="card-header">
              <div>
                <span class="eyebrow">Meta — Instagram Unified Login</span>
                <p class="text-muted">Connexion Meta centralisée : identifiants de l'application, configuration (Config ID) et jeton SUAT.</p>
              </div>
              <span class="status-badge ${metaConfigured ? 'active' : 'inactive'}" data-meta-badge>
                ${metaConfigured ? 'Configurée' : 'Non configurée'}
              </span>
            </div>
            <form data-form="meta-settings" class="card-body">
              <div class="form-row">
                <div class="form-group">
                  <label><span>App ID *</span>
                    <input name="app_id" autocomplete="off" maxlength="100" required placeholder="Identifiant de l'application Meta">
                  </label>
                </div>
                <div class="form-group">
                  <label><span>App Secret</span>
                    <input name="app_secret" type="password" autocomplete="new-password" maxlength="500" placeholder="Non configurée">
                    <small class="form-help" data-role="secret-help">Laisser vide pour conserver la valeur enregistrée.</small>
                  </label>
                </div>
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label><span>Config ID</span>
                    <input name="config_id" autocomplete="off" maxlength="100" placeholder="ID de configuration Unified Login">
                    <small class="form-help">Configuration « API setup with Unified login » de l'application Meta.</small>
                  </label>
                </div>
                <div class="form-group">
                  <label><span>Adresse de callback</span>
                    <input name="redirect_uri" type="url" maxlength="500" placeholder="https://…">
                    <small class="form-help">URL de redirection déclarée dans la configuration Meta.</small>
                  </label>
                </div>
              </div>
              <div class="form-row">
                <div class="form-group" style="grid-column: 1 / -1;">
                  <label><span>Meta Access Token (SUAT)</span>
                    <input name="access_token" type="password" autocomplete="new-password" maxlength="4000" placeholder="Aucun token enregistré">
                    <small class="form-help" data-role="token-help">Laisser vide pour conserver le jeton enregistré. Le token n'est jamais réaffiché après enregistrement.</small>
                  </label>
                </div>
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label><span>Business Portfolio ID</span>
                    <input name="client_business_id" maxlength="100" placeholder="ID du Business Portfolio Meta">
                    <small class="form-help">Optionnel : permet de vérifier que le token appartient au bon portefeuille.</small>
                  </label>
                </div>
                <div class="form-group">
                  <label><span>Instagram User ID</span>
                    <input name="instagram_user_id" maxlength="100" placeholder="ID du compte Instagram Business">
                    <small class="form-help">Optionnel : vérifie que le compte est bien partagé au portefeuille.</small>
                  </label>
                </div>
              </div>
              <div class="page-subtitle" data-role="meta-connection"></div>
              <div class="form-actions">
                <button class="btn btn-primary" type="button" data-meta-connect>Se connecter à Meta</button>
                <button class="btn btn-secondary" type="button" data-meta-disconnect ${igConnected ? '' : 'hidden'}>Déconnecter</button>
                <button class="btn btn-secondary" type="button" data-meta-test>Tester la connexion</button>
                <button class="btn btn-primary" type="submit">Enregistrer</button>
                <span data-role="meta-status" role="status"></span>
              </div>
              <div data-role="meta-test-result" aria-live="polite"></div>
            </form>
          </div>` : ''}

        </div>` : ''}

      </div>
    `;

    const garminPanel = this.element.querySelector('[data-tab-panel="garmin"]');
    if (garminPanel && this.garminPage) {
      garminPanel.innerHTML = '';
      garminPanel.appendChild(this.garminPage.render());
    }

    this._bindEvents();
    return this.element;
  }

  _bindEvents() {
    this.element.querySelectorAll('[data-tab]').forEach((btn) => {
      btn.addEventListener('click', () => this._switchTab(btn.dataset.tab));
    });

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

    const metaForm = this.element.querySelector('[data-form="meta-settings"]');
    if (metaForm) {
      const message = this.element.querySelector('[data-role="meta-status"]');
      const testResult = this.element.querySelector('[data-role="meta-test-result"]');
      const setValue = (name, value) => { metaForm.elements[name].value = value ?? ''; };
      setValue('app_id', this.metaSettings?.app_id);
      setValue('config_id', this.metaSettings?.config_id);
      setValue('redirect_uri', this.metaSettings?.redirect_uri);
      setValue('client_business_id', this.metaSettings?.client_business_id);
      setValue('instagram_user_id', this.metaSettings?.instagram_user_id);
      const secretInput = metaForm.elements.app_secret;
      if (secretInput) {
        secretInput.placeholder = this.metaSettings?.app_secret_configured
          ? 'Configurée — laisser vide pour conserver'
          : 'Non configurée';
      }
      const tokenInput = metaForm.elements.access_token;
      if (tokenInput) {
        tokenInput.placeholder = this.metaSettings?.access_token_configured
          ? 'Token enregistré — laisser vide pour conserver'
          : 'Aucun token enregistré';
      }

      const setStatus = (text, success) => {
        message.textContent = text;
        message.classList.toggle('text-success', !!success);
      };

      const renderTestResult = (result) => {
        if (!testResult) return;
        testResult.innerHTML = '';
        (result?.steps || []).forEach((step) => {
          const line = document.createElement('div');
          const cls = step.status === 'ok' ? 'text-success'
            : step.status === 'error' ? 'text-danger'
            : step.status === 'warning' ? 'text-warning'
            : 'text-muted';
          line.className = `page-subtitle ${cls}`;
          line.textContent = `${step.label} — ${step.detail || step.status}`;
          testResult.appendChild(line);
        });
      };

      metaForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const submitBtn = metaForm.querySelector('[type="submit"]');
        if (submitBtn?.disabled) return;
        if (submitBtn) submitBtn.disabled = true;
        try {
          this.metaSettings = await updateMetaSettings({
            app_id: metaForm.elements.app_id.value.trim(),
            app_secret: metaForm.elements.app_secret.value,
            config_id: metaForm.elements.config_id.value.trim(),
            redirect_uri: metaForm.elements.redirect_uri.value.trim(),
            access_token: metaForm.elements.access_token.value,
            client_business_id: metaForm.elements.client_business_id.value.trim(),
            instagram_user_id: metaForm.elements.instagram_user_id.value.trim(),
          });
          metaForm.elements.app_secret.value = '';
          metaForm.elements.access_token.value = '';
          if (secretInput && this.metaSettings?.app_secret_configured) {
            secretInput.placeholder = 'Configurée — laisser vide pour conserver';
          }
          if (tokenInput) {
            tokenInput.placeholder = this.metaSettings?.access_token_configured
              ? 'Token enregistré — laisser vide pour conserver'
              : 'Aucun token enregistré';
          }
          this._updateMetaBadge();
          await this._refreshMetaConnection();
          setStatus('Paramètres Meta enregistrés.', true);
        } catch (error) {
          setStatus(error.message || "Erreur lors de l'enregistrement.", false);
        } finally {
          if (submitBtn) submitBtn.disabled = false;
        }
      });

      const testBtn = metaForm.querySelector('[data-meta-test]');
      testBtn?.addEventListener('click', async () => {
        if (testBtn.disabled) return;
        testBtn.disabled = true;
        setStatus('Test en cours…', false);
        if (testResult) testResult.innerHTML = '';
        try {
          const result = await testMetaSettings();
          const ok = result.status === 'operational';
          setStatus(result.message || 'Connexion Meta validée.', ok);
          renderTestResult(result);
        } catch (error) {
          setStatus(error.data?.detail || error.message || 'Échec du test Meta.', false);
        } finally {
          testBtn.disabled = false;
        }
      });

      this._bindMetaConnection(metaForm);
    }
  }

  _bindMetaConnection(metaForm) {
    const message = this.element?.querySelector('[data-role="meta-status"]');
    const setMetaMessage = (text, success) => {
      if (!message) return;
      message.textContent = text;
      message.classList.toggle('text-success', !!success);
    };

    // Retour du callback OAuth Meta (?connected=1 ou ?error=…).
    const params = new URLSearchParams(window.location.search);
    if (params.has('connected')) {
      setMetaMessage('Compte Meta connecté.', true);
    } else if (params.get('error')) {
      setMetaMessage(params.get('error'), false);
    }
    if (params.has('connected') || params.has('error')) {
      const cleanUrl = new URL(window.location.href);
      cleanUrl.searchParams.delete('connected');
      cleanUrl.searchParams.delete('error');
      window.history.replaceState({}, '', cleanUrl);
    }

    const connectBtn = metaForm.querySelector('[data-meta-connect]');
    connectBtn?.addEventListener('click', async () => {
      if (connectBtn.disabled) return;
      connectBtn.disabled = true;
      setMetaMessage('Vérification de la configuration Meta…', false);
      try {
        // Pré-vérification avant de lancer le dialogue OAuth.
        let preflight;
        try {
          preflight = await getInstagramPreflight();
        } catch (preflightError) {
          // Si le preflight échoue (réseau, 503…), on tente quand même la connexion.
          console.warn('Preflight Meta indisponible:', preflightError);
        }
        if (preflight && !preflight.ready) {
          // Affiche les erreurs de configuration détectées.
          const details = (preflight.checks || [])
            .filter(c => c.status === 'error')
            .map(c => c.detail)
            .join(' ');
          setMetaMessage(
            details || preflight.message || 'Configuration Meta incomplète.',
            false,
          );
          connectBtn.disabled = false;
          return;
        }

        setMetaMessage('Démarrage de la connexion Meta…', false);
        const info = await getInstagramAuthUrl();
        if (!info?.authorize_url) {
          setMetaMessage(
            "Connexion Meta non configurée : renseignez l'App ID, l'App Secret, le Config ID et le callback.",
            false,
          );
          return;
        }
        // Redirection navigateur vers l'autorisation Unified Login (dialog Meta).
        window.location.assign(info.authorize_url);
      } catch (error) {
        setMetaMessage(
          error?.data?.detail || error?.message || 'Echec du lancement de la connexion Meta.',
          false,
        );
        connectBtn.disabled = false;
      }
    });

    const disconnectBtn = metaForm.querySelector('[data-meta-disconnect]');
    disconnectBtn?.addEventListener('click', async () => {
      if (disconnectBtn.disabled) return;
      disconnectBtn.disabled = true;
      try {
        await disconnectInstagram();
        await this._refreshMetaConnection();
        setMetaMessage('Connexion Meta déconnectée.', true);
      } catch (error) {
        setMetaMessage(error?.message || 'Déconnexion impossible.', false);
      } finally {
        disconnectBtn.disabled = false;
      }
    });

    this._renderMetaConnection();
  }

  async _refreshMetaConnection() {
    try {
      this.instagramStatus = await getInstagramConnectionStatus();
    } catch (error) {
      console.error('Erreur chargement connexion Meta:', error);
    }
    this._renderMetaConnection();
  }

  _renderMetaConnection() {
    const disconnectBtn = this.element?.querySelector('[data-meta-disconnect]');
    const info = this.element?.querySelector('[data-role="meta-connection"]');
    const status = this.instagramStatus;
    const connected = !!status?.connected;

    if (disconnectBtn) disconnectBtn.hidden = !connected;
    if (info) {
      if (connected) {
        const username = status.username ? `@${status.username} — ` : '';
        info.textContent = `Compte connecté : ${username}ID ${status.instagram_user_id}`;
      } else if (status && !status.configured) {
        info.textContent = 'Connexion Meta non configurée (App ID, App Secret, Config ID ou callback manquant).';
      } else {
        info.textContent = 'Aucun compte Meta connecté.';
      }
    }
  }

  _updateMetaBadge() {
    const badge = this.element?.querySelector('[data-meta-badge]');
    if (!badge) return;
    const configured = !!(
      this.metaSettings?.app_id &&
      (this.metaSettings?.app_secret_configured || this.metaSettings?.access_token_configured) &&
      this.metaSettings?.config_id
    );
    badge.textContent = configured ? 'Configurée' : 'Non configurée';
    badge.classList.toggle('active', configured);
    badge.classList.toggle('inactive', !configured);
  }

  _switchTab(tabId) {
    if (tabId === 'meta' && !this.showMetaTab) return;
    if (tabId === 'garmin' && !this.canSeeGarmin) return;
    this.currentTab = tabId;
    this.element.querySelectorAll('[data-tab]').forEach((el) => {
      const active = el.dataset.tab === tabId;
      el.classList.toggle('admin-tab--active', active);
      el.setAttribute('aria-selected', String(active));
    });
    this.element.querySelectorAll('[data-tab-panel]').forEach((el) => {
      const active = el.dataset.tabPanel === tabId;
      el.classList.toggle('admin-tab-panel--active', active);
      el.hidden = !active;
    });
  }
}

export function createSettingsPage(router) {
  return new UserSettingsPage(router);
}
