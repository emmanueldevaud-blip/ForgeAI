import { authStore } from '../stores/auth.js';
import { api } from '../services/api.js';
import {
  getMetaSettings,
  updateMetaSettings,
  testMetaSettings,
} from '../services/adminApi.js?v=6';
import { createSportGarminPage } from './SportGarminPage.js?v=5';
import { initMetaLogin } from '../services/sportApi.js?v=2';

export class UserSettingsPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.user = null;
    this.metaSettings = null;
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
    const metaConfigured = !!(this.metaSettings?.app_id && this.metaSettings?.app_secret_configured);

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
                <span class="eyebrow">Meta — Instagram Business</span>
                <p class="text-muted">Configuration Meta Business centralisée : identifiants d'application et jeton SUAT.</p>
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
                <div class="form-group" style="grid-column: 1 / -1;">
                  <label><span>Adresse de callback</span>
                    <input name="redirect_uri" type="url" maxlength="500" placeholder="https://…">
                    <small class="form-help">URL de redirection déclarée dans l'application Meta.</small>
                  </label>
                </div>
              </div>
              <div class="form-row">
                <div class="form-group" style="grid-column: 1 / -1;">
                  <label><span>Configuration ID (Unified Login)</span>
                    <input name="config_id" maxlength="100" placeholder="ID de configuration Facebook Login for Business">
                    <small class="form-help">Configuration Facebook Login for Business (API setup with Unified Login) déclarée dans l'application Meta.</small>
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
              <div class="form-actions">
                <button class="btn btn-primary" type="button" data-meta-connect>Connecter mon compte Meta</button>
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
      setValue('redirect_uri', this.metaSettings?.redirect_uri);
      setValue('config_id', this.metaSettings?.config_id);
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
            redirect_uri: metaForm.elements.redirect_uri.value.trim(),
            config_id: metaForm.elements.config_id.value.trim(),
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
          setStatus('Paramètres Meta enregistrés.', true);
        } catch (error) {
          setStatus(error.message || "Erreur lors de l'enregistrement.", false);
        } finally {
          if (submitBtn) submitBtn.disabled = false;
        }
      });

      const connectBtn = metaForm.querySelector('[data-meta-connect]');
      connectBtn?.addEventListener('click', async () => {
        if (connectBtn.disabled) return;
        connectBtn.disabled = true;
        setStatus('Demarrage du parcours Meta…', false);
        if (testResult) testResult.innerHTML = '';
        try {
          const info = await initMetaLogin();
          const state = info?.state;
          const configId = info?.config_id;
          const appId = info?.app_id;
          const redirectUri = info?.redirect_uri;
          if (!state || !configId) {
            setStatus("Parametres Meta incomplets : renseignez l'App ID et la Configuration ID.", false);
            return;
          }
          if (window.FB && !window.FB.__forgeai_initialized) {
            window.FB.init({ appId: appId || this.metaSettings?.app_id });
            window.FB.__forgeai_initialized = true;
          }
          window.FB?.login?.({
            config_id: configId,
            response_type: 'code',
            override_default_response_type: true,
            redirect_uri: redirectUri,
            state: state,
            success: async () => {
              setStatus('Meta connecte.', true);
              try { await this._loadMeta(); } catch (error) { console.error('Erreur recharge parametres Meta:', error); }
            },
            fail: async () => { setStatus('Echec de la connexion Meta.', false); },
          });
        } catch (error) {
          setStatus(error?.data?.detail || error?.message || 'Echec du lancement Meta.', false);
        } finally {
          connectBtn.disabled = false;
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
    }

  }

  _updateMetaBadge() {
    const badge = this.element?.querySelector('[data-meta-badge]');
    if (!badge) return;
    const configured = !!(
      this.metaSettings?.app_id &&
      (this.metaSettings?.app_secret_configured || this.metaSettings?.access_token_configured)
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
