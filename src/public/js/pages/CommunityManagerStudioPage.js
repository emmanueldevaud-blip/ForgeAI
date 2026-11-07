/**
 * Community Manager Studio Page - V3
 * Studio de création de publications Instagram avec UX repensée
 * Flux: Ton -> Titre -> Texte -> Visuel -> Aperçu -> Actions
 */

import { api } from '../services/api.js?v=5';
import {
  getStudioDraft,
  updateStudioDraft,
  generateStudioDraftVariants,
  validateStudioDraft,
  scheduleStudioDraft,
  previewStudioDraft,
  publishStudioDraft,
  generateStudioDraftText,
  lockStudioDraftTitle,
  lockStudioDraftContent,
  lockStudioDraftPhoto,
} from '../services/sportApi.js?v=12';
import { publicationPhotoUrl } from '../services/sportApi.js?v=11';


export class CommunityManagerStudioPage {
  constructor(router, publicationId, entryData = null) {
    this.router = router;
    this.publicationId = publicationId;
    this.entryData = entryData;
    this.element = null;
    this.publication = null;
    this.loading = true;
    this.saving = false;
    this.generating = false;
    this.previewFormat = 'feed';
    this.activeSection = 'text';
    this.error = null;
    this.success = null;
    this.availableTones = [
      { value: 'humor', label: 'Humour', desc: 'Second degré, situations absurdes, galères du traileur' },
      { value: 'self_deprecation', label: 'Autodérision', desc: 'Se moquer de soi-même avec légèreté' },
      { value: 'stats', label: 'Statistiques', desc: 'Chiffres marquants, analyses, comparaisons' },
      { value: 'storytelling', label: 'Storytelling', desc: 'Récit d\'aventure avec début, milieu, fin' },
      { value: 'inspiration', label: 'Inspiration', desc: 'Dépassement de soi, progression, objectifs' },
      { value: 'expert', label: 'Expert', desc: 'Analyse technique, conseils, données précises' },
      { value: 'professional', label: 'Professionnel', desc: 'Ton posé, informatif, crédible' },
    ];
  }

  async initialize() {
    try {
      this.publication = await getStudioDraft(this.publicationId);
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Impossible de charger le brouillon';
    }
  }

