/**
 * Community Manager Studio Page - V3
 * Créateur de publications réseaux sociaux (Instagram Feed, Story, Reel, Stratégique)
 * Flux : Ton -> Titre (avec verrou) -> Texte (court/long, avec verrou) -> Visuel & Photos Garmin -> Effets & Musique -> Aperçu en direct -> Actions
 */

import { api } from '../services/api.js?v=6';
import {
  getStudioDraft,
  updateStudioDraft,
  validateStudioDraft,
  scheduleStudioDraft,
  previewStudioDraft,
  publishStudioDraft,
  generateStudioDraftText,
  lockStudioDraftTitle,
  lockStudioDraftContent,
  lockStudioDraftPhoto,
  getSuggestedPhotos,
} from '../services/sportApi.js?v=13';
import { publicationPhotoUrl } from '../services/sportApi.js?v=13';

export class CommunityManagerStudioPage {
  constructor(router, publicationId, entryData = null, onBack = null) {
    this.router = router;
    this.publicationId = publicationId;
    this.entryData = entryData;
    this.onBack = onBack;
    this.element = null;
    this.publication = null;
    this.suggestedPhotos = [];
    this.loading = true;
    this.saving = false;
    this.generating = false;
    this.previewFormat = 'feed';
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

    this.availableEffects = [
      { value: 'none', label: 'Naturel', css: 'none', desc: 'Sans filtre' },
      { value: 'trail_epic', label: 'Trail Épique', css: 'contrast(1.25) saturate(1.2) brightness(1.05)', desc: 'Contraste et punch nature' },
      { value: 'golden_hour', label: 'Heure Dorée', css: 'sepia(0.25) saturate(1.3) brightness(1.08) hue-rotate(-10deg)', desc: 'Chaleur coucher de soleil' },
      { value: 'clean_contrast', label: 'Contraste Net', css: 'contrast(1.35) brightness(1.02)', desc: 'Détails nets et clairs' },
      { value: 'black_and_white', label: 'Noir & Blanc', css: 'grayscale(1) contrast(1.3)', desc: 'Monochrome contrasté' },
      { value: 'vintage', label: 'Rétro Aventure', css: 'sepia(0.35) contrast(1.1) brightness(0.95)', desc: 'Tons chauds vintage' },
    ];

    this.availableMusics = [
      { value: 'none', label: 'Aucune', icon: '🔇', track: '', desc: 'Sans son' },
      { value: 'motivation', label: 'Motivation', icon: '🔥', track: 'Dépassement de soi (Original)', desc: 'Rythme puissant' },
      { value: 'electronic', label: 'Électro Run', icon: '⚡', track: 'Night Pace 170 BPM', desc: 'Beat énergique' },
      { value: 'trail_nature', label: 'Trail Sauvage', icon: '🌲', track: 'Horizon Montagne (Acoustique)', desc: 'Ambiance grands espaces' },
      { value: 'lofi_chill', label: 'Lo-Fi Chill', icon: '🎧', track: 'Post-Run Vibes', desc: 'Récupération et détente' },
      { value: 'epic_climb', label: 'Sommet Épique', icon: '🏔️', track: 'To the Peak (Cinematic)', desc: 'Cordes et cuivres' },
    ];

    this.selectedEffect = 'none';
    this.selectedMusic = 'none';
  }

  async initialize() {
    try {
      this.loading = true;
      const [pub, photos] = await Promise.all([
        getStudioDraft(this.publicationId),
        getSuggestedPhotos(this.publicationId, 15).catch(() => []),
      ]);
      this.publication = pub;
      this.suggestedPhotos = photos || [];

      // Restaurer effet et musique depuis les styles ou métadonnées si présents
      if (Array.isArray(pub?.styles)) {
        const effectStyle = pub.styles.find(s => s.startsWith('effect:'));
        if (effectStyle) this.selectedEffect = effectStyle.replace('effect:', '');
        const musicStyle = pub.styles.find(s => s.startsWith('music:'));
        if (musicStyle) this.selectedMusic = musicStyle.replace('music:', '');
      }
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Impossible de charger le brouillon';
    } finally {
      this.loading = false;
    }
  }

