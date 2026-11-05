import { authStore } from '../stores/auth.js';
import { api } from '../services/api.js';
import { getMetaSettings, updateMetaSettings, testMetaSettings } from '../services/adminApi.js?v=4';
import {
  getInstagramConnectionStatus,
  connectInstagram,
  disconnectInstagram,
} from '../services/sportApi.js?v=9';
import { createSportGarminPage } from './SportGarminPage.js?v=5';

export class UserSettingsPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.user = null;
    this.metaSettings = null;
    this.instagramStatus = null;
    this.connectedFlash = false;
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
    this.canSeeInstagram = !!authStore?.authenticated && authStore.hasPermission('sport.publications.read');
    this.canManageInstagram = !!authStore?.authenticated && authStore.hasPermission('sport.publications.write');
    this.showMetaTab = this.canConfigureMeta || this.canSeeInstagram;

    if (typeof window !== 'undefined' && window.location.search.includes('connected=1')) {
      this.connectedFlash = true;
      try {
        const url = new URL(window.location.href);
        url.searchParams.delete('connected');
        window.history.replaceState({}, '', url.pathname + (url.search ? url.search : ''));
      } catch (_) {}
      if (this.showMetaTab) this.currentTab = 'meta';
    }

    if (this.canConfigureMeta) {
      try {
        this.metaSettings = await getMetaSettings();
      } catch (error) {
        console.error('Erreur chargement paramètres Meta:', error);
      }
    }
    if (this.canSeeInstagram) {
      await this._loadInstagramStatus();
    }
    this.canSeeGarmin = !!authStore?.authenticated && authStore.hasPermission('sport.activities.write');
    if (this.canSeeGarmin) {
      this.garminPage = createSportGarminPage(this.router);
      try { await this.garminPage.initialize(); } catch (error) { console.error('Erreur chargement parametres Garmin:', error); }
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
    if (!canMeta) this.currentTab = 'preferences';
    const metaConfigured = !!(this.metaSettings?.app_id && this.metaSettings?.app_secret_configured);
    const igInfo = this._instagramInfo();

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
        ${canMeta ? `
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

        ${canMeta ? `
        <div
          class="admin-tab-panel ${this.currentTab === 'meta' ? 'admin-tab-panel--active' : ''}"
          data-tab-panel="meta"
          role="tabpanel"
          aria-labelledby="tab-meta"
          style="display: flex; flex-direction: column; gap: var(--spacing-5);"
          ${this.currentTab !== 'meta' ? 'hidden' : ''}
        >
          ${this.canConfigureMeta ? `
          <div class="card">
            <div class="card-header">
              <div>
                <span class="eyebrow">Meta — Instagram Business</span>
                <p class="text-muted">Connexion OAuth utilisée pour les statistiques des publications.</p>
              </div>
              <span class="status-badge ${metaConfigured ? 'active' : 'inactive'}" data-meta-badge>
                ${metaConfigured ? 'Configurée' : 'Non configurée'}
              </span>
            </div>
            <form data-form="meta-settings" class="card-body">
              <div class="form-row">
                <div class="form-group">
                  <label><span>App ID *</span>
                    <input name="app_id" maxlength="100" required placeholder="Identifiant de l'application Meta">
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
                    <input name="redirect_uri" type="url" maxlength="500" placeholder="https://…/sport/publications/meta/callback">
                    <small class="form-help">Doit correspondre à l'URL de redirection déclarée dans l'application Meta.</small>
                  </label>
                </div>
              </div>
              <div class="form-row">
                <div class="form-group" style="grid-column: 1 / -1;">
                  <label><span>Configuration ID (Unified Login)</span>
                    <input name="config_id" maxlength="100" placeholder="ID de configuration Facebook Login for Business">
                    <small class="form-help">Obligatoire pour les nouvelles apps Meta (API setup with Unified Login). Laisser vide pour l'ancien flux par permission (scope).</small>
                  </label>
                </div>
              </div>
              <div class="form-actions">
                <button class="btn btn-secondary" type="button" data-meta-test>Tester la connexion</button>
                <button class="btn btn-primary" type="submit">Enregistrer</button>
                <span data-role="meta-status" role="status"></span>
              </div>
            </form>
          </div>` : ''}

          ${this.canSeeInstagram ? `
          <div class="card">
            <div class="card-header">
              <div>
                <span class="eyebrow">Connexion Instagram</span>
                <p class="text-muted">Compte Instagram Business relié à vos publications.</p>
              </div>
              <span class="status-badge ${igInfo.badgeClass}" data-ig-badge>${igInfo.badgeText}</span>
            </div>
            <div class="card-body">
              <p class="page-subtitle" data-ig-detail>${igInfo.detail}</p>
              ${this.canManageInstagram ? `
              <div class="form-actions">
                <button class="btn btn-primary" type="button" data-ig-connect>
                  ${this.instagramStatus?.connected ? 'Reconnecter' : 'Connecter Instagram'}
                </button>
                ${this.instagramStatus?.connected ? '<button class="btn btn-secondary" type="button" data-ig-disconnect>Se déconnecter</button>' : ''}
                <span data-role="ig-status" role="status"></span>
              </div>` : `
              <div class="form-actions">
                <span data-role="ig-status" role="status"></span>
              </div>`}
            </div>
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
      const setValue = (name, value) => { metaForm.elements[name].value = value ?? ''; };
      setValue('app_id', this.metaSettings?.app_id);
      setValue('redirect_uri', this.metaSettings?.redirect_uri);
      setValue('config_id', this.metaSettings?.config_id);
      const secretInput = metaForm.elements.app_secret;
      if (secretInput) {
        secretInput.placeholder = this.metaSettings?.app_secret_configured
          ? 'Configurée — laisser vide pour conserver'
          : 'Non configurée';
      }

      const setStatus = (text, success) => {
        message.textContent = text;
        message.classList.toggle('text-success', !!success);
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
          });
          metaForm.elements.app_secret.value = '';
          if (secretInput && this.metaSettings?.app_secret_configured) {
            secretInput.placeholder = 'Configurée — laisser vide pour conserver';
          }
          this._updateMetaBadge();
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
        try {
          const result = await testMetaSettings();
          setStatus(result.message || 'Connexion Meta validée.', true);
        } catch (error) {
          setStatus(error.data?.detail || error.message || 'Échec du test Meta.', false);
        } finally {
          testBtn.disabled = false;
        }
      });
    }

    await this._bindInstagram();
  }

  async _bindInstagram() {
    const setIgMessage = (text, success) => {
      const el = this.element?.querySelector('[data-role="ig-status"]');
      if (!el) return;
      el.textContent = text;
      el.classList.toggle('text-success', !!success);
    };

    this.element.querySelector('[data-ig-connect]')?.addEventListener('click', async (event) => {
      const btn = event.currentTarget;
      if (btn.disabled) return;
      btn.disabled = true;
      try {
        const data = await connectInstagram(null);
        const url = data && data.authorize_url;
        if (url) {
          window.location.href = url;
          return;
        }
        setIgMessage('URL de connexion Meta non reçue', false);
      } catch (error) {
        setIgMessage(error?.data?.detail || error?.message || 'Connexion Instagram impossible', false);
      } finally {
        btn.disabled = false;
      }
    });

    this.element.querySelector('[data-ig-disconnect]')?.addEventListener('click', async (event) => {
      const btn = event.currentTarget;
      if (btn.disabled) return;
      btn.disabled = true;
      setIgMessage('Déconnexion en cours…', false);
      try {
        await disconnectInstagram();
        await this._loadInstagramStatus();
        setIgMessage('Instagram déconnecté', true);
      } catch (error) {
        setIgMessage(error?.data?.detail || 'Erreur lors de la déconnexion', false);
        btn.disabled = false;
      }
    });

    if (this.connectedFlash) {
      this.connectedFlash = false;
      await this._loadInstagramStatus();
      setIgMessage('Compte Instagram connecté avec succès !', true);
    }
  }

  async _loadInstagramStatus() {
    try {
      this.instagramStatus = (await getInstagramConnectionStatus()) || this.instagramStatus;
    } catch (error) {
      this.instagramStatus = { connected: false, status: 'not_configured' };
    }
    if (this.element) {
      const badge = this.element.querySelector('[data-ig-badge]');
      const detail = this.element.querySelector('[data-ig-detail]');
      if (badge || detail) {
        const info = this._instagramInfo();
        if (badge) {
          badge.textContent = info.badgeText;
          badge.className = `status-badge ${info.badgeClass}`;
        }
        if (detail) detail.textContent = info.detail;
        const cardBody = badge?.closest('.card')?.querySelector('.card-body');
        if (cardBody && this.canManageInstagram) {
          const actions = cardBody.querySelector('.form-actions');
          if (actions) {
            const keepMsg = actions.querySelector('[data-role="ig-status"]');
            const msgHtml = keepMsg ? keepMsg.outerHTML : '<span data-role="ig-status" role="status"></span>';
            actions.innerHTML = `
              <button class="btn btn-primary" type="button" data-ig-connect>
                ${this.instagramStatus?.connected ? 'Reconnecter' : 'Connecter Instagram'}
              </button>
              ${this.instagramStatus?.connected ? '<button class="btn btn-secondary" type="button" data-ig-disconnect>Se déconnecter</button>' : ''}
              ${msgHtml}
            `;
            this._bindInstagram();
          }
        }
      }
    }
  }

  _instagramInfo() {
    const status = this.instagramStatus || {};
    if (status.connected) {
      const acct = status.instagram_business_account_id ? ` (ID : ${status.instagram_business_account_id})` : '';
      return {
        badgeClass: 'active',
        badgeText: 'Connecté',
        detail: `Compte Instagram connecté${acct}. Les publications peuvent être partagées.`,
      };
    }
    if (status.configured === false) {
      return {
        badgeClass: 'badge-warning',
        badgeText: 'Non configuré',
        detail: "Meta App non configurée : renseignez l'App ID et l'App Secret ci-dessus.",
      };
    }
    return {
      badgeClass: 'inactive',
      badgeText: 'Non connecté',
      detail: 'Aucun compte Instagram connecté pour le moment.',
    };
  }

  _updateMetaBadge() {
    const badge = this.element?.querySelector('[data-meta-badge]');
    if (!badge) return;
    const configured = !!(this.metaSettings?.app_id && this.metaSettings?.app_secret_configured);
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