  render() {
    if (!this.element) {
      this.element = document.createElement('div');
      this.element.className = 'cm-studio-page';
    }

    const pub = this.publication;

    this.element.innerHTML = `
      <div class="cm-studio-page">
        <header class="cm-studio-header">
          <div class="cm-studio-header-left">
            <button class="btn btn-secondary cm-studio-back" data-action="back">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M19 12H5M12 19l-7-7 7-7"/>
              </svg>
              <span>Calendrier</span>
            </button>
            <h1>Studio de création</h1>
          </div>
          <div class="cm-studio-header-right">
            <div class="cm-studio-status">
              <span class="status-badge ${this._getStatusBadgeClass(this.publication?.status)}">${this._formatStatus(this.publication?.status)}</span>
            </div>
          </div>
        </header>

        ${this.error ? `<div class="cm-studio-alert alert-error">${this._escape(this.error)}</div>` : ''}
        ${this.success ? `<div class="cm-studio-alert alert-success">${this._escape(this.success)}</div>` : ''}

        <main class="cm-studio-main">
          <!-- 1. CHOIX DU TON -->
          <section class="cm-studio-section">
            <div class="cm-section-header">
              <h2>1. Ton rédactionnel</h2>
              <p class="cm-section-desc">Le ton détermine le style de génération du titre et du texte.</            </div>
            <div class="cm-tone-selector">
              ${this.availableTones.map(t => `
                <button class="cm-tone-card ${this.publication?.tone_used === t.value ? 'active' : ''}" data-tone="${t.value}" title="${t.desc}">
                  <span class="cm-tone-label">${t.label}</span>
                </button>
              `).join('')}
            </div>
          </section>

          <!-- 2. TITRE -->
          <section class="cm-studio-section">
            <div class="cm-section-header">
              <h2>2. Titre</h2>
              <p class="cm-section-desc">Le titre accrocheur. Verrouillez-le quand il vous convient.</h2>
            </div>
            <div class="cm-field-group">
              <div class="cm-field-input-wrapper">
                <input type="text" class="cm-input-title" name="title" maxlength="200" placeholder="Titre de la publication" value="${this._escape(this.publication?.title || '')}" ${this.publication?.title_locked ? 'readonly' : ''}>
                <button class="btn-lock ${this.publication?.title_locked ? 'locked' : ''}" data-action="lock-title" title="${this.publication?.title_locked ? 'Déverrouiller' : 'Verrouiller'}" aria-label="${this.publication?.title_locked ? 'Déverrouiller le titre' : 'Verrouiller le titre'}">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                  </svg>
                </button>
              </div>
              <p class="cm-field-hint">${this.publication?.title_locked ? 'Titre verrouillé - cliquez pour déverrouiller' : 'Cliquez sur le cadenas pour verrouiller le titre'}</p>
            </div>
          </section>

          <!-- 3. TEXTE DE PUBLICATION -->
          <section class="cm-studio-section">
            <div class="cm-section-header">
              <h2>3. Texte de publication</h2>
              <p class="cm-section-desc">Générez un texte court ou long selon le ton choisi. Verrouillez quand satisfait.</h2>
            </div>

            <div class="cm-text-actions">
              <button class="btn btn-outline ${this.generating ? 'disabled' : ''}" data-action="generate-short" ${this.publication?.content_locked ? 'disabled' : ''} title="Générer un texte court (3-4 lignes max)">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="3" y1="12" x2="21" y2="12"/>
                  <line x1="3" y1="18" x2="15" y2="18"/>
                  <line x1="3" y1="6" x2="9" y2="6"/>
                </svg>
                Texte court
              </button>
              <button class="btn btn-primary ${this.generating ? 'disabled' : ''}" data-action="generate-long" ${this.publication?.content_locked ? 'disabled' : ''} title="Générer un texte long (développé, narratif)">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="3" y1="12" x2="21" y2="12"/>
                  <line x1="3" y1="18" x2="21" y2="18"/>
                  <line x1="3" y1="6" x2="21" y2="6"/>
                  <line x1="3" y1="14" x2="15" y2="14"/>
                </svg>
                Texte long
              </button>
            </div>

            <div class="cm-field-group">
              <textarea class="cm-textarea" name="content" rows="10" placeholder="Écrivez votre publication ici..." ${this.publication?.content_locked ? 'readonly' : ''}>${this._escape(this.publication?.content || '')}</textarea>
              <div class="cm-field-actions">
                <button class="btn-lock ${this.publication?.content_locked ? 'locked' : ''}" data-action="lock-content" title="${this.publication?.content_locked ? 'Déverrouiller' : 'Verrouiller'}" aria-label="${this.publication?.content_locked ? 'Déverrouiller le texte' : 'Verrouiller le texte'}">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                  </svg>
                </button>
                <span class="cm-field-hint">${this.publication?.content_locked ? 'Texte verrouillé - cliquez pour déverrouiller' : 'Cliquez sur le cadenas pour verrouiller le texte'}</span>
              </div>
            </div>

            <div class="cm-field-group">
              <label><span>Hashtags</span>
                <textarea name="hashtags" rows="2" placeholder="#trail #running #recovery">${this._escape(this.publication?.hashtags || '')}</textarea>
              </label>
            </div>
          </section>

          <!-- 4. VISUEL -->
          <section class="cm-studio-section">
            <div class="cm-section-header">
              <h2>4. Visuel</h2>
              <p class="cm-section-desc">Sélectionnez une photo ou générez un visuel (bientôt disponible).</h2>
            </div>

            <div class="cm-visual-preview">
              ${this.publication?.photo_id ? `
                <img src="${publicationPhotoUrl(this.publication.photo_id, 'large')}" alt="Visuel de la publication" class="cm-studio-visual-img">
                <button class="btn-remove-photo" data-action="remove-photo" title="Retirer le visuel" ${this.publication?.photo_locked ? 'disabled' : ''}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
                <button class="btn-lock ${this.publication?.photo_locked ? 'locked' : ''}" data-action="lock-photo" title="${this.publication?.photo_locked ? 'Déverrouiller' : 'Verrouiller'}" aria-label="${this.publication?.photo_locked ? 'Déverrouiller le visuel' : 'Verrouiller le visuel'}">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                  </svg>
                </button>
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

            <div class="cm-visual-actions">
              <button class="btn btn-primary" data-action="select-photo" ${this.publication?.photo_locked ? 'disabled' : ''}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 19V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2z"/>
                  <path d="M17 5l-5 5 5 5"/>
                </svg>
                Sélectionner une photo
              </button>
              <button class="btn btn-secondary" data-action="generate-visual" disabled title="Bientôt disponible">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 2a10 10 0 1 0 10 10 4 4 0 0 1-5-5 4 4 0 0 0-5-5"/>
                  <path d="M2 2l20 20"/>
                </svg>
                Générer par IA (bientôt)
              </button>
            </div>
            <p class="cm-field-hint">Sélectionnez une photo depuis votre bibliothèque ForgeAI Photos. Formats recommandés : 1:1 (feed), 4:5 (portrait), 9:16 (story/reel).</p>
          </section>

          <!-- 5. APERÇU INSTAGRAM EN TEMPS RÉEL -->
          <section class="cm-studio-section">
            <div class="cm-section-header">
              <h2>5. Aperçu Instagram</h2>
              <p class="cm-section-desc">Aperçu en temps réel du rendu final.</            </div>
            <div class="cm-preview-selector">
              <button class="cm-preview-format-btn ${this.previewFormat === 'feed' ? 'active' : ''}" data-format="feed">Feed (1:1)</button>
              <button class="cm-preview-format-btn ${this.previewFormat === 'story' ? 'active' : ''}" data-format="story">Story (9:16)</button>
              <button class="cm-preview-format-btn ${this.previewFormat === 'reel' ? 'active' : ''}" data-format="reel">Reel (9:16)</button>
              <button class="cm-preview-format-btn ${this.previewFormat === 'strategic' ? 'active' : ''}" data-format="strategic">Stratégique</button>
            </div>
            <div class="cm-preview-container" id="cm-preview-container">
              <div class="cm-preview-loading"><div class="spinner"></div><p>Chargement...</p></div>
            </div>
          </section>

          <!-- 6. ACTIONS FINALES -->
          <footer class="cm-studio-footer">
            <div class="cm-studio-actions-left">
              <button class="btn btn-secondary" data-action="save">${this.saving ? 'Sauvegarde...' : 'Sauvegarder'}</button>
              <span class="cm-status" data-role="status"></span>
            </div>
            <div class="cm-studio-actions-right">
              <button class="btn btn-primary" data-action="validate" ${!this.publication?.content ? 'disabled' : ''} ${this.publication?.status === 'validated' || this.publication?.status === 'scheduled' || this.publication?.status === 'shared' ? 'disabled' : ''}>
                ${this.publication?.status === 'validated' ? 'Validée' : this.publication?.status === 'scheduled' ? 'Planifiée' : this.publication?.status === 'shared' ? 'Publiée' : 'Valider'}
              </button>
              <button class="btn btn-success" data-action="publish" ${this.publication?.status !== 'validated' && this.publication?.status !== 'scheduled' ? 'disabled' : ''} ${!this.publication?.content || !this.publication?.photo_id ? 'disabled' : ''}>
                ${this.publication?.status === 'shared' ? 'Publiée' : this.publication?.status === 'publishing' ? 'Publication...' : 'Publier sur Instagram'}
              </button>
            </div>
          </footer>
        </main>
      </div>
    `;

    this._bindEvents();
    this._loadPreview(this.previewFormat);
    return this.element;
  }

  _bindEvents() {
    if (!this.element) return;

    // Back button
    this.element.querySelector('[data-action="back"]')?.addEventListener('click', () => {
      window.history.back();
    });

    // Tone selection
    this.element.querySelectorAll('[data-tone]').forEach(btn => {
      btn.addEventListener('click', () => this._selectTone(btn.dataset.tone));
    });

    // Title lock
    this.element.querySelector('[data-action="lock-title"]')?.addEventListener('click', () => {
      this._toggleTitleLock();
    });

    // Content lock
    this.element.querySelector('[data-action="lock-content"]')?.addEventListener('click', () => {
      this._toggleContentLock();
    });

    // Photo lock
    this.element.querySelector('[data-action="lock-photo"]')?.addEventListener('click', () => {
      this._togglePhotoLock();
    });

    // Title input
    this.element.querySelector('[name="title"]')?.addEventListener('input', (e) => this._onTitleInput(e));

    // Content input
    this.element.querySelector('[name="content"]')?.addEventListener('input', (e) => this._onContentInput(e));

    // Hashtags input
    this.element.querySelector('[name="hashtags"]')?.addEventListener('input', (e) => this._onHashtagsInput(e));

    // Generate short text
    this.element.querySelector('[data-action="generate-short"]')?.addEventListener('click', () => this._generateText('short'));

    // Generate long text
    this.element.querySelector('[data-action="generate-long"]')?.addEventListener('click', () => this._generateText('long'));

    // Select photo
    this.element.querySelector('[data-action="select-photo"]')?.addEventListener('click', () => this._openPhotoSelector());

    // Remove photo
    this.element.querySelector('[data-action="remove-photo"]')?.addEventListener('click', () => this._removePhoto());

    // Preview format
    this.element.querySelectorAll('[data-format]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.previewFormat = btn.dataset.format;
        this._updatePreviewFormatButtons();
        this._loadPreview(this.previewFormat);
      });
    });

    // Preview
    this.element.querySelector('[data-action="preview"]')?.addEventListener('click', () => {
      this._showPreview();
    });
    this.element.querySelector('[data-action="close-preview"]')?.addEventListener('click', () => {
      this._closeModal('cm-preview-modal');
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

  async _selectTone(tone) {
    if (this.generating) return;

    // Update UI immediately
    this.element.querySelectorAll('[data-tone]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tone === tone);
    });

    // Update publication
    try {
      const updated = await updateStudioDraft(this.publicationId, { tone_used: tone });
      this.publication = updated;
      this.publication.tone_used = tone;

      // Auto-regenerate title if not locked
      if (!this.publication?.title_locked) {
        await this._regenerateTitle(tone);
      }

      // Auto-regenerate text if not locked
      if (!this.publication?.content_locked) {
        await this._generateText('short');
      }
    } catch (error) {
      console.error('Erreur changement ton:', error);
    }
  }

  async _regenerateTitle(tone) {
    try {
      const result = await generateStudioDraftText(this.publicationId, {
        publication_id: this.publicationId,
        length: 'short',
        tone: tone,
        use_title: true,
        styles: this.publication?.styles,
        custom_instructions: this.publication?.custom_instructions,
      });
      if (result?.title && !this.publication?.title_locked) {
        this.publication.title = result.title;
        await updateStudioDraft(this.publicationId, { title: result.title });
      }
    } catch (error) {
      console.error('Erreur régénération titre:', error);
    }
  }

  _onTitleInput(e) {
    const title = e.target.value;
    this.publication.title = title;
    this._updatePreview();
  }

  _onContentInput(e) {
    const content = e.target.value;
    this.publication.content = content;
    this._updatePreview();
  }

  _onHashtagsInput(e) {
    const hashtags = e.target.value;
    this.publication.hashtags = hashtags;
    this._updatePreview();
  }

  async _toggleTitleLock() {
    const newLock = !this.publication.title_locked;
    try {
      await lockStudioDraftTitle(this.publicationId, newLock);
      this.publication.title_locked = newLock;
      this._updateLockUI('title');
    } catch (error) {
      console.error('Erreur verrouillage titre:', error);
    }
  }

  async _toggleContentLock() {
    const newLock = !this.publication.content_locked;
    try {
      await lockStudioDraftContent(this.publicationId, newLock);
      this.publication.content_locked = newLock;
      this._updateLockUI('content');
    } catch (error) {
      console.error('Erreur verrouillage contenu:', error);
    }
  }

  async _togglePhotoLock() {
    const newLock = !this.publication.photo_locked;
    try {
      await lockStudioDraftPhoto(this.publicationId, newLock);
      this.publication.photo_locked = newLock;
      this._updateLockUI('photo');
    } catch (error) {
      console.error('Erreur verrouillage photo:', error);
    }
  }

  _updateLockUI(type) {
    const pub = this.publication;
    const lockBtn = this.element.querySelector(`[data-action="lock-${type}"]`);
    const input = this.element.querySelector(`[name="${type === 'title' ? 'title' : type === 'content' ? 'content' : 'photo'}"]`);
    const hint = lockBtn?.parentElement?.querySelector('.cm-field-hint');

    if (lockBtn) {
      lockBtn.classList.toggle('locked', pub[`${type}_locked`]);
      lockBtn.title = pub[`${type}_locked`] ? 'Déverrouiller' : 'Verrouiller';
      lockBtn.setAttribute('aria-label', pub[`${type}_locked`] ? `Déverrouiller le ${type === 'title' ? 'titre' : type === 'content' ? 'texte' : 'visuel'}` : `Verrouiller le ${type === 'title' ? 'titre' : type === 'content' ? 'texte' : 'visuel'}`);
    }
    if (input) {
      input.readOnly = pub[`${type}_locked`];
    }
    if (hint) {
      hint.textContent = pub[`${type}_locked`] ? `${type === 'title' ? 'Titre' : type === 'content' ? 'Texte' : 'Visuel'} verrouillé - cliquez pour déverrouiller` : `Cliquez sur le cadenas pour verrouiller le ${type === 'title' ? 'titre' : type === 'content' ? 'texte' : 'visuel'}`;
    }
  }

  async _generateText(length) {
    if (this.generating) return;
    if (this.publication?.content_locked) return;

    const btn = this.element.querySelector(`[data-action="generate-${length}"]`);
    const statusEl = this.element.querySelector('[data-role="status"]');

    const setStatus = (text, success) => {
      const statusEl = this.element.querySelector('[data-role="status"]');
      if (statusEl) {
        statusEl.textContent = text;
        statusEl.classList.toggle('text-success', !!success);
        statusEl.classList.toggle('text-error', !success);
      }
    };

    try {
      this.generating = true;
      if (btn) btn.disabled = true;
      const btnText = btn?.querySelector('span') || btn;
      if (btnText) btnText.textContent = length === 'short' ? 'Génération...' : 'Génération...';
      setStatus('Génération en cours...', null);

      const result = await generateStudioDraftText(this.publicationId, {
        publication_id: this.publicationId,
        length: length,
        tone: this.publication.tone_used,
        use_title: true,
        styles: this.publication?.styles,
        custom_instructions: this.publication?.custom_instructions,
      });

      if (result?.content) {
        this.publication.content = result.content;
        this.publication.title = result.title || this.publication.title;
        this.publication.hashtags = result.hashtags || this.publication.hashtags;
        this.element.querySelector('[name="content"]').value = this.publication.content;
        this.element.querySelector('[name="title"]').value = this.publication.title || '';
        this.element.querySelector('[name="hashtags"]').value = this.publication.hashtags || '';
        setStatus(`${length === 'short' ? 'Texte court' : 'Texte long'} généré !`, true);
        this._updatePreview();
      }
    } catch (error) {
      const statusEl = this.element.querySelector('[data-role="status"]');
      if (statusEl) {
        statusEl.textContent = error?.data?.detail || error?.message || 'Génération impossible.';
        statusEl.classList.add('text-error');
      }
    } finally {
      this.generating = false;
      const btn = this.element.querySelector(`[data-action="generate-${length}"]`);
      if (btn) btn.disabled = false;
    }
  }

  async _openPhotoSelector() {
    const url = `/photos?select=1&callback=cmStudioPhotoSelected`;
    window.open(url, 'cmPhotoSelector', 'width=1000,height=700');
  }

  _removePhoto() {
    this.publication.photo_id = null;
    this.publication.visual_type = 'photo';
    this._refreshVisualTab();
    this._updatePreview();
    this._saveDraftFromActiveTab();
  }

  _showPreview() {
    this._loadPreview(this.previewFormat);
    const modal = this.element.querySelector('#cm-preview-modal');
    if (modal) modal.hidden = false;
  }

  async _loadPreview(format) {
    const body = this.element.querySelector('#cm-preview-body');
    if (!body) return;

    body.innerHTML = '<div class="cm-preview-loading"><div class="spinner"></div><p>Chargement...</p></div>';

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

  _updatePreviewFormatButtons() {
    this.element.querySelectorAll('[data-format]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.format === this.previewFormat);
    });
  }

  async _validateDraft() {
    const btn = this.element.querySelector('[data-action="validate"]');
    if (btn?.disabled) return;
    if (btn) btn.disabled = true;

    const setStatus = (text, success) => {
      const statusEl = this.element.querySelector('[data-role="status"]');
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
      this._refreshAfterValidation();
    } catch (error) {
      const statusEl = this.element.querySelector('[data-role="status"]');
      if (statusEl) {
        statusEl.textContent = error?.data?.detail || error?.message || 'Validation impossible.';
        statusEl.classList.add('text-error');
      }
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
  }

  async _publishDraft() {
    const btn = this.element.querySelector('[data-action="publish"]');
    if (btn?.disabled) return;
    if (btn) btn.disabled = true;

    const setStatus = (text, success) => {
      const statusEl = this.element.querySelector('[data-role="status"]');
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
      const statusEl = this.element.querySelector('[data-role="status"]');
      if (statusEl) {
        statusEl.textContent = error?.data?.detail || error?.message || 'Publication impossible.';
        statusEl.classList.add('text-error');
      }
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
  }

  _saveDraftFromActiveTab() {
    const form = this.element.querySelector('[data-form="cm-draft-text"]');
    if (form) {
      const formData = new FormData(form);
      const data = {
        title: formData.get('title') || null,
        content: formData.get('content') || null,
        hashtags: formData.get('hashtags') || null,
      };
      updateStudioDraft(this.publicationId, data).then(() => {
        this.success = 'Brouillon sauvegardé.';
        this._refreshTabs();
      }).catch(err => {
        this.error = err?.data?.detail || err?.message || 'Erreur de sauvegarde.';
        this._refreshTabs();
      });
    }
  }

  _updatePreview() {
    // Mise à jour instantanée de l'aperçu si la modal est ouverte
    const modal = this.element.querySelector('#cm-preview-modal');
    if (modal && !modal.hidden) {
      this._loadPreview(this.previewFormat);
    }
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

  _escape(text) {
    if (text == null) return '';
    return String(text)
      .replaceAll('&', '&')
      .replaceAll('<', '<')
      .replaceAll('>', '>')
      .replaceAll('"', '"')
      .replaceAll("'", '&#039;');
  }

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
}

window.cmStudioPageInstance = null;

export function createCommunityManagerStudioPage(router, publicationId, entryData = null) {
  const page = new CommunityManagerStudioPage(router, publicationId, entryData);
  window.cmStudioPageInstance = page;
  CommunityManagerStudioPage.registerPhotoCallback();
  return page;
}