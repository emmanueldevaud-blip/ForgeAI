/**
 * Community Manager Page - Module dédié
 * Stratégie éditoriale (modale), génération de calendrier et studio de création
 */

import { api } from '../services/api.js';
import { authStore } from '../stores/auth.js';
import {
  getCommunityManagerStrategy,
  updateCommunityManagerStrategy,
  generateCommunityManagerCalendar,
  getCommunityManagerCalendar,
  updateCommunityManagerCalendarEntry,
  deleteCommunityManagerCalendarEntry,
  createStudioDraftFromCalendar,
} from '../services/sportApi.js?v=12';
import { createCommunityManagerStudioPage } from './CommunityManagerStudioPage.js?v=5';

export class CommunityManagerPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.cmStrategy = null;
    this.cmCalendar = [];
    this.cmGenerating = false;
    this.cmError = null;
    this.cmSuccess = null;
    this.studioPage = null;
    this.showStudio = false;
    this.showStrategyModal = false;
  }

  async initialize() {
    try {
      await authStore.loadCurrentUser();
    } catch (error) {
      console.error('Erreur chargement utilisateur:', error);
    }

    this.canViewCMStrategy = !!authStore?.authenticated && authStore.hasPermission('community_manager.strategy_view');
    this.canUpdateCMStrategy = !!authStore?.authenticated && authStore.hasPermission('community_manager.strategy_update');
    this.canGenerateCMCalendar = !!authStore?.authenticated && authStore.hasPermission('community_manager.calendar_generate');
    this.canViewCMCalendar = !!authStore?.authenticated && authStore.hasPermission('community_manager.calendar_view');

    if (this.canViewCMStrategy) {
      await this._loadCMStrategy();
    }
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content';

    if (this.showStudio && this.studioPage) {
      this.element.appendChild(this.studioPage.render());
      return this.element;
    }

    const configured = !!this.cmStrategy;
    const hasCalendar = this.cmCalendar.length > 0;

    this.element.innerHTML = `
      <div class="page-header">
        <div>
          <h1>Community Manager IA</h1>
          <p class="page-subtitle">Stratégie éditoriale et génération de calendrier par IA</p>
        </div>
        <div class="page-header-actions">
          ${this.canUpdateCMStrategy ? `
            <button class="btn btn-secondary" data-action="open-strategy-modal">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
              </svg>
              Stratégie
            </button>
          ` : ''}
        </div>
      </div>

      ${this._renderStrategyModal()}

      <div class="cm-main-content">
        ${!configured ? this._renderEmptyState() : (
          !hasCalendar ? this._renderGenerationZone() : this._renderCalendarTable()
        )}
      </div>
    `;

    this._bindEvents();
    return this.element;
  }

  _renderStrategyModal() {
    return `
      <div class="cm-modal-overlay ${this.showStrategyModal ? '' : 'hidden'}" id="cm-strategy-modal" role="dialog" aria-modal="true" aria-labelledby="strategy-modal-title">
        <div class="cm-modal cm-modal-lg">
          <header class="cm-modal-header">
            <h2 id="strategy-modal-title">Stratégie éditoriale</h2>
            <button class="cm-modal-close" data-action="close-strategy-modal" aria-label="Fermer">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </header>
          ${this._renderStrategyModalContent()}
        </div>
      </div>
    `;
  }

  _renderStrategyModalContent() {
    const s = this.cmStrategy || {};
    const tones = ['professional', 'inspirational', 'casual', 'expert', 'motivational', 'educational'];
    const objectives = ['engagement', 'visibility', 'brand_awareness', 'community_building', 'lead_generation'];
    const themes = ['running', 'recovery', 'nutrition', 'training', 'gear', 'mental', 'races', 'lifestyle'];
    const networks = ['instagram', 'facebook', 'linkedin', 'twitter', 'threads'];

    const currentTones = s.tone || [];
    const currentObjectives = s.objectives || [];
    const currentThemes = s.themes || [];
    const currentNetworks = s.networks || [];

    const toneOptions = tones.map(t => `<option value="${t}" ${currentTones.includes(t) ? 'selected' : ''}>${t}</option>`).join('');
    const objectiveOptions = objectives.map(o => `<option value="${o}" ${currentObjectives.includes(o) ? 'selected' : ''}>${o}</option>`).join('');
    const themeOptions = themes.map(t => `<option value="${t}" ${currentThemes.includes(t) ? 'selected' : ''}>${t}</option>`).join('');
    const networkOptions = networks.map(n => `<option value="${n}" ${currentNetworks.includes(n) ? 'selected' : ''}>${n}</option>`).join('');

    return `
      <form data-form="community-manager-strategy" class="cm-modal-body">
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
              <textarea name="forbidden_topics" rows="2" maxlength="1000" placeholder="Ex: politique, concurrentiels">${this._escape((s.forbidden_topics || []).join(', '))}</textarea>
              <small class="form-help">Séparés par des virgules.</small>
            </label>
          </div>
        </div>
        <div class="form-actions">
          <button type="button" class="btn btn-secondary" data-action="close-strategy-modal">Annuler</button>
          <button class="btn btn-primary" type="submit" ${!this.canUpdateCMStrategy ? 'disabled' : ''}>Enregistrer la stratégie</button>
          <span data-role="cm-strategy-status" role="status"></span>
        </div>
      </form>
    `;
  }

  _renderEmptyState() {
    return `
      <div class="card">
        <div class="card-body" style="text-align: center; padding: 48px;">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin: 0 auto 16px; opacity: 0.5;">
            <rect x="3" y="4" width="18" height="18" rx="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line>
          </svg>
          <h3>Aucune stratégie configurée</h3>
          <p class="text-muted">Cliquez sur <strong>Stratégie</strong> dans l'en-tête pour configurer votre identité éditoriale.</p>
        </div>
      </div>
    `;
  }

  _renderGenerationZone() {
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
              <button class="btn btn-primary" type="submit" ${this.cmGenerating ? 'disabled' : ''} ${!this.canGenerateCMCalendar ? 'disabled' : ''}>
                ${this.cmGenerating ? 'Génération en cours…' : 'Générer le calendrier'}
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

  _renderCalendarTable() {
    const rows = this.cmCalendar.map(entry => `
      <tr data-entry-id="${entry.id}">
        <td>${this._formatDate(entry.date)}</td>
        <td><span class="badge badge-${this._getThemeBadgeClass(entry.theme)}">${this._escape(entry.theme || '')}</span></td>
        <td>${this._escape(entry.topic)}</td>
        <td>${this._escape(entry.objective || '')}</td>
        <td class="text-muted" style="max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${this._escape(entry.notes || '')}</td>
        <td>
          <div class="form-actions" style="gap: 8px;">
            ${entry.publication_id ? `
              <div style="display: inline-flex; align-items: center; gap: 8px;">
                <span class="status-badge ${this._getPubBadgeClass(entry.publication_status)}">${this._formatPubStatus(entry.publication_status)}</span>
                <button class="btn btn-sm btn-primary" data-cm-open-studio data-publication-id="${entry.publication_id}">
                  Ouvrir le Studio
                </button>
              </div>
            ` : (entry.status === 'brouillon' ? `
              <button class="btn btn-sm btn-primary" data-cm-validate data-entry-id="${entry.id}" ${!this.canGenerateCMCalendar ? 'disabled' : ''}>
                Valider
              </button>
              <button class="btn btn-sm btn-secondary" data-cm-reject data-entry-id="${entry.id}" ${!this.canGenerateCMCalendar ? 'disabled' : ''}>
                Refuser
              </button>
            ` : (entry.status === 'planifié' ? `
              <button class="btn btn-sm btn-primary" data-cm-create-publication data-entry-id="${entry.id}" data-entry-topic="${this._escape(entry.topic)}" ${!this.canGenerateCMCalendar ? 'disabled' : ''}>
                Créer la publication
              </button>
              <button class="btn btn-sm btn-secondary" data-cm-reject data-entry-id="${entry.id}" ${!this.canGenerateCMCalendar ? 'disabled' : ''}>
                Refuser
              </button>
            ` : `
              <span class="text-muted">Refusée</span>
            `))}
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
          <button class="btn btn-secondary" data-cm-regenerate ${!this.canGenerateCMCalendar ? 'disabled' : ''}>Régénérer le calendrier</button>
          <span data-role="cm-calendar-status" role="status"></span>
        </div>
      </div>
    `;
  }

  _formatDate(dateStr) {
    if (!dateStr) return '';
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

  _escape(text) {
    if (text == null) return '';
    return String(text)
      .replaceAll('&', '&')
      .replaceAll('<', '<')
      .replaceAll('>', '>')
      .replaceAll('"', '"')
      .replaceAll("'", '&#039;');
  }

  async _loadCMStrategy() {
    try {
      const result = await getCommunityManagerStrategy();
      if (result?.configured && result?.strategy) {
        this.cmStrategy = result.strategy;
      } else if (result && (result.brand_identity || result.id)) {
        this.cmStrategy = result;
      } else {
        this.cmStrategy = null;
      }
      if (this.cmStrategy) {
        await this._loadCMCalendar();
      }
    } catch (error) {
      if (error?.status !== 404) {
        console.error('Erreur chargement stratégie CM:', error);
      }
      this.cmStrategy = null;
    }
  }

  async _loadCMCalendar() {
    try {
      const result = await getCommunityManagerCalendar();
      this.cmCalendar = Array.isArray(result) ? result : (result?.calendar || []);
    } catch (error) {
      console.error('Erreur chargement calendrier CM:', error);
      this.cmCalendar = [];
    }
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
      this._closeStrategyModal();
      this._refreshContent();
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
    this._refreshContent();

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
      this._refreshContent();
    } catch (error) {
      this.cmError = error?.data?.detail || error?.message || 'Génération impossible.';
      this._refreshContent();
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
      this._refreshContent();
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
      this._refreshContent();
    } catch (error) {
      setStatus(error?.data?.detail || error?.message || 'Refus impossible.', false);
    }
  }

  async _regenerateCMCalendar() {
    const form = this.element.querySelector('[data-form="cm-generate-calendar"]');
    let count = 5;
    if (form && form.elements.count) {
      count = parseInt(form.elements.count.value, 10) || 5;
    }
    const tempForm = {
      elements: { count: { value: count } },
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

      const result = await createStudioDraftFromCalendar({
        calendar_entry_id: parseInt(entryId, 10),
        styles: ['stats'],
        visual_type: 'photo',
      });

      if (result?.publication_id) {
        setStatus(`Publication créée pour "${entryTopic}".`, true);
        this._openStudio(result.publication_id);
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

  _openStudio(publicationId) {
    this.showStudio = true;
    this.studioPage = createCommunityManagerStudioPage(this.router, publicationId, null, () => this._closeStudio());
    this.studioPage.initialize().then(() => {
      if (this.element) {
        this.element.innerHTML = '';
        this.element.appendChild(this.studioPage.render());
      }
    });
  }

  _closeStudio() {
    this.showStudio = false;
    this.studioPage = null;
    this._loadCMCalendar().then(() => {
      if (this.element) {
        this.element.innerHTML = '';
        this.element.appendChild(this.render());
      }
    });
  }

  _openStrategyModal() {
    this.showStrategyModal = true;
    const modal = this.element.querySelector('#cm-strategy-modal');
    if (modal) {
      // Re-render modal content with current strategy values
      modal.innerHTML = this._renderStrategyModalContent();
      modal.classList.remove('hidden');
      // Focus first input
      setTimeout(() => {
        modal.querySelector('input[name="brand_identity"]')?.focus();
      }, 10);
      // Re-bind form submit event for the newly rendered form
      const form = modal.querySelector('[data-form="community-manager-strategy"]');
      form?.addEventListener('submit', (e) => {
        e.preventDefault();
        this._saveCMStrategy(form);
      });
      // Re-bind close buttons
      modal.querySelectorAll('[data-action="close-strategy-modal"]').forEach(btn => {
        btn.addEventListener('click', () => this._closeStrategyModal());
      });
      // Close on overlay click
      modal.addEventListener('click', (e) => {
        if (e.target === modal) this._closeStrategyModal();
      });
    }
  }

  _closeStrategyModal() {
    this.showStrategyModal = false;
    const modal = this.element.querySelector('#cm-strategy-modal');
    if (modal) {
      modal.classList.add('hidden');
    }
  }

  _refreshContent() {
    if (this.showStudio && this.studioPage) {
      this.element.innerHTML = '';
      this.element.appendChild(this.studioPage.render());
      return;
    }

    const content = this.element.querySelector('.cm-main-content');
    if (content) {
      const configured = !!this.cmStrategy;
      const hasCalendar = this.cmCalendar.length > 0;
      if (!configured) {
        content.innerHTML = this._renderEmptyState();
      } else if (!hasCalendar) {
        content.innerHTML = this._renderGenerationZone();
      } else {
        content.innerHTML = this._renderCalendarTable();
      }
      this._bindEvents();
    }
  }

  _bindEvents() {
    // Strategy modal
    this.element.querySelector('[data-action="open-strategy-modal"]')?.addEventListener('click', () => this._openStrategyModal());
    this.element.querySelector('[data-action="close-strategy-modal"]')?.addEventListener('click', () => this._closeStrategyModal());

    // Close modal on overlay click
    this.element.querySelector('#cm-strategy-modal')?.addEventListener('click', (e) => {
      if (e.target === e.currentTarget) this._closeStrategyModal();
    });

    // Strategy form
    const strategyForm = this.element.querySelector('[data-form="community-manager-strategy"]');
    strategyForm?.addEventListener('submit', (e) => {
      e.preventDefault();
      this._saveCMStrategy(strategyForm);
    });

    // Generation form
    const generateForm = this.element.querySelector('[data-form="cm-generate-calendar"]');
    generateForm?.addEventListener('submit', (e) => {
      e.preventDefault();
      this._generateCMCalendar(generateForm);
    });

    // Calendar actions
    this.element.querySelectorAll('[data-cm-validate]').forEach(btn => {
      btn.addEventListener('click', () => this._validateCMEntry(parseInt(btn.dataset.entryId, 10)));
    });
    this.element.querySelectorAll('[data-cm-reject]').forEach(btn => {
      btn.addEventListener('click', () => this._rejectCMEntry(parseInt(btn.dataset.entryId, 10)));
    });
    this.element.querySelectorAll('[data-cm-create-publication]').forEach(btn => {
      btn.addEventListener('click', () => this._createPublicationFromEntry(btn.dataset.entryId, btn.dataset.entryTopic));
    });
    this.element.querySelectorAll('[data-cm-open-studio]').forEach(btn => {
      btn.addEventListener('click', () => {
        const pubId = parseInt(btn.dataset.publicationId, 10);
        if (pubId) this._openStudio(pubId);
      });
    });
    this.element.querySelector('[data-cm-regenerate]')?.addEventListener('click', () => this._regenerateCMCalendar());
  }

  _formatPubStatus(status) {
    const map = {
      draft: 'Brouillon',
      validated: 'Validée',
      scheduled: 'Planifiée',
      shared: 'Publiée',
      failed: 'Échec',
      publishing: 'Publication...',
    };
    return map[status] || status || 'Brouillon';
  }

  _getPubBadgeClass(status) {
    const map = {
      draft: 'inactive',
      validated: 'active',
      scheduled: 'warning',
      shared: 'success',
      failed: 'danger',
      publishing: 'warning',
    };
    return map[status] || 'inactive';
  }
}

export function createCommunityManagerPage(router) {
  return new CommunityManagerPage(router);
}