  render() {
    if (!this.element) {
      this.element = document.createElement('div');
      this.element.className = 'cm-studio-container';
    }

    const pub = this.publication;
    const currentPhoto = this._getCurrentPhoto();
    const effectConfig = this.availableEffects.find(e => e.value === this.selectedEffect) || this.availableEffects[0];
    const musicConfig = this.availableMusics.find(m => m.value === this.selectedMusic) || this.availableMusics[0];

    this.element.innerHTML = `
      <div class="cm-studio-wrapper">
        <!-- HEADER DU STUDIO -->
        <header class="cm-studio-topbar">
          <div class="cm-studio-topbar-left">
            <button class="btn btn-secondary btn-sm cm-studio-back-btn" data-action="back" title="Revenir au calendrier éditorial">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M19 12H5M12 19l-7-7 7-7"/>
              </svg>
              <span>Calendrier</span>
            </button>
            <div class="cm-studio-title-block">
              <h1>Studio de Création</h1>
              <span class="status-badge ${this._getStatusBadgeClass(pub?.status)}">${this._formatStatus(pub?.status)}</span>
            </div>
          </div>
          <div class="cm-studio-topbar-right">
            <button class="btn btn-secondary btn-sm" data-action="save">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                <polyline points="17 21 17 13 7 13 7 21"/>
                <polyline points="7 3 7 8 15 8"/>
              </svg>
              <span>${this.saving ? 'Sauvegarde...' : 'Sauvegarder le brouillon'}</span>
            </button>
            <button class="btn btn-primary btn-sm" data-action="validate" ${!pub?.content ? 'disabled' : ''} ${pub?.status === 'validated' || pub?.status === 'scheduled' || pub?.status === 'shared' ? 'disabled' : ''}>
              ${pub?.status === 'validated' ? 'Validée' : pub?.status === 'scheduled' ? 'Planifiée' : pub?.status === 'shared' ? 'Publiée' : 'Valider'}
            </button>
            <button class="btn btn-success btn-sm" data-action="publish" ${pub?.status !== 'validated' && pub?.status !== 'scheduled' ? 'disabled' : ''} ${!pub?.content || !pub?.photo_id ? 'disabled' : ''}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="2" y="2" width="20" height="20" rx="5" ry="5"/>
                <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"/>
                <line x1="17.5" y1="6.5" x2="17.51" y2="6.5"/>
              </svg>
              <span>${pub?.status === 'shared' ? 'Publiée' : pub?.status === 'publishing' ? 'Publication...' : 'Publier sur Instagram'}</span>
            </button>
          </div>
        </header>

        ${this.error ? `<div class="cm-studio-alert alert-error">${this._escape(this.error)}</div>` : ''}
        ${this.success ? `<div class="cm-studio-alert alert-success">${this._escape(this.success)}</div>` : ''}
        <div class="cm-feedback-bar" id="cm-feedback-bar" style="display: none;"></div>

        <!-- CORPS DU STUDIO EN 2 COLONNES -->
        <div class="cm-studio-layout">
          <!-- COLONNE GAUCHE : FLUX DE CRÉATION -->
          <div class="cm-studio-flow">

            <!-- 1. CHOIX DU TON -->
            <section class="cm-card">
              <div class="cm-card-header">
                <div>
                  <h2>1. Ton & Style Rédactionnel</h2>
                  <p class="cm-card-desc">Cliquez sur un ton pour adapter instantanément le titre et le texte (si non verrouillés).</p>
                </div>
              </div>
              <div class="cm-tone-pills">
                ${this.availableTones.map(t => `
                  <button type="button" class="cm-tone-pill ${pub?.tone_used === t.value ? 'active' : ''}" data-tone="${t.value}" title="${t.desc}">
                    <span>${t.label}</span>
                  </button>
                `).join('')}
              </div>
            </section>

            <!-- 2. TITRE -->
            <section class="cm-card">
              <div class="cm-card-header">
                <div>
                  <h2>2. Titre de la publication</h2>
                  <p class="cm-card-desc">Accroche principale. Verrouillez-le avec le cadenas pour qu'il ne change plus.</p>
                </div>
              </div>
              <div class="cm-lockable-input-row">
                <input type="text" class="form-control cm-title-input" name="title" maxlength="200" placeholder="Titre percutant de votre publication..." value="${this._escape(pub?.title || '')}" ${pub?.title_locked ? 'readonly' : ''}>
                <button type="button" class="btn-lock ${pub?.title_locked ? 'locked' : ''}" data-action="lock-title" title="${pub?.title_locked ? 'Titre verrouillé - Cliquez pour déverrouiller' : 'Titre libre - Cliquez pour verrouiller'}">
                  ${this._renderLockSvg(pub?.title_locked)}
                </button>
              </div>
              <p class="cm-hint-text">${pub?.title_locked ? '🔒 Titre verrouillé : protégé contre toute régénération automatique.' : '🔓 Titre déverrouillé : s\'adaptera automatiquement si vous changez de ton.'}</p>
            </section>

            <!-- 3. TEXTE & HASHTAGS -->
            <section class="cm-card">
              <div class="cm-card-header cm-header-flex">
                <div>
                  <h2>3. Texte & Légende</h2>
                  <p class="cm-card-desc">Générez par IA ou rédigez librement. Compteur de caractères et hashtags intégrés.</p>
                </div>
                <div class="cm-gen-buttons">
                  <button type="button" class="btn btn-sm btn-outline ${this.generating ? 'disabled' : ''}" data-action="generate-short" ${pub?.content_locked ? 'disabled' : ''} title="${pub?.content_locked ? 'Texte verrouillé' : 'Générer un texte court (3-4 lignes)'}">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="15" y2="18"/><line x1="3" y1="6" x2="9" y2="6"/></svg>
                    <span>Texte court</span>
                  </button>
                  <button type="button" class="btn btn-sm btn-primary ${this.generating ? 'disabled' : ''}" data-action="generate-long" ${pub?.content_locked ? 'disabled' : ''} title="${pub?.content_locked ? 'Texte verrouillé' : 'Générer un texte long développé'}">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="14" x2="15" y2="14"/></svg>
                    <span>Texte long</span>
                  </button>
                </div>
              </div>

              <div class="cm-lockable-textarea-wrap">
                <textarea class="form-control cm-content-textarea" name="content" rows="7" placeholder="Racontez votre sortie, partagez vos sensations..." ${pub?.content_locked ? 'readonly' : ''}>${this._escape(pub?.content || '')}</textarea>
                <div class="cm-textarea-actions">
                  <span class="cm-char-counter" id="cm-char-counter">${(pub?.content || '').length} car.</span>
                  <button type="button" class="btn-lock ${pub?.content_locked ? 'locked' : ''}" data-action="lock-content" title="${pub?.content_locked ? 'Texte verrouillé - Cliquez pour déverrouiller' : 'Texte libre - Cliquez pour verrouiller'}">
                    ${this._renderLockSvg(pub?.content_locked)}
                  </button>
                </div>
              </div>
              <p class="cm-hint-text">${pub?.content_locked ? '🔒 Texte verrouillé : vos modifications manuelles sont protégées.' : '🔓 Texte déverrouillé : vous pouvez générer en version courte ou longue.'}</p>

              <div class="cm-hashtags-group">
                <label for="cm-hashtags-input"><span>Hashtags suggérés</span></label>
                <input type="text" id="cm-hashtags-input" class="form-control" name="hashtags" placeholder="#trailrunning #garmin #outdoor #motivation" value="${this._escape(pub?.hashtags || '')}">
              </div>
            </section>

            <!-- 4. VISUEL & PHOTOS GARMIN -->
            <section class="cm-card">
              <div class="cm-card-header cm-header-flex">
                <div>
                  <h2>4. Photos, Musique & Effets</h2>
                  <p class="cm-card-desc">Liez vos photos Garmin, appliquez un filtre visuel et sélectionnez l'ambiance musicale.</p>
                </div>
                <div class="cm-photo-tools">
                  <button type="button" class="btn btn-sm btn-secondary" data-action="select-photo" ${pub?.photo_locked ? 'disabled' : ''}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>
                    <span>Parcourir la photothèque</span>
                  </button>
                </div>
              </div>

              <!-- PHOTOS SUGGÉRÉES LIÉES AUX ACTIVITÉS SPORT -->
              <div class="cm-suggested-photos-section">
                <div class="cm-subheading">
                  <span>📸 Photos suggérées (vos activités & récentes)</span>
                </div>
                <div class="cm-suggested-photos-grid">
                  ${this.suggestedPhotos.length > 0 ? this.suggestedPhotos.map(p => `
                    <div class="cm-photo-card ${pub?.photo_id === p.id ? 'selected' : ''}" data-photo-id="${p.id}" title="${p.title || ''}">
                      <img src="${p.thumbnail_url}" alt="${this._escape(p.title || '')}" loading="lazy">
                      <span class="cm-photo-badge badge-${p.badge_class || 'info'}">${this._escape(p.match_reason || 'Photo')}</span>
                      ${pub?.photo_id === p.id ? '<span class="cm-photo-check">✓</span>' : ''}
                    </div>
                  `).join('') : `
                    <p class="text-muted" style="padding: 12px; font-size: 13px;">Aucune photo trouvée récemment. Utilisez le bouton "Parcourir" pour en sélectionner une.</p>
                  `}
                </div>
              </div>

              <!-- PHOTO ACTUELLEMENT SÉLECTIONNÉE -->
              <div class="cm-selected-photo-preview">
                ${pub?.photo_id ? `
                  <div class="cm-current-photo-row">
                    <div class="cm-current-photo-img-wrap">
                      <img src="${publicationPhotoUrl(pub.photo_id, 'medium')}" class="cm-current-photo-img" style="filter: ${effectConfig.css};" alt="Visuel sélectionné">
                    </div>
                    <div class="cm-current-photo-meta">
                      <div class="cm-current-photo-title">Photo sélectionnée (#${pub.photo_id})</div>
                      <div class="cm-current-photo-actions">
                        <button type="button" class="btn btn-sm btn-secondary ${pub?.photo_locked ? 'locked' : ''}" data-action="lock-photo" title="${pub?.photo_locked ? 'Déverrouiller le visuel' : 'Verrouiller le visuel'}">
                          ${this._renderLockSvg(pub?.photo_locked)}
                          <span>${pub?.photo_locked ? 'Verrouillée' : 'Verrouiller'}</span>
                        </button>
                        <button type="button" class="btn btn-sm btn-outline text-danger" data-action="remove-photo" ${pub?.photo_locked ? 'disabled' : ''}>
                          Retirer
                        </button>
                      </div>
                    </div>
                  </div>
                ` : `
                  <div class="cm-no-photo-box">
                    <p>Aucune photo sélectionnée pour le moment. Cliquez sur une suggestion ci-dessus ou parcourez votre bibliothèque.</p>
                  </div>
                `}
              </div>

              <!-- EFFETS VISUELS & FILTRES -->
              <div class="cm-options-block">
                <div class="cm-subheading"><span>🎨 Filtre & Style Visuel</span></div>
                <div class="cm-pill-group">
                  ${this.availableEffects.map(eff => `
                    <button type="button" class="cm-pill-btn ${this.selectedEffect === eff.value ? 'active' : ''}" data-effect="${eff.value}" title="${eff.desc}">
                      <span>${eff.label}</span>
                    </button>
                  `).join('')}
                </div>
              </div>

              <!-- AMBIANCE MUSICALE & REELS -->
              <div class="cm-options-block">
                <div class="cm-subheading"><span>🎵 Musique & Ambiance Sonore (Reels / Stories)</span></div>
                <div class="cm-pill-group">
                  ${this.availableMusics.map(m => `
                    <button type="button" class="cm-pill-btn ${this.selectedMusic === m.value ? 'active' : ''}" data-music="${m.value}" title="${m.desc}">
                      <span>${m.icon} ${m.label}</span>
                    </button>
                  `).join('')}
                </div>
              </div>

            </section>
          </div>

          <!-- COLONNE DROITE : APERÇU INSTAGRAM EN TEMPS RÉEL (STICKY) -->
          <aside class="cm-studio-preview-col">
            <div class="cm-preview-card">
              <div class="cm-preview-header">
                <h3>Aperçu Instagram</h3>
                <div class="cm-preview-format-tabs">
                  <button type="button" class="cm-format-tab ${this.previewFormat === 'feed' ? 'active' : ''}" data-format="feed">Feed</button>
                  <button type="button" class="cm-format-tab ${this.previewFormat === 'story' ? 'active' : ''}" data-format="story">Story</button>
                  <button type="button" class="cm-format-tab ${this.previewFormat === 'reel' ? 'active' : ''}" data-format="reel">Reel</button>
                  <button type="button" class="cm-format-tab ${this.previewFormat === 'strategic' ? 'active' : ''}" data-format="strategic">Stratégique</button>
                </div>
              </div>

              <div class="cm-preview-viewport" id="cm-preview-container">
                <!-- Rendu live généré par _renderPreview() -->
              </div>
            </div>
          </aside>
        </div>
      </div>
    `;

    this._bindEvents();
    this._updateLivePreview();
    return this.element;
  }

  _bindEvents() {
    if (!this.element) return;

    // Retour au calendrier
    this.element.querySelector('[data-action="back"]')?.addEventListener('click', () => {
      this._handleBack();
    });

    // Choix du ton
    this.element.querySelectorAll('[data-tone]').forEach(btn => {
      btn.addEventListener('click', () => this._selectTone(btn.dataset.tone));
    });

    // Verrouillage Titre
    this.element.querySelector('[data-action="lock-title"]')?.addEventListener('click', () => {
      this._toggleTitleLock();
    });

    // Verrouillage Texte
    this.element.querySelector('[data-action="lock-content"]')?.addEventListener('click', () => {
      this._toggleContentLock();
    });

    // Verrouillage Photo
    this.element.querySelector('[data-action="lock-photo"]')?.addEventListener('click', () => {
      this._togglePhotoLock();
    });

    // Inputs en direct avec mise à jour immédiate de l'aperçu
    const titleInput = this.element.querySelector('[name="title"]');
    if (titleInput) {
      titleInput.addEventListener('input', (e) => {
        this.publication.title = e.target.value;
        this._updateLivePreview();
      });
    }

    const contentInput = this.element.querySelector('[name="content"]');
    if (contentInput) {
      contentInput.addEventListener('input', (e) => {
        this.publication.content = e.target.value;
        const counter = this.element.querySelector('#cm-char-counter');
        if (counter) counter.textContent = `${e.target.value.length} car.`;
        this._updateLivePreview();
      });
    }

    const hashtagsInput = this.element.querySelector('[name="hashtags"]');
    if (hashtagsInput) {
      hashtagsInput.addEventListener('input', (e) => {
        this.publication.hashtags = e.target.value;
        this._updateLivePreview();
      });
    }

    // Génération Texte court / long
    this.element.querySelector('[data-action="generate-short"]')?.addEventListener('click', () => this._generateText('short'));
    this.element.querySelector('[data-action="generate-long"]')?.addEventListener('click', () => this._generateText('long'));

    // Sélection de photos suggérées
    this.element.querySelectorAll('[data-photo-id]').forEach(card => {
      card.addEventListener('click', () => {
        if (this.publication?.photo_locked) {
          this._showToast('Le visuel est verrouillé. Déverrouillez-le pour changer de photo.', 'warning');
          return;
        }
        const photoId = parseInt(card.dataset.photoId, 10);
        this._selectSuggestedPhoto(photoId);
      });
    });

    // Parcourir photothèque externe
    this.element.querySelector('[data-action="select-photo"]')?.addEventListener('click', () => this._openPhotoSelector());

    // Retirer la photo
    this.element.querySelector('[data-action="remove-photo"]')?.addEventListener('click', () => this._removePhoto());

    // Choix des filtres / effets
    this.element.querySelectorAll('[data-effect]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.selectedEffect = btn.dataset.effect;
        this.element.querySelectorAll('[data-effect]').forEach(b => b.classList.toggle('active', b === btn));
        const currentImg = this.element.querySelector('.cm-current-photo-img');
        const effectConfig = this.availableEffects.find(e => e.value === this.selectedEffect);
        if (currentImg && effectConfig) {
          currentImg.style.filter = effectConfig.css;
        }
        this._updateLivePreview();
      });
    });

    // Choix de la musique
    this.element.querySelectorAll('[data-music]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.selectedMusic = btn.dataset.music;
        this.element.querySelectorAll('[data-music]').forEach(b => b.classList.toggle('active', b === btn));
        this._updateLivePreview();
      });
    });

    // Onglets de format d'aperçu
    this.element.querySelectorAll('[data-format]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.previewFormat = btn.dataset.format;
        this.element.querySelectorAll('[data-format]').forEach(b => b.classList.toggle('active', b === btn));
        this._updateLivePreview();
      });
    });

    // Actions principales
    this.element.querySelector('[data-action="save"]')?.addEventListener('click', () => {
      this._saveDraft();
    });

    this.element.querySelector('[data-action="validate"]')?.addEventListener('click', () => {
      this._validateDraft();
    });

    this.element.querySelector('[data-action="publish"]')?.addEventListener('click', () => {
      this._publishDraft();
    });
  }

  _handleBack() {
    if (typeof this.onBack === 'function') {
      this.onBack();
    } else {
      window.history.back();
    }
  }

  async _selectTone(tone) {
    if (this.generating) return;

    this.element.querySelectorAll('[data-tone]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tone === tone);
    });

    this.publication.tone_used = tone;
    this._showToast(`Ton « ${this.availableTones.find(t => t.value === tone)?.label || tone} » sélectionné.`, 'info');

    // Mettre à jour en base
    try {
      await updateStudioDraft(this.publicationId, { tone_used: tone });
    } catch (e) {
      console.warn('Erreur update tone:', e);
    }

    // Régénération automatique si déverrouillé
    if (!this.publication?.title_locked || !this.publication?.content_locked) {
      await this._generateText('short');
    } else {
      this._updateLivePreview();
    }
  }

  async _toggleTitleLock() {
    const newLock = !this.publication?.title_locked;
    try {
      await lockStudioDraftTitle(this.publicationId, newLock);
      this.publication.title_locked = newLock;
      const btn = this.element.querySelector('[data-action="lock-title"]');
      const input = this.element.querySelector('[name="title"]');
      const hint = input?.closest('.cm-card')?.querySelector('.cm-hint-text');

      if (btn) {
        btn.classList.toggle('locked', newLock);
        btn.innerHTML = this._renderLockSvg(newLock);
        btn.title = newLock ? 'Titre verrouillé - Cliquez pour déverrouiller' : 'Titre libre - Cliquez pour verrouiller';
      }
      if (input) {
        input.readOnly = newLock;
      }
      if (hint) {
        hint.textContent = newLock ? '🔒 Titre verrouillé : protégé contre toute régénération automatique.' : '🔓 Titre déverrouillé : s\'adaptera automatiquement si vous changez de ton.';
      }
      this._showToast(newLock ? 'Titre verrouillé.' : 'Titre déverrouillé.', 'info');
    } catch (error) {
      this._showToast('Erreur lors du verrouillage du titre.', 'error');
    }
  }

  async _toggleContentLock() {
    const newLock = !this.publication?.content_locked;
    try {
      await lockStudioDraftContent(this.publicationId, newLock);
      this.publication.content_locked = newLock;
      const btn = this.element.querySelector('[data-action="lock-content"]');
      const textarea = this.element.querySelector('[name="content"]');
      const hint = textarea?.closest('.cm-card')?.querySelector('.cm-hint-text');
      const genShort = this.element.querySelector('[data-action="generate-short"]');
      const genLong = this.element.querySelector('[data-action="generate-long"]');

      if (btn) {
        btn.classList.toggle('locked', newLock);
        btn.innerHTML = this._renderLockSvg(newLock);
        btn.title = newLock ? 'Texte verrouillé - Cliquez pour déverrouiller' : 'Texte libre - Cliquez pour verrouiller';
      }
      if (textarea) {
        textarea.readOnly = newLock;
      }
      if (genShort) genShort.disabled = newLock;
      if (genLong) genLong.disabled = newLock;
      if (hint) {
        hint.textContent = newLock ? '🔒 Texte verrouillé : vos modifications manuelles sont protégées.' : '🔓 Texte déverrouillé : vous pouvez générer en version courte ou longue.';
      }
      this._showToast(newLock ? 'Texte verrouillé.' : 'Texte déverrouillé.', 'info');
    } catch (error) {
      this._showToast('Erreur lors du verrouillage du texte.', 'error');
    }
  }

  async _togglePhotoLock() {
    const newLock = !this.publication?.photo_locked;
    try {
      await lockStudioDraftPhoto(this.publicationId, newLock);
      this.publication.photo_locked = newLock;
      const btn = this.element.querySelector('[data-action="lock-photo"]');
      const removeBtn = this.element.querySelector('[data-action="remove-photo"]');
      const selectBtn = this.element.querySelector('[data-action="select-photo"]');

      if (btn) {
        btn.classList.toggle('locked', newLock);
        btn.innerHTML = `${this._renderLockSvg(newLock)} <span>${newLock ? 'Verrouillée' : 'Verrouiller'}</span>`;
      }
      if (removeBtn) removeBtn.disabled = newLock;
      if (selectBtn) selectBtn.disabled = newLock;
      this._showToast(newLock ? 'Visuel verrouillé.' : 'Visuel déverrouillé.', 'info');
    } catch (error) {
      this._showToast('Erreur lors du verrouillage du visuel.', 'error');
    }
  }

  async _generateText(length) {
    if (this.generating) return;
    if (this.publication?.content_locked && this.publication?.title_locked) {
      this._showToast('Le titre et le texte sont tous deux verrouillés.', 'warning');
      return;
    }

    const shortBtn = this.element.querySelector('[data-action="generate-short"]');
    const longBtn = this.element.querySelector('[data-action="generate-long"]');

    try {
      this.generating = true;
      if (shortBtn) shortBtn.disabled = true;
      if (longBtn) longBtn.disabled = true;
      this._showToast(`Génération du ${length === 'short' ? 'texte court' : 'texte long'} par l'IA...`, 'loading');

      const result = await generateStudioDraftText(this.publicationId, {
        publication_id: this.publicationId,
        length: length,
        tone: this.publication?.tone_used,
        use_title: !!this.publication?.title_locked,
        styles: this._buildStylesArray(),
        custom_instructions: this.publication?.custom_instructions,
      });

      if (result) {
        if (result.content && !this.publication?.content_locked) {
          this.publication.content = result.content;
          const textarea = this.element.querySelector('[name="content"]');
          if (textarea) textarea.value = result.content;
          const counter = this.element.querySelector('#cm-char-counter');
          if (counter) counter.textContent = `${result.content.length} car.`;
        }

        if (result.title && !this.publication?.title_locked) {
          this.publication.title = result.title;
          const titleInput = this.element.querySelector('[name="title"]');
          if (titleInput) titleInput.value = result.title;
        }

        if (result.hashtags && !this.publication?.content_locked) {
          this.publication.hashtags = result.hashtags;
          const hashtagsInput = this.element.querySelector('[name="hashtags"]');
          if (hashtagsInput) hashtagsInput.value = result.hashtags;
        }

        this._showToast(`Texte ${length === 'short' ? 'court' : 'long'} généré avec succès !`, 'success');
        this._updateLivePreview();
      }
    } catch (error) {
      this._showToast(error?.data?.detail || error?.message || 'Erreur lors de la génération IA.', 'error');
    } finally {
      this.generating = false;
      if (shortBtn) shortBtn.disabled = !!this.publication?.content_locked;
      if (longBtn) longBtn.disabled = !!this.publication?.content_locked;
    }
  }

  _selectSuggestedPhoto(photoId) {
    this.publication.photo_id = photoId;
    this.publication.visual_type = 'photo';

    // Mettre à jour la grille visuelle
    this.element.querySelectorAll('[data-photo-id]').forEach(card => {
      const isSelected = parseInt(card.dataset.photoId, 10) === photoId;
      card.classList.toggle('selected', isSelected);
      let check = card.querySelector('.cm-photo-check');
      if (isSelected && !check) {
        card.insertAdjacentHTML('beforeend', '<span class="cm-photo-check">✓</span>');
      } else if (!isSelected && check) {
        check.remove();
      }
    });

    // Mettre à jour la zone de photo sélectionnée
    const effectConfig = this.availableEffects.find(e => e.value === this.selectedEffect) || this.availableEffects[0];
    const previewBox = this.element.querySelector('.cm-selected-photo-preview');
    if (previewBox) {
      previewBox.innerHTML = `
        <div class="cm-current-photo-row">
          <div class="cm-current-photo-img-wrap">
            <img src="${publicationPhotoUrl(photoId, 'medium')}" class="cm-current-photo-img" style="filter: ${effectConfig.css};" alt="Visuel sélectionné">
          </div>
          <div class="cm-current-photo-meta">
            <div class="cm-current-photo-title">Photo sélectionnée (#${photoId})</div>
            <div class="cm-current-photo-actions">
              <button type="button" class="btn btn-sm btn-secondary ${this.publication?.photo_locked ? 'locked' : ''}" data-action="lock-photo" title="${this.publication?.photo_locked ? 'Déverrouiller le visuel' : 'Verrouiller le visuel'}">
                ${this._renderLockSvg(this.publication?.photo_locked)}
                <span>${this.publication?.photo_locked ? 'Verrouillée' : 'Verrouiller'}</span>
              </button>
              <button type="button" class="btn btn-sm btn-outline text-danger" data-action="remove-photo" ${this.publication?.photo_locked ? 'disabled' : ''}>
                Retirer
              </button>
            </div>
          </div>
        </div>
      `;
      // Rebrancher les boutons
      previewBox.querySelector('[data-action="lock-photo"]')?.addEventListener('click', () => this._togglePhotoLock());
      previewBox.querySelector('[data-action="remove-photo"]')?.addEventListener('click', () => this._removePhoto());
    }

    this._updateLivePreview();
    this._saveDraft(true);
  }

  _removePhoto() {
    this.publication.photo_id = null;
    this.element.querySelectorAll('[data-photo-id]').forEach(card => {
      card.classList.remove('selected');
      card.querySelector('.cm-photo-check')?.remove();
    });

    const previewBox = this.element.querySelector('.cm-selected-photo-preview');
    if (previewBox) {
      previewBox.innerHTML = `
        <div class="cm-no-photo-box">
          <p>Aucune photo sélectionnée pour le moment. Cliquez sur une suggestion ci-dessus ou parcourez votre bibliothèque.</p>
        </div>
      `;
    }

    this._updateLivePreview();
    this._saveDraft(true);
  }

  async _openPhotoSelector() {
    const url = `/photos?select=1&callback=cmStudioPhotoSelected`;
    window.open(url, 'cmPhotoSelector', 'width=1000,height=700');
  }

  _buildStylesArray() {
    const styles = ['stats'];
    if (this.selectedEffect && this.selectedEffect !== 'none') {
      styles.push(`effect:${this.selectedEffect}`);
    }
    if (this.selectedMusic && this.selectedMusic !== 'none') {
      styles.push(`music:${this.selectedMusic}`);
    }
    return styles;
  }

  async _saveDraft(silent = false) {
    if (this.saving) return;

    const title = this.element.querySelector('[name="title"]')?.value ?? this.publication?.title;
    const content = this.element.querySelector('[name="content"]')?.value ?? this.publication?.content;
    const hashtags = this.element.querySelector('[name="hashtags"]')?.value ?? this.publication?.hashtags;

    const payload = {
      title: title || null,
      content: content || null,
      hashtags: hashtags || null,
      photo_id: this.publication?.photo_id || null,
      tone_used: this.publication?.tone_used || null,
      styles: this._buildStylesArray(),
      title_locked: this.publication?.title_locked,
      content_locked: this.publication?.content_locked,
      photo_locked: this.publication?.photo_locked,
    };

    try {
      this.saving = true;
      const saveBtn = this.element.querySelector('[data-action="save"] span');
      if (saveBtn) saveBtn.textContent = 'Sauvegarde...';

      const updated = await updateStudioDraft(this.publicationId, payload);
      this.publication = { ...this.publication, ...updated };

      // Mise à jour de l'état des boutons de validation
      const validateBtn = this.element.querySelector('[data-action="validate"]');
      if (validateBtn && pubStateCanValidate(this.publication)) {
        validateBtn.disabled = false;
      }

      if (!silent) {
        this._showToast('Brouillon sauvegardé avec succès !', 'success');
      }
    } catch (error) {
      if (!silent) {
        this._showToast(error?.data?.detail || error?.message || 'Erreur lors de la sauvegarde.', 'error');
      }
    } finally {
      this.saving = false;
      const saveBtn = this.element.querySelector('[data-action="save"] span');
      if (saveBtn) saveBtn.textContent = 'Sauvegarder le brouillon';
    }
  }

  async _validateDraft() {
    const btn = this.element.querySelector('[data-action="validate"]');
    if (btn?.disabled) return;

    try {
      btn.disabled = true;
      btn.textContent = 'Validation...';
      const updated = await validateStudioDraft(this.publicationId, { confirm: true });
      this.publication = { ...this.publication, ...updated };
      this._updateStatusBadges('validated');
      this._showToast('Publication validée et prête pour Instagram !', 'success');
      const publishBtn = this.element.querySelector('[data-action="publish"]');
      if (publishBtn && this.publication.photo_id) publishBtn.disabled = false;
    } catch (error) {
      this._showToast(error?.data?.detail || error?.message || 'Validation impossible.', 'error');
      btn.disabled = false;
      btn.textContent = 'Valider';
    }
  }

  async _publishDraft() {
    const btn = this.element.querySelector('[data-action="publish"]');
    if (btn?.disabled) return;

    if (!confirm('Confirmez-vous la publication immédiate sur votre compte Instagram ?')) {
      return;
    }

    try {
      btn.disabled = true;
      btn.textContent = 'Publication en cours...';
      this._showToast('Publication sur Instagram en cours via l\'API Meta...', 'loading');

      const result = await publishStudioDraft(this.publicationId, { confirm: true });
      this.publication = { ...this.publication, ...result };
      this._updateStatusBadges(this.publication.status);
      this._showToast('Publication réussie sur Instagram ! 🎉', 'success');
      btn.textContent = 'Publiée sur Instagram';
    } catch (error) {
      this._showToast(error?.data?.detail || error?.message || 'Échec de publication Instagram.', 'error');
      btn.disabled = false;
      btn.textContent = 'Publier sur Instagram';
    }
  }

  _updateLivePreview() {
    const container = this.element?.querySelector('#cm-preview-container');
    if (!container) return;

    const title = this.element?.querySelector('[name="title"]')?.value ?? (this.publication?.title || '');
    const content = this.element?.querySelector('[name="content"]')?.value ?? (this.publication?.content || '');
    const hashtags = this.element?.querySelector('[name="hashtags"]')?.value ?? (this.publication?.hashtags || '');
    const photoId = this.publication?.photo_id;
    const photoUrl = photoId ? publicationPhotoUrl(photoId, 'large') : null;

    const effectConfig = this.availableEffects.find(e => e.value === this.selectedEffect) || this.availableEffects[0];
    const musicConfig = this.availableMusics.find(m => m.value === this.selectedMusic) || this.availableMusics[0];

    const filterCss = effectConfig.css || 'none';
    const musicTrack = musicConfig.track ? `🎵 ${musicConfig.track}` : null;

    if (this.previewFormat === 'feed') {
      container.innerHTML = `
        <div class="insta-feed-mockup">
          <div class="insta-mockup-header">
            <div class="insta-mockup-avatar"></div>
            <div class="insta-mockup-user">
              <span class="insta-username">forgeai_athlete</span>
              ${musicTrack ? `<span class="insta-audiotrack">${musicTrack}</span>` : '<span class="insta-location">Trail & Outdoor</span>'}
            </div>
            <div class="insta-mockup-dots">•••</div>
          </div>
          <div class="insta-mockup-media">
            ${photoUrl ? `
              <img src="${photoUrl}" style="filter: ${filterCss};" alt="Visuel Feed">
            ` : `
              <div class="insta-no-media">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>
                <span>Sélectionnez une photo</span>
              </div>
            `}
          </div>
          <div class="insta-mockup-actions">
            <div class="insta-actions-left">
              <span>❤️</span>
              <span>💬</span>
              <span>📤</span>
            </div>
            <div class="insta-actions-right">
              <span>🔖</span>
            </div>
          </div>
          <div class="insta-mockup-body">
            ${title ? `<div class="insta-mockup-title"><strong>${this._escape(title)}</strong></div>` : ''}
            <div class="insta-mockup-text">${this._escape(content) || '<span class="text-muted">Votre texte s\'affichera ici...</span>'}</div>
            ${hashtags ? `<div class="insta-mockup-hashtags">${this._escape(hashtags)}</div>` : ''}
          </div>
        </div>
      `;
    } else if (this.previewFormat === 'story' || this.previewFormat === 'reel') {
      const isReel = this.previewFormat === 'reel';
      container.innerHTML = `
        <div class="insta-story-mockup ${isReel ? 'reel' : ''}">
          <div class="insta-story-media">
            ${photoUrl ? `
              <img src="${photoUrl}" style="filter: ${filterCss};" alt="Story Media">
            ` : `
              <div class="insta-no-media dark">
                <span>Visuel Story / Reel 9:16</span>
              </div>
            `}
          </div>
          <div class="insta-story-overlay">
            <div class="insta-story-top">
              <div class="insta-mockup-avatar sm"></div>
              <span class="insta-username light">forgeai_athlete</span>
              <span class="insta-time">2h</span>
            </div>
            ${musicTrack ? `
              <div class="insta-audio-badge">
                <span class="music-icon">🎵</span>
                <span class="music-name">${musicTrack}</span>
              </div>
            ` : ''}
            <div class="insta-story-bottom">
              ${title ? `<h4 class="insta-story-title">${this._escape(title)}</h4>` : ''}
              <p class="insta-story-caption">${this._escape(content)}</p>
              ${hashtags ? `<p class="insta-story-tags">${this._escape(hashtags)}</p>` : ''}
            </div>
          </div>
          ${isReel ? `
            <div class="insta-reel-sidebar">
              <div class="reel-icon-btn"><span>❤️</span><small>2.4k</small></div>
              <div class="reel-icon-btn"><span>💬</span><small>84</small></div>
              <div class="reel-icon-btn"><span>📤</span><small>Partager</small></div>
              <div class="reel-icon-btn"><span>🎵</span></div>
            </div>
          ` : ''}
        </div>
      `;
    } else if (this.previewFormat === 'strategic') {
      const stats = this._extractStatsFromText(content);
      container.innerHTML = `
        <div class="insta-feed-mockup strategic">
          <div class="insta-mockup-header">
            <div class="insta-mockup-avatar"></div>
            <div class="insta-mockup-user">
              <span class="insta-username">forgeai_athlete</span>
              <span class="insta-location">Format Stratégique Garmin</span>
            </div>
          </div>
          <div class="insta-mockup-media">
            ${photoUrl ? `
              <img src="${photoUrl}" style="filter: ${filterCss};" alt="Visuel Stratégique">
            ` : `
              <div class="insta-no-media"><span>Visuel</span></div>
            `}
          </div>
          <div class="insta-strategic-card">
            ${stats.length > 0 ? `
              <div class="insta-stats-chips">
                ${stats.map(s => `<span class="insta-stat-chip">${s}</span>`).join('')}
              </div>
            ` : ''}
            ${title ? `<div class="insta-mockup-title"><strong>${this._escape(title)}</strong></div>` : ''}
            <div class="insta-mockup-text">${this._escape(content)}</div>
            ${hashtags ? `<div class="insta-mockup-hashtags">${this._escape(hashtags)}</div>` : ''}
          </div>
        </div>
      `;
    }
  }

  _extractStatsFromText(text) {
    if (!text) return [];
    const stats = [];
    const km = text.match(/(\d+(?:[.,]\d+)?)\s*km/i);
    if (km) stats.push(`🏃 ${km[1]} km`);
    const dplus = text.match(/(\d+)\s*m\s*(?:d\+|de dénivelé|\+)/i);
    if (dplus) stats.push(`⛰️ +${dplus[1]}m D+`);
    const bpm = text.match(/(\d+)\s*bpm/i);
    if (bpm) stats.push(`❤️ ${bpm[1]} bpm`);
    const pace = text.match(/(\d+[:'’]\d+)\s*(?:\/km|min\/km)/i);
    if (pace) stats.push(`⚡ ${pace[1]} /km`);
    return stats;
  }

  _getCurrentPhoto() {
    if (!this.publication?.photo_id) return null;
    return this.suggestedPhotos.find(p => p.id === this.publication.photo_id) || { id: this.publication.photo_id };
  }

  _showToast(message, type = 'info') {
    const bar = this.element?.querySelector('#cm-feedback-bar');
    if (!bar) return;
    bar.style.display = 'block';
    bar.className = `cm-feedback-bar ${type}`;
    bar.innerHTML = `
      <span>${this._escape(message)}</span>
      <button type="button" class="cm-feedback-close" onclick="this.parentElement.style.display='none'">✕</button>
    `;
    if (type !== 'loading') {
      clearTimeout(this._toastTimeout);
      this._toastTimeout = setTimeout(() => {
        if (bar) bar.style.display = 'none';
      }, 4000);
    }
  }

  _updateStatusBadges(status) {
    this.publication.status = status;
    const badge = this.element?.querySelector('.cm-studio-topbar .status-badge');
    if (badge) {
      badge.className = `status-badge ${this._getStatusBadgeClass(status)}`;
      badge.textContent = this._formatStatus(status);
    }
  }

  _renderLockSvg(locked) {
    if (locked) {
      // Cadenas fermé
      return `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
          <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
        </svg>
      `;
    }
    // Cadenas ouvert
    return `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
        <path d="M7 11V7a5 5 0 0 1 9.9-1"/>
      </svg>
    `;
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
    return map[status] || status || 'Brouillon';
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

  _escape(text) {
    if (text == null) return '';
    return String(text)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  static registerPhotoCallback() {
    window.cmStudioPhotoSelected = (photoId) => {
      const page = window.cmStudioPageInstance;
      if (page) {
        page._selectSuggestedPhoto(parseInt(photoId, 10));
      }
    };
  }
}

function pubStateCanValidate(pub) {
  return pub && pub.content && pub.status === 'draft';
}

window.cmStudioPageInstance = null;

export function createCommunityManagerStudioPage(router, publicationId, entryData = null, onBack = null) {
  const page = new CommunityManagerStudioPage(router, publicationId, entryData, onBack);
  window.cmStudioPageInstance = page;
  CommunityManagerStudioPage.registerPhotoCallback();
  return page;
}
