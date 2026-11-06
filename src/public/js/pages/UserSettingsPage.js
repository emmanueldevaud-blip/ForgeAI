import { authStore } from '../stores/auth.js';
import { api } from '../services/api.js';
import { getMetaSettings, updateMetaSettings, testMetaSettings } from '../services/adminApi.js?v=4';
import {
  getInstagramConnectionStatus,
  connectInstagram,
  disconnectInstagram,
  getCommunityManagerStrategy,
  updateCommunityManagerStrategy,
  generateCommunityManagerCalendar,
  getCommunityManagerCalendar,
  updateCommunityManagerCalendarEntry,
  deleteCommunityManagerCalendarEntry,
  createStudioDraftFromCalendar,
} from '../services/sportApi.js?v=10';
import { createSportGarminPage } from './SportGarminPage.js?v=5';
import { createCommunityManagerStudioPage } from './CommunityManagerStudioPage.js?v=1';

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
    // Community Manager state
    this.cmStrategy = null;
    this.cmCalendar = [];
    this.cmGenerating = false;
    this.cmError = null;
    this.cmSuccess = null;
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

    // Community Manager permissions
    this.canViewCMStrategy = !!authStore?.authenticated && authStore.hasPermission('community_manager.strategy_view');
    this.canUpdateCMStrategy = !!authStore?.authenticated && authStore.hasPermission('community_manager.strategy_update');
    this.canGenerateCMCalendar = !!authStore?.authenticated && authStore.hasPermission('community_manager.calendar_generate');
    this.canViewCMCalendar = !!authStore?.authenticated && authStore.hasPermission('community_manager.calendar_view');
    this.showCMTab = this.canViewCMStrategy || this.canUpdateCMStrategy || this.canGenerateCMCalendar || this.canViewCMCalendar;

    // Handle OAuth callback parameters
    if (typeof window !== 'undefined') {
      const searchParams = new URLSearchParams(window.location.search);
      let shouldShowMetaTab = false;
      let errorMessage = null;
      let successMessage = null;

      if (searchParams.has('error')) {
        errorMessage = decodeURIComponent(searchParams.get('error'));
        searchParams.delete('error');
        shouldShowMetaTab = true;
      }
      if (searchParams.has('connected')) {
        successMessage = 'Compte Instagram connecté avec succès !';
        searchParams.delete('connected');
        shouldShowMetaTab = true;
      }
      // If both present, error takes precedence (security)
      if (shouldShowMetaTab && this.showMetaTab) {
        this.currentTab = 'meta';
      }
      // Update URL without reload
      try {
        const url = new URL(window.location.href);
        url.search = searchParams.toString();
        window.history.replaceState({}, '', url.pathname + (url.search ? '?' + url.search : ''));
      } catch (_) {}

      if (errorMessage) {
        this.oauthError = errorMessage;
      }
      if (successMessage && !errorMessage) {
        this.connectedFlash = true;
      }
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
    if (this.showCMTab) {
      await this._loadCMStrategy();
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
    const canCM = !!this.showCMTab;
    if (!canMeta && !canCM) this.currentTab = 'preferences';
    const metaConfigured = !!(this.metaSettings?.app_id && this.metaSettings?.app_secret_configured);
    const igInfo = this._instagramInfo();
    const cmConfigured = !!this.cmStrategy;
    const cmHasCalendar = this.cmCalendar.length > 0;

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
        ${canCM ? `
        <button
          class="admin-tab ${this.currentTab === 'cm' ? 'admin-tab--active' : ''}"
          role="tab"
          id="tab-cm"
          data-tab="cm"
          aria-selected="${this.currentTab === 'cm'}"
        >Stratégie IA</button>` : ''}
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

          ${this.oauthError ? `
          <div class="card">
            <div class="card-body">
              <div class="alert alert-error">${this._escape(this.oauthError)}</div>
            </div>
          </div>` : ''}

          ${this.connectedFlash ? `
          <div class="card">
            <div class="card-body">
              <div class="alert alert-success">Compte Instagram connecté avec succès !</div>
            </div>
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

        ${canCM ? `
        <div
          class="admin-tab-panel ${this.currentTab === 'cm' ? 'admin-tab-panel--active' : ''}"
          data-tab-panel="cm"
          role="tabpanel"
          aria-labelledby="tab-cm"
          ${this.currentTab !== 'cm' ? 'hidden' : ''}
        >
          ${this._renderCMTab()}
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

    this._bindInstagram();
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

  _escape(text) {
    if (text == null) return '';
    return String(text)
      .replaceAll('&', '&')
      .replaceAll('<', '<')
      .replaceAll('>', '>')
      .replaceAll('"', '"')
      .replaceAll("'", '&#039;');
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

  // --- Community Manager methods ---

  async _loadCMStrategy() {
    try {
      const result = await getCommunityManagerStrategy();
      if (result?.configured && result?.strategy) {
        this.cmStrategy = result.strategy;
      } else {
        this.cmStrategy = null;
      }
      // Charger le calendrier si stratégie existe
      if (this.cmStrategy) {
        await this._loadCMCalendar();
      }
    } catch (error) {
      console.error('Erreur chargement stratégie CM:', error);
      this.cmStrategy = null;
    }
  }

  async _loadCMCalendar() {
    try {
      const result = await getCommunityManagerCalendar();
      this.cmCalendar = result?.calendar || [];
    } catch (error) {
      console.error('Erreur chargement calendrier CM:', error);
      this.cmCalendar = [];
    }
  }

  _renderCMTab() {
    const configured = !!this.cmStrategy;
    const hasCalendar = this.cmCalendar.length > 0;

    if (!configured) {
      // État 1 : Non configuré -> Formulaire de stratégie
      return this._renderCMStrategyForm();
    }

    if (!hasCalendar) {
      // État 2 : Configuré mais pas de calendrier -> Zone de génération
      return this._renderCMGenerationZone();
    }

    // État 3 : Calendrier généré -> Tableau avec propositions
    return this._renderCMCalendarTable();
  }

  _renderCMStrategyForm() {
    const s = this.cmStrategy || {};
    const tones = ['professional', 'inspirational', 'casual', 'expert', 'motivational', 'educational'];
    const objectives = ['engagement', 'visibility', 'brand_awareness', 'community_building', 'lead_generation'];
    const themes = ['running', 'recovery', 'nutrition', 'training', 'gear', 'mental', 'races', 'lifestyle'];
    const networks = ['instagram', 'facebook', 'linkedin', 'twitter', 'threads'];

    const toneOptions = tones.map(t => `<option value="${t}">${t}</option>`).join('');
    const objectiveOptions = objectives.map(o => `<option value="${o}">${o}</option>`).join('');
    const themeOptions = themes.map(t => `<option value="${t}">${t}</option>`).join('');
    const networkOptions = networks.map(n => `<option value="${n}">${n}</option>`).join('');

    return `
      <div class="card">
        <div class="card-header">
          <div>
            <span class="eyebrow">Stratégie éditoriale — Community Manager IA</span>
            <p class="text-muted">Configurez votre identité de marque, vos thèmes et votre ton pour la génération automatique de calendrier éditorial.</p>
          </div>
          <span class="status-badge inactive">Non configurée</span>
        </div>
        <form data-form="community-manager-strategy" class="card-body">
          <div class="form-row">
            <div class="form-group" style="grid-column: 1 / -1;">
              <label><span>Identité de marque *</span>
                <input name="brand_identity" type="text" maxlength="200" placeholder="Ex: ForgeAI" value="${this._escape(s.brand_identity || '')}" required>
              </label>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label><span>Ton *</span>
                <select name="tone" multiple size="4" required>
                  ${toneOptions}
                </select>
                <small class="form-help">Maintenez Ctrl/Cmd pour sélectionner plusieurs tons.</small>
              </label>
            </div>
            <div class="form-group">
              <label><span>Fréquence (pubs/semaine) *</span>
                <input name="frequency" type="number" min="1" max="14" value="${s.frequency || 3}" required>
              </label>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group" style="grid-column: 1 / -1;">
              <label><span>Audience cible *</span>
                <textarea name="target_audience" rows="3" maxlength="1000" placeholder="Ex: Athlètes endurance 25-45 ans" required>${this._escape(s.target_audience || '')}</textarea>
              </label>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label><span>Objectifs *</span>
                <select name="objectives" multiple size="4" required>
                  ${objectiveOptions}
                </select>
              </label>
            </div>
            <div class="form-group">
              <label><span>Thèmes *</span>
                <select name="themes" multiple size="4" required>
                  ${themeOptions}
                </select>
              </label>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label><span>Réseaux *</span>
                <select name="networks" multiple size="4" required>
                  ${networkOptions}
                </select>
              </label>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group" style="grid-column: 1 / -1;">
              <label><span>Règles éditoriales</span>
                <textarea name="rules" rows="3" maxlength="2000" placeholder="Ex: Pas de résultats inventés, Utiliser les vraies données Garmin">${this._escape((s.rules || []).join('\n'))}</textarea>
                <small class="form-help">Une règle par ligne.</small>
              </label>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group" style="grid-column: 1 / -1;">
              <label><span>Sujets interdits</span>
                <textarea name="forbidden_topics" rows="2" maxlength="1000" placeholder="Ex: politique, concurrentiels">${this._escape((s.forbidden_topics || []).join(', '))}</small>
                <small class="form-help">Séparés par des virgules.</small>
              </label>
            </div>
          </div>
          <div class="form-actions">
            <button class="btn btn-primary" type="submit">Enregistrer la stratégie</button>
            <span data-role="cm-strategy-status" role="status"></span>
          </div>
        </form>
      </div>
    `;
  }

  _renderCMGenerationZone() {
    return `
      <div class="card">
        <div class="card-header">
          <div>
            <span class="eyebrow">Génération du calendrier éditorial</span>
            <p class="text-muted">Stratégie configurée : <strong>${this._escape(this.cmStrategy?.brand_identity || '')}</strong> — ${(this.cmStrategy?.tone || []).join(', ')}</p>
          </div>
          <span class="status-badge active">Prête</span>
        </div>
        <div class="card-body">
          <form data-form="cm-generate-calendar">
            <div class="form-row">
              <div class="form-group">
                <label><span>Nombre de propositions *</span>
                  <input name="count" type="number" min="1" max="20" value="5" required>
                </label>
              </div>
            </div>
            <div class="form-actions">
              <button class="btn btn-primary" type="submit" ${this.cmGenerating ? 'disabled' : ''}>
                ${this.cmGenerating ? 'Génération en cours…' : 'Générer le calendrier'}
              </button>
              <button class="btn btn-secondary" type="button" data-action="cm-edit-strategy">
                Modifier la stratégie
              </button>
              <span data-role="cm-generate-status" role="status" class="${this.cmSuccess ? 'text-success' : ''} ${this.cmError ? 'text-error' : ''}"></span>
            </div>
          </form>
          ${this.cmError ? `<div class="alert alert-error" style="margin-top: 12px;">${this._escape(this.cmError)}</div>` : ''}
          ${this.cmSuccess ? `<div class="alert alert-success" style="margin-top: 12px;">${this._escape(this.cmSuccess)}</div>` : ''}
        </div>
      </div>
    `;
  }

  _renderCMCalendarTable() {
    const rows = this.cmCalendar.map(entry => `
      <tr data-entry-id="${entry.id}">
        <td>${this._formatDate(entry.date)}</td>
        <td><span class="badge badge-${this._getThemeBadgeClass(entry.theme)}">${this._escape(entry.theme || '')}</span></td>
        <td>${this._escape(entry.topic)}</td>
        <td>${this._escape(entry.objective || '')}</td>
        <td class="text-muted" style="max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${this._escape(entry.notes || '')}</td>
        <td>
          <div class="form-actions" style="gap: 8px;">
            ${entry.status === 'brouillon' ? `
              <button class="btn btn-sm btn-primary" data-cm-validate data-entry-id="${entry.id}">
                Valider
              </button>
              <button class="btn btn-sm btn-secondary" data-cm-reject data-entry-id="${entry.id}">
                Refuser
              </button>
            ` : ''}
            ${entry.status === 'planifié' ? `
              <button class="btn btn-sm btn-primary" data-cm-create-publication data-entry-id="${entry.id}" data-entry-topic="${this._escape(entry.topic)}">
                Créer la publication
              </button>
              <button class="btn btn-sm btn-secondary" data-cm-reject data-entry-id="${entry.id}">
                Refuser
              </button>
            ` : ''}
            ${entry.status === 'refusé' ? `
              <span class="text-muted">Refusée</span>
            ` : ''}
          </div>
        </td>
      </tr>
    `).join('');

    return `
      <div class="card">
        <div class="card-header">
          <div>
            <span class="eyebrow">Calendrier éditorial — ${this.cmCalendar.length} proposition(s)</span>
            <p class="text-muted">Validez ou refusez chaque proposition. Les entrées validées passent en statut « planifié ».</p>
          </div>
        </div>
        <div class="card-body" style="overflow-x: auto;">
          <table class="table" style="min-width: 800px;">
            <thead>
              <tr>
                <th>Date</th>
                <th>Thème</th>
                <th>Sujet</th>
                <th>Objectif</th>
                <th>Note IA</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${rows}
            </tbody>
          </table>
        </div>
        <div class="form-actions" style="margin-top: 12px;">
          <button class="btn btn-secondary" data-cm-regenerate>Régénérer le calendrier</button>
          <span data-role="cm-calendar-status" role="status"></span>
        </div>
      </div>
    `;
  }

  _formatDate(dateStr) {
    if (!dateStr) return '';
    // Traiter la date comme UTC pour éviter les décalages de fuseau horaire
    const d = new Date(dateStr + 'T00:00:00Z');
    return d.toLocaleDateString('fr-FR', { weekday: 'short', day: '2-digit', month: 'short', timeZone: 'UTC' });
  }

  _getThemeBadgeClass(theme) {
    const map = {
      running: 'primary',
      recovery: 'success',
      nutrition: 'info',
      training: 'warning',
      gear: 'secondary',
      mental: 'purple',
      races: 'danger',
      lifestyle: 'dark',
    };
    return map[theme] || 'secondary';
  }

  async _saveCMStrategy(form) {
    const message = this.element.querySelector('[data-role="cm-strategy-status"]');
    const submitBtn = form.querySelector('[type="submit"]');
    if (submitBtn?.disabled) return;
    if (submitBtn) submitBtn.disabled = true;

    const getSelectedValues = (name) => {
      const select = form.elements[name];
      if (!select) return [];
      return Array.from(select.selectedOptions).map(o => o.value);
    };

    const getTextareaLines = (name) => {
      const textarea = form.elements[name];
      if (!textarea) return [];
      return textarea.value.split('\n').map(l => l.trim()).filter(l => l);
    };

    const getTextareaComma = (name) => {
      const textarea = form.elements[name];
      if (!textarea) return [];
      return textarea.value.split(',').map(l => l.trim()).filter(l => l);
    };

    const setStatus = (text, success) => {
      if (message) {
        message.textContent = text;
        message.classList.toggle('text-success', !!success);
        message.classList.toggle('text-error', !success);
      }
    };

    try {
      const data = {
        brand_identity: form.elements.brand_identity.value.trim(),
        tone: getSelectedValues('tone'),
        target_audience: form.elements.target_audience.value.trim(),
        objectives: getSelectedValues('objectives'),
        themes: getSelectedValues('themes'),
        frequency: parseInt(form.elements.frequency.value, 10),
        networks: getSelectedValues('networks'),
        rules: getTextareaLines('rules'),
        forbidden_topics: getTextareaComma('forbidden_topics'),
      };

      this.cmStrategy = await updateCommunityManagerStrategy(data);
      setStatus('Stratégie enregistrée avec succès.', true);
      // Re-render l'onglet pour afficher la zone de génération
      this._refreshCMTab();
    } catch (error) {
      setStatus(error?.data?.detail || error?.message || 'Erreur lors de l\'enregistrement.', false);
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  }

  async _generateCMCalendar(form) {
    const message = this.element.querySelector('[data-role="cm-generate-status"]');
    const submitBtn = form.querySelector('[type="submit"]');
    if (submitBtn?.disabled) return;
    if (submitBtn) submitBtn.disabled = true;

    this.cmGenerating = true;
    this.cmError = null;
    this.cmSuccess = null;
    this._refreshCMTab();

    const setStatus = (text, success) => {
      if (message) {
        message.textContent = text;
        message.classList.toggle('text-success', !!success);
        message.classList.toggle('text-error', !success);
      }
    };

    try {
      const count = parseInt(form.elements.count.value, 10);
      const result = await generateCommunityManagerCalendar(count);
      this.cmCalendar = result?.calendar || [];
      this.cmSuccess = `${this.cmCalendar.length} proposition(s) générée(s).`;
      this._refreshCMTab();
    } catch (error) {
      this.cmError = error?.data?.detail || error?.message || 'Génération impossible.';
      this._refreshCMTab();
    } finally {
      this.cmGenerating = false;
      if (submitBtn) submitBtn.disabled = false;
    }
  }

  async _validateCMEntry(entryId) {
    const message = this.element.querySelector('[data-role="cm-calendar-status"]');
    const setStatus = (text, success) => {
      if (message) {
        message.textContent = text;
        message.classList.toggle('text-success', !!success);
        message.classList.toggle('text-error', !success);
      }
    };

    try {
      await updateCommunityManagerCalendarEntry(entryId, { status: 'planifié' });
      const entry = this.cmCalendar.find(e => e.id === entryId);
      if (entry) entry.status = 'planifié';
      setStatus('Proposition validée et planifiée.', true);
      this._refreshCMTab();
    } catch (error) {
      setStatus(error?.data?.detail || error?.message || 'Validation impossible.', false);
    }
  }

  async _rejectCMEntry(entryId) {
    const message = this.element.querySelector('[data-role="cm-calendar-status"]');
    const setStatus = (text, success) => {
      if (message) {
        message.textContent = text;
        message.classList.toggle('text-success', !!success);
        message.classList.toggle('text-error', !success);
      }
    };

    try {
      await deleteCommunityManagerCalendarEntry(entryId);
      this.cmCalendar = this.cmCalendar.filter(e => e.id !== entryId);
      setStatus('Proposition refusée et supprimée.', true);
      this._refreshCMTab();
    } catch (error) {
      setStatus(error?.data?.detail || error?.message || 'Refus impossible.', false);
    }
  }

  async _regenerateCMCalendar() {
    // Réutilise la logique de génération avec le count du formulaire ou 5 par défaut
    const form = this.element.querySelector('[data-form="cm-generate-calendar"]');
    let count = 5;
    if (form && form.elements.count) {
      count = parseInt(form.elements.count.value, 10) || 5;
    }
    // Créer un formulaire temporaire pour la régénération
    const tempForm = {
      elements: {
        count: { value: count },
      },
      querySelector: () => null,
    };
    await this._generateCMCalendar(tempForm);
  }

  async _createPublicationFromEntry(entryId, entryTopic) {
    const btn = this.element.querySelector(`[data-cm-create-publication][data-entry-id="${entryId}"]`);
    if (btn?.disabled) return;
    if (btn) btn.disabled = true;

    const setStatus = (text, success) => {
      const statusEl = this.element.querySelector('[data-role="cm-calendar-status"]');
      if (statusEl) {
        statusEl.textContent = text;
        statusEl.classList.toggle('text-success', !!success);
        statusEl.classList.toggle('text-error', !success);
      }
    };

    try {
      setStatus('Création du brouillon...', null);
      if (btn) btn.textContent = 'Création...';

      // Appeler l'API pour créer le brouillon
      const result = await createStudioDraftFromCalendar({
        calendar_entry_id: parseInt(entryId, 10),
        styles: ['stats'],
        visual_type: 'photo',
      });

      if (result?.publication_id) {
        setStatus(`Publication créée pour "${entryTopic}".`, true);
        // Naviguer vers le studio
        this.router.navigate(`/settings/cm/studio/${result.publication_id}`);
      } else {
        setStatus('Création échouée.', false);
      }
    } catch (error) {
      setStatus(error?.data?.detail || error?.message || 'Création impossible.', false);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Créer la publication';
      }
    }
  }

  _refreshCMTab() {
    const panel = this.element.querySelector('[data-tab-panel="cm"]');
    if (panel) {
      panel.innerHTML = this._renderCMTab();
      this._bindCMEvents();
    }
  }

  _bindCMEvents() {
    // Formulaire stratégie
    const strategyForm = this.element.querySelector('[data-form="community-manager-strategy"]');
    strategyForm?.addEventListener('submit', (e) => {
      e.preventDefault();
      this._saveCMStrategy(strategyForm);
    });

    // Formulaire génération
    const generateForm = this.element.querySelector('[data-form="cm-generate-calendar"]');
    generateForm?.addEventListener('submit', (e) => {
      e.preventDefault();
      this._generateCMCalendar(generateForm);
    });

    // Boutons valider/refuser
    this.element.querySelectorAll('[data-cm-validate]').forEach(btn => {
      btn.addEventListener('click', () => this._validateCMEntry(parseInt(btn.dataset.entryId, 10)));
    });
    this.element.querySelectorAll('[data-cm-reject]').forEach(btn => {
      btn.addEventListener('click', () => this._rejectCMEntry(parseInt(btn.dataset.entryId, 10)));
    });

    // Bouton créer publication
    this.element.querySelectorAll('[data-cm-create-publication]').forEach(btn => {
      btn.addEventListener('click', () => this._createPublicationFromEntry(btn.dataset.entryId, btn.dataset.entryTopic));
    });

    // Régénérer
    this.element.querySelector('[data-cm-regenerate]')?.addEventListener('click', () => this._regenerateCMCalendar());

    // Modifier la stratégie
    this.element.querySelector('[data-action="cm-edit-strategy"]')?.addEventListener('click', () => {
      this.cmStrategy = null;
      this.cmCalendar = [];
      this._refreshCMTab();
    });
  }

  _switchTab(tabId) {
    if (tabId === 'meta' && !this.showMetaTab) return;
    if (tabId === 'garmin' && !this.canSeeGarmin) return;
    if (tabId === 'cm' && !this.showCMTab) return;
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
    // Re-bind CM events when switching to CM tab
    if (tabId === 'cm' && this.showCMTab) {
      this._bindCMEvents();
    }
  }
}

export function createSettingsPage(router) {
  return new UserSettingsPage(router);
}
