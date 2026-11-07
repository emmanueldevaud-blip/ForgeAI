/**
 * Community Manager Studio Page - V2
 * Studio de création de publications Instagram depuis le calendrier éditorial
 */

import { api } from '../services/api.js?v=4';
import {
  getStudioDraft,
  updateStudioDraft,
  generateStudioDraftVariants,
  validateStudioDraft,
  scheduleStudioDraft,
  previewStudioDraft,
  publishStudioDraft,
} from '../services/sportApi.js?v=11';
import { publicationPhotoUrl } from '../services/sportApi.js?v=11';


export class CommunityManagerStudioPage {
  constructor(router, publicationId, entryData = null) {
    this.router = router;
    this.publicationId = publicationId;
    this.entryData = entryData; // Données de l'entrée de calendrier si fournie
    this.element = null;
    this.publication = null;
    this.loading = true;
    this.saving = false;
    this.generating = false;
    this.previewFormat = 'feed';
    this.activeTab = 'text';
    this.error = null;
    this.success = null;
  }

  async initialize() {
    try {
      this.publication = await getStudioDraft(this.publicationId);
      this.loading = false;
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Impossible de charger le brouillon';
      this.loading = false;
    }
  }

  render() {
    if (!this.element) {
      this.element = document.createElement('div');
      this.element.className = 'cm-studio-page';
    }

    if (this.loading) {
      this.element.innerHTML = `
        <div class="cm-studio-loading">
          <div class="spinner"></div>
          <p>Chargement du studio...</p>
        </div>
      `;
      return this.element;
    }

    if (this.error) {
      this.element.innerHTML = `
        <div class="cm-studio-error">
          <div class="alert alert-error">${this._escape(this.error)}</div>
          <button class="btn btn-primary" onclick="window.history.back()">Retour au calendrier</button>
        </div>
      `;
      return this.element;
    }

    const pub = this.publication;
    const entry = pub.calendar_entry;
    const isV2 = pub.created_from === 'calendar';

    this.element.innerHTML = `
      <div class="cm-studio">
        <!-- Header -->
        <header class="cm-studio-header">
          <div class="cm-studio-header-left">
            <button class="btn btn-secondary cm-studio-back" data-action="back">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M19 12H5M12 19l-7-7 7-7"/>
              </svg>
              <span>Calendrier</span>
            </button>
            <h1>Studio de création</h1>
            ${isV2 && entry ? `
              <span class="cm-studio-entry-badge">
                ${this._escape(entry.topic)}
              </span>
            ` : ''}
          </div>
          <div class="cm-studio-header-right">
            <div class="cm-studio-status">
              <span class="status-badge ${this._getStatusBadgeClass(pub.status)}">${this._formatStatus(pub.status)}</span>
            </div>
            <div class="cm-studio-actions">
              <button class="btn btn-secondary" data-action="preview" ${!pub.content ? 'disabled' : ''}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                </svg>
                Aperçu
              </button>
              <button class="btn btn-primary" data-action="validate" ${pub.status === 'validated' || pub.status === 'scheduled' || pub.status === 'shared' || pub.status === 'publishing' ? 'disabled' : ''} ${!pub.content ? 'disabled' : ''}>
                ${pub.status === 'validated' ? 'Validée' : pub.status === 'scheduled' ? 'Planifiée' : pub.status === 'shared' ? 'Publiée' : pub.status === 'publishing' ? 'Publication...' : 'Valider'}
              </button>
              <button class="btn btn-success" data-action="publish" ${pub.status !== 'validated' && pub.status !== 'scheduled' ? 'disabled' : ''} ${!pub.content || !pub.photo_id ? 'disabled' : ''}>
                ${pub.status === 'shared' ? 'Publiée' : pub.status === 'publishing' ? 'Publication...' : 'Publier sur Instagram'}
              </button>
            </div>
          </div>
        </header>

        <!-- Info bar (V2) -->
        ${isV2 && entry ? this._renderInfoBar(entry) : ''}

        <!-- Main content -->
        <div class="cm-studio-main">
          <!-- Sidebar: Informations du sujet -->
          <aside class="cm-studio-sidebar">
            ${isV2 ? this._renderEntryInfo(entry) : this._renderActivityInfo(pub.activity)}
            <div class="cm-studio-sidebar-section">
              <h3>Publication</h3>
              <dl class="cm-studio-meta">
                <dt>Statut</dt><dd><span class="status-badge ${this._getStatusBadgeClass(pub.status)}">${this._formatStatus(pub.status)}</span></dd>
                <dt>Créée le</dt><dd>${this._formatDateTime(pub.created_at)}</dd>
                ${pub.validated_at ? `<dt>Validée le</dt><dd>${this._formatDateTime(pub.validated_at)}</dd>` : ''}
                ${pub.scheduled_at ? `<dt>Planifiée pour</dt><dd>${this._formatDateTime(pub.scheduled_at)}</dd>` : ''}
                ${pub.tone_used ? `<dt>Ton utilisé</dt><dd>${this._escape(pub.tone_used)}</dd>` : ''}
                <dt>Source</dt><dd>${pub.created_from === 'calendar' ? 'Calendrier éditorial' : 'Activité Garmin'}</dd>
              </dl>
            </div>
          </aside>

          <!-- Main editor area -->
          <main class="cm-studio-editor">
            <!-- Tabs -->
            <nav class="cm-studio-tabs" role="tablist">
              <button class="cm-studio-tab ${this.activeTab === 'text' ? 'active' : ''}" role="tab" data-tab="text" aria-selected="${this.activeTab === 'text'}">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
                Texte
              </button>
              <button class="cm-studio-tab ${this.activeTab === 'visual' ? 'active' : ''}" role="tab" data-tab="visual" aria-selected="${this.activeTab === 'visual'}">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>
                Visuel
              </button>
              <button class="cm-studio-tab ${this.activeTab === 'variants' ? 'active' : ''}" role="tab" data-tab="variants" aria-selected="${this.activeTab === 'variants'}">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
                Variantes
              </button>
            </nav>

            <!-- Tab panels -->
            <div class="cm-studio-tab-panels">
              <!-- Text tab -->
              <div class="cm-studio-tab-panel ${this.activeTab === 'text' ? 'active' : ''}" data-tab-panel="text" role="tabpanel">
                ${this._renderTextTab()}
              </div>

              <!-- Visual tab -->
              <div class="cm-studio-tab-panel ${this.activeTab === 'visual' ? 'active' : ''}" data-tab-panel="visual" role="tabpanel">
                ${this._renderVisualTab()}
              </div>

              <!-- Variants tab -->
              <div class="cm-studio-tab-panel ${this.activeTab === 'variants' ? 'active' : ''}" data-tab-panel="variants" role="tabpanel">
                ${this._renderVariantsTab()}
              </div>
            </div>
          </main>

          <!-- Preview modal -->
          <div class="cm-modal-overlay" id="cm-preview-modal" role="dialog" aria-modal="true" aria-labelledby="preview-title" hidden>
            <div class="cm-modal cm-modal-lg">
              <header class="cm-modal-header">
                <h2 id="preview-title">Aperçu Instagram</h2>
                <button class="cm-modal-close" data-action="close-preview" aria-label="Fermer">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </header>
              <div class="cm-modal-body" id="cm-preview-body"></div>
              <footer class="cm-modal-footer">
                <select class="form-select" id="cm-preview-format" style="width: auto;">
                  <option value="feed">Feed (1:1)</option>
                  <option value="story">Story (9:16)</option>
                  <option value="reel">Reel (9:16)</option>
                  <option value="strategic">Stratégique (stats + accroche)</option>
                </select>
              </footer>
            </div>
          </div>

          <!-- Schedule modal -->
          <div class="cm-modal-overlay" id="cm-schedule-modal" role="dialog" aria-modal="true" aria-labelledby="schedule-title" hidden>
            <div class="cm-modal">
              <header class="cm-modal-header">
                <h2 id="schedule-title">Planifier la publication</h2>
                <button class="cm-modal-close" data-action="close-schedule" aria-label="Fermer">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </header>
              <div class="cm-modal-body">
                <form data-form="cm-schedule">
                  <div class="form-group">
                    <label><span>Date et heure *</span>
                      <input type="datetime-local" name="scheduled_at" required>
                    </label>
                  </div>
                  <div class="form-actions">
                    <button type="button" class="btn btn-secondary" data-action="close-schedule">Annuler</button>
                    <button type="submit" class="btn btn-primary">Planifier</button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    this._bindEvents();
    return this.element;
  }

  _renderInfoBar(entry) {
    return `
      <div class="cm-studio-info-bar">
        <div class="cm-studio-info-item">
          <span class="cm-studio-info-label">Thème</span>
          <span class="badge badge-${this._getThemeBadgeClass(entry.theme)}">${this._escape(entry.theme || '')}</span>
        </div>
        <div class="cm-studio-info-item">
          <span class="cm-studio-info-label">Objectif</span>
          <span>${this._escape(entry.objective || '')}</span>
        </div>
        <div class="cm-studio-info-item">
          <span class="cm-studio-info-label">Date suggérée</span>
          <span>${this._formatDate(entry.date)}</span>
        </div>
        <div class="cm-studio-info-item">
          <span class="cm-studio-info-label">Note IA</span>
          <span class="text-muted">${this._escape(entry.notes || '')}</span>
        </div>
      </div>
    `;
  }

  _renderEntryInfo(entry) {
    return `
      <div class="cm-studio-sidebar-section">
        <h3>Sujet éditorial</h3>
        <p class="cm-studio-entry-topic">${this._escape(entry.topic)}</p>
        <dl class="cm-studio-meta">
          <dt>Thème</dt><dd><span class="badge badge-${this._getThemeBadgeClass(entry.theme)}">${this._escape(entry.theme || '')}</span></dd>
          <dt>Objectif</dt><dd>${this._escape(entry.objective || '')}</dd>
          <dt>Date suggérée</dt><dd>${this._formatDate(entry.date)}</dd>
        </dl>
        ${entry.notes ? `<p class="cm-studio-notes">${this._escape(entry.notes)}</p>` : ''}
      </div>
    `;
  }

  _renderActivityInfo(activity) {
    if (!activity) return '';
    return `
      <div class="cm-studio-sidebar-section">
        <h3>Activité Garmin</h3>
        <p class="cm-studio-entry-topic">${this._escape(activity.activity_name || activity.sport_type)}</p>
        <dl class="cm-studio-meta">
          <dt>Type</dt><dd>${this._escape(activity.sport_type)}</dd>
          <dt>Date</dt><dd>${this._formatDate(activity.started_at)}</dd>
          ${activity.distance_m ? `<dt>Distance</dt><dd>${(activity.distance_m / 1000).toFixed(1)} km</dd>` : ''}
          ${activity.elevation_gain_m ? `<dt>D+</dt><dd>${Math.round(activity.elevation_gain_m)} m</dd>` : ''}
          ${activity.duration_seconds ? `<dt>Durée</dt><dd>${this._formatDuration(activity.duration_seconds)}</dd>` : ''}
          ${activity.avg_heart_rate ? `<dt>FC moy.</dt><dd>${Math.round(activity.avg_heart_rate)} bpm</dd>` : ''}
        </dl>
      </div>
    `;
  }

  _renderTextTab() {
    const pub = this.publication;
    const tones = [
      { value: 'humor', label: 'Humour & autodérision', desc: 'Second degré, situations absurdes, galères du traileur' },
      { value: 'self_deprecation', label: 'Autodérision', desc: 'Se moquer de soi-même avec légèreté' },
      { value: 'stats', label: 'Statistiques & performance', desc: 'Chiffres marquants, analyses, comparaisons' },
      { value: 'storytelling', label: 'Storytelling', desc: 'Récit d\'aventure avec début, milieu, fin' },
      { value: 'inspiration', label: 'Inspiration & motivation', desc: 'Dépassement de soi, progression, objectifs' },
      { value: 'expert', label: 'Expert & technique', desc: 'Analyse technique, conseils, données précises' },
      { value: 'professional', label: 'Professionnel', desc: 'Ton posé, informatif, crédible' },
    ];

    const toneOptions = tones.map(t => `
      <option value="${t.value}">${t.label}</option>
    `).join('');

    return `
      <form data-form="cm-draft-text" class="cm-studio-form">
        <div class="cm-studio-form-row">
          <div class="cm-studio-form-group">
            <label><span>Titre</span>
              <input type="text" name="title" maxlength="200" placeholder="Titre de la publication" value="${this._escape(pub.title || '')}">
            </label>
          </div>
        </div>

        <div class="cm-studio-form-row">
          <div class="cm-studio-form-group">
            <label><span>Ton rédactionnel</span>
              <select name="tone_used">
                <option value="">-- Par défaut (stratégie) --</option>
                ${toneOptions}
              </select>
              <small class="form-help">Remplace le ton de la stratégie pour cette publication.</small>
            </label>
          </div>
        </div>

        <div class="cm-studio-form-row">
          <div class="cm-studio-form-group" style="grid-column: 1 / -1;">
            <label><span>Contenu *</span>
              <textarea name="content" rows="12" placeholder="Écrivez votre publication ici...">${this._escape(pub.content || '')}</textarea>
              <small class="form-help">Éditez librement. Les modifications sont conservées.</small>
            </label>
          </div>
        </div>

        <div class="cm-studio-form-row">
          <div class="cm-studio-form-group" style="grid-column: 1 / -1;">
            <label><span>Hashtags</span>
              <textarea name="hashtags" rows="3" placeholder="#trail #running #recovery">${this._escape(pub.hashtags || '')}</textarea>
              <small class="form-help">Séparés par des espaces.</small>
            </label>
          </div>
        </div>

        <div class="cm-studio-form-actions">
          <button type="submit" class="btn btn-primary" ${this.saving ? 'disabled' : ''}>
            ${this.saving ? 'Sauvegarde...' : 'Sauvegarder le brouillon'}
          </button>
          <span data-role="draft-status" class="${this.success ? 'text-success' : ''} ${this.error ? 'text-error' : ''}"></span>
        </div>
      </form>

      ${this.error ? `<div class="alert alert-error" style="margin-top: 12px;">${this._escape(this.error)}</div>` : ''}
      ${this.success ? `<div class="alert alert-success" style="margin-top: 12px;">${this._escape(this.success)}</div>` : ''}
    `;
  }

  _renderVisualTab() {
    const pub = this.publication;
    const photoUrl = pub.photo_id ? publicationPhotoUrl(pub.photo_id, 'large') : null;

    return `
      <div class="cm-studio-visual">
        <div class="cm-studio-visual-preview">
          ${photoUrl ? `
            <img src="${photoUrl}" alt="Visuel de la publication" class="cm-studio-visual-img">
          ` : `
            <div class="cm-studio-visual-empty">
              <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                <circle cx="8.5" cy="8.5" r="1.5"/>
                <path d="M21 15l-5-5L5 21"/>
              </svg>
              <p>Aucun visuel sélectionné</p>
            </div>
          `}
        </div>

        <div class="cm-studio-visual-tabs">
          <button class="cm-studio-visual-tab ${pub.visual_type !== 'generated' ? 'active' : ''}" data-visual-tab="photo">Mes photos</button>
          <button class="cm-studio-visual-tab ${pub.visual_type === 'generated' ? 'active' : ''}" data-visual-tab="generated" disabled>Génération IA</button>
        </div>

        <div class="cm-studio-visual-panels">
          <!-- Mes photos -->
          <div class="cm-studio-visual-panel active" data-visual-panel="photo">
            <div class="cm-studio-visual-actions">
              <button class="btn btn-primary" data-action="select-photo">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 19V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2z"/>
                  <path d="M17 5l-5 5 5 5"/>
                </svg>
                Sélectionner une photo
              </button>
              ${pub.photo_id ? `<button class="btn btn-secondary" data-action="remove-photo">Retirer</button>` : ''}
            </div>
            <p class="text-muted" style="font-size: 12px; margin-top: 8px;">
              Sélectionnez une photo depuis votre bibliothèque ForgeAI Photos.
              Formats recommandés : 1:1 (feed), 4:5 (portrait), 9:16 (story/reel).
            </p>
          </div>

          <!-- Génération IA (placeholder) -->
          <div class="cm-studio-visual-panel" data-visual-panel="generated">
            <div class="cm-studio-ai-placeholder">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M12 2a10 10 0 1 0 10 10 4 4 0 0 1-5-5 4 4 0 0 0-5-5"/>
                <path d="M2 2l20 20"/>
              </svg>
              <h3>Génération d'images IA</h3>
              <p>Cette fonctionnalité sera disponible dans une prochaine version.</p>
              <p class="text-muted">Pour l'instant, utilisez vos propres photos depuis la bibliothèque.</p>
              <div class="cm-studio-ai-prompt-preview" style="display: none;">
                <label><span>Prompt de génération</span>
                  <textarea readonly rows="4"></textarea>
                </label>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  _renderVariantsTab() {
    const pub = this.publication;
    const hasProposals = pub.proposals && pub.proposals.length > 0;

    if (!hasProposals) {
      return `
        <div class="cm-studio-empty">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="3" width="7" height="7" rx="1"/>
            <rect x="14" y="3" width="7" height="7" rx="1"/>
            <rect x="3" y="14" width="7" height="7" rx="1"/>
            <rect x="14" y="14" width="7" height="7" rx="1"/>
          </svg>
          <h3>Aucune variante générée</h3>
          <p>Générez d'abord des propositions de texte dans l'onglet <strong>Texte</strong> ou cliquez ci-dessous.</p>
          <div class="cm-studio-form-actions" style="margin-top: 16px;">
            <button class="btn btn-primary" data-action="generate-variants">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2a10 10 0 1 0 10 10 4 4 0 0 1-5-5 4 4 0 0 0-5-5"/>
                <path d="M2 2l20 20"/>
              </svg>
              Générer 3 variantes
            </button>
          </div>
        </div>
      `;
    }

    return `
      <div class="cm-studio-variants">
        <div class="cm-studio-variants-header">
          <h3>${pub.proposals.length} proposition(s) générée(s)</h3>
          <button class="btn btn-primary" data-action="regenerate-variants">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
            Régénérer
          </button>
        </div>
        <div class="cm-studio-variants-list">
          ${pub.proposals.map((prop, idx) => `
            <article class="cm-studio-variant ${idx === pub.selected_proposal ? 'selected' : ''}" data-variant-index="${idx}">
              <div class="cm-studio-variant-header">
                <span class="cm-studio-variant-index">Variante ${idx + 1}</span>
                ${idx === pub.selected_proposal ? '<span class="badge badge-success">Sélectionnée</span>' : `
                  <button class="btn btn-sm btn-secondary" data-action="select-variant" data-index="${idx}">Sélectionner</button>
                `}
              </div>
              ${prop.title ? `<h4 class="cm-studio-variant-title">${this._escape(prop.title)}</h4>` : ''}
              <div class="cm-studio-variant-content">${this._escape(prop.content)}</div>
              ${prop.hashtags ? `<div class="cm-studio-variant-hashtags">${this._escape(prop.hashtags)}</div>` : ''}
              <div class="cm-studio-variant-meta">
                ${prop.format ? `<span class="badge badge-info">${this._escape(prop.format)}</span>` : ''}
                ${prop.objectif ? `<span class="badge badge-secondary">${this._escape(prop.objectif)}</span>` : ''}
              </div>
              ${prop.idee_visuelle ? `<p class="cm-studio-variant-idee"><strong>Idée visuelle :</strong> ${this._escape(prop.idee_visuelle)}</p>` : ''}
            </article>
          `).join('')}
        </div>
        <div class="cm-studio-form-actions" style="margin-top: 16px;">
          <button class="btn btn-primary" data-action="apply-selected-variant" ${!pub.content ? 'disabled' : ''}>
            Appliquer la variante sélectionnée
          </button>
        </div>
      `;
  }

  _bindEvents() {
    if (!this.element) return;

    // Back button
    this.element.querySelector('[data-action="back"]')?.addEventListener('click', () => {
      window.history.back();
    });

    // Tabs
    this.element.querySelectorAll('.cm-studio-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        this.activeTab = tab.dataset.tab;
        this._refreshTabs();
      });
    });

    // Visual tabs
    this.element.querySelectorAll('[data-visual-tab]').forEach(tab => {
      tab.addEventListener('click', () => {
        this._switchVisualTab(tab.dataset.visualTab);
      });
    });

    // Form submission - draft text
    const draftForm = this.element.querySelector('[data-form="cm-draft-text"]');
    draftForm?.addEventListener('submit', (e) => {
      e.preventDefault();
      this._saveDraft(draftForm);
    });

    // Save draft from any tab
    this.element.querySelectorAll('[data-action="save-draft"]').forEach(btn => {
      btn.addEventListener('click', () => this._saveDraftFromActiveTab());
    });

    // Generate variants
    this.element.querySelector('[data-action="generate-variants"]')?.addEventListener('click', () => {
      this._generateVariants();
    });
    this.element.querySelector('[data-action="regenerate-variants"]')?.addEventListener('click', () => {
      this._generateVariants();
    });

    // Select variant
    this.element.querySelectorAll('[data-action="select-variant"]').forEach(btn => {
      btn.addEventListener('click', () => this._selectVariant(parseInt(btn.dataset.index, 10)));
    });

    // Apply selected variant
    this.element.querySelector('[data-action="apply-selected-variant"]')?.addEventListener('click', () => {
      this._applySelectedVariant();
    });

    // Visual tabs
    this.element.querySelector('[data-action="select-photo"]')?.addEventListener('click', () => {
      this._openPhotoSelector();
    });
    this.element.querySelector('[data-action="remove-photo"]')?.addEventListener('click', () => {
      this._removePhoto();
    });

    // Preview
    this.element.querySelector('[data-action="preview"]')?.addEventListener('click', () => {
      this._showPreview();
    });
    this.element.querySelector('[data-action="close-preview"]')?.addEventListener('click', () => {
      this._closeModal('cm-preview-modal');
    });
    this.element.querySelector('#cm-preview-format')?.addEventListener('change', (e) => {
      this.previewFormat = e.target.value;
      this._showPreview();
    });

    // Validate
    this.element.querySelector('[data-action="validate"]')?.addEventListener('click', () => {
      this._validateDraft();
    });

    // Publish
    this.element.querySelector('[data-action="publish"]')?.addEventListener('click', () => {
      this._publishDraft();
    });

    // Schedule
    this.element.querySelector('[data-action="schedule"]')?.addEventListener('click', () => {
      this._showScheduleModal();
    });
    this.element.querySelector('[data-form="cm-schedule"]')?.addEventListener('submit', (e) => {
      e.preventDefault();
      this._scheduleDraft(e.target);
    });
    this.element.querySelector('[data-action="close-schedule"]')?.addEventListener('click', () => {
      this._closeModal('cm-schedule-modal');
    });

    // Modal close on overlay click
    this.element.querySelectorAll('.cm-modal-overlay').forEach(overlay => {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
          overlay.hidden = true;
        }
      });
    });
  }

  _refreshTabs() {
    this.element.querySelectorAll('.cm-studio-tab').forEach(tab => {
      const active = tab.dataset.tab === this.activeTab;
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-selected', active);
    });
    this.element.querySelectorAll('.cm-studio-tab-panel').forEach(panel => {
      const active = panel.dataset.tabPanel === this.activeTab;
      panel.classList.toggle('active', active);
      panel.hidden = !active;
    });
  }

  _switchVisualTab(tabName) {
    this.element.querySelectorAll('[data-visual-tab]').forEach(tab => {
      tab.classList.toggle('active', tab.dataset.visualTab === tabName);
    });
    this.element.querySelectorAll('[data-visual-panel]').forEach(panel => {
      const active = panel.dataset.visualPanel === tabName;
      panel.classList.toggle('active', active);
      panel.hidden = !active;
    });
  }

  async _saveDraft(form) {
    const statusEl = this.element.querySelector('[data-role="draft-status"]');
    const submitBtn = form?.querySelector('[type="submit"]');
    if (submitBtn?.disabled) return;
    if (submitBtn) submitBtn.disabled = true;

    const setStatus = (text, success) => {
      if (statusEl) {
        statusEl.textContent = text;
        statusEl.classList.toggle('text-success', !!success);
        statusEl.classList.toggle('text-error', !success);
      }
    };

    try {
      const formData = new FormData(form);
      const data = {
        title: formData.get('title') || null,
        content: formData.get('content') || null,
        hashtags: formData.get('hashtags') || null,
        tone_used: formData.get('tone_used') || null,
      };

      this.saving = true;
      if (submitBtn) submitBtn.textContent = 'Sauvegarde...';

      const updated = await updateStudioDraft(this.publicationId, data);
      this.publication = updated;
      setStatus('Brouillon sauvegardé.', true);
      this.success = 'Brouillon sauvegardé.';
    } catch (error) {
      setStatus(error?.data?.detail || error?.message || 'Erreur de sauvegarde.', false);
      this.error = error?.data?.detail || error?.message || 'Erreur de sauvegarde.';
    } finally {
      this.saving = false;
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Sauvegarder le brouillon';
      }
    }
  }

  _saveDraftFromActiveTab() {
    const form = this.element.querySelector('[data-form="cm-draft-text"]');
    if (form) this._saveDraft(form);
  }

  async _generateVariants() {
    const statusEl = this.element.querySelector('[data-role="draft-status"]') || this.element.querySelector('[data-role="cm-variants-status"]');
    const btn = this.element.querySelector('[data-action="generate-variants"], [data-action="regenerate-variants"]');
    if (btn?.disabled) return;
    if (btn) btn.disabled = true;

    const setStatus = (text, success) => {
      if (statusEl) {
        statusEl.textContent = text;
        statusEl.classList.toggle('text-success', !!success);
        statusEl.classList.toggle('text-error', !success);
      }
    };

    try {
      const form = this.element.querySelector('[data-form="cm-draft-text"]');
      const formData = form ? new FormData(form) : null;
      const data = {
        tone: formData?.get('tone_used') || this.publication.tone_used,
        styles: this.publication.styles,
        custom_instructions: this.publication.custom_instructions,
      };

      this.generating = true;
      if (btn) btn.textContent = 'Génération...';
      setStatus('Génération des variantes...', null);

      const result = await generateStudioDraftVariants(this.publicationId, data);
      this.publication.proposals = result.variants || [];
      this.publication = { ...this.publication, ...result };
      setStatus(`${this.publication.proposals.length} variante(s) générée(s).`, true);
      this._refreshVariantsTab();
    } catch (error) {
      setStatus(error?.data?.detail || error?.message || 'Génération impossible.', false);
    } finally {
      this.generating = false;
      if (btn) {
        btn.disabled = false;
        btn.textContent = btn.dataset.action === 'regenerate-variants' ? 'Régénérer' : 'Générer 3 variantes';
      }
    }
  }

  _refreshVariantsTab() {
    if (this.activeTab === 'variants') {
      const panel = this.element.querySelector('[data-tab-panel="variants"]');
      if (panel) {
        panel.innerHTML = this._renderVariantsTab();
        // Re-bind variant events
        panel.querySelectorAll('[data-action="select-variant"]').forEach(btn => {
          btn.addEventListener('click', () => this._selectVariant(parseInt(btn.dataset.index, 10)));
        });
        panel.querySelector('[data-action="regenerate-variants"]')?.addEventListener('click', () => this._generateVariants());
        panel.querySelector('[data-action="apply-selected-variant"]')?.addEventListener('click', () => this._applySelectedVariant());
      }
    }
  }

  _selectVariant(index) {
    this.publication.selected_proposal = index;
    this._refreshVariantsTab();
  }

  async _applySelectedVariant() {
    const pub = this.publication;
    const idx = pub.selected_proposal;
    if (idx === null || !pub.proposals || idx >= pub.proposals.length) return;

    const prop = pub.proposals[idx];
    const form = this.element.querySelector('[data-form="cm-draft-text"]');
    if (!form) return;

    form.elements.title.value = prop.title || '';
    form.elements.content.value = prop.content || '';
    form.elements.hashtags.value = prop.hashtags || '';

    // Mettre à jour la publication locale
    pub.title = prop.title;
    pub.content = prop.content;
    pub.hashtags = prop.hashtags;

    // Sauvegarder automatiquement
    await this._saveDraft(form);
  }

  async _validateDraft() {
    const btn = this.element.querySelector('[data-action="validate"]');
    if (btn?.disabled) return;
    if (btn) btn.disabled = true;

    const setStatus = (text, success) => {
      const statusEl = this.element.querySelector('[data-role="draft-status"]');
      if (statusEl) {
        statusEl.textContent = text;
        statusEl.classList.toggle('text-success', !!success);
        statusEl.classList.toggle('text-error', !success);
      }
    };

    try {
      btn.textContent = 'Validation...';
      const result = await validateStudioDraft(this.publicationId, { confirm: true });
      this.publication = result;
      setStatus('Publication validée.', true);
      this._refreshAfterValidation();
    } catch (error) {
      setStatus(error?.data?.detail || error?.message || 'Validation impossible.', false);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Valider';
      }
    }
  }

  _refreshAfterValidation() {
    const statusBadge = this.element.querySelector('.cm-studio-status .status-badge');
    if (statusBadge) {
      statusBadge.textContent = this._formatStatus(this.publication.status);
      statusBadge.className = `status-badge ${this._getStatusBadgeClass(this.publication.status)}`;
    }
    const validateBtn = this.element.querySelector('[data-action="validate"]');
    if (validateBtn) {
      validateBtn.disabled = true;
      validateBtn.textContent = 'Validée';
    }
    const publishBtn = this.element.querySelector('[data-action="publish"]');
    if (publishBtn) {
      publishBtn.disabled = false;
    }
    this._refreshTabs();
  }

  async _publishDraft() {
    const btn = this.element.querySelector('[data-action="publish"]');
    if (btn?.disabled) return;
    if (btn) btn.disabled = true;

    const setStatus = (text, success) => {
      const statusEl = this.element.querySelector('[data-role="draft-status"]');
      if (statusEl) {
        statusEl.textContent = text;
        statusEl.classList.toggle('text-success', !!success);
        statusEl.classList.toggle('text-error', !success);
      }
    };

    if (!confirm('Confirmez-vous la publication sur Instagram ? Cette action est irréversible.')) {
      if (btn) btn.disabled = false;
      return;
    }

    try {
      btn.textContent = 'Publication...';
      setStatus('Publication sur Instagram en cours...', null);

      const result = await publishStudioDraft(this.publicationId, { confirm: true });
      this.publication = result;
      setStatus('Publication réussie !', true);
      this._refreshAfterPublish();
    } catch (error) {
      setStatus(error?.data?.detail || error?.message || 'Publication impossible.', false);
    } finally {
      if (btn) {
        btn.disabled = false;
        if (this.publication.status === 'shared') {
          btn.textContent = 'Publiée';
          btn.disabled = true;
        } else if (this.publication.status === 'publishing') {
          btn.textContent = 'Publication...';
          btn.disabled = true;
        } else if (this.publication.status === 'failed') {
          btn.textContent = 'Publier sur Instagram';
          btn.disabled = false;
        } else {
          btn.textContent = 'Publier sur Instagram';
          btn.disabled = false;
        }
      }
    }
  }

  _refreshAfterPublish() {
    const statusBadge = this.element.querySelector('.cm-studio-header-right .status-badge');
    if (statusBadge) {
      statusBadge.textContent = this._formatStatus(this.publication.status);
      statusBadge.className = `status-badge ${this._getStatusBadgeClass(this.publication.status)}`;
    }
    const validateBtn = this.element.querySelector('[data-action="validate"]');
    if (validateBtn) {
      validateBtn.disabled = true;
      validateBtn.textContent = 'Validée';
    }
    const publishBtn = this.element.querySelector('[data-action="publish"]');
    if (publishBtn) {
      if (this.publication.status === 'shared') {
        publishBtn.textContent = 'Publiée';
        publishBtn.disabled = true;
      } else if (this.publication.status === 'failed') {
        publishBtn.textContent = 'Publier sur Instagram';
        publishBtn.disabled = false;
      }
    }
    // Afficher l'ID Instagram et le permalink si disponibles
    if (this.publication.instagram_media_id || this.publication.instagram_permalink) {
      const metaInfo = document.createElement('div');
      metaInfo.className = 'cm-studio-meta-info';
      metaInfo.innerHTML = `
        <h4>Détails de la publication Instagram</h4>
        <dl class="cm-studio-meta">
          ${this.publication.instagram_media_id ? `<dt>ID Instagram</dt><dd><code>${this._escape(this.publication.instagram_media_id)}</code></dd>` : ''}
          ${this.publication.instagram_permalink ? `<dt>Lien</dt><dd><a href="${this._escape(this.publication.instagram_permalink)}" target="_blank" rel="noopener">Voir sur Instagram</a></dd>` : ''}
        </dl>
      `;
      const sidebar = this.element.querySelector('.cm-studio-sidebar');
      if (sidebar) {
        sidebar.appendChild(metaInfo);
      }
    }
    this._refreshTabs();
  }

  _showPreview() {
    this._loadPreview(this.previewFormat);
    const modal = this.element.querySelector('#cm-preview-modal');
    if (modal) modal.hidden = false;
  }

  async _loadPreview(format) {
    const body = this.element.querySelector('#cm-preview-body');
    if (!body) return;

    body.innerHTML = '<div class="cm-preview-loading"><div class="spinner"></div><p>Génération de l\'aperçu...</p></div>';

    try {
      const result = await previewStudioDraft(this.publicationId, format);
      this.previewFormat = format;
      body.innerHTML = result.preview_html;
    } catch (error) {
      body.innerHTML = `<div class="alert alert-error">${this._escape(error?.data?.detail || error?.message || 'Erreur de prévisualisation')}</div>`;
    }
  }

  _closeModal(id) {
    const modal = this.element.querySelector(`#${id}`);
    if (modal) modal.hidden = true;
  }

  _showScheduleModal() {
    const modal = this.element.querySelector('#cm-schedule-modal');
    if (!modal) return;
    const input = modal.querySelector('[name="scheduled_at"]');
    if (input) {
      // Pré-remplir avec la date suggérée si disponible
      if (this.publication.calendar_entry?.date) {
        input.value = this.publication.calendar_entry.date + 'T10:00';
      } else {
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        tomorrow.setHours(10, 0, 0, 0);
        input.value = tomorrow.toISOString().slice(0, 16);
      }
    }
    modal.hidden = false;
  }

  async _scheduleDraft(form) {
    const formData = new FormData(form);
    const scheduledAt = new Date(formData.get('scheduled_at'));
    const btn = form.querySelector('[type="submit"]');
    if (btn) btn.disabled = true;

    try {
      const result = await scheduleStudioDraft(this.publicationId, scheduledAt);
      this.publication = result;
      this._closeModal('cm-schedule-modal');
      this._refreshAfterValidation();
    } catch (error) {
      alert(error?.data?.detail || error?.message || 'Planification impossible');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  _openPhotoSelector() {
    // Ouvre le sélecteur de photos ForgeAI dans une modale
    const url = `/photos?select=1&callback=cmStudioPhotoSelected`;
    window.open(url, 'cmPhotoSelector', 'width=1000,height=700');
  }

  _removePhoto() {
    this.publication.photo_id = null;
    this.publication.visual_type = 'photo';
    this._refreshVisualTab();
    // Sauvegarder
    this._saveDraftFromActiveTab();
  }

  _refreshVisualTab() {
    if (this.activeTab === 'visual') {
      const panel = this.element.querySelector('[data-tab-panel="visual"]');
      if (panel) {
        panel.innerHTML = this._renderVisualTab();
        // Re-bind visual events
        panel.querySelector('[data-action="select-photo"]')?.addEventListener('click', () => this._openPhotoSelector());
        panel.querySelector('[data-action="remove-photo"]')?.addEventListener('click', () => this._removePhoto());
        panel.querySelectorAll('[data-visual-tab]').forEach(tab => {
          tab.addEventListener('click', () => this._switchVisualTab(tab.dataset.visualTab));
        });
      }
    }
  }

  // Callback global pour la sélection de photo
  static registerPhotoCallback() {
    window.cmStudioPhotoSelected = (photoId) => {
      const page = window.cmStudioPageInstance;
      if (page) {
        page.publication.photo_id = photoId;
        page.publication.visual_type = 'photo';
        page._refreshVisualTab();
        page._saveDraftFromActiveTab();
      }
    };
  }

  // Utilitaires
  _escape(text) {
    if (text == null) return '';
    return String(text)
      .replaceAll('&', '&')
      .replaceAll('<', '<')
      .replaceAll('>', '>')
      .replaceAll('"', '"')
      .replaceAll("'", '&#039;');
  }

  _formatDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr + 'T00:00:00Z');
    return d.toLocaleDateString('fr-FR', { weekday: 'short', day: '2-digit', month: 'short', timeZone: 'UTC' });
  }

  _formatDateTime(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleString('fr-FR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  }

  _formatDuration(seconds) {
    if (!seconds) return '';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return h > 0 ? `${h}h${m.toString().padStart(2, '0')}` : `${m}:${s.toString().padStart(2, '0')}`;
  }

  _formatStatus(status) {
    const map = {
      draft: 'Brouillon',
      validated: 'Validée',
      scheduled: 'Planifiée',
      shared: 'Partagée',
      failed: 'Échec',
      refused: 'Refusée',
      publishing: 'Publication...',
    };
    return map[status] || status;
  }

  _getStatusBadgeClass(status) {
    const map = {
      draft: 'inactive',
      validated: 'active',
      scheduled: 'warning',
      shared: 'success',
      failed: 'danger',
      refused: 'inactive',
      publishing: 'warning',
    };
    return map[status] || 'inactive';
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
}

// Instance globale pour le callback photo
window.cmStudioPageInstance = null;

export function createCommunityManagerStudioPage(router, publicationId, entryData = null) {
  const page = new CommunityManagerStudioPage(router, publicationId, entryData);
  window.cmStudioPageInstance = page;
  CommunityManagerStudioPage.registerPhotoCallback();
  return page;
}